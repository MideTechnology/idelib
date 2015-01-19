'''
========================
Example MIDE File Reader
========================

THIS CODE IS PROVIDED ONLY AS AN EXAMPLE. USE AT YOUR OWN RISK. 

This script will parse data from an IDE file recorded by a Slam Stick X. Some
modification will be required to parse data from another source.

Requirements
------------
python-ebml (https://github.com/jspiros/python-ebml)
Numpy


Getting Started
---------------
1. Install the Numpy module as normal, if not already installed.
2. Download the python-ebml library and place it the same directory as this
    script (or elsewhere in your PYTHONPATH). 
3. Copy the files `mide.py` and `mide.xml` to the library's schema directory
    (`ebml/schema/`). The directory should already contain `matroska.py` and
    `matroska.xml`.



Created on Jan 16, 2015

@author: dstokes
'''

from collections import Counter, OrderedDict, Sequence
import csv
from datetime import datetime
import os.path
import pprint
import struct
import sys

try:
    import ebml.schema.base
    from ebml.schema.mide import MideDocument
    import numpy as np
except ImportError as err:
    msg = "%s - see the file's docstring for setup info!" % err.message
    raise ImportError(msg)

#===============================================================================
# Low-level EBML parsing functions
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


def parse_ebml(elements, ordered=True):
    """ Reads a sequence of EBML elements and builds a (nested) dictionary,
        keyed by element name. Elements marked as "multiple" in the schema
        will produce a list containing one item for each element.
    """
    result = OrderedDict() if ordered else dict()
    if not isinstance(elements, Sequence):
        elements = [elements]
    for el in elements:
        if isinstance(el.value, list) or el.children:
            value = parse_ebml(el.value, ordered=ordered)
        else:
            value = el.value
        if el.multiple:
            result.setdefault(el.name, list()).append(value)
        else:
            result[el.name] = value
    return result
            

def dump_ebml(el, stream=None, indent=0, tabsize=4):
    """ Testing: Crawl an EBML Document and dump its contents, showing the 
        stream offset, name, and value of each child element. 
    """
    if el.name == "Void":
        return
    
    if stream is None:
        stream = sys.stdout
    
    if indent == 0:
        stream.write("\nRead element %s: " % el.name)
    else:
        stream.write("%s%-28s" % (" "*indent, el.name+": "))
    if not el.children:
        stream.write("%r\n" % el.value)
    else:
        stream.write("\n")
        for child in el.value:
            dump_ebml(child, stream, indent+tabsize, tabsize) 
    if indent == 0:
        stream.write("\n")
    stream.flush()

  

#===============================================================================
# Data payload parsers
#===============================================================================

def parseAccelData(data, startTime, endTime):
    """ Parse accelerometer data from a `ChannelDataBlock` payload. The raw
        data consists of sets of 3 uint16 values, ordered Z, Y, X.
    
        @param data: The payload's binary data (string or bytearray)
        @param startTime: The block's start time
        @param endTime: The block's end time
        @return: A 2D array of times and normalized accelerometer values.
            Multiply by accelerometer max to get actual 'g' values.
            Note that the data is in the order Z,Y,X!
    """
    # A full buffer of accelerometer data is always 1360*3 values. A truncated
    # buffer may occur at the end of the recording, but the timing is the same.
    numSamples = 1360
    # Parse the values and create a 1360x3 2D array, padding if needed.
    d = np.frombuffer(data, np.uint16)
    d = np.hstack((d, np.zeros(3*numSamples - d.shape[0]))).reshape((-1,3))
    # Normalize the values. Multiply by accelerometer max later.
    d = (d.astype(float) - 32767.0) / 32767.0
    # Generate the timestamps for each subsample
    t = np.linspace(startTime, endTime, numSamples).reshape((-1,1))
    # Append the time to the start of each 'row'
    return np.hstack((t, d))


def parsePressureTempData(data, startTime, endTime):
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
        @return: A one-row 2D array of the time, pressure (Pa) and temperature
            (degrees C).
    """
    rawpressure = struct.unpack_from(">i", data)[0] >> 14
    fracpressure, rawtemp, fractemp = struct.unpack_from(">xxBbB", data)
    fracpressure = ((fracpressure >> 4) & 0b11) * 0.25
    fractemp = (fractemp >> 4) * 0.0625

    return [(startTime, rawpressure + fracpressure, rawtemp + fractemp)]
    
#===============================================================================
# 
#===============================================================================

class ChannelDataBlockHandler(object):
    """ A simple handler for `ChannelDataBlock` elements, which calls the
        appropriate parser and handler for the payload based on element's 
        channel ID.
    """
    maxTimestamp = 2**16
    timeScalar = 1000000.0 / 2**15

    def __init__(self, channelHandlers):
        self.handlers = channelHandlers
        self.parsers = {0: parseAccelData,
                        1: parsePressureTempData}
        self.firstTime = None
        self.lastTime = 0
        self.timestampOffset = 0
        self.lastStamp = 0
    

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
        """
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
        data = self.parsers[channelId](payload, start, end)
        self.handlers[channelId](data)
        

    def close(self):
        for handler in self.handlers.values():
            handler.close()
            
#===============================================================================
# 
#===============================================================================

def handleCalibration(el):
    dump_ebml(el)

def handleTimeBase(el):
    print "Read element %s: %d (%s UTC)" % (el.name, el.value, 
                                            datetime.utcfromtimestamp(el.value))    

#===============================================================================
# 
#===============================================================================

class Writer(object):
    def __init__(self, filename):
        self.numRows = 0
        self.stream = open(filename, 'wb')
        self.writer = csv.writer(self.stream)
    
    def close(self):
        self.stream.close()
    
    def __call__(self, rows):
        self.writer.writerows(rows)
        self.numRows += len(rows)


def printElement(el):
    if el.children:
        print "Read element %s:" % el.name
        pprint.pprint(parse_ebml(el.value, ordered=False))
    else:
        print "Read element %s = %r" % (el.name, el.value)


#===============================================================================
# 
#===============================================================================


def parseIdeFile(filename, savePath=None, updateInterval=25):
    """
    """
    if not savePath:
        savePath = os.path.dirname(filename)
    rootname = os.path.splitext(os.path.basename(filename))[0]
    
    accelFile = os.path.join(savePath, "%s_ch0_accel.csv" % rootname)
    pressTempFile = os.path.join(savePath, "%s_ch1_press_temp.csv" % rootname)
    dataBlockHandler = ChannelDataBlockHandler({0: Writer(accelFile),
                                                1: Writer(pressTempFile)})
    handlers = {
        "ChannelDataBlock": dataBlockHandler,
        "CalibrationList": handleCalibration, #CalibrationHandler(),
        "TimeBaseUTC": handleTimeBase,
        # Un-comment these lines to see additional data. Warning: Sync and Void 
        #    may occur extremely often!
#         "Sync": pprint.pprint,
#         "Void": pprint.pprint,
#         "ElementTag": pprint.pprint,
    }
    
    processed = Counter()
    with open(filename, 'rb') as f:
        doc = MideDocument(f)
        for n, el in enumerate(iter_roots(doc)):
            processed[el.name] += 1
            if el.name in handlers:
                handlers[el.name](el)
            
            # Updater, to provide a visualization of progress
            if updateInterval > 0 and n % updateInterval == 0:
                msg = ('Read %s elements...      ' % n)
                sys.stdout.write('%s%s' % (msg, '\x08'*len(msg)))
                sys.stdout.flush()
            
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
    