import json
import os.path
import shutil

import pytest

from idelib import importer, sync, userdata


SYNC_INFO = {
    'SyncActive': True,
    'SyncChannelIDRef': 103,
    'SyncSubChannelIDRef': 0,
    'SyncSourceName': 'MIDE-Corp',
    'SyncSourceIdentifier': 'F0:9C:E9:5F:93:14',
    'SyncZero': 6234333139,
    'TimeBaseUTCFine': [1737569556.123],
    'SyncFilename': 'testing/TSF2.IDE',
    'SyncFingerprint': '71f7501261809bfbbf9c659b5376e373',
    'SyncReferenceZero': 6224001645,
    'SyncReferenceFilename': 'testing/TSF1.IDE',
    'SyncReferenceFingerprint': '6af87d674b94e1d1655a3492ac7bb690',
    'SyncReferenceTimeBase': 1737569545.123
}

SYNC_INFO_NO_REFERENCE = {
    'SyncActive': True,
    'SyncChannelIDRef': 103,
    'SyncSubChannelIDRef': 0,
    'SyncSourceName': 'MIDE-Corp',
    'SyncSourceIdentifier': 'F0:9C:E9:5F:93:14',
    'SyncZero': 6234333139,
    'TimeBaseUTCFine': [1737569556.123],
    'SyncFilename': 'testing/TSF2.IDE',
    'SyncFingerprint': '71f7501261809bfbbf9c659b5376e373'
}


def test_offset():
    """ Test that session timestamp offset works.
    """
    filename1 = os.path.join(os.path.dirname(__file__), 'TSF1.IDE')
    doc1 = importer.importFile(filename1)

    accel1 = doc1.channels[80].getSession()
    first1 = accel1[0][0]
    last1 = accel1[-1][0]

    offset = 10 ** 6

    # Positive offset
    accel1.session.offset = offset
    assert accel1[0][0] != first1
    assert accel1[-1][0] != last1
    assert accel1[0][0] == first1 + offset
    assert accel1[-1][0] == last1 + offset

    # Offset reset
    accel1.session.offset = 0
    assert accel1[0][0] == first1
    assert accel1[-1][0] == last1

    # Negative offset
    accel1.session.offset = -offset
    assert accel1[0][0] != first1
    assert accel1[-1][0] != last1
    assert accel1[0][0] == first1 - offset
    assert accel1[-1][0] == last1 - offset


def test_getSyncSensor():
    """ Test that getSyncSensor() returns the correct source.
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))
    _sensor1 = sync.getSyncSensor(doc1, sourceId='F0:9C:E9:5F:93:14')
    _sensor2 = sync.getSyncSensor(doc1, sourceName='MIDE-Corp')
    _sensor3 = sync.getSyncSensor(doc1, sourceName='MIDE-Corp', sourceId='F0:9C:E9:5F:93:14')

    with pytest.raises(sync.SyncError):
        _ = sync.getSyncSensor(doc1, sourceId=None, sourceName=None)

    with pytest.raises(sync.SyncError):
        _ = sync.getSyncSensor(doc1, sourceId='bogus')

    with pytest.raises(sync.SyncError):
        _ = sync.getSyncSensor(doc1, sourceName='bogus')

    with pytest.raises(sync.SyncError):
        _ = sync.getSyncSensor(doc1, sourceId='bogus', sourceName='MIDE-Corp')

    with pytest.raises(sync.SyncError):
        _ = sync.getSyncSensor(doc1, sourceId='F0:9C:E9:5F:93:14', sourceName='bogus')


def test_getCommonSensorIds():
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))
    doc2 = importer.importFile(os.path.join(cwd, 'TSF2.IDE'))
    doc3 = importer.importFile(os.path.join(cwd, 'test3.IDE'))  # No sync reference

    assert len(sync.getCommonSensorIds(doc1, doc2)) == 1

    with pytest.raises(sync.SyncError):
        _ = sync.getCommonSensorIds(doc1)

    with pytest.raises(sync.SyncError):
        _ = sync.getCommonSensorIds(doc1, doc3)

    with pytest.raises(sync.SyncError):
        _ = sync.getCommonSensorIds(doc1, doc2, doc3)


def test_getSyncSources():
    """ Test getting sync reference sensor data.
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))  # Has sync reference
    doc2 = importer.importFile(os.path.join(cwd, 'test3.IDE'))  # No sync reference

    sources1 = sync.getSyncSources(doc1)
    assert len(sources1) > 0

    sources2 = sync.getSyncSources(doc2)
    assert len(sources2) == 0

    sensor = sync.getSyncSensors(doc1)[0]
    assert sources1[0].parent.sensor == sensor


def test_getSyncTimeZero():
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))  # Has sync reference
    doc2 = importer.importFile(os.path.join(cwd, 'test3.IDE'))  # No sync reference
    doc3 = importer.openFile(os.path.join(cwd, 'TSF2.IDE'))  # Has sync reference

    sync.getSyncTimeZero(doc1)
    assert doc1.currentSession.syncZero is not None

    with pytest.raises(TypeError):
        # Not a Dataset or EventArray
        sync.getSyncTimeZero('an invalid object')

    with pytest.raises(sync.SyncError):
        # Bad sensor ID
        sync.getSyncTimeZero(doc1, sensorId=254, clear=True)

    with pytest.raises(sync.SyncError):
        # No sync reference
        _ = sync.getSyncTimeZero(doc2)

    with pytest.raises(sync.SyncError):
        # Only header loaded, no reference data
        sync.getSyncTimeZero(doc3)


def test_sync_basic():
    """ Test that sync will modify the target file but not the reference.
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))
    doc2 = importer.importFile(os.path.join(cwd, 'TSF2.IDE'))
    doc3 = importer.importFile(os.path.join(cwd, 'test3.IDE'))  # No sync reference

    # Sanity check
    assert len(sync.getSyncSensors(doc1)) == 1
    assert len(sync.getSyncSensors(doc2)) == 1
    assert len(sync.getSyncSensors(doc3)) == 0
    assert sync.getSyncTimeZero(doc1) != 0
    assert sync.getSyncTimeZero(doc2) != 0

    accel1 = doc1.channels[80].getSession()
    accel2 = doc2.channels[80].getSession()
    first1 = accel1[0][0]
    last1 = accel1[-1][0]
    first2 = accel2[0][0]
    last2 = accel2[-1][0]
    utc1 = accel1.session.utcStartTime
    utc2 = accel2.session.utcStartTime

    # Sanity check: initial offsets are zero, start times different
    assert accel1.session.offset == 0
    assert accel2.session.offset == 0
    assert utc1 != utc2

    sync.sync(doc1, doc2)
    assert accel1.session.offset == 0  # doc1 (the reference) offset unchanged
    assert accel2.session.offset != 0  # doc2 offset modified
    assert accel1[0][0] == first1  # doc1 timestamps unchanged
    assert accel1[-1][0] == last1
    assert accel2[0][0] == first2 + accel2.session.offset  # doc2 timestamps offset
    assert accel2[-1][0] == last2 + accel2.session.offset

    assert accel1.session.utcStartTime == utc1
    assert accel2.session.utcStartTime == utc1

    # Get sync time zero again; value should have been cached
    # (mainly for code coverage)
    assert doc1.currentSession.syncZero is not None
    sync.getSyncTimeZero(doc1)

    with pytest.raises(sync.SyncError):
        # At least 2 datasets needed (reference and another)
        sync.sync(doc1)

    with pytest.raises(sync.SyncError):
        # No sync reference in doc3
        sync.sync(doc1, doc3)

    with pytest.raises(sync.SyncError):
        # Sync reference in doc1 and doc2; no sync reference in doc3
        sync.sync(doc1, doc2, doc3)

    with pytest.raises(sync.SyncError):
        sync.sync(doc1, doc3, sensorId=103)


def test_sync_repeat():
    """ Test that syncing an already synced session doesn't cause problems.
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))
    doc2 = importer.importFile(os.path.join(cwd, 'TSF2.IDE'))

    accel2 = doc2.channels[80].getSession()
    offsetPreSync = accel2.session.offset

    # Verify sync applied
    sync.sync(doc1, doc2)
    offsetPostSync = accel2.session.offset
    assert offsetPostSync != offsetPreSync

    # Verify multiple syncs don't stack/conflict
    sync.sync(doc1, doc2)
    assert accel2.session.offset == offsetPostSync


def test_sync_inherit():
    """ Test syncing with the 'inherit' flag set and unset.
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))
    doc2 = importer.importFile(os.path.join(cwd, 'TSF2.IDE'))

    doc1_startTimeOriginal = doc1.currentSession.utcStartTime


    # Set the syncInfo in doc1 as if it were synced to another recording
    sync.getSyncTimeZero(doc1)

    doc1.currentSession.syncInfo.update({
        'SyncActive': True,
        'SyncReferenceZero': doc1.currentSession.syncZero + 6000,
        'SyncReferenceFilename': 'bogus.ide',
        'SyncReferenceTimeBase': doc1.currentSession.utcStartTime + 60.,
    })

    # sync w/o clear: doc2 uses doc1's syncInfo (as if doc1 was synced to another)
    sync.sync(doc1, doc2, inherit=True)
    assert doc2.currentSession.utcStartTime == doc1.currentSession.utcStartTimeOriginal + 60.
    assert doc2.currentSession.syncInfo['SyncReferenceFilename'] == 'bogus.ide'

    # sync w/ clear: doc2 syncs to doc1
    sync.sync(doc1, doc2, inherit=False)
    assert doc2.currentSession.utcStartTime == doc1.currentSession.utcStartTimeOriginal
    assert doc2.currentSession.syncInfo['SyncReferenceFilename'] == doc1.filename

    # sync w/o clear, but doc1 has no syncInfo: same as clear
    sync.removeSync(doc1, clean=True)
    sync.sync(doc1, doc2, inherit=True)
    assert doc2.currentSession.utcStartTime == doc1.currentSession.utcStartTime
    assert doc2.currentSession.syncInfo['SyncReferenceFilename'] == doc1.filename


def test_apply_sync():
    """ Test applying a dictionary of sync info. In this test, the info is
        deserialized from JSON, as one use of applySyncInfo is for copying
        between IDEs in enDAQ Lab. Copying will (probably) use JSON and the
        clipboard (at least initially).
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))
    doc2 = importer.importFile(os.path.join(cwd, 'TSF2.IDE'))

    # Files start with no sync info
    assert not sync.isSynced(doc1)
    assert not sync.isSynced(doc2)

    sync.sync(doc1, doc2, inherit=False)

    # The timing of the reference recording (1st IDE) not change, but the 2nd
    # recording should be synced to the 1st.
    assert not sync.isSynced(doc1)
    assert sync.isSynced(doc2)
    assert doc2.currentSession.utcStartTime == doc1.currentSession.utcStartTime

    info = json.loads(json.dumps(doc2.currentSession.syncInfo))
    offset = doc2.currentSession.offset
    sensor = doc2.currentSession.syncSensor

    sync.removeSync(doc2, clean=True)
    assert not sync.isSynced(doc2)
    assert doc2.currentSession.offset == 0
    assert doc2.currentSession.utcStartTime != doc1.currentSession.utcStartTime
    assert doc2.currentSession.syncSensor is None

    sync.applySyncInfo(doc2, info)
    assert doc2.currentSession.syncInfo == info
    assert doc2.currentSession.offset == offset
    assert doc2.currentSession.utcStartTime == doc1.currentSession.utcStartTime
    assert doc2.currentSession.syncSensor == sensor


def test_sync_userdata():
    """ Test reading/writing sync info from IDE user data. These tests
        don't actually save the userdata to the file, only verify the
        userdata (in memory) is updated.
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))
    doc2 = importer.importFile(os.path.join(cwd, 'TSF2.IDE'))

    sync.sync(doc1, doc2)

    assert not sync.isSynced(doc1)
    assert sync.isSynced(doc2)

    userdata.readUserData(doc2)
    sync.updateUserdata(doc2)
    assert sync.isSynced(doc2)

    ud = userdata.readUserData(doc2)
    si = doc2.currentSession.syncInfo

    assert 'SyncInfo' in ud
    assert ud['SyncInfo'] == {k: v for k, v in si.items()
                              if v is not None}

    sync.removeSync(doc2, clean=True)
    assert not sync.isSynced(doc2)

    sync.updateUserdata(doc2)

    ud = userdata.readUserData(doc2)  # Note: this will return the cached copy
    assert 'SyncInfo' not in ud


def test_validateSyncInfo():
    """ Test validation of a sync info dictionary.
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))

    assert sync.validateSyncInfo(doc1, SYNC_INFO) is True
    assert sync.validateSyncInfo(doc1, {}) is False

    with pytest.raises(sync.SyncError):
        # Bad key
        sync.validateSyncInfo(doc1, {'bogus': 1})

    with pytest.raises(sync.SyncError):
        # Real schema element, but bad key for SyncInfo
        sync.validateSyncInfo(doc1, {'ChannelDataBlock': {}})


def test_sync_reference_info():
    """ Test a couple functions related to syc reference info.
    """
    # Test hasSyncReferenceInfo()
    assert sync.hasSyncReferenceInfo(SYNC_INFO) is True
    assert sync.hasSyncReferenceInfo(SYNC_INFO_NO_REFERENCE) is False
    assert sync.hasSyncReferenceInfo({}) is False

    # Test makeSyncReferenceInfo()
    info = sync.makeSyncReferenceInfo(SYNC_INFO_NO_REFERENCE)
    assert sync.hasSyncReferenceInfo(info) is True


def test_file_sync_userdata(tmp_path):
    """ Test reading/writing sync info from a recording's userdata.
    """
    cwd = os.path.dirname(__file__)
    sourcename = os.path.join(cwd, 'TSF1.IDE')
    filename = tmp_path / os.path.basename(sourcename)
    shutil.copyfile(sourcename, filename)

    with importer.importFile(filename) as doc:
        userdata.readUserData(doc)
        info = sync.getSyncInfo(doc)
        sync.updateUserdata(doc)
        userdata.writeUserData(doc, doc._userdata)

    with importer.importFile(filename) as doc:
        # Check saved info
        sync.loadSyncInfo(doc)
        assert info == sync.getSyncInfo(doc)

        # Check removed info
        sync.removeSync(doc, clean=True)
        sync.updateUserdata(doc)
        assert 'SyncInfo' not in doc._userdata

    # Check file without userdata
    doc2 = importer.importFile(os.path.join(cwd, 'test3.IDE'))
    assert sync.loadSyncInfo(doc2) is False


# ===========================================================================
#
# ===========================================================================

def test_gnss_sync():
    """ Basic test: add and remove GPS/GNSS time base modification.
    """
    cwd = os.path.dirname(__file__)
    filename = os.path.join(cwd, 'GNSS1.IDE')

    with importer.importFile(filename) as doc:
        oldTime = doc.currentSession.utcStartTime
        sync.applyGNSSTime(doc)
        assert doc.currentSession.utcStartTime != oldTime

        sync.removeGNSSTime(doc)
        assert doc.currentSession.utcStartTime == oldTime


def test_gnss_sync_nodata(tmp_path):
    """ Test failing to get/apply GNSS time base.
    """
    cwd = os.path.dirname(__file__)

    # File has no GNSS Time channel, obvious fail
    filename = os.path.join(cwd, 'test3.IDE')
    with importer.importFile(filename) as doc:
        with pytest.raises(sync.SyncError):
            sync.applyGNSSTime(doc)

    # File has a GNSS Time channel, but it has no data
    filename = os.path.join(cwd, 'TSF1.IDE')
    with importer.importFile(filename) as doc:
        with pytest.raises(sync.SyncError):
            sync.applyGNSSTime(doc)


def test_gnss_sync_userdata(tmp_path):
    """ Test reading/writing GPS/GNSS time base info from a recording's
        userdata.
    """
    cwd = os.path.dirname(__file__)
    sourcename = os.path.join(cwd, 'GNSS1.IDE')
    filename = tmp_path / os.path.basename(sourcename)
    shutil.copyfile(sourcename, filename)

    with importer.importFile(filename) as doc:
        # Write GNSS timebase to userdata
        sync.applyGNSSTime(doc)
        sync.updateUserdata(doc)
        gnsstime = doc.currentSession.utcStartTime
        assert doc._userdata['TimeBaseUTCFine'] == gnsstime
        userdata.writeUserData(doc, doc._userdata)

    with importer.importFile(filename) as doc:
        # Check saved info
        assert 'TimeBaseUTCFine' not in (doc._userdata or {})
        assert doc.currentSession.utcStartTime == doc.currentSession.utcStartTimeOriginal
        assert doc.currentSession.utcStartTime != gnsstime
        sync.loadSyncInfo(doc)
        assert 'TimeBaseUTCFine' in doc._userdata
        assert doc.currentSession.utcStartTime != doc.currentSession.utcStartTimeOriginal
        assert doc.currentSession.utcStartTime == gnsstime
