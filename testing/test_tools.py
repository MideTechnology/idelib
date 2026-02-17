from glob import glob
import os.path
import shutil

import pytest

from idelib import importer, sync, userdata
from idelib.tools import ideexport, ideinfo, idesync


# ===========================================================================
# ideexport tests
# ===========================================================================

def test_ideexport_basic(tmpdir_factory):
    """ Basic ideexport test, verify the correct number of files are created.
    """
    filename = './testing/test3.IDE'
    basename = os.path.splitext(os.path.basename(filename))[0]

    path = tmpdir_factory.mktemp('test_ideexport')
    ideexport.main(['--output', str(path), filename])
    ideexport.main(['--output', str(path), '-t', 'mat', filename])

    doc = importer.openFile(filename)
    csvs = glob(str(path / '*.csv'))
    mats = glob(str(path / '*.mat'))
    assert len(doc.channels) == len(csvs)
    assert len(doc.channels) == len(mats)
    assert os.path.exists(path / f'{basename}_info.txt')


def test_ideexport_csv(tmpdir_factory):
    """ Verify the number of exported rows matches the number of events in
        the original IDE.
    """
    filename = './testing/test3.IDE'
    basename = os.path.splitext(os.path.basename(filename))[0]
    path = tmpdir_factory.mktemp('test_ideexport')

    with importer.importFile(filename) as doc:
        ideexport.main(['--output', str(path), filename])
        for ch in doc.channels.values():
            events = ch.getSession()
            csvname = f'{path}/{basename}_Ch{ch.id:02d}.csv'
            with open(csvname, 'r') as f:
                lines = len(f.readlines())
                assert lines == len(events)


# ===========================================================================
# ideinfo tests
# ===========================================================================

def test_ideinfo_basic(tmpdir_factory):
    """ Test that ideinfo creates an info file.
    """
    filename = './testing/test3.IDE'
    basename = os.path.splitext(os.path.basename(filename))[0]
    outfile = str(tmpdir_factory.mktemp('test_ideinfo') / f'{basename}.txt')

    ideinfo.main(['--output', outfile, filename])
    assert os.path.exists(outfile)


# ===========================================================================
# idesync tests
# ===========================================================================

def test_idesync_basics(tmpdir_factory):
    """ Test basic idesync functionality. Note that this skips the `main()`
        function and calls `syncFiles()` directly in order to get exceptions
        that `main()` catches.
    """
    filenames = []
    cwd = os.path.dirname(__file__)
    path = tmpdir_factory.mktemp('test_idesync_basics')

    for f in ('GNSS1.IDE', 'TSF1.IDE', 'TSF2.IDE'):
        shutil.copy2(os.path.join(cwd, f), path / f)
        filenames.append(str(path / f))  # Filenames will be strings when run from the CLI

    # One file: just set GPS/GNSS time base
    successes, failures = idesync.syncFiles(filenames[0], gps=True)
    assert len(successes) == 1
    assert len(failures) == 0

    with importer.importFile(filenames[0]) as doc:
        userdata.readUserData(doc)
        assert doc._userdata['TimeBaseUTCFine'] != doc.currentSession.utcStartTimeOriginal


def test_idesync_fail(tmpdir_factory):
    """ Test basic idesync failures. Note that this skips the `main()`
        function and calls `syncFiles()` directly in order to get exceptions
        that `main()` catches.
    """
    filenames = []
    cwd = os.path.dirname(__file__)
    path = tmpdir_factory.mktemp('test_idesync_fail')
    for f in ('GNSS1.IDE', 'TSF1.IDE', 'TSF2.IDE', 'test3.IDE'):
        shutil.copy2(os.path.join(cwd, f), path / f)
        filenames.append(str(path / f))  # Filenames will be strings when run from the CLI

    # Fail: can't use `gps` and `inherit` together
    with pytest.raises(sync.SyncError, match=r'.*mutually exclusive.*'):
        idesync.syncFiles(filenames[1], filenames[2], gps=True, inherit=True)

    # Fail: No GPS/GNSS time data
    with pytest.raises(sync.SyncError, match=r'No GPS/GNSS data.*'):
        idesync.syncFiles(filenames[1], filenames[2], gps=True, inherit=False)

    successes, failures = idesync.syncFiles(filenames[0], filenames[1], filenames[2], gps=False)
    assert len(successes) == 0
    assert len(failures) == 2


def test_idesync_ideexport(tmpdir_factory):
    """ Basic ideexport test, verify the correct number of files are created.
    """
    filenames = []
    cwd = os.path.dirname(__file__)
    path = tmpdir_factory.mktemp('test_idesync_ideexport')
    for f in ('TSF1.IDE', 'TSF2.IDE', 'GNSS1.IDE'):
        shutil.copy2(os.path.join(cwd, f), path / f)
        filenames.append(str(path / f))  # Filenames will be strings when run from the CLI

    idesync.syncFiles(filenames[0], filenames[1])
    idesync.syncFiles(filenames[2], gps=True)

    # Just see if the files can be exported with sync without failing
    ideexport.main(['--output', str(path), '-s', filenames[1]])
    ideexport.main(['--output', str(path), '-s', filenames[2]])

    # FUTURE: Check export content, even though test_sync tests data?
