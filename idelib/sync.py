"""
Functions to assist in syncing one file to another.
"""

from typing import List, Optional, Union

from idelib.dataset import Dataset, EventArray, Sensor, SubChannel


# ===========================================================================
#
# ===========================================================================

class SyncError(ValueError):
    """ Exception raised when files cannot be synchronized. """


# ===========================================================================
#
# ===========================================================================

def getSyncSensors(doc: Dataset) -> List[Sensor]:
    """ Get the 'sensors' that can be used for time synchronization.
    """
    return [s for s in doc.sensors.values() if s.name and 'Time' in s.name]


def getSyncSources(doc: Dataset) -> List[SubChannel]:
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

def getSyncTimeZero(data: Union[Dataset, EventArray],
                    startTime: Optional[int] = None,
                    endTime: Optional[int] = None) -> int:
    """ Get the sync reference time corresponding to the recording's
        relative timestamp zero. Note: if both `startTime` and `endTime`
        are `None`, the recording's first sync timestamp in the recording
        is used. In some cases, single values may be off, and a mean
        over some interval of time used instead.

        :param data: The data from which to get the reference time. It can
            be either a `Dataset` (in which case it uses the first sync
            source found) or an `EventArray` (to use a specific subchannel).
        :param startTime: The start of a time range (relative to the
            recording's timestamps) from which to average the sync
            zero offset. For use with noisy sync times.
        :param endTime: The end of a time range (relative to the
            recording's timestamps) from which to average the sync
            zero offset. For use with noisy sync times.
        :returns: The sync reference time (in microseconds) corresponding to
            the recording's relative timestamp zero.
    """
    # TODO: Once this PoC is proven, this can be made a method of `Dataset`
    #  and/or `EventArray` with no arguments (or different ones).
    if isinstance(data, Dataset):
        sources = getSyncSources(data)
        if not sources:
            raise ValueError('Dataset does not contain any sync sources')
        sync = sources[0]
    else:
        sync = data

    if len(sync) == 0:
        raise SyncError(f'No sync reference data in {data}')

    if startTime is None and endTime is None:
        timestamp, synctime = sync[0]
    else:
        timestamp, synctime = sync.getRange(startTime, endTime).mean(axis=1)

    return synctime - timestamp



def getCommonSensorIds(*datasets: Dataset) -> List[int]:
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


def sync(reference: Dataset, *datasets: Dataset):
    """ Synchronize one or more recordings with a canonical 'reference'
        recording. The 'reference' is not modified.
    """
    # NOTE: This assumes there is only one session, only one reference time
    #  sensor, and only one subchannel for the reference time.
    alldata = (reference, *datasets)
    sensorId = getCommonSensorIds(*alldata)[0]

    for ds in (reference, *datasets):
        ch = ds.sensors[sensorId].getReferrers()[0]
        ref = ch.getSession()
        ds.currentSession.syncZero = getSyncTimeZero(ref)

    refzero = reference.currentSession.syncZero
    refutc = reference.currentSession.utcStartTime

    for ds in datasets:
        offset = ds.currentSession.syncZero - refzero
        ds.currentSession.offset = offset
        ds.currentSession.utcStartTime = refutc


