"""
Functions to assist in syncing one file to another.

NOTE: This is currently a proof of concept. Some functionality may eventually
be rolled directly into classes in `idelib.dataset`.
"""

from typing import List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from idelib.dataset import Dataset, EventArray, Sensor, SubChannel


# ===========================================================================
#
# ===========================================================================

class SyncError(ValueError):
    """ Exception raised when files cannot be synchronized. """


# ===========================================================================
#
# ===========================================================================

def getSyncSensors(doc: "Dataset") -> List["Sensor"]:
    """ Get the 'sensors' that can be used for time synchronization.
    """
    return [s for s in doc.sensors.values() if s.name and 'Time' in s.name]


def getSyncSources(doc: "Dataset") -> List["SubChannel"]:
    """ Get the `SubChannel`s that can be used for time synchronization.

        :param doc: The `Dataset` from which to get the sources.
    """
    sources = []
    for s in getSyncSensors(doc):
        for ch in s.getReferrers():
            sources.append(ch.getSession())
    return sources


# ===========================================================================
#
# ===========================================================================

def getSyncTimeZero(data: Union["Dataset", "EventArray"],
                    start: Optional[int] = None,
                    end: Optional[int] = None,
                    sensorId: Optional[int] = None) -> int:
    """ Get the sync reference's time corresponding to the recording's
        relative timestamp zero.

        Note: if both `start` and `end` are `None`, the recording's first
        reference timestamp is used. However, in some cases, individual
        values may vary, and a mean of multiple time reference values is
        more accurate. To use the mean of all reference values, use
        `start=0` and no `end`.

        :param data: The data from which to get the reference time. It can
            be either a `Dataset` (in which case it uses the first sync
            source found) or an `EventArray` (to use a specific subchannel
            as the time reference).
        :param start: The starting index into the time reference data. For
            use with noisy sync times.
        :param end: The ending index into the time reference data. For
            use with noisy sync times.
        :param sensorId: The ID of a specific time reference sensor. Only
            used if `data` is a `Dataset`. If `None`, the first time
            reference sensor found is used.
        :returns: The sync reference time (in microseconds) corresponding to
            the recording's relative timestamp zero.
    """
    # TODO: Once this PoC is proven, this can be made a method of `Dataset`
    #  and/or `EventArray` with no arguments (or different ones).

    # HACK: An indirect means of detecting a `Dataset`, avoiding circular imports.
    if hasattr(data, 'filename'):  # isinstance(data, Dataset):
        sources = getSyncSources(data)
        if not sources:
            raise SyncError('Dataset does not contain any sync sources')
        if sensorId is not None:
            sources = [s for s in sources if s.sensor.id == sensorId]
            if not sources:
                raise SyncError(f'Dataset does not contain time reference sensor ID {sensorId}')
        sync = sources[0]
    else:
        sync = data

    if len(sync) == 0:
        raise SyncError(f'No sync reference data in {data} - was it not fully imported?')

    with sync.dataset._channelDataLock:
        if start is None and end is None:
            timestamp, synctime = sync[0]
        else:
            timestamp, synctime = sync.arraySlice(start, end).mean(axis=1)

    return synctime - timestamp


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
         start: Optional[int] = None,
         end: Optional[int] = None,
         sensorId: Optional[int] = None):
    """ Synchronize one or more recordings with a canonical 'reference'
        recording. The 'reference' is not modified. Synched recordings
        will have their timestamps and UTC start time offset to match
        the reference.

        :param reference: The reference `Dataset` to which to synchronize
            the others.
        :param datasets: One or more `Dataset` objects to synchronize.
        :param start: The starting index into the time reference data of
            each recording. For use with noisy sync times.
        :param end: The ending index into the time reference data. For
            use with noisy sync times.
        :param sensorId: The time reference's sensor ID. If `None`, the
            first common time reference sensor detected is used. Use if
            the recordings have multiple time references in common.
    """
    # NOTE: This function assumes there is only one session, only one
    #  reference time sensor, and only one subchannel for the reference time.

    if len(datasets) < 1:
        raise SyncError('At least one dataset to sync is required')

    if sensorId is None:
        ids = tuple(getCommonSensorIds(reference, *datasets))
        if len(ids) > 1:
            raise SyncError(f'Recordings share multiple time references {ids}, '
                            'use sensorId parameter to select one')
        sensorId = ids[0]
    elif not all(sensorId in ds.sensors for ds in (reference, *datasets)):
        raise SyncError(f'Not all recordings contain sensor ID {sensorId}')

    # Backup offsets/zero times, in case of failure
    origOffsets = [ds.currentSession.offset for ds in datasets]
    origZeros = [ds.currentSession.syncZero for ds in datasets]
    origInfo = [ds.currentSession.syncInfo for ds in datasets]

    try:
        for ds in (reference, *datasets):
            ch = ds.sensors[sensorId].getReferrers()[0]
            ref = ch.getSession()
            ds.currentSession.offset = 0
            ds.currentSession.syncZero = getSyncTimeZero(ref, start=start, end=end)

        refzero = reference.currentSession.syncZero
        refutc = reference.currentSession.utcStartTime

        for ds in datasets:
            with ds._channelDataLock:
                offset = ds.currentSession.syncZero - refzero
                ds.currentSession.offset = offset
                ds.currentSession.utcStartTime = refutc

                sensor = ds.sensors[sensorId]
                ch = sensor.getReferrers()[0]
                ds.currentSession.syncInfo = {
                    'SyncActive': True,
                    'SyncChannelIDRef': ch.parent.id,
                    'SyncSubChannelIDRef': ch.id,
                    'SyncSourceName': sensor.sourceName,
                    'SyncSourceIdentifier': sensor.sourceId,
                    'SyncZero': ds.currentSession.syncZero,
                    'SyncReferenceZero': refzero,
                    'SyncReferenceFilename': reference.filename,
                    'TimeBaseUTC': refutc
                }

    except Exception:
        # Failure: Restore original pre-sync values.
        for ds, offset, zero, info in zip(datasets, origOffsets, origZeros, origInfo):
            with ds._channelDataLock:
                ds.currentSession.syncZero = zero
                ds.currentSession.offset = offset
                ds.currentSession.utcStartTime = ds.currentSession.utcStartTimeOriginal
                ds.currentSession.syncInfo = info
        raise
