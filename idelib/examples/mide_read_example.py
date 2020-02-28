'''
========================
Example MIDE File Reader
========================
(c) 2015 Mide Technology Corp.

The Mide Instrumentation Data Exchange (MIDE) format is based on EBML,
a structured binary format. This script will parse data from an IDE file
recorded by a Slam Stick X. Some modification will be required to parse data
from another source.


Requirements
------------
Python 2.7.*
python-ebml (https://github.com/jspiros/python-ebml)
Numpy (http://www.numpy.org/)


Getting Started
---------------
1. Install the Numpy module as normal, if not already installed. The specifics
    vary by platform.
2. Download the python-ebml library and place it the same directory as this
    script (or elsewhere in your PYTHONPATH).
3. Copy the files `mide.py` and `mide.xml` to the library's schema directory
    (`ebml/schema/`). The directory should already contain `matroska.py` and
    `matroska.xml`.


Disclaimer
----------
THIS CODE IS PROVIDED ONLY AS AN EXAMPLE. USE AT YOUR OWN RISK. MIDE TECHNOLOGY
CORPORATION DISCLAIMS ANY AND ALL WARRANTIES, EXPRESSED OR IMPLIED.

Created on Jan 16, 2015
@author: dstokes
'''
import sys
if sys.version_info.major != 2 and sys.version_info.minor != 7:
    raise RuntimeError("This demo requires Python 2.7!")

from collections import Counter, Sequence
import csv
from datetime import datetime
import os.path
import struct

try:
    import ebml.schema.base
    from ebml.schema.mide import MideDocument
    import numpy as np
except ImportError as err:
    msg = "%s - see the file's docstring for setup info!" % err.message
    raise ImportError(msg)

#===============================================================================
# Low-level EBML parsing and utility functions, not specific to IDE data
#===============================================================================

def iter_roots(document):
    """ Iterate over an EBML stream's elements. Note that this does some
        low-level manipulation of the python-ebml library, so any major change
        in that library may cause this to break.
    """
    stream = document.stream
    children = document.children
    size = stream.size
    while size:
        element_offset = stream.size - size
        stream.seek(element_offset)
        element_id, element_id_size = ebml.schema.base.read_element_id(stream)
        element_size, element_size_size = ebml.schema.base.read_element_size(stream)
        element_stream_size = element_id_size + element_size_size + element_size
        element_stream = stream.substream(element_offset, element_stream_size)
        size -= element_stream_size

        element_class = None
        for child in (children + document.globals):
            if child.id == element_id:
                element_class = child
                break

        if element_class is None:
            element = ebml.schema.base.UnknownElement(document, element_stream, element_id)
        else:
            element = element_class(document, element_stream)

        yield(element)


def parse_ebml(elements):
    """ Reads a sequence of EBML elements and builds a (nested) dictionary,
        keyed by element name. Elements marked as "multiple" in the schema
        will produce a list containing one item for each element of that type.
    """
    result = {}
    if not isinstance(elements, Sequence):
        elements = [elements]
    for el in elements:
        if isinstance(el.value, list) or el.children:
            value = parse_ebml(el.value)
        else:
            value = el.value
        if el.multiple:
            result.setdefault(el.name, list()).append(value)
        else:
            result[el.name] = value
    return result


def dump_ebml(el, indent=0, tabsize=4, index=None):
    """ Recursively crawl an EBML 'container' element and dump its contents,
        showing the name and value of each child element. Nicer than `pprint`.
    """
    if el.name == "Void":
        # 'Void' elements are used for padding, so structures can have
        # consistent sizes, even though EBML compresses values.
        return el

    if indent == 0:
        # Parent element
        print ("\nRead element %s:" % el.name),
    else:
        # Child element
        print ("%s%-28s" % (" "*indent, el.name+":")),

    # 'children' in this case is a list of possible sub-element classes that
    # could be sub-elements of an element, not actual instances of things.
    if not el.children:
        # No 'children' means element is not a container. Just print value.
        print el.value
    else:
        print
        for child in el.value:
            dump_ebml(child, indent=indent+tabsize, tabsize=tabsize)

    if indent == 0:
        print
    return el


#===============================================================================
#
#===============================================================================

def format2dtype(s):
    """ Convert a `struct`-style formatting string to a Numpy `dtype`.
    """
    types = []
    # Get native endian code
    endianCode = '<' if sys.byteorder == 'little' else '>'
    # Replace any endian codes with either big or little indicator.
    # Python structs do not allow multiple indicators, but the .IDE spec does.
    s.replace('!','>').replace('@', endianCode).replace('=', endianCode)
    idx = 0
    for c in s:
        if c in '<>':
            endianCode = c
        else:
            types.append((str(idx), '%s%s' % (endianCode, c)))
            idx += 1
    return np.dtype(types)


#===============================================================================
#
#===============================================================================

class Subchannel(object):
    """ Class representing one axis of data.
    """

    def __init__(self, parent, data):
        """
        """
        self.parent = parent
        self.id = data.get('SubChannelID', len(parent.subchannels))
        self.name = data.get('SubChannelName',
                             'Subchannel_%d.%02d' % (self.parent.id, self.id))
        self.label = data.get('SubChannelLabel', self.name)
        self.units = data.get('SubChannelUnits', None)
        self.calId = data.get('SubChannelCalibrationIDRef', None)


class Channel(object):
    """
    """

    def __init__(self, dataset, data):
        """
        """
        self.dataset = dataset
        self.id = data.get('ChannelID')
        self.name = data.get('ChannelName', 'Channel_%d' % self.id)
        self.calId = data.get('ChannelCalibrationIDRef', None)

        # A Channel contains one or more Subchannels. Subchannel IDs are
        # always contiguous, so they are stored in a list rather than a dict
        # (as Channels are in the parent Dataset).
        self.subchannels = []

        # TimeCodeScale is stored as a string in order to simplify the handling
        # of floating point values on the Slam Stick.
        self.timeScale = eval(data.get('TimeCodeScale', '1.0/32768'))

        # The timestamps in each DataBlock are 24 bit, and any lengthy
        # recording will cause the timer to roll over. By knowing the maximum
        # time, we can correct for this.
        self.timeMod = data.get('TimeCodeModulus', 24**2)
        self.modulus = 0


    def parseDataBlock(self, block):
        """
        """


class Dataset(object):
    """ Class representing an IDE file.
    """

    def __init__(self, data):
        """
        """
        self.channels = {}
        self.calibration = {}


#===============================================================================
# Data payload parsers
#===============================================================================

def parseAccelData(data, startTime, endTime, scalar=1):
    """ Parse accelerometer data from a `ChannelDataBlock` payload. The raw
        data consists of sets of 3 uint16 values, ordered Z, Y, X.

        @param data: The payload's binary data (string or bytearray)
        @param startTime: The block's start time
        @param endTime: The block's end time
        @keyword scalar: A scalar value for the data, i.e. the accelerometer's
            maximum g-level.
        @return: A 2D array of times and accelerometer values. Note that the
            data is in the order Z,Y,X!
    """
    # On a Slam Stick X, a full buffer of accelerometer data is 1360*3 uint16
    # values. A truncated buffer may be written at the end of the recording,
    # but the end time recorded will be for the entire buffer, not just the
    # portion that was written.
    numSamples = 1360
    # Parse the values and create a 1360x3 2D array, padding if needed.
    d = np.frombuffer(data, np.uint16)
    d = np.hstack((d, np.zeros(3*numSamples - d.shape[0]))).reshape((-1,3))
    # Normalize the values. Multiply by accelerometer max.
    d = ((d.astype(float) - 32767.0) / 32767.0) * scalar
    # Generate the timestamps for each subsample
    t = np.linspace(startTime, endTime, numSamples).reshape((-1,1))
    # Append the time to the start of each 'row'
    return np.hstack((t, d))


def parsePressureTempData(data, startTime, endTime, scalar=1):
    """ Parse temperature/pressure data from a `ChannelDataBlock` payload. The
        data is in the native format generated by the MPL3115 Pressure/
        Temperature sensor, 5 bytes in total:

            Pressure (3 bytes):
                Bits [23..6] whole-number value (signed)
                Bits [5..4] fractional value (unsigned)
                Bits [3..0] (ignored)
            Temperature (2 bytes):
                Bits [15..8] whole-number value (signed)
                Bits [7..4] fractional value (unsigned)
                Bits [3..0] (ignored)

        @param data: The payload's binary data (string or bytearray)
        @param startTime: The block's start time
        @param endTime: The block's end time
        @keyword scalar: A scalar value for the data. Unused by this function.
        @return: A one-row 2D array of the time, pressure (Pa) and temperature
            (degrees C).
    """
    rawpressure = struct.unpack_from(">i", data)[0] >> 14
    fracpressure, rawtemp, fractemp = struct.unpack_from(">xxBbB", data)
    fracpressure = ((fracpressure >> 4) & 0b11) * 0.25
    fractemp = (fractemp >> 4) * 0.0625

    return [(startTime, rawpressure + fracpressure, rawtemp + fractemp)]


#===============================================================================
# Complex data handlers
#===============================================================================

class ChannelDataBlockHandler(object):
    """ A rudimentary handler for `ChannelDataBlock` elements, which calls the
        appropriate parser and data handler for the payload based on the
        element's channel ID. Because some state need to be maintained (e.g.
        the timestamp modulus correction), this is a class rather than a simple
        function. This class is function-like, however, in that you can use an
        instance like a function, making it congruous with the other element
        handling functions.
    """
    # Timestamps are uint16 values, and can be expected 'roll over' in a file.
    maxTimestamp = 2**16
    # Scalar to convert from timestamp units (clock ticks) to microseconds
    timeScalar = 1000000.0 / 2**15

    def __init__(self, channelHandlers):
        # Handlers: the output generators. In this case, CSV writers.
        self.handlers = channelHandlers

        # Parsers, in a dictionary keyed by channel ID. On a Slam Stick X,
        # Channel 0 is the accelerometer, Channel 1 is the combined pressure/
        # temperature sensor. Some early versions of the SSX firmware may
        # generate data in other Channels, but they are for diagnostic purposes
        # and can be ignored.
        self.parsers = {8: parseAccelData,
                        36: parsePressureTempData}

        # Variables for correcting the modulus
        self.timestampOffset = 0
        self.lastStamp = 0

        # Scalar for the accelerometer. Accelerometer raw data is always
        # 0 to 65535, relative to the accelerometer's minimum and maximum
        # values (i.e. -100 to 100 on a 100 g accelerometer). This gets set
        # between this class being instantiated and when it is first used,
        # based on the recorder info read from the file.
        self.accelScalar = 100


    def fixOverflow(self, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        # Timestamps within an element are stored as uint16 counts of clock
        # ticks (32768/second). Correct for the modulus roll-over (if any)
        # and convert to microseconds.
        timestamp += self.timestampOffset
        if timestamp < self.lastStamp:
            timestamp += self.maxTimestamp
            self.timestampOffset += self.maxTimestamp
        self.lastStamp = timestamp
        return timestamp * self.timeScalar


    def __call__(self, element):
        """ Process a ChannelDataBlock element. Use an instance of this class
            like a function.
        """
        # Sanity check: make sure this is actually a ChannelDataBlock
        assert element.name == "ChannelDataBlock"

        # Create a dictionary from the element's children. This is probably
        # overkill, since the subelements within a ChannelDataBlock written by
        # a Slam Stick X are consistent, so they could be accessed by index.
        data = parse_ebml(element.value)

        # Only process this element if it has a known Channel ID. Depending on
        # the firmware version, an IDE may contain diagnostic channels, but
        # these can be safely ignored.
        channelId = data['ChannelIDRef']
        if channelId not in self.parsers:
            return
        # Timestamps within an element are stored as uint16 counts of clock
        # ticks (32768/second). Fix the modulus and convert to microseconds.
        start = self.fixOverflow(data['StartTimeCodeAbsMod'])
        end = self.fixOverflow(data['EndTimeCodeAbsMod'])

        # Parse the payload data and send it through the handler for this
        # element's channel ID.
        payload = data['ChannelDataPayload']
        data = self.parsers[channelId](payload, start, end, self.accelScalar)
        self.handlers[channelId](data)


    def close(self):
        for handler in self.handlers.values():
            handler.close()

#===============================================================================
# Simpler element-handling functions
#===============================================================================

def handleRecordingProperties(el):
    """ Called when a `RecordingProperties` element is read.
    """
    # The contents are fairly straight-forward and human-readable after being
    # read from the EBML.
    return dump_ebml(el)


def handleCalibration(el):
    """ Called when a `CalibrationList` element is read.
    """
    return dump_ebml(el)


def handleTimeBase(el):
    """ Called when a `TimeBaseUTC` element is read.
    """
    # The date/time is stored as a standard *NIX 'epoch' time: seconds since
    # midnight, January 1, 1970 UTC.
    print "Read element %s: %d (%s UTC)\n" % (el.name, el.value,
                                            datetime.utcfromtimestamp(el.value))
    return el


def handleElementTag(el):
    """ Called when an `ElementTag` element is read.
        Not currently in use.
    """
    # ElementTags form a sort of meta-parent around the otherwise flat data
    # in an IDE file. It doesn't encode the size like a real EBML parent, so
    # the file can be closed abnormally (e.g. the battery dies) without damage.
    # The tag is not currently in use. Ignore it.
    return el


def handleSync(el):
    """ Called when a 'Sync' element is read.
    """
    # Sync tags occur periodically, intended for future use in streamed data or
    # in repairing a damaged file. They can be ignored.
    return el

#===============================================================================
# Output.
#===============================================================================

class Writer(object):
    """ Simple wrapper for CSV output.
    """
    def __init__(self, filename):
        self.numRows = 0
        self.stream = open(filename, 'wb')
        self.writer = csv.writer(self.stream)

    def close(self):
        self.stream.close()

    def __call__(self, rows):
        self.writer.writerows(rows)
        self.numRows += len(rows)


#===============================================================================
#
#===============================================================================

def getRecorderRange(typeId):
    """ Get the recorder's accelerometer range based on its type ID.
    """
    return { 0x10:  25.0,
             0x12: 100.0,
             0x13: 200.0,
             0x14: 500.0 }.get(typeId & 0xff, 100)


def parseIdeFile(filename, savePath=None, updateInterval=25):
    """ Open an IDE file and iterate over its contents, writing recorded data
        to a pair of CSV files, one for each sensor channel (accelerometer and
        pressure/temperature).
    """
    # Generate the filenames of the output CSVs
    if not savePath:
        savePath = os.path.dirname(filename)
    rootname = os.path.splitext(os.path.basename(filename))[0]
    accelFile = os.path.join(savePath, "%s_ch0_accel.csv" % rootname)
    pressTempFile = os.path.join(savePath, "%s_ch1_press_temp.csv" % rootname)

    # Create the handler for ChannelDataBlock elements, providing a dictionary
    # of output-writing functions (or, in this case, function-like objects)
    # keyed by Channel ID. As previously noted, a Slam Stick X writes two
    # channels, corresponding to its two sensors: Channel 0, the accelerometer;
    # and Channel 1, the combined pressure/temperature
    dataBlockHandler = ChannelDataBlockHandler({8: Writer(accelFile),
                                                36: Writer(pressTempFile)})

    # Handlers: functions (or function-like objects) that take an element as
    # an argument. In a dictionary keyed by element name for easy access.
    handlers = {
        "RecordingProperties": handleRecordingProperties,
        "CalibrationList": handleCalibration,
        "TimeBaseUTC": handleTimeBase,
        "ChannelDataBlock": dataBlockHandler,
        "Sync": handleSync,
        "ElementTag": handleElementTag,
    }

    # Keep track of the number of elements processed
    processed = Counter()

    with open(filename, 'rb') as f:
        doc = MideDocument(f)
        for n, el in enumerate(iter_roots(doc)):
            print n,el.name
            if el.name in handlers:

                # Each handler is a function (or function-like object) that
                # takes an element as an argument, so they all get called the
                # same way:
                handlers[el.name](el)

                # Special case: get the accelerometer max based on the
                # recorder's type ID. This is a special case because it has to
                # modify something outside of the handler's scope.
                if el.name == "RecordingProperties":
                    try:
                        info = parse_ebml(el.value)['RecorderInfo']
                        recType = info['RecorderTypeUID']
                        dataBlockHandler.accelScalar = getRecorderRange(recType)
                    except KeyError:
                        pass

            # Updater, to provide a visualization of progress.
            if updateInterval > 0 and n % updateInterval == 0:
                msg = ('Read %s elements...      ' % n)
                # Write the message with a bunch of backspaces, so each update
                # will overwrite the previous one.
                sys.stdout.write('%s%s' % (msg, '\x08'*len(msg)))
                sys.stdout.flush()

            processed[el.name] += 1

    dataBlockHandler.close()
    return processed

#===============================================================================
#
#===============================================================================
if __name__ == "__main__":
    import argparse

    argparser = argparse.ArgumentParser(description= \
        "MIDE IDE Parser Example. Writes separate CSV files for the "
        "accelerometer and pressure/temperature channels.")
    argparser.add_argument('-o', '--output', help= \
       "The path to which to save the .CSV files. Defaults to the same path as "
       "the source file.")
    argparser.add_argument('source', help="The source .IDE file to convert.")

    args = argparser.parse_args()
    source = args.source
    savePath = args.output if args.output else os.path.dirname(source)

    print "=" * 78
    print "Reading %s..." % source
    print "-" * 78
    results = parseIdeFile(source, savePath)


    print "-" * 78
    print "Completed parsing %s." % source
    print
    print "The file contained these elements:"
    for n,c in sorted(results.items(), key=lambda x: x[0]):
        print "%10d %s" % (c,n)
    print "=" * 78
