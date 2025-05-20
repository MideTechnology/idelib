"""
Functions to assist in syncing one file to another.

NOTE: This is currently a proof of concept. Some functionality may eventually
be rolled directly into classes in `idelib.dataset`.
"""

from copy import deepcopy
import logging
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from idelib import userdata

if TYPE_CHECKING:
    from idelib.dataset import Dataset, EventArray, Sensor


logger = logging.getLogger(__name__)


# ===========================================================================
#
# ===========================================================================

class SyncError(ValueError):
    """ Exception raised when files cannot be synchronized. """


# ===========================================================================
#
# ===========================================================================

def getSyncSensors(dataset: "Dataset") -> List["Sensor"]:
    """ Get all the 'sensors' in a `Dataset` that can be used for time
        synchronization.
    """
    return [s for s in dataset.sensors.values()
            if s.name and 'Time' in s.name and not s.relative]


def getSyncSensor(dataset: "Dataset",
                  sourceId: Optional[str] = None,
                  sourceName: Optional[str] = None) -> "Sensor":
    """ Get a specific time reference sensor from a `Dataset` by name and/or
        identifier.

        :param dataset: The `Dataset` from which to get the sensor.
        :param sourceId: The time reference sensor's unique ID (e.g., the MAC
            address of a Wi-Fi access point generating TSF data).
        :param sourceName: The name of the time reference sensor (e.g., the
            name of a Wi-Fi access point generating TSF data).
    """
    if not (sourceId or sourceName):
        raise SyncError('Must specify a sourceId, sourceName, or both')
    for s in getSyncSensors(dataset):
        if (sourceId is None or s.sourceId == sourceId) and \
           (sourceName is None or s.sourceName == sourceName):
            return s
    msgs = []
    if sourceId:
        msgs.append(f'with ID {sourceId!r}')
    if sourceName:
        msgs.append(f'named {sourceName!r}')
    raise SyncError(f'Dataset does not have a time reference {" ".join(msgs)}')


def getSyncSources(dataset: "Dataset") -> List["EventArray"]:
    """ Get the `SubChannel`s that can be used for time synchronization.

        :param dataset: The `Dataset` from which to get the sources.
    """
    sources = []
    for s in getSyncSensors(dataset):
        for ch in s.getReferrers():
            sources.append(ch.getSession())
    return sources


# ===========================================================================
#
# ===========================================================================

def getSyncTimeZero(data: Union["Dataset", "EventArray"],
                    start: Optional[int] = None,
                    end: Optional[int] = None,
                    sensorId: Optional[int] = None,
                    clear: bool = False) -> int:
    """ Get the sync reference's time corresponding to the recording's
        relative timestamp zero.

        :param data: The data from which to get the reference time. It can
            be either a `Dataset` (in which case it uses either the first sync
            source found or the one indicated by `sensorId`) or an `EventArray`
            (to use a specific subchannel as the time reference).
        :param start: The starting index into the time reference data, to use
            a limited range to compute the zero offset. For use with large
            and/or noisy Datasets. Defaults to the beginning of the data.
        :param end: The ending index into the time reference data, to use
            a limited range to compute the zero offset. For use with large
            and/or noisy Datasets. Defaults to the end of the data.
        :param sensorId: The ID of a specific time reference sensor. Only
            used if `data` is a `Dataset`. If `None`, the first time
            reference sensor found is used.
        :param clear: If `False`, use cached zero offset (if present).
        :returns: The sync reference time (in microseconds) corresponding to
            the recording's relative timestamp zero.
    """
    # TODO: Once this PoC is proven, this can be made a method of `Dataset`
    #  and/or `EventArray` with no arguments (or different ones).

    if hasattr(data, 'channels'):
        # data is a Dataset
        session = data.currentSession
        dataset = data
    elif hasattr(data, 'session'):
        # data is an EventArray
        session = data.session
        dataset = data.dataset
    else:
        raise SyncError(f'Cannot get sync info from {data!r}')

    if session.syncZero is not None and session.syncInfo and not clear:
        return session.syncZero

    # HACK: An indirect means of detecting a `Dataset`, avoiding circular imports.
    if hasattr(data, 'channels'):  # isinstance(data, Dataset):
        sources = getSyncSources(data)
        if not sources:
            raise SyncError(f'{dataset} does not contain any sync time sources')
        if sensorId is not None:
            sources = [s for s in sources if s.parent.sensor.id == sensorId]
            if not sources:
                raise SyncError(f'{dataset} does not contain time reference sensor ID {sensorId}')
        sync = sources[0]
    else:
        sync = data

    if len(sync) == 0:
        raise SyncError(f'No sync reference data in {dataset} - was it not fully imported?')

    with sync.dataset._channelDataLock:
        timestamp, synctime = sync.arraySlice(start, end).mean(axis=1)

        session.syncZero = int(synctime - timestamp)
        session.syncSensor = sync.parent.sensor

        if session.syncInfo is None or clear is True:
            session.syncInfo = {'SyncActive': False}

        session.syncInfo.update({
            'SyncChannelIDRef': sync.parent.parent.id,
            'SyncSubChannelIDRef': sync.parent.id,
            'SyncSourceName': sync.parent.sensor.sourceName,
            'SyncSourceIdentifier':  sync.parent.sensor.sourceId,
            'SyncZero': session.syncZero,
            'TimeBaseUTC': [session.utcStartTimeOriginal],
            'SyncFilename': dataset.filename,
            'SyncFingerprint': dataset.fingerprint,
        })

    return session.syncZero


def getCommonSensorIds(*datasets: "Dataset") -> List[int]:
    """ Get the Sensor ID of the time reference shared by two or more
        recordings. This does *not* verify that any time data has been
        recorded from it, only that the sensor exists.
    """
    if len(datasets)  < 2:
        raise SyncError('At least two datasets are required')

    sources = set(getSyncSensors(datasets[0]))
    for ds in datasets[1:]:
        s = getSyncSensors(ds)
        if not s:
            raise SyncError(f'No usable time reference found in {ds}')
        sources.intersection_update(s)

    if not sources:
        raise SyncError('Recordings do not share a common time reference')

    # TODO: More tests? Check compatible times (similar UTCs)?
    return [s.id for s in sources]


# ===========================================================================
#
# ===========================================================================

def sync(reference: "Dataset", *datasets: "Dataset",
         sensorId: Optional[int] = None,
         inherit: bool = True):
    """ Synchronize one or more recordings with a canonical 'reference'
        recording. The 'reference' is not modified. Synched recordings
        will have their timestamps and UTC start time offset to match
        the reference.

        :param reference: The reference `Dataset` to which to synchronize
            the others.
        :param datasets: One or more `Dataset` objects to synchronize.
        :param sensorId: The time reference's sensor ID. If `None`, the
            first common time reference sensor detected is used. Use if the
            recordings have multiple time references in common.
        :param inherit: If `True` and the `reference` Dataset has been synced
            to another recording, sync the `datasets` to the same recording
            `reference` has been synced to. If `False`, clear existing sync
            info from the `reference` and sync the `datasets` to the
            reference's zero time.
    """
    # NOTE: This function assumes there is only one session, only one
    #  reference time sensor, and only one subchannel for the reference time.

    if len(datasets) < 1:
        raise SyncError('At least one dataset to sync is required')

    allDatasets = (reference, *datasets)

    if sensorId is None:
        ids = tuple(getCommonSensorIds(reference, *datasets))
        if len(ids) > 1:
            raise SyncError(f'Recordings share multiple time references {ids}, '
                            'use sensorId parameter to select one')
        sensorId = ids[0]
    elif not all(sensorId in ds.sensors for ds in (reference, *datasets)):
        raise SyncError(f'Not all recordings contain sensor ID {sensorId}')

    # Backup offsets/zero times, in case of failure
    origOffsets = [ds.currentSession.offset for ds in allDatasets]
    origZeros = [ds.currentSession.syncZero for ds in allDatasets]
    origInfo = [deepcopy(ds.currentSession.syncInfo) for ds in allDatasets]

    refInfo = reference.currentSession.syncInfo or {}
    clear = not inherit or 'SyncReferenceZero' not in refInfo

    try:
        for ds in allDatasets if clear else datasets:
            ch = ds.sensors[sensorId].getReferrers()[0]
            ref = ch.getSession()
            ds.currentSession.offset = 0
            ds.currentSession.syncZero = getSyncTimeZero(ref, start=0)

        if clear:
            refzero = reference.currentSession.syncZero
            refutc = reference.currentSession.utcStartTime
            refFilename = reference.filename
            refFingerprint = reference.fingerprint
        else:
            refzero = refInfo.get('SyncReferenceZero', reference.currentSession.syncZero)
            refutc = refInfo.get('SyncTimeBaseUTC', reference.currentSession.utcStartTime)
            refFilename = refInfo.get('SyncReferenceFilename')
            refFingerprint = refInfo.get('SyncReferenceFingerprint')

        for ds in datasets:
            with ds._channelDataLock:
                offset = ds.currentSession.syncZero - refzero
                ds.currentSession.offset = offset
                ds.currentSession.utcStartTime = refutc

                # Update syncInfo set by getSyncTimeZero()
                ds.currentSession.syncInfo.update({
                    'SyncActive': True,
                    'SyncReferenceZero': refzero,
                    'SyncReferenceFilename': refFilename,
                    'SyncReferenceFingerprint': refFingerprint,
                    'SyncTimeBaseUTC': refutc
                })

    except Exception:
        # Failure: Restore original pre-sync values.
        for ds, offset, zero, info in zip(allDatasets, origOffsets, origZeros, origInfo):
            with ds._channelDataLock:
                ds.currentSession.syncZero = zero
                ds.currentSession.offset = offset
                ds.currentSession.utcStartTime = ds.currentSession.utcStartTimeOriginal
                ds.currentSession.syncInfo = info
        raise


# ===========================================================================
# Getting/applying sync info loaded from userdata and/or copied from another
# recording.
# ===========================================================================

def validateSyncInfo(dataset: "Dataset",
                     info: Dict[str, Any]) -> bool:
    """ Check that a dictionary of sync info is valid for a dataset.

        :param dataset: The `Dataset` to which the sync info will be applied.
        :param info: The dictionary of synchronization info to validate. The
            keys match the names of ``SyncInfo`` child elements in the
            ``mide_ide.xml`` EBML schema.
    """
    if not info:
        return False

    schema = dataset.ebmldoc.schema
    validElements = [schema[eid].name for eid in schema['SyncInfo'].children]
    for key in info:
        if key not in validElements:
            raise SyncError(f'Invalid sync info key {key!r}')

    # Find the time source. This will raise an exception if the source is not found.
    getSyncSensor(dataset,
                  sourceId=info.get('SyncSourceIdentifier'),
                  sourceName=info.get('SyncSourceName'))

    # TODO: Additional validation (time range compatibility, etc.)?
    return True


def hasSyncReferenceInfo(info: Dict[str, Any]) -> bool:
    """ Check if a dictionary of sync info contains the information
        needed to sync to a reference recording (e.g., copied from a
        recording that has already been synced).

        :param info: The dictionary of synchronization info to check. The
            keys match the names of ``SyncInfo`` child elements in the
            ``mide_ide.xml`` EBML schema.
    """
    if 'SyncSourceName' not in info and 'SyncSourceIdentifier' not in info:
        return False
    return 'SyncReferenceZero' in info and 'SyncTimeBaseUTC' in info


def makeSyncReferenceInfo(info: Dict[str, Any]) -> Dict[str, Any]:
    """ Create a dictionary of sync 'reference' info from a dictionary of
        sync 'target' info. For use with `applySyncInfo()` when applying
        sync info copied from another recording, to sync to that recording.
    """
    info = deepcopy(info)
    info.update({
        'SyncActive': True,
        'SyncReferenceZero': info.pop('SyncZero', None),
        'SyncReferenceFilename': info.pop('SyncFilename', None),
        'SyncReferenceFingerprint': info.pop('SyncFingerprint', None),
        'SyncTimeBaseUTC': info.pop('TimeBaseUTC', [0])[0]
    })
    return info


def applySyncInfo(dataset: "Dataset",
                  info: Dict[str, Any],
                  validate: bool = True):
    """ Apply a dictionary of sync info to a dataset.

        :param dataset: The `Dataset` to which the sync info will be applied.
        :param info: The dictionary of synchronization info to validate. The
            keys match the names of ``SyncInfo`` child elements in the
            ``mide_ide.xml`` EBML schema.
        :param validate: If `True`, validate the sync info before applying.
    """
    info = {k: v for k, v in info.items() if v is not None}

    if validate:
        validateSyncInfo(dataset, info)

    session = dataset.currentSession
    session.syncSensor = getSyncSensor(dataset,
                                       sourceId=info.get('SyncSourceIdentifier'),
                                       sourceName=info.get('SyncSourceName'))
    getSyncTimeZero(dataset, sensorId=session.syncSensor.id)
    session.syncInfo = info

    if not info.get('SyncActive', True):
        return

    session.utcStartTime = info.get('SyncTimeBaseUTC', session.utcStartTimeOriginal)
    session.offset = session.syncZero - info.get('SyncReferenceZero', 0)


def getSyncInfo(dataset: "Dataset") -> Dict[str, Any]:
    """ Get a dictionary of sync info from a recording.
    """
    getSyncTimeZero(dataset)
    session = dataset.currentSession

    # Remove any `None` values
    return {k: v for k, v in session.syncInfo.items() if v is not None}


def removeSyncInfo(dataset: "Dataset"):
    """ Remove sync info from a Dataset.
    """
    with dataset._channelDataLock:
        session = dataset.currentSession
        session.syncInfo = None
        session.syncSensor = None
        session.offset = 0
        session.utcStartTime = session.utcStartTimeOriginal
        session.firstTime = session.firstTimeOriginal
        session.lastTime = session.lastTimeOriginal


def loadSyncInfo(dataset: "Dataset",
                 refresh: bool = False) -> bool:
    """ Read and apply sync info from a file's userdata.

        :param dataset: The `Dataset` from which to load the sync info.
        :param refresh: If `True`, ignore any cached user data and reload
            from the file.
        :return: `True` if sync info was present, `False` otherwise. Errors
            in the sync data will raise exceptions (e.g., `SyncError`).
    """
    data = userdata.readUserData(dataset, refresh=refresh)
    if data and 'SyncInfo' in data:
        applySyncInfo(dataset, data['SyncInfo'], validate=False)
        return True
    return False


def updateUserdata(dataset: "Dataset"):
    """ Create or update sync info in a Dataset's userdata. Note that this does
        not save the user data to the file; `idelib.userdata.writeUserData()`
        must be called explicitly.

        :param dataset: The `Dataset` to update.
    """
    data = userdata.readUserData(dataset) or {}
    session = dataset.currentSession
    if not session.syncInfo:
        data.pop('SyncInfo', None)
        return

    info = getSyncInfo(dataset)

    if info:
        data['SyncInfo'] = info
    else:
        data.pop('SyncInfo', None)

    if data is not dataset._userdata:
        dataset._userdata = data
