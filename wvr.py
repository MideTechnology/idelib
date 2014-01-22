'''
NOTE: This requires that the modified version of the EBML library be used:
the one with the Mide extensions to the schema set.

Created on Sep 24, 2013
@author: dstokes
'''

from collections import OrderedDict
import struct

# from ebml.schema import EBMLDocument, UnknownElement, CONTAINER, BINARY
from ebml.schema import UnknownElement
from ebml.schema.mide import MideDocument

from dataset import Dataset, Session, Channel, SubChannel, SuperChannel, MultiEventSuperChannel


# XXX: Remove me (and all references to me)
DEBUG = True

class ParsingError(IOError):
    """ Exception raised for any failure to parse a WVR EBML file. """
    pass


class SimpleWvrData(Dataset):
    """
    """

    def _reportError(self, msg):
        """ Wrapper for survivable exceptions. Will raise an exception if 
            the SimpleWvrData instance's `quiet` attribute is `False`. A 
            debugging message will be printed if the `debug` attribute is
            `True`. 
            
            @todo: Use standard Python logging framework?
            
            @param msg: The message or exception to display. If `msg` is
                a string and `quiet` is `False`, it is used as the message
                in a `ParsingError`.
        """
        if self.debug:
            print "*** %r" % msg
        if not self.quiet:
            if isinstance(msg, Exception):
                raise msg
            raise ParsingError(msg)
            
    
    #===========================================================================
    # 
    #===========================================================================
    
    # The size of a SimpleChannelDataBlock 'header' (timestamp and channel no.)
    HEADER_SISE = struct.calcsize("<HB")
    
    TIMESTAMP_SIZE = (2**16)
    
    
    #===========================================================================
    # Element parsers. Named "_parse_" + element name.
    #===========================================================================
    
    def _parse_SimpleChannelDataBlock(self, element):
        """ Parser for `SimpleChannelDataBlock` elements. Mainly calls the
            appropriate channel-specific parser.
        """
        channel = struct.unpack_from("<HB", element.value)[1]
        channelParserName = "_parse_SimpleChannelDataBlock_0x%02X" % channel
        parser = getattr(self, channelParserName, None)
        if parser is None:
            self._reportError("Unrecognized channel 0x%02x in element %s (id=0x%02x)" % \
                              (channel, element.name, element.id))
            return None
        return parser(element)


    def _parse_ElementTag(self, element):
        """ Parser for `ElementTag` elements. Doesn't do anything ATM.
        """
        # TODO: Write me!
        pass
    

    #===========================================================================
    # Parsers for specific SimpleChannelDataBlock channels.
    # Named "_parse_SimpleChannelDataBlock" + channel number in hex (in caps) 
    #===========================================================================
    
    def getTimestampAndChannel(self, element):
        """ Return the timestamp and channel number of a block. Doesn't touch
            the rest of its data.
        """
        try:
            return struct.unpack_from("<HB", element.value)
        except TypeError:
            return None, None
    
    
    def splitData(self, element, structure=None):
        """ Split an element's contents into timestamp, channel number, and
            raw data. 
            
            @keyword structure: An additional `struct` format string to apply
                to the data. Simplifies parsing elements with simple contents.
        """
        timestamp, channel = struct.unpack_from("<HB", element.value)
        rawdata = element.value[self.HEADER_SISE:]
        if structure is not None:
            try:
                rawdata = struct.unpack_from(structure, rawdata)
            except struct.error as e:
                self._reportError("%s id=0x%02x channel 0x%02x: %s" % \
                              (element.name, element.id, channel, e.msg))
        return timestamp, channel, rawdata
    
    
    def _parse_SimpleChannelDataBlock_0x00(self, element):
        """ Parse XYZ accelerometer data (channel number 0).
        """
        timestamp, channel, rawdata = self.splitData(element)
        if len(rawdata) % 6 != 0 or len(rawdata) == 0:
            self._reportError("%s id=0x%02x channel 0x02 (XYZ) had bad length: %i" % \
                              (element.name, element.id, len(rawdata)))
            return []
        data = [struct.unpack_from(">HHH", rawdata, offset=i) for i in xrange(0, len(rawdata), 6)]
        return timestamp, channel, data
        

    def _parse_SimpleChannelDataBlock_0x40(self, element):
        """ Parse the native-format pressure/temperature from MPL3115 sensor
            (channel number 64) into a pair of standard floats.
        """
        # native-format pressure/temperature from MPL3115 sensor
        # Diag pres/temp data format is 5-byte total 3-byte barometric pressure, 2 byte degC
        # Pressure is: top 18 bits [23..6] signed, next 2 bits [5..4] fractional (unsigned), bits [3..0] don't care.
        # Temperature is: top 8 bits [15..8] signed, next 4 bits [7..4] fractional (unsigned), bits [3..0] don't care.
        # TODO: Make sure if fractional part is calculated correctly for negative values 
        timestamp, channel, rawdata = self.splitData(element)
        rawpressure, rawtemp = struct.unpack(">li", chr(0)+rawdata[:5])
        fracpressure = (abs(rawpressure) >> 3 & 0b11) * 0.25
        fractemp = (abs(rawtemp) >> 3 & 0b11) * 0.25

        pressure = rawpressure >> 5 + fracpressure #         pressure /= 64.0 #(2**6 + 0.0)
        temperature = rawtemp >> 5 + fractemp #         temperature /= 256.0 #(2**8 + 0.0)

        return timestamp, channel, (pressure, temperature)


    def _parse_SimpleChannelDataBlock_0x43(self, element):
        """ Parse crystal drift diagnostic data (channel number 67)
        """
        # Unpack timecode, channel, tccounts, hftcounts; send the latter two
        return self.splitData(element, ">II")
        
   
    def _parse_SimpleChannelDataBlock_0x45(self, element):
        """ Parse uint32_t gain/offset combined result (channel 69)
        """
        return self.splitData(element, "<i")
    
    
    def hasSubsamples(self, channel):
        """ Returns whether a given channel number contains multiple data.
        """
        return channel in (0x00, )
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    def parseElement(self, element):
        """ Generic wrapper for parsing the contents of a 
        """
        if isinstance(element, UnknownElement):
            return None
        
        parserName = "_parse_%s" % element.name
        parser = getattr(self, parserName, None)
        if parser is None:
            self._reportError("No parser for element %s (i.e. %s)" % \
                              (element.name, parserName))
            return None
        return parser(element)
    
        
    #===========================================================================
    # 
    #===========================================================================

    def __init__(self, stream, quiet=False, debug=DEBUG):
        """
        """
        self.debug = debug
        self.quiet = quiet
        
        self.roots = []
        self.elements = {}
        self.sampleRates = {}
        self.fileDamaged = False
        
        super(SimpleWvrData, self).__init__(stream)
        
        try:
            lastStamps = {}
            stampOffsets = {}
            for root in self.doc.iterroots():
                timestamp, channel = self.getTimestampAndChannel(root)
                if timestamp is not None:
                    self.roots.append(root)
                    timestamp += stampOffsets.setdefault(channel, 0)
                    if timestamp < lastStamps.get(channel, 0):
                        timestamp += self.TIMESTAMP_SIZE
                        stampOffsets[channel] += self.TIMESTAMP_SIZE
                    self.elements.setdefault(channel, OrderedDict())[timestamp] = root
                    lastStamps[channel] = timestamp
        except IOError as e:
            self.fileDamaged = True
            self._reportError(e)
            

    def getSampleRate(self, channel):
        """ Returns the sample rate of a given channel. For channels without
            subsamples, this is just the time between elements. For channels
            with multiple samples per element, this time is divided by the
            number of samples. A constant sample rate is presumed.
        """
        if channel not in self.elements:
            return None
        if channel in self.sampleRates:
            return self.sampleRates[channel]
        if len(self.elements.get(channel, "")) < 2:
            self.sampleRates[channel] = -1
            return -1
        keys = self.elements[channel].keys()
        keys.sort()
        sampleRate = keys[1] - keys[0]
        if self.hasSubsamples(channel):
            subsamples = len(self.parseElement(self.elements[channel][keys[0]])[2])
            if subsamples > 0:
                sampleRate /= subsamples
        self.sampleRates[channel] = sampleRate
        return sampleRate
        
            
    def getRange(self, channel, startTime=0, endTime=-1):
        """ Get a set of data occurring in a given interval.
        """
        result = []
        stamps = self.elements[channel].keys()
        hasSubsamples = self.hasSubsamples(channel)
        startIdx = self._getClosestIdx(stamps, startTime, hasSubsamples)
        endIdx = self._getClosestIdx(stamps, endTime, not hasSubsamples)
        if self.hasSubsamples(channel):
            for s in stamps[startIdx:endIdx]:
                result.extend(self.getSubsamples(self.elements[channel][s], startTime, endTime))
        else:
            for s in stamps[startIdx:endIdx]:
                result.append(self.parseElement(self.elements[channel][s]))
        return result


    def getSubsamples(self, element, startTime, endTime):
        """
        """
        timestamp, channel, data = self.parseElement(element)
        sampleRate = self.getSampleRate(channel)
        stamps = [timestamp + sampleRate * i for i in xrange(len(data))]
        startIdx = self._getClosestIdx(stamps, startTime, True)
        endIdx = self._getClosestIdx(stamps, endTime)
        return zip(stamps, data)[startIdx:endIdx]
        
    
    
    def _getClosestIdx(self, stamps, val, roundDown=False):
        """
        """
        lenStamps = len(stamps)
        
        if val == -1 or val > stamps[-1]:
            return lenStamps
        if val < stamps[0]:
            return 0
        if val > stamps[-1]:
            return lenStamps
        
        try:
            return stamps.index(val)
        except ValueError: 
            pass
        
        def _getClosest(start, stop):
            if stop - start < 2:
                return start if roundDown else stop
            middle = (start + stop) / 2
            if stamps[middle] > val:
                return _getClosest(start, middle)
            return _getClosest(middle, stop)
        
        return _getClosest(0, lenStamps)
                

#===============================================================================
# 
#===============================================================================

dataFilename = "test.dat"
stream = None

def load(filename=dataFilename):
    print "Loading from %s" % filename
    global stream
    global dataFilename
    if isinstance(stream, file):
        if stream.name != filename:
            stream.close()
        if stream.closed():
            stream = open(filename, "rb")
        else:
            stream.seek(0)
    else:
        stream = open(filename, "rb")

    return SimpleWvrData(stream)