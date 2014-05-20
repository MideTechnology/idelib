"""
"""

import struct

headerParser = struct.Struct("<IBxIxxBBHH")

class DataParser(struct.Struct):
    ranges = (((-0xFFF8/2), (0xFFF8/2)-1),) * 3
    
    def unpack_from(self, data, offset=0):
        data = super(DataParser, self).unpack_from(data, offset)
        return (data[0] & 0xFFF8, data[1] & 0xFFF8, data[2] & 0xFFF8)


class RecordingHeaderParser(struct.Struct):
    headerParser = struct.Struct("<IBxIxxBBHH")
    
    def decodeFatDateTime(self, raw_date, raw_time):
        year = ((raw_date & 0xFE00) >> 9) + 1980 # correct for "years since 1980" offset
        month = (raw_date & 0x01E0) >> 5
        day = (raw_date & 0x001F)
        
        hour = (raw_time & 0xF800) >> 11
        minute = (raw_time & 0x07E0) >> 5
        second = (raw_time & 0x001F) << 1
    
    def decodeFatDate(self, raw_date):
        pass
        
    def unpack_from(self, data, offset=0):
        data = super(RecordingHeaderParser, self).unpack_from(data, offset)



class FileHeaderParser(object):
    """ Parser for the file header, a/k/a the management block.
    """
    def parse(self, f):
        f.seek(0)
        
    
