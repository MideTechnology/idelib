"""
"""

from datetime import datetime
import os.path
import struct

from mide_ebml import importer
from mide_ebml import parsers
import dataset

#===============================================================================
# Data parsers
#===============================================================================

class AccelerometerParser(object):
    """
    """
    parser = struct.Struct("<hhh")
    format = parser.format
    size = parser.size
#     ranges = (((-0xFFF8/2) * 0.00048828125, ((0xFFF8/2)-1) * 0.00048828125)) * 3
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
    headerParser = struct.Struct("<IBxIxxbBHH")
    indexParser = struct.Struct("<HH")
    secondScalar = 1000000.0
    timeScalar = secondScalar / 2**15
    
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

    
    def findEnd(self, data, sampleSize):
        """ Find the end of the final recording session.
        """
        data = data.rtrim('\xff')
        return data[:len(data)-(len(data)%sampleSize)]
    
    
    def parseSession(self, pos, channelId=0):
        """
        """
        startPos = pos[0] * self.sectorSize
        endPos = pos[1] * self.sectorSize
        
        self.doc.file.seek(startPos)
        header = self.doc.file.read(self.headerParser.size)
        size, sampleRate, ticks, tzOffset, flags, date, time = \
            self.headerParser.unpack_from(header)
        
        dataStart = self.doc.file.tell()
        channel = self.doc.channels[channelId]
        sampLen = channel.parser.size
        
        if flags & 0x00000001:
            # 'device clock is set' bit
            timestamp = self.decodeFatDateTime(date, time, tzOffset)
        else:
            timestamp = None
        
        if ticks == 0xffffffff or size == 0xffffffff:
#             print "truncated session"
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
#             print "whole session, size=%r length=%r numSamples=%r" % (size, length, numSamples)

#         print "len(rawData)=%r" % len(rawData)
        data = []
        for i in xrange(0,size,channel.parser.size):
            try:
                data.append(channel.parser.unpack_from(rawData, i))
            except struct.error:
                print "failed to parse w/ offset %r" % i
                raise parsers.ParsingError()
#         data = [channel.parser.unpack_from(rawData, i) \
#                 for i in xrange(0,size,channel.parser.size)] 
        
        print "self.doc.addSession(%r, %r, %r, %r, %r, %r)" % (0, length,
                                  timestamp, dataStart, 
                                  dataStart+size, sampleRate)
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
            self.parseSession((0, os.path.getsize(self.doc.file.name)/512), 
                              channelId)


class FileHeaderParser(object):
    """ Parser for the file header, a/k/a the management block.
    """
    def parse(self, f):
        f.seek(0)
        

#===============================================================================
# 
#===============================================================================


# Hard-coded sensor/channel mapping for the Slam Stick Classic.
# TODO: Base default sensors on the device type UID.
default_sensors = {
    0x00: {"name": "SlamStick Classic Combined Sensor", 
           "channels": {
                0x00: {"name": "Accelerometer XYZ",
                       "parser": AccelerometerParser(),
                       "subchannels":{0: {"name": "Accelerometer X", 
                                          "units":('g','g'),
                                          "displayRange": (-100.0,100.0),
                                         },
                                      1: {"name": "Accelerometer Y", 
                                          "units":('g','g'),
                                          "displayRange": (-100.0,100.0),
                                          },
                                      2: {"name": "Accelerometer Z", 
                                          "units":('g','g'),
                                          "displayRange": (-100.0,100.0),
                                          },
                                    },
                       },
                },
           },
}


def createDefaultSensors(doc, sensors=default_sensors):
    """ Given a nested set of dictionaries containing the definition of one or
        more sensors, instantiate those sensors and add them to the dataset
        document.
    """
    for sensorId, sensorInfo in sensors.iteritems():
        sensor = doc.addSensor(sensorId, sensorInfo.get("name", None))
        for chId, chInfo in sensorInfo['channels'].iteritems():
            channel = sensor.addChannel(chId, chInfo['parser'],
                                        name=chInfo.get('name',None),
                                        channelClass=dataset.Channel)
            if 'subchannels' not in chInfo:
                continue
            for subChId, subChInfo in chInfo['subchannels'].iteritems():
                channel.addSubChannel(subChId, channelClass=dataset.SubChannel,
                                      **subChInfo)


#===============================================================================
# 
#===============================================================================

def importFile(f, defaultSensors=default_sensors):
    """
    """
    if isinstance(f, basestring):
        f = open(f, 'rb')
    doc = dataset.Dataset(f)
    if defaultSensors is not None:
        createDefaultSensors(doc, defaultSensors)
    parser = RecordingParser(doc)
    parser.parse()
    return doc
    
    
def readData(doc, updater=importer.nullUpdater, numUpdates=500, 
             updateInterval=1.0, parserTypes=None, 
             defaultSensors=default_sensors):
    """ 
    """
    
    updater(0)

    if defaultSensors is not None:
        createDefaultSensors(doc, defaultSensors)
    parser = RecordingParser(doc)
    parser.parse()

    updater(count=1, percent=1.0)
    updater(done=True)#, total=eventsRead)

    doc.loading = False
    return doc
