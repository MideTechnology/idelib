"""
Utility functions for doing low-level, general-purpose EBML reading and writing.
"""

from collections import Counter
from io import IOBase
import logging
from pathlib import Path
import sys

from ebmlite import loadSchema

from .importer import filterTime, openFile

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

    copiedBytes = 0

    # Updater stuff
    totalElements = len(doc.ebmldoc)  # TODO: Change this, so the EBML document doesn't get crawled to count elements. Use file size and `tell()`?
    increment = int(totalElements / 20)

    if isinstance(out, (str, Path)):
        fs = open(out, 'wb')
    elif isinstance(out, IOBase) or hasattr(out, 'seek'):
        fs = out
    else:
        raise TypeError("unsupported type for output; expected filename "
                        "or stream, got {} ".format(type(out)))

    try:
        for n, el in enumerate(filterTime(doc, startTime, endTime, channels=channels), 1):
            if updater:
                if updater.cancelled:
                    break

                if n % increment == 0:
                    updater(count=n, total=totalElements)

            if el is not None:
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

    return copiedBytes
