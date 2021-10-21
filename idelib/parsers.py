"""
This file contains three types of things: special-case data parsers, handlers
for specific EBML elements, and wrapper classes for EBML data-containing
elements.

Special-case data-parsing objects are for parsing element data needing more 
post-processing than simply grabbing values with a `struct.Struct`, such as a 
sensor that produces data in a non-power-of-two length (e.g. 24 bits). 
Special-case parsers must (to a limited degree) quack like `struct.Struct` 
objects; they must provide `size` and `format` attributes (the latter should be 
`None`), and they must implement the method `unpack_from()`. They may also 
include optional `types` and `ranges` attributes, which are used to provide
'hints' about the data. These are automatically computed if not defined
explicitly.

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

:todo: Clean this up! it's grown a little too organically.

Created on Sep 26, 2013
:author: dstokes
"""

from collections import OrderedDict
from collections.abc import Sequence
import math
import struct
import sys
import types

import numpy as np  

from . import transforms
from .attributes import decode_attributes

import logging
logger = logging.getLogger('idelib')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")

#===============================================================================
# 
#===============================================================================

DATA_PARSERS = {}

def dataParser(cls):
    """ Decorator. Used to register classes as parsers of data payloads. 
    """
    global DATA_PARSERS
    DATA_PARSERS[cls.__name__] = cls
    return cls


#===============================================================================
# Utility Functions
#===============================================================================            
    
def renameKeys(d, renamed, exclude=True, recurse=True, ordered=False,
               mergeAttributes=True):
    """ Create a new dictionary from and old one, using different keys. Used
        primarily for converting EBML element names to function keyword
        arguments.
    
        :param d: The source dictionary
        :param renamed: A dictionary of new names keyed by old names
        :keyword exclude: If `True`, only keys appearing in `renamed` are
            copied to the new dictionary.
        :keyword recurse: If `True`, the renaming operates over all nested
            dictionaries.
        :keyword ordered: If `True`, the results are returned as an
            `OrderedDict` rather than a standard dictionary.
        :keyword mergeAttributes: If `True`, any `Attribute` elements are
            processed into a standard key/values and merged into the main
            dictionary.
        :return: A new dictionary, a deep copy of the original, with different
            keys.
    """
    if isinstance(d, (str, bytes, bytearray)):
        return d
    elif isinstance(d, Sequence):
        return [renameKeys(i, renamed, exclude, recurse, ordered, mergeAttributes) for i in d]
    elif not isinstance(d, dict):
        return d
    
    if ordered:
        result = OrderedDict()
    else:
        result = {}
        
    for oldname,v in d.items():
        if oldname == "Attribute":
            if mergeAttributes:
                result.update(decode_attributes(v))
            else:
                result['Attribute'] = decode_attributes(v)
            continue
        
        if oldname not in renamed and exclude:
            continue
        
        newname = renamed.get(oldname, oldname)
        
        if recurse:
            result[newname] = renameKeys(v, renamed, exclude, recurse)
        else:
            result[newname] = v
            
    return result


def valEval(value, allowedChars='+-/*01234567890abcdefx.,() ;\t\n_'):
    """ A slightly safer version of `eval()` designed for simple mathematical
        expressions. Only permits math stuff.
    """
    # XXX: This is a hideous Rube Goldberg machine of a function. Could probably
    # be accomplished better with a suitably complex regular expression.
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    value = value.strip()
    val = value.lower().replace('math.', '')
    
    # Allow functions from the math module. Replace them with a placeholder
    # character (128+). Do in reverse order of length to prevent partial
    # replacement (e.g. 'e' in 'exp', 'tan' in 'atan2'
    funcs = sorted([x for x in dir(math) if not x.startswith('_')],
                   key=lambda x: len(x), reverse=True)
    # funcs = tuple(enumerate(funcs, 128))
    
    for n, f in enumerate(funcs, 128):
        allowedChars = "%s%s" % (allowedChars, chr(n))
        if f in val:
            val = val.replace(f, chr(n))
            continue

    allowedChars = set(allowedChars)
        
    if len(set(val).difference(allowedChars)) > 0: 
        raise TypeError("valEval(): Invalid/Unsafe character in %r" % value)
    
    # Put the math functions back, with module reference
    if len(val) < len(value):
        for n, f in enumerate(funcs, 128):
            val = val.replace(chr(n), 'math.%s' % f)
    
    return eval(val)
    
    
def parseAttribute(obj, element, multiple=True):
    """ Utility function to parse an `Attribute` element's data into a 
        key/value pair and apply it to an object's `attribute` attribute
        (a dictionary).
        
        :param element: The `Attribute` element to parse.
        :keyword multiple: An object may have more than one Attribute element
            with the same name. If `True`, the value corresponding to the name
            is a list which is appended to. If `False`, the value is that of
            the last `Attribute` element parsed. 
    """
    if not hasattr(obj, 'attributes'):
        obj.attributes = OrderedDict()
        
    k = v = None
    for ch in element.value:
        if ch.name == "AttributeName":
            k = ch.value
        else:
            v = ch.value
            
    if k is not None:
        if multiple:
            obj.attributes.setdefault(k, []).append(v)
        else:
            obj.attributes[k] = v
        
    return k, v


#===============================================================================
# 
#===============================================================================

# The minimum and maximum values for data parsed out of data blocks.
# Used to provide an initial range, which is later corrected for actual
# values. Note that floats default to the normalized range of (-1.0, 1.0).
RANGES = {'c': None,
          'b': (-128,127),
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
        
        :param parser: A `struct.Struct`-like parser.
        :return: A tuple of Python types.
    """
    if hasattr(parser, "types"):
        return parser.types
    return tuple([type(x) for x in parser.unpack_from(b'\xff'*parser.size)])


def getParserRanges(parser, useDefaults=True):
    """ Get the range of values created by a parser. If the parser doesn't
        explicitly define them in a `ranges` attribute, the theoretical 
        minimum and maximum values of the resulting data type are returned.
        Note that floating point values are typically reported as (-1.0,1.0).
        
        :param parser: A `struct.Struct`-like parser.
        :return: A tuple of (min, max) tuples. Non-numeric values will
            have a reported range of `None`.
    """
    if hasattr(parser, "ranges"):
        return parser.ranges
    if not useDefaults:
        return None
    ranges = []
    for c in parser.format:
        if isinstance(c, int):
            c = chr(c)
        if c in RANGES:
            ranges.append(RANGES[c])
    return tuple(ranges)
    

#===============================================================================
# 
#===============================================================================

def getElementHandlers(module=None, subElements=False):
    """ Retrieve all EBML element handlers (parsers) from a module. Handlers
        are identified by being subclasses of `ElementHandler`.
    
        :keyword module: The module from which to get the handlers. Defaults to
            the current module (i.e. `idelib.parsers`).
        :keyword subElements: `True` if the set of handlers should also
            include non-root elements (e.g. the sub-elements of a
            `RecordingProperties` or `ChannelDataBlock`).
        :return: A list of element handler classes.
    """
    elementParserTypes = []
    if module is None:
        if __name__ in sys.modules:
            moduleDict = sys.modules[__name__].__dict__
        else:
            moduleDict = globals()
    else:
        moduleDict = module.__dict__
    for p in moduleDict.values():
        if not isinstance(p, type) or p == ElementHandler:
            continue
        if issubclass(p, ElementHandler):
            if subElements or not p.isSubElement:
                elementParserTypes.append(p)
    return elementParserTypes


#===============================================================================
# EXCEPTIONS
#===============================================================================

class ParsingError(IOError):
    """ Exception raised for any failure to parse an EBML file. """
    pass


#===============================================================================
#--- SENSOR DATA PARSING
#===============================================================================

@dataParser
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
        
        :todo: Make sure the unsigned fraction part is correct for negative 
            whole values. This currently assumes -1 and .5 is -0.5, not -1.5

        :deprecated: Used only for really old recordings without recorder
            description data. Later firmware writes the data padded to a more 
            easily handled form.
            
        :cvar size: The size (in bytes) of one parsed sample. Always `5`.
        :cvar format: For compatibility with `struct.Struct`. Always `None`
        :cvar ranges: A tuple containing the absolute min and max values.
        :cvar types: A tuple containing the types of data parsed.
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
        rawpressure = self._pressureParser.unpack_from(data, offset)[0] >> 14
        fracpressure, rawtemp, fractemp = self._parser.unpack_from(data, offset)
        fracpressure = ((fracpressure >> 4) & 0b11) * 0.25
        fractemp = (fractemp >> 4) * 0.0625

        return (rawpressure + fracpressure, rawtemp + fractemp)
            

@dataParser
class AccelerometerParser(object):
    """ Parser for the accelerometer data. Accelerometer values are recorded
        as uint16 but represent values -(max) to (max) G, with 'max' being
        a property of the specific accelerometer part number. This parser 
        performs the conversion on the fly.
        
        :deprecated: Used only for really old recordings without recorder
            description data.
        :cvar size: The size (in bytes) of one parsed sample.
        :cvar format: The `struct.Struct` parsing format string used to parse.
        :cvar ranges: A tuple containing the absolute min and max values.
    """

    def __init__(self, formatting="<HHH"):
        self.parser = struct.Struct(formatting)
        self.format = self.parser.format
        self.size = self.parser.size
        self.ranges = ((-32768, 32767),) * 3

    def unpack_from(self, data, offset=0):
        # This parser converts to signed ints to avoid some problems with the
        # inverted 'z' axis.
        z, y, x = self.parser.unpack_from(data, offset)
        return 32768-z, y-32768, x-32768
    

################################################################################
#===============================================================================
#--- Base element parsing and data storing classes
#===============================================================================
################################################################################

class ElementHandler(object):
    """ Base class for all element handlers (i.e. parsers). ElementHandlers are
        instantiated after a `Dataset` has been created, and their `parse()`
        methods add data to (or modify) that Dataset.
        
        :cvar product: The class of object generated by the handler (if any).
            Used by data block parsers.
        :cvar elementName: The name of the EBML element handled.
        :cvar isSubElement: `False` if the element occurs at the root level of
            the EBML file.
        :cvar children: A list/tuple of the parsers for sub-elements of this
            element, if any.
    """
    product = None
    elementName = None
    isSubElement = False
    isHeader = False
    children = None
    
    def __init__(self, doc, **kwargs):
        self.doc = doc
        
        # Initialize the sub-element handlers
        if self.children is not None:
            self.childHandlers = {}
            for parser in self.children:
                if parser.elementName is None:
                    continue
                p = parser(self.doc)
                if isinstance(parser.elementName, (str, bytes, bytearray)):
                    self.childHandlers[parser.elementName] = p
                else:
                    for n in parser.elementName:
                        self.childHandlers[n] = p
                
        
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
                    handler = self.childHandlers[el.name]
                    result.append(handler.parse(el, **kwargs))
            return result

    
    def getElementName(self, element):
        """ Generate a string with an element's name, ID, and file position
            for debugging/error reporting.
        """
        try:
            return "%r (0x%x) @%r" % (element.name, element.id,
                                      element.offset)
        except AttributeError:
            # Possibly an old python-ebml element
            # TODO: Remove legacy code
            return "%r (0x%x) @%r" % (element.name, element.id,
                                      element.stream.offset)


    def makesData(self):
        """ Does this handler produce sample data?
        """
        return self.product is not None and \
            issubclass(self.product, BaseDataBlock)


################################################################################
#===============================================================================
#--- Data parsers and handlers
#===============================================================================
################################################################################

class BaseDataBlock(object):
    """ Base class for all data-containing elements. Created by the
        appropriate ElementHandler for the given EBML element type.
        
        :cvar maxTimestamp: The modulus of the data's timestamp
        :cvar timeScalar: The scaling factor to convert native units (i.e.
            clock ticks) to microseconds.
    """
    maxTimestamp = 2**24 
    timeScalar = 1000000.0 / 2**15
    
    def __init__(self, element, maxTimestamp=maxTimestamp, timeScalar=timeScalar):
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
        self.payloadSize = None
        self.cache = False
        
        self.minMeanMax = None
        self.min = None
        self.mean = None
        self.max = None
        self._rollingMean = None
        self._rollingMeanSpan = 5000000
        self._rollingMeanLen = None  # length of set at last rolling mean
        
        self.maxTimestamp = maxTimestamp
        self.timeScalar = timeScalar
        

    def __repr__(self):
        return "<%s Channel: %d>" % (self.__class__.__name__, self.getHeader()[1])


    def getNumSamples(self, parser):
        """ Compute the number of subsamples in an element's payload, as
            parsed by the given data parser.
        """
        if self.numSamples is not None:
            return self.numSamples
        self.numSamples = int(self.payloadSize/parser.size)
        return self.numSamples


    def isValidLength(self, parser):
        """ Check if an element's payload data is evenly divisible by into
            a set of channels.
        
            :param n: The size of the data in bytes.
            :return: `True` if the number of bytes can be evenly
                distributed into subsamples.
        """
        return self.payloadSize > 0 and self.payloadSize % parser.size == 0

    
    @property
    def payload(self):
        return self.element.value


#===============================================================================
# SimpleChannelDataBlock-related handlers
#===============================================================================

class SimpleChannelDataBlock(BaseDataBlock):
    """ Wrapper for SimpleChannelDataBlock elements, which consist of only a
        binary payload of raw data prefixed with a 16b timestamp and an 8b
        channel ID. Also keeps track of some metadata used by its Channel.
        
        :cvar headerSize: The size of the header information stored in the
            element's payload, if any.
    """
    headerParser = struct.Struct(">HB")
    headerSize = headerParser.size
    maxTimestamp = 2**16

    def __init__(self, element):
        super(SimpleChannelDataBlock, self).__init__(element)
        self.element = element
        self.startTime, self.channel = self.getHeader()
        self.payloadSize = element.size - self.headerSize
   
    
    def __len__(self):
        """ x.__len__() <==> len(x)
            This returns the length of the payload.
        """
        return self.numSamples
    
    
    def getHeader(self):
        """ Extract the block's header info. In SimpleChannelDataBlocks,
            this is part of the payload.
        """
        return self.headerParser.unpack_from(self.payload)
    

    @property
    def timestamp(self):
        return self.getHeader()[0]


    def parseWith(self, parser, start=None, end=None, step=1, subchannel=None):
        """ Parse an element's payload. Use this instead of directly using
            `parser.parse()` for consistency's sake.
            
            :param parser: The DataParser to use
            :keyword start: First subsample index to parse 
            :keyword end: Last subsample index to parse
            :keyword step: The number of samples to skip, if the start and end
                cover more than one sample.
            :keyword subchannel: The subchannel to get, if specified.
        """
        # SimpleChannelDataBlock payloads contain header info; skip it.
        data = self.payload
        start, end, step = slice(start, end, step).indices(
            (self.payloadSize-self.headerSize) // parser.size
        )

        start = self.headerSize + (start*parser.size)
        end = self.headerSize + (end*parser.size)
        
        parser_unpack_from = parser.unpack_from
        if subchannel is not None:
            for i in range(start, end, parser.size*step):
                yield parser_unpack_from(data, i)[subchannel]
        else:
            for i in range(start, end, parser.size*step):
                yield parser_unpack_from(data, i)


    def parseByIndexWith(self, parser, indices, subchannel=None):
        """ Parse an element's payload and get a specific set of samples. Used
            primarily for resampling tricks.
            
            :param parser: The DataParser to use
            :param indices: A list of indices into the block's data. 
            :keyword subchannel: The subchannel to get, if specified.
        """
        # SimpleChannelDataBlock payloads contain header info; skip it.
        data = self.payload
        parser_unpack_from = parser.unpack_from
        parser_size = parser.size
        for i in indices:
            if i >= self.numSamples:
                continue
            idx = self.headerSize + (i*parser_size)
            if subchannel is not None:
                yield parser_unpack_from(data, idx)[subchannel]
            else:
                yield parser_unpack_from(data, idx)



class SimpleChannelDataBlockParser(ElementHandler):
    """ 'Factory' for SimpleChannelDataBlock elements. Instantiated once
        per session (or maybe channel, depending). It handles the modulus
        correction of the block's short timestamps.
        
        :cvar elementName: The name of the element handled by this parser
        :cvar product: The class of object generated by the parser
    """
    product = SimpleChannelDataBlock
    elementName = product.__name__
    isHeader = False

    # The default block time scalar.
    timeScalar = 1000000.0 / 2**15

    def __init__(self, doc, **kwargs):
        super(SimpleChannelDataBlockParser, self).__init__(doc, **kwargs)

        # Timestamp conversion/correction is done per channel        
        self.timestampOffset = {}
        self.lastStamp = {}
        self.timeScalars = {}
        self.timeModulus = {}


    def fixOverflow(self, block, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        # TODO: Identify blocks with non-modulo timestamps and just return the
        #    unmodified timestamp. Will be slightly more efficient.
        
        channel = block.getHeader()[1]
        modulus = self.timeModulus.setdefault(channel, block.maxTimestamp)
        offset = self.timestampOffset.setdefault(channel, 0)
        
        if timestamp > modulus:
            # Timestamp is (probably) not modulo; will occur in split files.
            offset = timestamp - (timestamp % modulus)
            timestamp = timestamp % modulus
            self.timestampOffset[channel] = offset
        elif timestamp < self.lastStamp.get(channel, 0):
            # Modulo rollover (probably) occurred.
            offset += modulus
            self.timestampOffset[channel] = offset
            
        self.lastStamp[channel] = timestamp
        timestamp += self.timestampOffset[channel]
        return timestamp * self.timeScalars.setdefault(channel, self.timeScalar)
    
   
    def parse(self, element, sessionId=None, timeOffset=0):
        """ Create a (Simple)ChannelDataBlock from the given EBML element.
        
            :param element: A sample-carrying EBML element.
            :keyword sessionId: The session currently being read; defaults to
                whatever the Dataset says is current.
            :return: The number of subsamples read from the element's payload.
        """
        try:
            block = self.product(element)
            timestamp, channel = block.getHeader()
        except struct.error as e:
            raise ParsingError("Element would not parse: %s (ID %d) @%d (%s)" %
                               (element.name, element.id, element.offset, e))
        except AttributeError:
            # Can happen if the block had no timestamp (broken imported data?)
            # TODO: Actually handle, instead of ignoring?
            logger.warning("XXX: bad attribute in element %s" % element)
            return 0
            
        
        block.startTime = timeOffset + int(self.fixOverflow(block, timestamp))
        if block.endTime is not None:
            block.endTime = timeOffset + int(self.fixOverflow(block, block.endTime))

        if channel not in self.doc.channels:
            # Unknown channel; could be debugging info, so that might be okay.
            # FUTURE: Better handling of unknown channel types. Low priority.
            return 0

        try:
            ch = self.doc.channels[channel]
            ch.getSession(sessionId).append(block)
            return block.getNumSamples(ch.parser) * len(ch.children)
        except ZeroDivisionError:
            return 0


#===============================================================================
# ChannelDataBlock: Element wrapper and handler
#===============================================================================

class ChannelDataBlock(BaseDataBlock):
    """ Wrapper for ChannelDataBlock elements, which features additional data
        excluded from the simple version. ChannelDataBlock elements are 'master'
        elements with several child elements, such as full timestamps and
        and sample minimum/mean/maximum.
    """
    maxTimestamp = 2**24

    def __init__(self, element):
        super(ChannelDataBlock, self).__init__(element)
        self._payloadIdx = None
        self._payloadEl = None
        
        self._minMeanMaxEl = None
        self._minMeanMax = None
        
        self.element = element
        for el in element:
            # These are roughly in order of probability, optional and/or
            # unimplemented elements are at the end.
            if el.name == "ChannelIDRef":
                self.channel = el.value
            elif el.name == "ChannelDataPayload":
                self._payloadEl = el
                self.payloadSize = el.size
            elif el.name == "StartTimeCodeAbsMod":
                self.startTime = el.value
                self._timestamp = el.value
            elif el.name == "EndTimeCodeAbsMod":
                self.endTime = el.value
            elif el.name == "ChannelDataMinMeanMax":
#                 self.minMeanMax = el.value
                self._minMeanMaxEl = el
            elif el.name == "Void":
                continue
            elif el.name == 'Attribute':
                parseAttribute(self, el)
                el.gc()
            elif el.name == "StartTimeCodeAbs":
                # TODO: store indicator that the start timestamp is non-modulo?
                self.startTime = el.value
                self._timestamp = el.value
            elif el.name == "EndTimeCodeAbs":
                # TODO: store indicator that the end timestamp is non-modulo?
                self.endTime = el.value
            elif el.name == "ChannelFlags":
                # FUTURE: Handle channel flag bits
                continue
            # Add other child element handlers here.
        
        element.gc(recurse=False)
        
        # Single-sample blocks have a total time of 0. Old files did not write
        # the end timestamp; if it's missing, duplicate the starting time.
        if self.endTime is None:
            self.endTime = self.startTime

        self._payload = None

        self._parser = None
        self._streamDtype = None
        self._commonDtype = None

    @property
    def payload(self):
        if self._payload is None:
            self._payload = np.array(self._payloadEl.value)
            self._payloadEl.gc()
        return self._payload

    # Define standard mapping from struct to numpy typestring
    #   (conversions taken from struct & numpy docs:)
    #   https://docs.python.org/3/library/struct.html#format-characters
    #   https://numpy.org/doc/stable/reference/arrays.dtypes.html#specifying-and-constructing-data-types
    TO_NP_TYPESTR = {
        # 'x': '',
        'c': 'b',
        'b': 'b',
        'B': 'B',
        '?': '?',
        'h': 'i2',
        'H': 'u2',
        'i': 'i4',
        'I': 'u4',
        'l': 'i4',
        'L': 'u4',
        'q': 'i8',
        'Q': 'u8',
        # 'n': '',
        # 'N': '',
        # 'e': 'f2',  unsupported in Python3.5
        'f': 'f4',
        'd': 'f8',
        # 's': '',
        # 'p': '',
        # 'P': '',
    }

    @property
    def minMeanMax(self):
        if self._minMeanMaxEl is None:
            return self._minMeanMax
        return self._minMeanMaxEl.value
    
    
    @minMeanMax.setter
    def minMeanMax(self, v):
        # Explicitly set (done when block contains a single sample)
        self._minMeanMax = v
    
    
    def getHeader(self):
        """ Extract the block's header info (timestamp and channel ID).
        """
        return self._timestamp, self.channel


class ChannelDataBlockParser(SimpleChannelDataBlockParser):
    """ Factory for ChannelDataBlock elements.  Instantiated once per
        session/channel, handles modulus correction for the blocks' timestamps.
        Unlike the ChannelDataBlockParser, this returns blocks which store
        (cache?) data as numpy arrays.

        :cvar product: The class of object generated by the parser
    """
    product = ChannelDataBlock
    elementName = product.__name__

    timeScalar = 1e6 / 2**15


################################################################################
#===============================================================================
#--- RecordingProperties element and sub-element parsers
#===============================================================================
################################################################################

class RecorderPropertyParser(ElementHandler):
    """ Base class for elements that just add a value to the Dataset's
        `recorderInfo` but aren't in the `RecorderInfo` element.
    """
    isHeader = True
    isSubElement = True
    
    def parse(self, element, **kwargs):
        if self.doc is not None:
            if element.name == 'Attribute':
                parseAttribute(self.doc, element)
            else:
                self.doc.recorderInfo[element.name] = element.value
   

#===============================================================================
# RecordingProperties: Calibration
#===============================================================================

class PolynomialParser(ElementHandler):
    """ The handler for both Univariate and Bivariate calibration polynomials.
        Each are a subclass of this, although this class does all the work.
    """
    elementName = ("UnivariatePolynomial", "BivariatePolynomial")
    isSubElement = True
    isHeader = True
    
    # Parameter names: mapping of element names to the keyword arguments used
    # to instantiate a polynomial object. Also used to remove unknown elements
    # (see `renameKeys`).
    parameterNames = {"CalID": "calId",
                      "CalReferenceValue": "reference",
                      "BivariateCalReferenceValue": "reference2",
                      "BivariateChannelIDRef": "channelId",
                      "BivariateSubChannelIDRef": "subchannelId",
                      "PolynomialCoef": "coeffs",
                      "Attribute": "attributes"}

    def parse(self, element, **kwargs):
        """
        """
        # Element name (plus ID and file position) for error messages
        elName = self.getElementName(element)
        params = renameKeys(element.dump(), self.parameterNames)
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
                raise ParsingError("%s supplied %d coefficients; 4 required" %
                                   (elName, len(coeffs)))
            cal = transforms.Bivariate(coeffs, **params)
            
        elif element.name == "UnivariatePolynomial":
            cal = transforms.Univariate(coeffs, **params)
            
        else:
            # Unknown polynomial type. 
            raise ParsingError("%s: unknown polynomial type" % elName)
        
        # self.doc might (validly) be None if a configuration tool is 
        # reading the device info file, rather than reading a recording file. 
        if self.doc is not None:
            self.doc.addTransform(cal)
        
        return cal


class CalibrationElementParser(RecorderPropertyParser):
    """ Simple handler for calibration birthday (optional). """
    elementName = ("CalibrationDate",
                   "CalibrationExpiry",
                   "CalibrationSerialNumber")


class CalibrationListParser(ElementHandler):
    """ Root-level parser for calibration data. Handles parsing of the
        individual calibration elements (its children). Unlike (most) other
        parsers, this one can be instantiated without a reference to a 
        `dataset.Dataset`. It also keeps a copy of all the calibration items
        in a `items` attribute (a list). 
    """
    isHeader = True
    elementName = "CalibrationList"
    children = (PolynomialParser, CalibrationElementParser)


#===============================================================================
# RecordingProperties: Sensor-related parsers
#===============================================================================

class SensorListParser(ElementHandler):
    """ Handle `SensorList` elements, creating the individual Sensors from
        the element's children.
    """
    elementName = "SensorList"
    isSubElement = True

    # Parameter names: mapping of element names to the keyword arguments used
    # to instantiate the various children of SensorListParser. Also used to 
    # remove unknown elements (see `renameKeys`).
    parameterNames = {
        "Sensor": "sensors",
        "SensorID": "sensorId",
        "SensorName": "name",
        "TraceabilityData": "traceData",
        "SensorSerialNumber": "serialNum",
        "Attribute": "attributes",
#         "SensorBwLimitIDRef": "bandwidthLimitId" # FUTURE
    }
    
    def parse(self, element, **kwargs):
        """ Parse a SensorList 
        """
#         data = parse_ebml(element.value)
        data = element.dump()
        if 'attributes' in data:
            atts = self.doc.recorderInfo.setdefault('sensorAttributes', {})
            atts.update(decode_attributes(data['attributes']))
        data = renameKeys(data, self.parameterNames)
        if "sensors" in data:
            for sensor in data['sensors']:
                self.doc.addSensor(**sensor)
    

#===============================================================================
# RecordingProperties: Channel and Subchannel parsers
#===============================================================================

class ChannelParser(ElementHandler):
    """ Handle individual Channel elements. Separate from ChannelList so it can
        be subclassed for Plots. 
    """
    elementName = "Channel"
    isSubElement = True
    isHeader = True

    parameterNames = {
        # Parent `Channel parameters.
        "ChannelID": "channelId",
        "ChannelName": "name",
        # "TimeCodeScale": "timeScale",
        # "TimeCodeModulus": "timeModulus",
        "SampleRate": "sampleRate",
        "ChannelParser": "parser",
        "ChannelFormat": "format",
        "ChannelCalibrationIDRef": "transform",
        "TimeCodeScale": "timeScalar",
        "TimeCodeModulus": "timeMod",
        "cache": "cache",
        "singleSample": "singleSample",
        "SubChannel": "subchannels", # Multiple, so it will parse into a list

        # Child SubChannel parameters; `renameKeys` operates recursively.
        "SubChannelID": "subchannelId",
        "SubChannelName": "name",
        "SubChannelAxisName": "axisName",
        "SubChannelCalibrationIDRef": "transform",
        "SubChannelLabel": "label",
        "SubChannelUnits": "units",
        "SubChannelRangeMin": "rangeMin",
        "SubChannelRangeMax": "rangeMax",
        "SubChannelSensorRef": "sensorId",
        "SubChannelWarningRef": "warningId",
        "SubChannelPlotColor": "color",
        
        # Generic attribute elements.
        "Attribute": "attributes"
    }
    
    
    def parse(self, element, **kwargs):
        """ Create the `dataset.Channel` object and its `dataset.SubChannel` 
            children elements from a `Channel` element of the `ChannelList`.
        """
        data = renameKeys(element.dump(), self.parameterNames)
        
        # Pop off the subchannels; create them in a second pass.
        subchannels = data.pop('subchannels', None)
        
        channelId = data['channelId']
        
        # Parsing. Either a regular struct.Struct, or a custom parser.
        if 'parser' in data:
            # A named parser; use the special-case parser function.
            data.pop('format', None)
            data['parser'] = DATA_PARSERS[data['parser']]()
        elif 'format' in data:
            # build struct instead.
            # TODO (future): Handle special (non-standard) format characters
            data['parser'] = struct.Struct(data.pop('format'))

        # sampleRate is stored as a string to avoid floats on the recorder.
        if 'sampleRate' in data:
            data['sampleRate'] = valEval(data['sampleRate'])
        
        # Channel timestamp correction stuff.
        timeScale = data.pop('timeScalar', None)
        timeModulus = data.pop('timeMod', None)
        
        # Update timestamp modulo in parsers
        for p in [x for x in list(self.doc._parsers.values()) if x.makesData()]:
            if timeModulus is not None:
                p.timeModulus[channelId] = timeModulus
            if timeScale is not None:
                p.timeScalars[channelId] = valEval(timeScale) * 1000000.0
        
        ch = self.doc.addChannel(**data)
        
        if subchannels is not None:
            for subData in subchannels:
                displayRange = subData.pop("rangeMin", None), subData.pop("rangeMax", None)
                subData['displayRange'] = None if None in displayRange else displayRange
                units = subData.pop('label', None), subData.pop('units', None)
                if units[0] is None:
                    units = units[1], units[1]
                subData['units'] = None if None in units else units
                
                ch.addSubChannel(**subData)
        return ch


class PlotListParser(ChannelParser):
    """ Handle the parent of all `Plot` elements. 
        Note: Not currently implemented.
    """
    elementName = "PlotList"
    isSubElement = True

    # Most Plot parameters are the same as those of Subchannel. 
    parameterNames = {
        'PlotSource': 'sources',
        'PlotChannelRef': 'channelId',
        'PlotSubChannelRef': 'subchannelId'
    }
    
    def __init__(self, *args, **kwargs):
        pnames = super(PlotListParser, self).parameterNames.copy()
        self.parameterNames.update(pnames)
        self.parameterNames = pnames

    def parse(self, element, **kwargs):
        """
        """
        # FUTURE: IMPLEMENT, but later. Not required for immediate goals.
        pass
    

class ChannelListParser(ElementHandler):
    """ Handle `ChannelList` elements and their children. Just wraps the
        sub-element parsers.
    """
    elementName = "ChannelList"
    isSubElement = True
    isHeader = True
    children = (ChannelParser,) #PlotListParser)


#===============================================================================
# 
#===============================================================================

class WarningListParser(ElementHandler):
    """ Handle `WarningList` elements and their children (`Warning`).
    """
    elementName = "WarningList"
    isSubElement = True
    isHeader = True
    
    # Note: Includes child `Warning` parameters.
    parameterNames = {
        "Warning": "warnings",
        "WarningID": "warningId",
        "WarningChannelRef": "channelId",
        "WarningSubChannelRef": "subchannelId",
        "WarningRangeMin": "low",
        "WarningRangeMax": "high",
        "Attribute": "attributes"
    }
    
    def parse(self, element, **kwargs):
        raw = element.dump()
        data = renameKeys(raw, self.parameterNames)
        
        if 'warnings' in data:
            for w in data['warnings']:
                self.doc.addWarning(**w)
    
    
#===============================================================================
# RecordingProperties: RecorderInfo
#===============================================================================

class RecorderInfoParser(ElementHandler):
    """ Handle the `RecorderInfo` element, child of RecordingProperties.
    """
    elementName = "RecorderInfo"
    isSubElement = True
    
    def parse(self, element, **kwargs):
        """
        """
        # This one is simple; it just sticks the data into the Dataset.
        val = element.dump()
        if 'Attribute' in val:
            self.doc.recorderInfo.update(decode_attributes(val.pop('Attribute')))
        self.doc.recorderInfo.update(val)
        return self.doc.recorderInfo  


#===============================================================================
# 
#===============================================================================

class BwLimitListParser(ElementHandler):
    """ Handle the `BwLimitList` element, child of RecordingProperties.
    """
    elementName = "BwLimitList"
    isSubElement = True
    isHeader = True

    def parse(self, element, **kwargs):
        """
        """
        self.doc.bandwidthLimits = limits = {}
        val = element.value.dump()
        for limit in val.get('BwLimit', []):
            limitId = limit.pop('BwLimitID', None)
            if limitId is not None:
                limits[limitId] = limit
        return limits  

    
#===============================================================================
# RecordingProperties parent element parser.
#===============================================================================

class RecordingPropertiesParser(ElementHandler):
    """ Stub for RecordingProperties element handler. All relevant data is in
        its child elements.
    
        :cvar elementName: The name of the element handled by this parser
    """
    elementName = "RecordingProperties"
    isSubElement = False
    isHeader = True
    children = (RecorderInfoParser, 
                SensorListParser, 
                ChannelListParser, 
                WarningListParser)


################################################################################
#===============================================================================
#--- Miscellaneous element parsers
#===============================================================================
################################################################################

class TimeBaseUTCParser(ElementHandler):
    """ Handle TimeBaseUTC elements, applying it as the UTC start time of the
        current Session.
    """
    elementName = "TimeBaseUTC"
    isHeader = True
    
    def parse(self, element, **kwargs):
        val = element.value
        self.doc.lastUtcTime = val
        self.doc.lastSession.utcStartTime = val


class RecorderUserDataParser(ElementHandler):
    """
    """
    elementName = "RecorderUserData"
    isSubElement = True
    isHeader = True
    
    parameterNames = {"RecorderName": "RecorderName",
                      "RecorderDesc": "RecorderDescription"}

    def parse(self, element, **kwargs):
        if self.doc is not None:
            raw = element.dump()
            data = renameKeys(raw, self.parameterNames)
            self.doc.recorderInfo.update(data)


class RecorderConfigurationListParser(ElementHandler):
    """
    """
    elementName = "RecorderConfigurationList"
    isSubElement = True
    isHeader = True

    parameterNames = {0x8ff7f: "RecorderName",
                      0x9ff7f: "RecorderDescription"}
    
    def parse(self, element, **kwargs):
        if self.doc is not None:
            for el in element:
                if el[0].name != "ConfigID":
                    continue
                if el[0].value in self.parameterNames:
                    name = self.parameterNames[el[0].value]
                    self.doc.recorderInfo[name] = el[1].value


class RecorderConfigurationParser(ElementHandler):
    """ Handle Recorder configuration data in a recording. This just parses it
        and stores it verbatim.
    """
    elementName = "RecorderConfiguration"
    isHeader = True
    isSubElement = False
    children = (RecorderConfigurationListParser, RecorderUserDataParser)


class AttributeParser(ElementHandler):
    """ Handle a root-level Attribute element. 
    """
    elementName = "Attribute"
    isHeader = True
    isSubElement = False
     
    def parse(self, element, **kwargs):
        parseAttribute(self.doc, element)
        return 0

    
#===============================================================================
# 
#===============================================================================

class NullParser(ElementHandler):
    """ Dummy handler for all root level elements we know of but don't care 
        about (at least for now). Note that this includes the `EBML` element,
        because the EBML library itself has already handled it.
    """
    elementName = ('EBML',
                   'ElementTag',
                   'RecorderConfigurationList',
                   'Session',
                   'Sync',
                   'Void',
                   'UnknownElement')

    def parse(self, *args, **kwargs):
        pass
