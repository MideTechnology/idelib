"""
Utility functions for doing low-level, general-purpose EBML reading and writing.
"""

from collections import Counter
from io import IOBase
import logging
import os.path
from pathlib import Path
import sys

from ebmlite import loadSchema

from .dataset import Dataset
from .importer import openFile

# ==============================================================================
#
# ==============================================================================

logger = logging.getLogger('idelib')


# ==============================================================================
#
# ==============================================================================

def verify(data, schema=None):
    """ Basic sanity-check of data validity. If the data is bad an exception
        will be raised. The specific exception varies depending on the problem
        in the data.

        :keyword schema: The full module name of the EBML schema.
        :return: `True`. Any problems will raise exceptions.
    """
    if schema is None:
        schema = loadSchema('mide_ide.xml')
    return schema.verify(data)


# ==============================================================================
#
# ==============================================================================

def extractTime(doc, out, startTime=0, endTime=None, channels=None,
                updater=None):
    """ Efficiently extract data within a certain interval from an IDE file.
        Note that due to the way data is stored in an IDE, the exported
        interval will be slightly wider than the specified start and end
        times; this ensures the data is copied verbatim and without loss.

        :param doc: A loaded `Dataset` or the name of an IDE file.
        :param out: A filename or stream to which to save the extracted data.
        :param startTime: The start of the extraction range, relative to the
            recording's start.
        :param endTime: The end of the extraction range, relative to the
            recording's end.
        :param channels: A list of channel IDs to specifically export. If
            `None`, all channels will be exported. Note excluded channels will
            still appear in the new IDE's `channels` dictionary, but the file
            will contain no data for them.
        :param updater: A function (or function-like object) to notify as
            work is done. It should take four keyword arguments: `count` (the
            current line number), `total` (the total number of samples), `error`
            (an unexpected exception, if raised during the import), and `done`
            (will be `True` when the split is complete). If the updater object
            has a `cancelled` attribute that is `True`, the import will be
            aborted. The default callback is `None` (nothing will be notified).
        :return: The total number of bytes written, and total number of
            ChannelDataBlock elements copied.
    """
    if isinstance(doc, (str, Path)):
        doc = openFile(doc)

    if endTime is None:
        endTime = float('infinity')

    # Dictionaries (and similar) for tracking progress of each ChannelDataBlock
    # element handled. All keyed by channel ID (ChannelIDRef).
    lastBlocks = {}  # Previous element w/ its start and end times
    channelsWritten = Counter()  # Number of elements extracted per channel
    finished = {}  # Channels that have completed extraction

    copiedBytes = 0

    # Updater stuff
    totalElements = len(doc.ebmldoc)
    increment = int(totalElements / 20)

    if isinstance(out, (str, Path)):
        fs = open(out, 'wb')
    elif isinstance(out, IOBase) or hasattr(out, 'seek'):
        fs = out
    else:
        raise TypeError("unsupported type for output; expected filename "
                        "or stream, got {} ".format(type(out)))

    try:
        timeScalars = doc._parsers['ChannelDataBlock'].timeScalars

        for n, el in enumerate(doc.ebmldoc, 1):
            if updater:
                if updater.cancelled:
                    break

                if n % increment == 0:
                    updater(count=n, total=totalElements)

            if el.name == 'ChannelDataBlock':
                # Get ChannelIDRef, StartTimeCodeAbs, and EndTimeCodeAbs;
                # usually the 1st three, in order, but don't assume!
                chId = blockStart = blockEnd = None
                for subEl in el:
                    if subEl.name == "ChannelIDRef":
                        chId = subEl.value
                    elif subEl.name == "StartTimeCodeAbs":
                        blockStart = subEl.value
                    elif subEl.name == "EndTimeCodeAbs":
                        blockEnd = subEl.value

                blockEnd = blockEnd or blockStart
                if chId is None:
                    logger.warning("Extractor: {} missing <ChannelIDRef> subelement, skipping.".format(el))
                    continue
                if blockStart is None:
                    logger.warning("Extractor: {} missing <StartTimeCodeAbs> subelement, skipping.".format(el))
                    continue

                if channels and chId not in channels:
                    continue
                if finished.setdefault(chId, False):
                    continue

                # TODO: Modulus correction, if still needed.
                scalar = timeScalars.get(chId, 1)
                blockStart *= scalar
                blockEnd *= scalar

                writeCurrent = True
                writePrev = False  # write previous block, if current one starts late

                if blockEnd < startTime:
                    # Entirely before extraction interval. Write nothing.
                    writeCurrent = False
                elif blockStart <= startTime:
                    # Block overlaps start of interval. Write block.
                    # Mark channel finished if block also includes end of interval.
                    writePrev = False
                    finished[chId] = blockEnd >= endTime
                elif blockEnd <= endTime:
                    # Block within interval. Write block (w/ prev. if needed).
                    writePrev = channelsWritten[chId] == 0
                else:
                    # Block overlaps end of interval. Write block (w/ prev. if needed).
                    # Mark channel finished.
                    finished[chId] = True
                    writePrev = channelsWritten[chId] == 0

                if writePrev:
                    # Write the previous block, which is before the extraction interval.
                    # This is to ensure that initial data is not left out.
                    prev = lastBlocks.get(chId, None)
                    if prev:
                        data = prev[0].getRaw()
                        fs.write(data)
                        copiedBytes += len(data)
                        channelsWritten[chId] += 1

                lastBlocks[chId] = (el, blockStart, blockEnd)

                if writeCurrent:
                    channelsWritten[chId] += 1
                else:
                    # Skip to next element without writing anything.
                    continue

            data = el.getRaw()
            fs.write(data)
            copiedBytes += len(data)

    except (StopIteration, KeyboardInterrupt):
        pass

    finally:
        if isinstance(out, (str, Path)):
            fs.close()

    if updater:
        updater(done=True)

    return copiedBytes, sum(channelsWritten.values())


# ==============================================================================
#
# ==============================================================================

CHUNK_SIZE = 512 * 1024  # Size of chunks when looking for last sync
SYNC = b'\xfa\x84ZZZZ'  # The raw EBML of a Sync element


def _getSize(stream):
    """
    Get the length of a stream from its data.

    :param stream: A file stream or file-like object (must implement `tell()`
        and `seek()`).
    :returns: The total length of the file.
    """
    if hasattr(stream, 'name'):
        if os.path.isfile(stream.name):
            return os.path.getsize(stream.name)

    if not (hasattr(stream, 'seek') and hasattr(stream, 'tell')):
        raise TypeError('Cannot get size of non-stream {}'.format(type(stream)))

    originalPos = stream.tell()
    thisRead = CHUNK_SIZE
    while thisRead == CHUNK_SIZE:
        thisRead = len(stream.read(CHUNK_SIZE))

    eof = stream.tell()
    stream.seek(originalPos)
    return eof


def _getLastSync(stream, length=None):
    """
    Retrieve the offset of the last `Sync` element with data after it in
    an IDE.

    :param doc: The opened IDE `idelib.dataset.Dataset`
    :return: The offset of the last EBML `Sync` element in the file
    """

    if not (hasattr(stream, 'seek') and hasattr(stream, 'tell')):
        raise TypeError("IDE file had bad stream type ({})".format(type(stream)))

    originalPos = stream.tell()
    offset = length or _getSize(stream)

    while True:
        offset = max(0, offset - CHUNK_SIZE)
        stream.seek(offset)
        chunk = stream.read(CHUNK_SIZE + len(SYNC))
        sync_idx = chunk.find(SYNC)
        if sync_idx > -1:
            # Make sure there's data after it by checking for ChannelDataBlock
            # IDs. This is somewhat brittle, since the IDs are 1 byte, but it
            # is not likely for anything but a ChannelDataBlock would have the
            # IDs for ChannelDataBlock and ChannelIDRef in order. Even if
            # they are in the payload, it still implies a ChannelDataBlock.
            block_idx = chunk.find(b'\xa1', sync_idx)
            if -1 < block_idx < chunk.rfind(b'\xb0', block_idx):
                offset += sync_idx
                break
        if offset <= 0:
            break

    stream.seek(originalPos)
    return max(offset, 0)


def _getBlockTime(doc, el):
    """
    Internal utility function to quickly get the ID and start and end times
    of an IDE `ChannelDataBlock`. Works directly with the EBML.

    :param doc: The opened IDE `idelib.dataset.Dataset`
    :param el: The `ChannelDataBlock EBML element to process
    :return: A tuple containing channel ID, start time, and end time.
    """
    start = end = None
    chId = blockStart = blockEnd = None
    for subEl in el:
        if subEl.name == "ChannelIDRef":
            chId = subEl.value
        elif subEl.name == "StartTimeCodeAbs":
            blockStart = subEl.value
        elif subEl.name == "EndTimeCodeAbs":
            blockEnd = subEl.value

    # TODO: Modulus correction, if still needed (i.e., very old files)
    blockEnd = blockEnd or blockStart
    scalar = doc._parsers['ChannelDataBlock'].timeScalars.get(chId, 1)
    if blockStart is not None:
        # logger.warning("getLength: {} missing <EndTimeCodeAbs> subelement, skipping.".format(el))
        start = blockStart // (1.0 / scalar)
    if blockEnd is not None:
        # logger.warning("getLength: {} missing <EndTimeCodeAbs> subelement, skipping.".format(el))
        end = blockEnd // (1.0 / scalar)

    return chId, start, end


def _getLength(doc):
    """
    Retrieve the start and end times of an `idelib.dataset.Dataset` (e.g. an
    open/imported IDE file). Used by `getLength()`.

    :param doc: The opened IDE file
    :return: The timestamps of the first and last samples in the file, in
        microseconds, relative to the start of the recording.
    """
    start = float('infinity')
    end = 0

    # Get starting time, reading several blocks since different channels
    # may not be in chronological order.
    count = 0
    for el in doc.ebmldoc:
        if el.name != "ChannelDataBlock":
            continue
        _chId, blockStart, _blockEnd = _getBlockTime(doc, el)
        start = min(blockStart, start) if blockStart is not None else blockStart

        count += 1
        if count > 10:  # Note: number is somewhat arbitrary
            break

    # Get ending time by jumping to a Sync near the end and reading blocks
    # from there to the end of file.
    stream = doc.ebmldoc.stream

    # Use the cached EBML document size if the IDE was already fully imported,
    # otherwise use `None` so `_getLastSync()` will calculate it (faster than
    # getting uncached `soc.ebmldoc.size`)
    streamLength = None if doc.loading else doc.ebmldoc.size
    stream.seek(_getLastSync(stream, streamLength))
    temp_ebml = doc.ebmldoc.schema.load(stream)

    for el in temp_ebml:
        if el.name != "ChannelDataBlock":
            continue

        _chId, _blockStart, blockEnd = _getBlockTime(doc, el)
        if blockEnd:
            end = max(blockEnd, end)

    return start, end


def getLength(doc):
    """
    Efficiently retrieve the start and end times of an IDE file, without it
    having to be fully imported.

    :param doc: The IDE filename, an `idelib.dataset.Dataset`, or stream
        containing IDE data.
    :return: The timestamps of the first and last samples in the file, in
        microseconds, relative to the start of the recording.
    """
    # This really just wraps `_getLength()` in order to handle different
    # source `doc` types
    if isinstance(doc, str):
        with open(doc, 'rb') as f:
            return _getLength(openFile(f))
    elif isinstance(doc, Dataset):
        return _getLength(doc)
    elif isinstance(doc, IOBase):
        return _getLength(openFile(doc))

    raise TypeError("getLength() needs a filename, stream, or Dataset; got {}".format(type(doc)))


# ==============================================================================
#
# ==============================================================================


def getExitCondition(recording):
    """ Get the ``ExitCond`` Attribute from the end of a recording, if present.
        The result will be an integer:

        * 1: Button press
        * 2: USB connection
        * 3: Recording time limit reached
        * 4: Low battery
        * 5: File size limit reached
        * 128: I/O error (can occur if disk is full or 4GB FAT32 size limit
          reached.

        :param recording: The IDE file, either a filename or a file-like object.
    """
    result = None

    if isinstance(recording, str):
        with open(recording, "rb") as fs:
            return getExitCondition(fs)

    offset = recording.tell()

    recording.seek(_getSize(recording) - CHUNK_SIZE)
    data = recording.read()
    try:
        # Seek out the exit condition Attribute by the
        # string of its name, then offset to where the
        # data is expected to be.
        idx = data.index(b"ExitCond") + 11
        if idx <= len(data):
            result = data[idx]
    except (IOError, IndexError, ValueError) as e:
        logger.warning(e)

    recording.seek(offset)
    return result
