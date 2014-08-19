"""
"""

import os.path
import struct
import time

from mide_ebml import parsers

#===============================================================================
# Data parsers
#===============================================================================

class AccelerometerParser(object):
    """
    """
    parser = struct.Struct("<hhh")
    format = parser.format
    size = parser.size
    ranges = ((-0xFFF8>>4) * 0.00048828125, 
              ((0xFFF8>>4)-1) * 0.00048828125) * 3
        
    def adjustment(self, val): 
        return val * 0.00048828125 
        
    def unpack_from(self, data, offset=0):
        return tuple(map(self.adjustment, 
                         self.parser.unpack_from(data, offset)))


#===============================================================================
# 
#===============================================================================

class RecordingParser(object):
    """
        classic header struct: "<IBxIxxBBHH"
            * (uint32-LE) Recording size in bytes, including header
            * (uint8) Sample rate code (contents of ADXL345 BW_RATE register)
            * 1 byte padding/unused (reserved)
            * (uint32-LE) Number of ticks elapsed (32.768KHz)
            * 2 bytes padding/unused
            * (uint8) flags
            * (uint8) 1 byte time zone offset
            * (uint16-LE) Date in FAT encoded format (v2+ only)
            * (uint16-LE) Time in FAT encoded format (v2+ only)
            
        sample rate = (6.25 * (2 ** (samprateCode - 6)))
    """
    sectorSize = 512
    headerParser = struct.Struct("<IBxIxxBBHH")
    indexParser = struct.Struct("<HH")
    secondScalar = 1000000.0
    timeScalar = secondScalar / 2**15
    
    def __init__(self, doc, **kwargs):
        self.doc = doc
        self.filesize = os.path.getsize(self.doc.file.name)
        
        
    def decodeFatDateTime(self, raw_date, raw_time, tzoffset):
        year = ((raw_date >> 9) & 0x7f) + 1980 # fix "years since 1980" offset
        month = (raw_date >> 5) & 0x0f
        day = (raw_date & 0x1f)
        
#         raw_time >>= 16
        second = (raw_time & 0x1f) * 2
        minute = (raw_time >> 5) & 0x3f
        hour = (raw_time >> 11) & 0x1f
#         hour = (raw_time & 0xF800) >> 11
#         minute = (raw_time & 0x07E0) >> 5
#         second = (raw_time & 0x001F) << 1

        try:
#             return datetime(year, month, day, hour, minute, second)
            return time.mktime((year, month, day, hour, minute, second,0,0,0))
        except ValueError:
            return None

    
    def findEnd(self, data, sampleSize):
        """ Find the end of the final recording session.
        """
        data = data.rstrip('\xff')
        return data[:len(data)-(len(data)%sampleSize)]
    
    
    def parseSession(self, pos, channelId=0):
        """
        """
        startPos = pos[0] * self.sectorSize
        endPos = pos[1] * self.sectorSize
        
        if startPos >= self.filesize:
            raise parsers.ParsingError("Classic data file appears damaged.")
        if endPos > self.filesize:
            endPos = self.filesize
        
        self.doc.file.seek(startPos)
        header = self.doc.file.read(self.headerParser.size)
        size, sampleRate, ticks, flags, tzOffset, date, time = \
            self.headerParser.unpack_from(header)
        
        dataStart = self.doc.file.tell()
        channel = self.doc.channels[channelId]
        sampLen = channel.parser.size
        
#         print "flags: %s, date: %x, time: %x" % (bin(flags), date, time)
        if flags & 0x01 and not flags & 0b10000000:
            # 'device clock is set' bit, and flags aren't invalid
            timestamp = self.decodeFatDateTime(time, date, tzOffset)
        else:
            timestamp = None
        
        if ticks == 0xffffffff or size == 0xffffffff:
            # Abnormally terminated file; seek the end and calculate size, etc.
            rawData = self.findEnd(self.doc.file.read(), sampLen)
            size = len(rawData)
            numSamples = size/sampLen
            sampleRate = (6.25 * (2 ** (sampleRate - 6))) # in Hz
            length = (numSamples / sampleRate) * self.secondScalar
        else:
            # Nicely terminated file with valid size and ticks fields.
            size = min(size-self.headerParser.size, endPos-dataStart)
            size -= size % sampLen
            rawData = self.doc.file.read(size)
            length = ticks * self.timeScalar # converted to microseconds
            numSamples = size/sampLen
            sampleRate = (numSamples / length) * self.secondScalar

        data = []
        for i in xrange(0,size,channel.parser.size):
            try:
                data.append(channel.parser.unpack_from(rawData, i))
            except struct.error:
                print "failed to parse w/ offset %r" % i
                raise parsers.ParsingError()
        
        session = self.doc.addSession(startTime=0, endTime=length,
                                  utcStartTime=timestamp, offset=dataStart, 
                                  endPos=dataStart+size, sampleRate=sampleRate)
        channel.getSession(session.sessionId).setData(data)
        
        return numSamples
        
    
    def parse(self, channelId=0):
        self.doc.file.seek(0)
        code = self.doc.file.read(4)
        if code == "VR20":
            # Multi-session (or at least not definitely single-session)
            sessions = []
            for _ in xrange(1023):
                data = self.doc.file.read(self.indexParser.size)
                if data == "\xff\xff\xff\xff":
                    break
                sessions.append(self.indexParser.unpack(data))
            for s in sessions:
#                 print "parsing session %r" % list(s)
                self.parseSession(s, channelId)
            pass
        else:
            try:
                n = self.parseSession((0, os.path.getsize(self.doc.file.name)/512), 
                                      channelId)
            except parsers.ParsingError as err:
                raise err
            except Exception:
                raise parsers.ParsingError()

            if n < 1: 
                raise parsers.ParsingError(
                               "File does not appear to be a Classic data file")


class FileHeaderParser(object):
    """ Parser for the file header, a/k/a the management block.
    """
    def parse(self, f):
        f.seek(0)
        

