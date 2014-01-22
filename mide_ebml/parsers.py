'''
This file contains three types of things: special-case data parsers, handlers
for specific EBML elements, and wrapper classes for EBML data-containing
elements.

Special-case data-parsing objects are for parsing element data needing 
more post-processing than simply grabbing values with a `struct.Struct`, 
such as a sensor that produces data in a non-power-of-two length (e.g. 
24 bits). Special-case parsers must (to a limited degree) quack like 
`struct.Struct` objects; they must provide `size` and `format` attributes 
(the latter should be `None`), and they must implement the method
`unpack_from()`.

Element handlers are called by the importer as it iterates through the 'root'
elements of an EBML file. Generally, handlers are instantiated only once.
Handlers of data-containing elements (e.g. `ChannelDataBlock` and
`SimpleChannelDataBlock`) operate as factories, manufacturing instances of
their respective wrapper objects. All handlers have an `elementName`
attribute containing the name of the EBML element on which they work.
Data-producing handlers also have a `product` attribute, which is a
reference to the class of the object they manufacture. It is up to the
handler to handle any children of their respective elements.

Data elements wrap EBML elements and abstract the details of getting
at their data. A sensor that outputs the same data in both normal 
`ChannelDataBlock` and `SimpleChannelDataBlock` elements are
represented the same way in the API.

See the `dataset` module for more information.

Created on Sep 26, 2013
@author: dstokes
'''

import struct
import sys
import types


#===============================================================================
# 
#===============================================================================

# The minimum and maximum values for values parsed out of data blocks.
# Used to provide an initial range, which is later corrected for actual
# values.
RANGES = {'c': None,
          'b': (-127,126),
          'B': (0,255),
          '?': (0,1),
          'h': (-(2**(8*2))/2, (2**(8*2))/2-1),
          'H': (0, 2**(8*2)-1),
          'i': (-(2**(8*4))/2, (2**(8*4))/2-1),
          'I': (0, 2**(8*4)-1),
          'l': (-(2**(8*4))/2, (2**(8*4))/2-1),
          'L': (0, 2**(8*4)-1),
          'q': (-(2**(8*8))/2, (2**(8*8))/2-1),
          'Q': (0, 2**(8*8)-1),
          'f': (-1.0, 1.0),
          'd': (-1.0, 1.0),
          'p': None,
          'P': None,
          's': None
}


def getParserTypes(parser):
    """ Get the Python types produced by a parser. 
    """
    if hasattr(parser, "types"):
        return parser.types
    return tuple([type(x) for x in parser.unpack_from(chr(255)*parser.size)])


def getParserRanges(parser):
    """ Get the theoretical minimum and maximum values that can be returned
        for each value parsed out of sensor data. Note that floating point
        values are typically reported as (-1.0,1.0).
        
        @param parser: A `struct.Struct`-like parser.
        @return: A collection of (min, max) tuples. Non-numeric values will
            have a reported range of `None`.
    """
    if hasattr(parser, "ranges"):
        return parser.ranges
    ranges = []
    for c in parser.format:
        if c in RANGES:
            ranges.append(RANGES[c])
    return tuple(ranges)
    

#===============================================================================
# 
#===============================================================================

def getElementHandlers(module=None, subElements=False):
    """ Retrieve all EBML element handlers from a module. Handlers are
        identified by being subclasses of `ElementHandler`.
    
        @keyword module: The module from which to get the handlers. Defaults to
            the current module (ie. `parsers`).
        @keyword subElements: `True` if the set of handlers should also
            include non-root elements (e.g. the sub-elements of a
            RecordingProperties or ChannelDataBlock).
        @return: A list of element handler classes.
    """
    elementParserTypes = []
    if module is None:
        if __name__ in sys.modules:
            moduleDict = sys.modules[__name__].__dict__
        else:
            moduleDict = globals()
    else:
        moduleDict = module.__dict__
    for p in moduleDict.itervalues():
        if not isinstance(p, types.TypeType) or p == ElementHandler:
            continue
        if issubclass(p, ElementHandler):
            if subElements or not p.isSubElement:
#                 print "Installing handler for", p.elementName
                elementParserTypes.append(p)
    return elementParserTypes

#===============================================================================
# EXCEPTIONS
#===============================================================================

class ParsingError(IOError):
    """ Exception raised for any failure to parse a WVR EBML file. """
    pass


#===============================================================================
# SENSOR DATA PARSING
#===============================================================================

class MPL3115PressureTempParser(object):
    """ A special-case channel parser for the native raw data generated by 
        the MPL3115 Pressure/Temperature sensor. See module docs for more
        information on custom parsers.

        Data format is 5 bytes in total:
            Pressure (3 bytes): 
                Bits [23..6] whole-number value (signed)
                Bits [5..4] fractional value (unsigned)
                Bits [3..0] (ignored)
            Temperature (2 bytes): 
                Bits [15..8] whole-number value (signed)
                Bits [7..4] fractional value (unsigned)
                Bits [3..0] (ignored)
        
        @todo: Make sure fraction part is correct for negative whole values.
    """

    # Custom parsers need to provide a subset of a struct.Struct's methods
    # and attributes: 
    size = 5
    format = None

    # The absolute min and max values. Normal struct.Struct objects get this
    # computed from their formatting string.
    ranges = ((-(2**18)/2.0, (2**18)/2.0-1),
              (-(2**16)/2.0, (2**16)/2.0-1))
    
    # This is weirdly formed data. Using two parsers over the same data is
    # cheaper than using one plus extra bit manipulation.
    _pressureParser = struct.Struct(">i")
    _parser = struct.Struct(">xxBbB")
        
    def unpack_from(self, data, offset=0):
        """ Special-case parsing of a temperature data block.
        """
        # TODO: Make sure if fractional part is calculated correctly for negative values
        rawpressure = self._pressureParser.unpack_from(data, offset)[0] >> 13
        fracpressure, rawtemp, fractemp = self._parser.unpack_from(data, offset)
        fracpressure = ((fracpressure >> 3) & 0b11) * 0.25
        fractemp = (fractemp >> 3) * 0.0625

        return (rawpressure + fracpressure, rawtemp + fractemp)



class AccelerometerParser(object):
    """ Parser for the accelerometer data. Accelerometer values are recorded
        as uint16 but represent values -100 to 100 G. This parser performs
        the conversion on the fly.
        
        If using this parser, do not perform this adjustment at the Channel 
        or Subchannel level!
    """

    def __init__(self, inMin=0, inMax=65535, outMin=-100.0, outMax=100.0, 
                 formatting="<HHH"):
        self.parser = struct.Struct(formatting)
        self.format = self.parser.format
        self.size = self.parser.size
        self.ranges = ((outMin, outMax),) * 3
        
        self.adjustment = lambda v: (v - inMin + 0.0) * (outMax - outMin) / (inMax - inMin) + outMin

    def unpack_from(self, data, offset=0):
        return tuple(map(self.adjustment, self.parser.unpack_from(data, offset)))
    

#===============================================================================
# 
#===============================================================================

class ElementHandler(object):
    """ Base class for all element handlers (i.e. parsers).
    """
    product = None
    elementName = None
    isSubElement = False
    
    def __init__(self, doc, **kwargs):
        self.doc = doc
        
    def __call__(self, element):
#         print "Handling %s" % self.elementName
        pass

    def makesData(self):
        """ Does this handler produce sample data?
        """
        return self.product is not None and \
            issubclass(self.product, BaseDataBlock)


class BaseDataBlock(object):
    """ Base class for all data-containing elements. Created by the
        appropriate ElementHandler for the given EBML element type.
        
        @cvar headerSize: The size of the header information stored in the
            element's payload, if any.
        @cvar maxTimestamp: The 
    """
    headerSize = 0
    maxTimestamp = 2**16
    timeScalar = 1000000.0 / 2**15
    
    def __init__(self, element):
        self.element = element
        
        # This stuff will vary based on parser:
        self.blockIndex = -1
        self.startTime = None
        self.endTime = None
        self.numSamples = None
        self.sampleRate = None
        self.sampleTime = None
        self.indexRange = None
        self._len = None
        self.body_size = None
        self.minValue = self.maxValue = None

    def parseWith(self, parser, start=0, end=-1, subchannel=None, step=1):
        """ Parse an element's payload. Use this instead of directly using
            `parser.parse()` for consistency's sake.
            
            @param parser: The DataParser to use
            @param start: First subsample index to parse 
            @param end: Last subsample index to parse
        """
        # SimpleChannelDataBlock payloads contain header info; skip it.
        data = self.payload.value
        start = self.headerSize + (start*parser.size)
        end = self.payload.body_size + end if end < 0 else self.headerSize + (end*parser.size)
        for i in xrange(start,end,parser.size*step):
            if subchannel is not None:
                yield parser.unpack_from(data, i)[subchannel]
            else:
                yield parser.unpack_from(data, i)


    def parseByIndexWith(self, parser, indices, subchannel=None):
        """ Parse an element's payload and get a specific set of samples.
            
            @param parser: The DataParser to use
            @param indices: A list of indices into the block's data. 
            @keyword subchannel: The subchannel to get, if specified.
        """
        # SimpleChannelDataBlock payloads contain header info; skip it.
        data = self.payload.value
        for i in indices:
            if i >= self.numSamples:
                continue
            idx = self.headerSize + (i*parser.size)
            if subchannel is not None:
                yield parser.unpack_from(data, idx)[subchannel]
            else:
                yield parser.unpack_from(data, idx)


    def getNumSamples(self, parser):
        """ Compute the number of subsamples in an element's payload, as
            parsed by the given data parser.
        """
        if self.numSamples is not None:
            return self.numSamples
        n = self.payload.body_size - self.headerSize
        self.numSamples = n / parser.size
        return self.numSamples


    def isValidLength(self, parser):
        """ Check if an element's payload data is evenly divisible by into
            a set of channels.
        
            @param n: The size of the data in bytes.
            @return: `True` if the number of bytes can be evenly
                distributed into subsamples.
        """
        return self.body_size > 0 and self.body_size % parser.size == 0


#===============================================================================
# 
#===============================================================================

class SimpleChannelDataBlock(BaseDataBlock):
    """ Wrapper for SimpleChannelDataBlock elements, which consist of only a
        binary payload of raw data prefixed with a 16b timestamp and an 8b
        channel ID. Also keeps track of some metadata used by its Channel.
    """
    headerParser = struct.Struct(">HB")
    headerSize = headerParser.size

    def __init__(self, element):
        super(SimpleChannelDataBlock, self).__init__(element)
        self.element = element
        self.payload = element
        self.startTime, self.channel = self.getHeader()
        self.body_size = element.body_size - self.headerSize
   
    
    def __len__(self):
        """ x.__len__() <==> len(x)
            This returns the length of the payload.
        """
        if self._len is None:
            self._len = len(self.payload.value) - self.headerSize
        return self._len
    
    
    def getHeader(self):
        """ Extract the block's header info. In SimpleChannelDataBlocks,
            this is part of the payload.
        """
        return self.headerParser.unpack_from(self.element.value)
    

    @property
    def timestamp(self):
        return self.getHeader()[0]


class SimpleChannelDataBlockParser(ElementHandler):
    """ 'Factory' for SimpleChannelDataBlock elements. Instantiated once
        per session (or maybe channel, depending). It handles the modulus
        correction of the block's short timestamps.
        
        @cvar elementName: The name of the element handled by this parser
        @cvar product: The class of object generated by the parser
    """
    product = SimpleChannelDataBlock
    elementName = product.__name__
   
    def __init__(self, doc, **kwargs):
        super(SimpleChannelDataBlockParser, self).__init__(doc, **kwargs)
        
        self.timestampOffset = 0
        self.stampRollover = 0
        self.lastStamp = 0
        
    def fixOverflow(self, block, timestamp):
        timestamp += self.timestampOffset
        # NOTE: This might need to just be '<' (for discontinuities)
        if timestamp <= self.lastStamp:
            timestamp += block.maxTimestamp
            self.timestampOffset += block.maxTimestamp
        self.lastStamp = timestamp
        return timestamp
    
   
    def __call__(self, element, sessionId=None):
        """
        """
        sessionId = self.doc.lastSession.sessionId if sessionId is None else sessionId
        block = self.product(element)
        timestamp, channel = block.getHeader()
        
        block.startTime = int(self.fixOverflow(block, timestamp) * block.timeScalar)
        if block.endTime is not None:
            block.endTime = int(self.fixOverflow(block, block.endTime) * block.timeScalar)
            
        self.doc.channels[channel].getSession(sessionId).append(block)
        
        return block.getNumSamples(self.doc.channels[0].parser)


#===============================================================================
# ChannelDataBlock: Element wrapper and handler
#===============================================================================

class ChannelDataBlock(BaseDataBlock):
    """
    """
    maxTimestamp = 2**24 #2**32

    def __init__(self, element):
        super(ChannelDataBlock, self).__init__(element)
        self._payloadIdx = None
        
        self.element = element
        for num, el in enumerate(element.value):
            if el.name == "ChannelIDRef":
                self.channel = el.value
            elif el.name == "StartTimeCodeAbsMod":
                self.startTime = el.value
                # TODO: Correct start time for modulus
                self._timestamp = el.value
            elif el.name == "EndTimeCodeAbsMod":
                self.endTime = el.value
            elif el.name == "ChannelFlags":
                self.flags = el.value
            elif el.name == "ChannelDataPayload":
                self._payloadIdx = num
                self.body_size = el.body_size
            # Add other child element handlers here.
                      
    
    @property
    def payload(self):
        # 'value' is actually a property that does the file seek, so it (and
        # not a reference to a child element) has to be used every time.
        return self.element.value[self._payloadIdx]
    
    
    def getHeader(self):
        """ Extract the block's header info.
        """
        return self._timestamp, self.channel


    
class ChannelDataBlockParser(SimpleChannelDataBlockParser):
    """ 'Factory' for ChannelDataBlock elements. Instantiated once per 
        session (or maybe channel, depending). It handles the modulus
        correction of the block's timestamps.
        
        @cvar elementName: The name of the element parsed by this parser
        @cvar product: The class of object generated by the parser
    """
    product = ChannelDataBlock
    elementName = product.__name__
   
    def __init__(self, doc, **kwargs):
        super(ChannelDataBlockParser, self).__init__(doc, **kwargs)
        
        self.timestampOffset = 0
        self.stampRollover = 0
        self.lastStamp = 0

#===============================================================================
# 
#===============================================================================

class ElementTagParser(ElementHandler):
    """ Dummy handler of ElementBlock elements. 
        @cvar elementName: The name of the element handled by this parser
    """
    elementName = "ElementTag"


#===============================================================================
# 
#===============================================================================

class SessionParser(ElementHandler):
    """ Stub for Session element handler.
        @cvar elementName: The name of the element handled by this parser
    """
    elementName = "Session"


#===============================================================================
# 
#===============================================================================

class TimeBaseUTCParser(ElementHandler):
    """ Stub for Session element handler
        @todo: Implement TimeBaseUTCParser
    """
    elementName = "TimeBaseUTC"
    

#===============================================================================
# 
#===============================================================================

class SyncParser(ElementHandler):
    """ Stub for Session element handler.
    
        @cvar elementName: The name of the element handled by this parser
    """
    elementName = "Sync"
    
    def __call__(self, *args, **kwargs):
        # Override the default to suppress console spam: these are many.
        pass
    

#===============================================================================
# 
#===============================================================================


class RecordingPropertiesParser(ElementHandler):
    """ Stub for RecordingProperties element handler.
    
        @cvar elementName: The name of the element handled by this parser
        @todo: Implement RecordingPropertiesParser
    """
    elementName = "RecordingProperties"


class TimeCodeScaleParser(ElementHandler):
    """ Stub for TimeCodeScale element handler.
    
        @cvar elementName: The name of the element handled by this parser
    """
    elementName = "TimeCodeScale"
    isSubElement = True


class TimeCodeModulusParser(ElementHandler):
    """ Stub for TimeCodeModulus element handler.
    
        @cvar elementName: The name of the element handled by this parser
    """
    elementName="TimeCodeModulus"
    isSubElement = True


#===============================================================================
# 
#===============================================================================
