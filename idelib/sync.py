"""
Functions to assist in syncing one file to another.
"""

from typing import List, Optional, Union

from idelib.dataset import Dataset, EventArray, Sensor, Session, SubChannel


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
        for ch in s.getReferers():
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
        return getSyncTimeZero(sources[0])

    if startTime is None and endTime is None:
        timestamp, synctime = data[0]
    else:
        timestamp, synctime = data.getRange(startTime, endTime).mean(axis=1)

    return synctime - timestamp
