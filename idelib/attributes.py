"""
Utility functions for doing low-level, general-purpose EBML reading and writing.

Note: Most of the functionality that was here is now part of ebmlite. This
    module now contains little besides the 'Attribute' handling functions.

Created on Dec 10, 2013

:author: dstokes

"""

from collections import Counter, OrderedDict
import datetime
from io import IOBase
from pathlib import Path
import time

from ebmlite import loadSchema

from .importer import openFile


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

def decode_attributes(data, withTypes=False):
    """ Convert a set of Attributes (as a list of dictionaries containing an
        `AttributeName` and one of the Attribute value elements (`IntAttribute`,
        `FloatAttribute`, etc.) to a proper dictionary. Attributes are tagged
        as 'multiple,' so they become lists when the EBML is parsed.
    """
    result = OrderedDict()
    for atts in data:
        k = atts.pop('AttributeName', None)
        if k is None:
            continue
        t, v = list(atts.items())[0]
        if withTypes:
            att = (v, t)
        else:
            att = v
        result.setdefault(k, []).append(att)
    return result

    
def encode_attributes(data):
    """ Construct a set of `Attribute` dicts from a dictionary or list of
        tuples/lists. Each value should be either a simple data type or a
        tuple containing the value and the specific value element name
        (IntAttribute, FloatAttribute, etc.). The value element type will 
        otherwise be inferred.
    """
    datetimeTypes = (datetime.datetime, datetime.date)
    attTypes = ((str, 'UnicodeAttribute'),
                (bytes, 'StringAttribute'),
                (float, 'FloatAttribute'),
                (int, 'IntAttribute'),
                (time.struct_time, 'DateAttribute'),
                (datetimeTypes, 'DateAttribute'))
    
    if isinstance(data, dict):
        data = list(data.items())
    
    result = []
    elementType = None

    for d in data:
        if isinstance(d[1], (tuple, list)) and not isinstance(d[1], time.struct_time):
            k = d[0]
            v, elementType = d[1]
        else:
            k, v = d
            for t, elementType in attTypes:
                if isinstance(v, t):
                    break
                elementType = 'BinaryAttribute'
        
        if elementType == 'DateAttribute':
            if isinstance(v, (int, float)):
                v = int(v)
            elif isinstance(data, datetimeTypes):
                v = int(time.mktime(data.timetuple()))
            elif isinstance(data, time.struct_time):
                v = int(time.mktime(v))
                
        result.append({'AttributeName': k, elementType: v})

    return result
    

def build_attributes(data):
    """ Construct `Attribute` EBML from dictionary or list of key/value pairs. 
        Each value should be either a simple data type or a tuple containing 
        the value and the specific value element name (`IntAttribute`, 
        `FloatAttribute`, etc.). The value element type will otherwise be 
        inferred.
    """
    mideSchema = loadSchema('mide_ide.xml')
    return mideSchema['Attribute'].encode(encode_attributes(data))


# ==============================================================================
#
# ==============================================================================

def extractTime(doc, out, startTime=None, endTime=None, channels=None,
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
            `None`, all channels will be exported.
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
    elif isinstance(out, IOBase):
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
                    # logger.warning(f"Extractor: {el} missing <ChannelIDRef> subelement, skipping.")
                    continue
                if blockStart is None:
                    # logger.warning(f"Extractor: {el} missing <StartTimeCodeAbs> subelement, skipping.")
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

