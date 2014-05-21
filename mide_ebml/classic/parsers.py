"""
"""

from datetime import datetime
import os.path
import struct


#===============================================================================
# Data parsers
#===============================================================================

class AccelerometerParser(object):
    """
    """
    parser = struct.Struct("<hhh")
    format = parser.format
    size = parser.size
    ranges = (((-0xFFF8/2) * 0.00048828125, ((0xFFF8/2)-1) * 0.00048828125)) * 3
        
    def adjustment(self, val): 
        return val * 0.00048828125 
        
    def unpack_from(self, data, offset=0):
        return tuple(map(self.adjustment, 
                         self.parser.unpack_from(data, offset)))

#===============================================================================
# 
#===============================================================================

class RecordingHeaderParser(object):
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
    headerParser = struct.Struct("<IBxIxxbBHH")
    timeScalar = 1000000.0 / 2**15
    
    def __init__(self, doc, **kwargs):
        self.doc = doc
        
        
    def decodeFatDateTime(self, raw_date, raw_time, tzoffset):
        year = ((raw_date & 0xFE00) >> 9) + 1980 # fix "years since 1980" offset
        month = (raw_date & 0x01E0) >> 5
        day = (raw_date & 0x001F)
        
        hour = (raw_time & 0xF800) >> 11
        minute = (raw_time & 0x07E0) >> 5
        second = (raw_time & 0x001F) << 1
        
        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            return None

    
    def findEnd(self, startPos, bufferSize=1024):
        """ Find the end of the final recording session.
        """
        filesize = os.path.getsize(self.doc.filename)
        fileEnd = filesize - ((filesize - startPos) % 6)
        bufferSize = min(bufferSize, fileEnd-startPos)
        i = 1
        idx = 0
        pos = fileEnd - bufferSize
        while pos > startPos:
            self.doc.file.seek(pos)
            buf = self.doc.file.read(bufferSize)
            idx = buf.find('\xff\xff') # Two should only appear in bad data
            if idx != 0:
                break
            i += 1
            pos = (fileEnd - (bufferSize*i))

        if idx == -1:
            end = self.doc.file.tell()
        else:
            end = fileEnd - (bufferSize*i) + idx
            
        self.doc.file.seek(startPos)
        return end 
    
    
    def parseSession(self, pos):
        """
        """
        raw = self.doc.file.read(self.headerParser.size)
        size, sampleRate, ticks, tzOffset, flags, date, time = \
            self.headerParser.unpack_from(raw)
            
        dataStart = self.doc.file.tell()
        
        if flags & 0x00000001:
            # 'device clock is set' bit
            timestamp = self.decodeFatDate(date, time, tzOffset)
        else:
            timestamp = None
        
        if ticks == 0xffffffff or size == 0xffffffff:
            # Abnormally terminated file; seek the end and calculate size, etc.
            size = self.findEnd(dataStart) - dataStart
            sampleRate = (6.25 * (2 ** (sampleRate - 6))) # in Hz
            length = ((size/3) / sampleRate) * 1000000
        else:
            # Nicely terminated file with valid size and ticks fields.
            length = ticks * self.timeScalar # converted to microseconds
            sampleRate = ((size/3) / length) / 1000000
        
        self.doc.addSession(startTime=0, endTime=length,
                 utcStartTime=timestamp, offset=dataStart, 
                 endPos=dataStart+size, sampleRate=sampleRate)
    
    
    def parse(self, f):
        pass


class FileHeaderParser(object):
    """ Parser for the file header, a/k/a the management block.
    """
    def parse(self, f):
        f.seek(0)
        


