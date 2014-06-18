'''
This file contains three types of things: special-case data parsers, handlers
for specific EBML elements, and wrapper classes for EBML data-containing
elements.

Special-case data-parsing objects are for parsing element data needing more 
post-processing than simply grabbing values with a `struct.Struct`, such as a 
sensor that produces data in a non-power-of-two length (e.g. 24 bits). 
Special-case parsers must (to a limited degree) quack like `struct.Struct` 
objects; they must provide `size` and `format` attributes (the latter should be 
`None`), and they must implement the method `unpack_from()`. They may also 
include optional `types` and `ranges` attributes, which are used to 

Element handlers are called by the importer as it iterates through the 'root'
elements of an EBML file. Generally, handlers are instantiated only once, just
after the new `Dataset` has been created. Handlers of data-containing elements 
(e.g. `ChannelDataBlock` and `SimpleChannelDataBlock`) operate as factories, 
manufacturing instances of their respective wrapper objects. All handlers have 
an `elementName` attribute containing the name of the EBML element on which 
they work. A single handler class handles a single element type. Data-producing 
handlers also have a `product` attribute, which is a reference to the class of 
the object they manufacture. It is up to the handler to handle any children of 
their respective elements.

Data elements wrap EBML elements and abstract the details of getting at their 
data. A sensor that outputs the same data in both normal `ChannelDataBlock` 
and `SimpleChannelDataBlock` elements are represented the same way in the API.

See the `dataset` module for more information.

Created on Sep 26, 2013
@author: dstokes
'''

from collections import OrderedDict, Sequence
import struct
import sys
import types

import calibration
from util import parse_ebml

#===============================================================================
# 
#===============================================================================            
    
def renameKeys(d, renamed, exclude=True, recurse=True, ordered=False):
    """ Create a new dictionary from and old one, using different keys. Used
        primarily for converting EBML element names to function keyword
        arguments.
    
        @param d: The source dictionary
        @param renamed: A dictionary of new names keyed by old names
        @keyword exclude: If `True`, only keys appearing in `renamed` are
            copied to the new dictionary.
        @keyword recurse: If `True`, the renaming operates over all nested
            dictionaries.
        @return: A new dictionary, a deep copy of the original, with different
            keys.
    """
    if isinstance(d, Sequence):
        return [renameKeys(i, renamed, exclude) for i in d]
    if not isinstance(d, dict):
        return d
    
    if ordered:
        result = OrderedDict()
    else:
        result = {}
        
    for oldname,v in d.iteritems():
        if oldname not in renamed and exclude:
            continue
        newname = renamed.get(oldname, oldname)
        if recurse:
            result[newname] = renameKeys(v, renamed, exclude, recurse)
        else:
            result[newname] = v
    return result

#===============================================================================
# 
#===============================================================================

# The minimum and maximum values for data parsed out of data blocks.
# Used to provide an initial range, which is later corrected for actual
# values. Note that floats default to the normalized range of (-1.0, 1.0).
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
    """ Get the Python types produced by a parser. If the parser doesn't
        explicitly define them in a `types` attribute, the types are
        derived from what the parser generates.
        
        @param parser: A `struct.Struct`-like parser.
        @return: A tuple of Python types.
    """
    if hasattr(parser, "types"):
        return parser.types
    return tuple([type(x) for x in parser.unpack_from(chr(255)*parser.size)])


def getParserRanges(parser):
    """ Get the range of values created by a parser. If the parser doesn't
        explicitly define them in a `ranges` attribute, the theoretical 
        minimum and maximum values of the resulting data type are returned.
        Note that floating point values are typically reported as (-1.0,1.0).
        
        @param parser: A `struct.Struct`-like parser.
        @return: A tuple of (min, max) tuples. Non-numeric values will
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
    """ Retrieve all EBML element handlers (parsers) from a module. Handlers
        are identified by being subclasses of `ElementHandler`.
    
        @keyword module: The module from which to get the handlers. Defaults to
            the current module (i.e. `mide_ebml.parsers`).
        @keyword subElements: `True` if the set of handlers should also
            include non-root elements (e.g. the sub-elements of a
            `RecordingProperties` or `ChannelDataBlock`).
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
        
        @todo: Make sure the unsigned fraction part is correct for negative 
            whole values. This currently assumes -1 and .5 is -0.5, not -1.5
            
        @cvar size: The size (in bytes) of one parsed sample. Always `5`.
        @cvar format: For compatibility with `struct.Struct`. Always `None`
        @cvar ranges: A tuple containing the absolute min and max values.
        @cvar types: A tuple containing the types of data parsed.
    """

    # Custom parsers need to provide a subset of a struct.Struct's methods
    # and attributes: 
    size = 5
    format = None

    # The absolute min and max values, returned via `getParserRanges()`. This
    # must be implemented. Normal `struct.Struct` objects get this computed
    # from their formatting string.
    ranges = ((0.0,120000.0), (-40.0,80.0))
    
    # The types of data parsed from each channel, returned via 
    # `getParserTypes()`. If this doesn't exist, the types are computed. 
    types = (float, float)
    
    # This is weirdly formed data. Using two parsers over the same data is
    # cheaper than using one plus extra bit manipulation.
    _pressureParser = struct.Struct(">i")
    _parser = struct.Struct(">xxBbB")
        
    def unpack_from(self, data, offset=0):
        """ Special-case parsing of a temperature data block.
        """
        try:
            # TODO: Make sure if fractional part is correct for negative values
            rawpressure = self._pressureParser.unpack_from(data, offset)[0] >> 14
            fracpressure, rawtemp, fractemp = self._parser.unpack_from(data, offset)
            fracpressure = ((fracpressure >> 4) & 0b11) * 0.25
            fractemp = (fractemp >> 4) * 0.0625
    
            return (rawpressure + fracpressure, rawtemp + fractemp)
        except:
            import pdb; pdb.set_trace()
            


class AccelerometerParser(object):
    """ Parser for the accelerometer data. Accelerometer values are recorded
        as uint16 but represent values -100 to 100 G. This parser performs
        the conversion on the fly.
        
        If using this parser, do not perform this adjustment at the Channel 
        or Subchannel level via a Transform!
        
        @cvar size: The size (in bytes) of one parsed sample.
        @cvar format: The `struct.Struct` parsing format string used to parse.
        @cvar ranges: A tuple containing the absolute min and max values.
    """

    def __init__(self, inMin=0, inMax=65535, outMin=-100.0, outMax=100.0, 
                 formatting="<HHH"):
        self.parser = struct.Struct(formatting)
        self.format = self.parser.format
        self.size = self.parser.size
        self.ranges = ((-32768, 32767),) * 3
        
#         self.adjustment = lambda v: \
#             (v - inMin + 0.0) * (outMax - outMin) / (inMax - inMin) + outMin
    @classmethod
    def adjustment(cls, v):
        return v-32767

    def unpack_from(self, data, offset=0):
        return tuple(map(self.adjustment, 
                         self.parser.unpack_from(data, offset)))
    

#===============================================================================
# Base element parsing and data storing classes
#===============================================================================

class ElementHandler(object):
    """ Base class for all element handlers (i.e. parsers). ElementHandlers are
        instantiated after a `Dataset` has been created, and their `parse()`
        methods add data to (or modify) that Dataset.
        
        @cvar product: The class of object generated by the handler (if any).
            Used by data block parsers.
        @cvar elementName: The name of the EBML element handled.
        @cvar isSubElement: `False` if the element occurs at the root level of
            the EBML file.
        @cvar children: A list/tuple of the parsers for sub-elements of this
            element, if any.
    """
    product = None
    elementName = None
    isSubElement = False
    children = None
    
    def __init__(self, doc, **kwargs):
        self.doc = doc
        
        # Initialize the sub-element handlers
        if self.children is not None:
            self.childHandlers = {}
            for parser in self.children:
                self.childHandlers[parser.elementName] = parser(self.doc)
                
        
    def parse(self, element, **kwargs):
        """ Process an EBML element's contents. Handlers that generate data
            blocks should return the number of samples read. Other element
            types can return whatever their role requires.
        """ 
        # Apply the sub-element handlers (if any) to the element's payload
        if self.children is not None:
            result = []
            for el in element.value:
                if el.name in self.childHandlers:
                    result.append(self.childHandlers[el.name].parse(el, 
                                                                    **kwargs))
            return result

    
    def getElementName(self, element):
        """ Generate a string with an element's name, ID, and file position
            for debugging/error reporting.
        """
        return "%r (0x%x) @%r" % (element.name, element.id, 
                                  element.stream.offset)


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
        @cvar maxTimestamp: The modulus of the data's timestamp
        @cvar timeScalar: The scaling factor to convert native units (i.e.
            clock ticks) to microseconds.
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
#         self._len = None
        self.body_size = None
        self.cache = False
        
        self.minMeanMax = None
        self.min = None
        self.mean = None
        self.max = None
        self._rollingMean = None
        self._rollingMeanSpan = 5000000
        self._rollingMeanLen = None  # length of set at last rolling mean
        

    def __repr__(self):
        return "<%s Channel: 0x%02x>" % (self.__class__.__name__, self.getHeader()[1])


    def parseWith(self, parser, start=0, end=-1, step=1, subchannel=None):
        """ Parse an element's payload. Use this instead of directly using
            `parser.parse()` for consistency's sake.
            
            @param parser: The DataParser to use
            @keyword start: First subsample index to parse 
            @keyword end: Last subsample index to parse
            @keyword step: The number of samples to skip, if the start and end
                cover more than one sample.
            @keyword subchannel: The subchannel to get, if specified.
        """
        # SimpleChannelDataBlock payloads contain header info; skip it.
        data = self.payload
        start = self.headerSize + (start*parser.size)
        if end < 0:
            end += self.body_size
        else:
            end = self.headerSize + (end * parser.size)
            
        for i in xrange(start,end,parser.size*step):
            if subchannel is not None:
                yield parser.unpack_from(data, i)[subchannel]
            else:
                yield parser.unpack_from(data, i)


    def parseByIndexWith(self, parser, indices, subchannel=None):
        """ Parse an element's payload and get a specific set of samples. Used
            primarily for resampling tricks.
            
            @param parser: The DataParser to use
            @param indices: A list of indices into the block's data. 
            @keyword subchannel: The subchannel to get, if specified.
        """
        # SimpleChannelDataBlock payloads contain header info; skip it.
        data = self.payload
        for i in indices:
            if i >= self.numSamples:
                continue
            idx = self.headerSize + (i*parser.size)
            if subchannel is not None:
                yield parser.unpack_from(data, idx)[subchannel]
            else:
                yield parser.unpack_from(data, idx)


    def parseMinMeanMax(self, parser):
        if self.minMeanMax is None:
            return None
        self.min = parser.unpack_from(self.minMeanMax)
        self.mean = parser.unpack_from(self.minMeanMax, parser.size)
        self.max = parser.unpack_from(self.minMeanMax, parser.size*2)
        return self.min, self.mean, self.max


    def getNumSamples(self, parser):
        """ Compute the number of subsamples in an element's payload, as
            parsed by the given data parser.
        """
        if self.numSamples is not None:
            return self.numSamples
        n = len(self.payload) - self.headerSize
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

    
    @property
    def payload(self):
        return self.element.value

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
        self.startTime, self.channel = self.getHeader()
        self.body_size = element.body_size - self.headerSize
   
    
    def __len__(self):
        """ x.__len__() <==> len(x)
            This returns the length of the payload.
        """
        return self.numSamples
#         if self._len is None:
#             self._len = len(self.payload) - self.headerSize
#         return self._len
    
    
    def getHeader(self):
        """ Extract the block's header info. In SimpleChannelDataBlocks,
            this is part of the payload.
        """
        return self.headerParser.unpack_from(self.payload)
    

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
        
        self.timestampOffset = {}
        self.stampRollover = {}
        self.lastStamp = {}
    
    
    def fixOverflow(self, block, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        channel = block.getHeader()[1]
        timestamp += self.timestampOffset.setdefault(channel, 0)
        # NOTE: This might need to just be '<' (for discontinuities)
        if timestamp <= self.lastStamp.get(channel,0):
            timestamp += block.maxTimestamp
            self.timestampOffset[channel] += block.maxTimestamp
        self.lastStamp[channel] = timestamp
        return timestamp * block.timeScalar
    
   
    def parse(self, element, sessionId=None):
        """ Create a (Simple)ChannelDataBlock from the given EBML element.
        
            @param element: A sample-carrying EBML element.
            @keyword sessionId: The session currently being read; defaults to
                whatever the Dataset says is current.
            @return: The number of subsamples read from the element's payload.
        """
        try:
            block = self.product(element)
            timestamp, channel = block.getHeader()
        except struct.error, e:
            # TODO: Log error
            print "Element would not parse: %s (ID 0x%02x) @%d (%s)" % (element.name, element.id, element.stream.offset, e)
            return 0
        
        block.startTime = int(self.fixOverflow(block, timestamp))
        if block.endTime is not None:
            block.endTime = int(self.fixOverflow(block, block.endTime))

        if channel not in self.doc.channels:
            # TODO: Log error
            return 0

        self.doc.channels[channel].getSession(sessionId).append(block)
        return block.getNumSamples(self.doc.channels[channel].parser)


#===============================================================================
# ChannelDataBlock: Element wrapper and handler
#===============================================================================

class ChannelDataBlock(BaseDataBlock):
    """ Wrapper for ChannelDataBlock elements, which features additional data
        excluded from the simple version. ChannelDataBlock elements are 'master'
        elements with several child elements, such as full timestamps and
        and sample minimum/mean/maximum.
    """
    maxTimestamp = 2**24 #2**32

    def __init__(self, element):
        super(ChannelDataBlock, self).__init__(element)
        self._payloadIdx = None
        self._payload = None
        
        self.element = element
        for num, el in enumerate(element.value):
            if el.name == "Void":
                continue
            elif el.name == "ChannelIDRef":
                self.channel = el.value
            elif el.name == "ChannelFlags":
                # TODO: Handle channel flag bits
                continue
            elif el.name == "ChannelDataPayload":
                self._payloadIdx = num
                self.body_size = el.body_size
            elif el.name == "StartTimeCodeAbs":
                # TODO: Support this. Not currently generated (2014.04.23)
                continue
            elif el.name == "EndTimeCodeAbs":
                # TODO: Support this. Not currently generated (2014.04.23)
                continue
            elif el.name == "StartTimeCodeAbsMod":
                self.startTime = el.value
                # TODO: Correct start time for modulus (?)
                self._timestamp = el.value
            elif el.name == "EndTimeCodeAbsMod":
                self.endTime = el.value
            elif el.name == "ChannelDataMinMeanMax":
                self.minMeanMax = el.value
            # Add other child element handlers here.
        
        # Single-sample blocks have a total time of 0.
        # Set endTime to None, so the end times will be computed.
        if self.startTime == self.endTime:
            self.endTime = None
    
    
    @property
    def payload(self):
        # Simple caching, intended for use with small blocks
        if self.cache:
            if self._payload is None:
                self._payload = self.element.value[self._payloadIdx].value
            return self._payload
        
        # 'value' is actually a property that does the file seek, so it (and
        # not a reference to a child element) has to be used every time.
        # TODO: Optimize value retrieval (fix python-ebml caching)
        return self.element.value[self._payloadIdx].value
    
    
    def getHeader(self):
        """ Extract the block's header info (timestamp and channel ID).
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

    timeScalar = 1000000.0 / 2**15

    def __init__(self, doc, **kwargs):
        super(ChannelDataBlockParser, self).__init__(doc, **kwargs)
        
        self.timestampOffset = {}
        self.stampRollover = {}
        self.lastStamp = {}



#===============================================================================
# 
#===============================================================================

class RecorderPropertyParser(ElementHandler):
    """ Base class for elements that just add a value to the Dataset's
        `recorderInfo` but aren't in the `RecorderInfo` element.
    """
    def parse(self, element, **kwargs):
        self.doc.recorderInfo[self.elementName] = element.value
        

class PolynomialParser(ElementHandler):
    """ The handler for both Univariate and Bivariate calibration polynomials.
        Each are a subclass of this, although this class does all the work.
    """
    isSubElement = True
    
    # Parameter names: mapping of element names to the keyword arguments used
    # to instantiate a polynomial object. Also used to remove unknown elements
    # (see `renameKeys`).
    parameterNames = {"CalID": "calId",
                      "CalReferenceValue": "reference",
                      "BivariateCalReferenceValue": "reference2",
                      "BivariateChannelIDRef": "channelId",
                      "BivariateSubChannelIDRef": "subchannelId",
                      "PolynomialCoef": "coeffs"}

    def parse(self, element, **kwargs):
        """
        """
        # Element name (plus ID and file position) for error messages
        elName = self.getElementName(element)
        params = renameKeys(parse_ebml(element.value), self.parameterNames)
        params['dataset'] = self.doc
        
        coeffs = params.pop("coeffs", None)
        if coeffs is None:
            raise ParsingError("%s had no coefficients" % elName)
        
        if "calId" not in params:
            raise ParsingError("%s had no calibration ID" % elName)
        
        if element.name == "BivariatePolynomial":
            # Bivariate polynomial. Do extra error checking.
            if "channelId" not in params or "subchannelId" not in params:
                raise ParsingError("%s had no channel reference!" % elName)
            if len(coeffs) != 4:
                raise ParsingError("%s supplied %d coefficients; 4 required" % \
                                   (elName, len(coeffs)))
            cal = calibration.Bivariate(coeffs, **params)
            
        elif element.name == "UnivariatePolynomial":
            cal = calibration.Univariate(coeffs, **params)
            
        else:
            # Unknown polynomial type. 
            raise ParsingError("%s: unknown polynomial type" % elName)
        
        # self.doc might (validly) be None if a configuration tool were 
        # reading the device info file, rather than reading a recording file. 
        if self.doc is not None:
            self.doc.addTransform(cal)
        
        return cal


class UnivariatePolynomialParser(PolynomialParser):
    """ Parses a single-variable polynomial. 
    """
    elementName = "UnivariatePolynomial"


class BivariatePolynomialParser(PolynomialParser):
    """ Parses a two-variable polynomial. 
    """
    elementName = "BivariatePolynomial"


class CalibrationDateParser(RecorderPropertyParser):
    """ Simple handler for calibration birthday (optional). """
    elementName = "CalibrationDate"
    
class CalibrationExpiryParser(RecorderPropertyParser):
    """ Simple handler for calibration 'sell-by' date (optional). """
    elementName = "CalibrationExpiry"

class CalibrationSerialNumber(RecorderPropertyParser):
    """ Simple handler for calibration serial number (optional). """
    elementName = "CalibrationSerialNumber"


class CalibrationListParser(ElementHandler):
    """ Root-level parser for calibration data. Handles parsing of the
        individual calibration elements (its children). Unlike (most) other
        parsers, this one can be instantiated without a reference to a 
        `dataset.Dataset`. It also keeps a copy of all the calibration items
        in a `items` attribute (a list). 
    """
    elementName = "CalibrationList"
    children = (UnivariatePolynomialParser, BivariatePolynomialParser,
                CalibrationDateParser, CalibrationExpiryParser,
                CalibrationSerialNumber)


#===============================================================================
# 
#===============================================================================

class SensorParser(ElementHandler):
    """ Handle `Sensor` elements, children of `SensorList`.
    """
    elementName = "Sensor"
    isSubElement = True

    # Parameter names: mapping of element names to the keyword arguments used
    # to instantiate the various children of SensorParser. Also used to remove
    # unknown elements (see `renameKeys`).
    parameterNames = {
        "Sensor": "sensors",
                      
        "SensorID": "sensorId",
        "SensorName": "name", 
        "TraceabilityData": "traceData",
        "SensorCalibrationIDRef": "transform",
        "SensorChannel": "channels",
      
        "SensorChannelID": "channelId",
        "SensorChannelName": "name", 
        "TimeCodeScale": "timeScale",
        "TimeCodeModulus": "timeModulus",
#         "SensorChannelFormat": "parser", # TBD;
        "SensorChannelCalibrationIDRef": "transform",
        "SensorSubChannel": "subchannels",   

        "SubChannelID": "subchannelId",
        "SubChannelName": "name",
        "SubChannelCalibrationIDRef": "transform",
        "SubChannelSubChannelAxisName": "axisName",
        "SubChannelSubChannelAxisName": "axisId",
        "SubChannelUnitsName": "units",
        "SubChannelUnitsXRef": "unitsId",
        "SubChannelRangeMin": "rangeMin",
        "SubChannelRangeMax": "rangeMax"
    }
    
    def parse(self, element, **kwargs):
        """
        """
        def getXform(d):
            if "transform" in d:
                d['transform'] = self.doc.transforms[d['transform']]
        
        data = renameKeys(parse_ebml(element.value), self.parameterNames)
        getXform(data)
        
        channels = data.pop("channels","")
        sensor = self.doc.addSensor(**data)
        
        for channelData in channels:
            getXform(channelData)
            subchannels = channelData.pop("subchannels","")
            channel = self.doc.addChannel(**channelData)
            for subchannelData in subchannels:
                getXform(subchannelData)
                channel.addSubChannel(**subchannelData)
        
        return sensor


class SensorListParser(ElementHandler):
    """ Handle the `SensorList` element, child of RecorderInfo. Really only
        a wrapper around a set of `Sensor` elements.
    """
    elementName = "SensorList"
    isSubElement = True
    children = (SensorParser, )


class PlotParser(ElementHandler):
    """
    """
    elementName = "Plot"
    isSubElement = True
    
    def parse(self, element, **kwargs):
        """
        """
        # TODO: IMPLEMENT, but later. Not required for immediate goals.
        pass


class PlotListParser(ElementHandler):
    """
    """
    elementName = "PlotList"
    isSubElement = True
    children = (PlotParser, )
    

class RecorderInfoParser(ElementHandler):
    """ Handle the `RecorderInfo` element, child of RecordingProperties.
    """
    elementName = "RecorderInfo"
    isSubElement = True
    
    def parse(self, element, **kwargs):
        """
        """
        # This one is simple; it just sticks the data into the Dataset.
        self.doc.recorderInfo.update(parse_ebml(element.value)) 
        return self.doc.recorderInfo  


class RecordingPropertiesParser(ElementHandler):
    """ Stub for RecordingProperties element handler. All relevant data is in
        its child elements.
    
        @cvar elementName: The name of the element handled by this parser
        @todo: Implement RecordingPropertiesParser
    """
    elementName = "RecordingProperties"
    isSubElement = False
    children = (RecorderInfoParser, SensorListParser)



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
    """ Handle TimeBaseUTC elements, applying it as the UTC start time of the
        current Session.
    """
    elementName = "TimeBaseUTC"
    
    def parse(self, element, **kwargs):
        val = element.value
        self.doc.lastUtcTime = val
        self.doc.lastSession.utcStartTime = val


#===============================================================================
# 
#===============================================================================

class SyncParser(ElementHandler):
    """ Stub for Session element handler.
    
        @cvar elementName: The name of the element handled by this parser
    """
    elementName = "Sync"
    
    def parse(self, *args, **kwargs):
        # The contents aren't (and will never be) important; continue.
        pass
    

#===============================================================================
# 
#===============================================================================


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

class EBMLParser(ElementHandler):
    """ Stub for gracefully handling the standard EBML element, typically the 
        first in any EBML file.
    """
    elementName="EBML"
    
    def parse(self, element, **kwargs):
        # Don't care about this tag; the library automatically parses it.
        pass


class VoidParser(ElementHandler):
    """ Stub for gracefully handling the standard Void element.
    """
    elementName="Void"
    
    def parse(self, element, **kwargs):
        # Don't care about this tag; the library automatically parses it.
        pass

