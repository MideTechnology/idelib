'''

FOR TESTING: 

Read entire file:
import importer; doc=importer.importFile(updater=importer.SimpleUpdater()); l=doc.channels[0].getSession(0)

Read 25%
import importer; doc=importer.importFile(updater=importer.SimpleUpdater(0.25)); l=doc.channels[0].getSession(0)

Time to read file:
From Slam Stick X: 0:06:47.506000
'''

from datetime import datetime
# import os
import struct
import sys
import time

from dataset import Dataset, Transform
import parsers

from dataset import __DEBUG__

#===============================================================================
# Parsers/Element Handlers
#===============================================================================

# Parser importer. These are taken from the module by type. We may want to 
# create the list of parser types 'manually' in the real app; it's marginally 
# safer.
elementParserTypes = parsers.getElementHandlers()

#===============================================================================
# Defaults
#===============================================================================

# XXX: Remove me before production.
# testFile = r"e:\test.dat"
# testFile = r"test_full_cdb.DAT"
testFile = r"P:\WVR_RIF\04_Design\Electronic\Software\testing\test_ebml_files\test_full_cdb_huge.dat"


class AccelTransform(Transform):
    """ A simple transform to convert accelerometer values (recorded as
        uint16) to floats in the range -100 to 100 G.
        
        Do not use if using already `AccelerometerParser` to parse the 
        channel.
    """
    def __call__(self, event, channel=None, session=None):
        return event[:-1] + ((event[-1] * 200.0) / 65535 - 100,)

# from parsers import AccelerometerParser

# Hard-coded sensor/channel mapping. Will eventually be read from EBML file,
# but these should be default for the standard Slam Stick X.
default_sensors = {
    0x00: {"name": "SlamStick Combined Sensor", 
           "channels": {
                0x00: {"name": "Accelerometer XYZ",
                       "parser": struct.Struct("<HHH"), #AccelerometerParser(),
                        "calibration": (AccelTransform(),
                                        AccelTransform(),
                                        AccelTransform()),
                        "subchannels":{0: {"name": "X", 
                                           "units":('G','G')},
                                       1: {"name": "Y", 
                                           "units":('G','G')},
                                       2: {"name": "Z", 
                                           "units":('G','G')},
                                    },
                       },
                0x40: {"name": "Pressure/Temperature",
                       "parser": parsers.MPL3115PressureTempParser(),
                       "subchannels": {0: {"name": "Pressure", 
                                           "units":('kPa','kPa')},
                                       1: {"name": "Temperature", 
                                           "units":(u'\xb0C',u'\xb0C')}
                                       },
                       },
                0x43: {"name": "Crystal Drift",
                       "parser": struct.Struct(">II") 
                       },
                0x45: {"name": "Gain/Offset",
                       "parser": struct.Struct("<i"), 
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
        for channelId, channelInfo in sensorInfo['channels'].iteritems():
            channel = sensor.addChannel(channelId, channelInfo['parser'],
                                        name=channelInfo.get('name',None),
                                        calibration=channelInfo.get('calibration',None))
            if 'subchannels' not in channelInfo:
                continue
            for subChId, subChInfo in channelInfo['subchannels'].iteritems():
                channel.addSubChannel(subChId, **subChInfo)
    


#===============================================================================
# Updaters
#===============================================================================

def nullUpdater(*args, **kwargs):
    """ A progress updater stand-in that does nothing. """
    if kwargs.get('error',None) is not None:
        raise kwargs['error']
nullUpdater.cancelled = False


class SimpleUpdater(object):
    """ A simple text-based progress updater.
    
        @todo: Make cross-platform? Character 0x0D won't necessarily work
            outside of Windows.
    """
    
    def __init__(self, cancelAt=1.0):
        self.cancelled = False
        self.startTime = None
        self.cancelAt = cancelAt
        self.estSum = None
        
    def __call__(self, count=0, total=None, percent=None, error=None, 
                 starting=False, done=False):
        if percent >= self.cancelAt:
            self.cancelled=True
        if self.startTime is None:
            self.startTime = datetime.now()
        if starting:
            "Import started at %s" % self.startTime
            return
        if done:
            print "\nImport completed in %s" % (datetime.now() - self.startTime)
            print "Original estimate was %s" % self.estSum
        else:
            sys.stdout.write('\x0d%s samples read' % count)
            if percent is not None:
                p = int(percent*100)
                sys.stdout.write(' (%d%%)' % p)
                if p > 0 and p < 100:
                    d = ((datetime.now() - self.startTime) / p) * (100-p)
                    sys.stdout.write(' - est. completion in %s' % d)
                    if self.estSum is None:
                        self.estSum = d
                else:
                    sys.stdout.write(' '*25)
            sys.stdout.flush()

    

#===============================================================================
# ACTUAL FILE READING HAPPENS BELOW
#===============================================================================

def importFile(filename=testFile, updater=None, numUpdates=500, 
               updateInterval=1.0, parserTypes=elementParserTypes, 
               defaultSensors=default_sensors):
    """ Create a new Dataset object and import the data from a MIDE file. 
        Primarily for testing purposes. The GUI does the file creation and 
        data loading in two discrete steps, as it will need a reference to 
        the document before the loading starts.
    """
    stream = open(filename, "rb")
    doc = Dataset(stream)
    readData(doc, updater=updater, numUpdates=numUpdates, 
             updateInterval=updateInterval, parserTypes=parserTypes, 
             defaultSensors=defaultSensors)
    return doc


def readData(doc, updater=None, numUpdates=500, updateInterval=1.0,
             parserTypes=elementParserTypes, defaultSensors=default_sensors):
    """ Import the data from a file into a Dataset.
    
        @param doc: The Dataset document into which to import the data.
        @keyword updater: A function (or function-like object) to notify
            as work is done. It should take four keyword arguments:
            `count` (the current line number), `total` (the total number of
            lines), `error` (an unexpected exception, if raised during the
            import), and `done` (will be `True` when the export is
            complete). If the updater object has a `cancelled`
            attribute that is `True`, the CSV export will be aborted.
            The default callback is `None` (nothing will be notified).
        @keyword numUpdates: The minimum number of calls to the updater to be
            made. 
        @keyword updateInterval: The maximum number of seconds between
            calls to the updater
        @keyword parserTypes: 
        @keyword defaultSensors:
 
    """
    
    if updater is None:
        updater = nullUpdater
    
    elementParsers = dict([(f.elementName, f(doc)) for f in parserTypes])

    doc.addSession(0)

    elementCount = 0
    eventsRead = 0
    
    # Progress display stuff
    filesize = doc.ebmldoc.stream.size
    
    if numUpdates > 0:
        ticSize = filesize / numUpdates 
    else:
        # An unreachable file position effectively disables the updates.
        ticSize = filesize+1
    
    if updateInterval > 0:
        nextUpdateTime = time.time() + updateInterval
    else:
        # An update time 24 hours in the future should mean no updates.
        nextUpdateTime = time.time() + 5184000
    
    firstDataPos = 0
    nextUpdatePos = ticSize
    
    readRecordingProperties = False
    readingData = False
    
    try:    
        for r in doc.ebmldoc.iterroots():
            if getattr(updater, "cancelled", False):
                doc.loadCancelled = True
                break

            if r.name in elementParsers:
                readRecordingProperties = r.name == "RecordingProperties" 
                parser = elementParsers[r.name]
                    
                if not readingData and parser.makesData():
                    # The first data has been read. Notify the updater!
                    updater(0)
                    if not readRecordingProperties:
                        # Got data before the recording props; use defaults.
                        if defaultSensors is not None:
                            createDefaultSensors(doc, defaultSensors)
                        readRecordingProperties = True
                    firstDataPos = r.stream.offset
                    dataSize = filesize - firstDataPos + 0.0
                    readingData = True
            
                added = parser(r)
                if added is not None:
                    eventsRead += added

            else:
                # Unknown block type
                if __DEBUG__ is True:
                    print "unknown block %r (ID %r), continuing" % \
                        (r.name, r.id)
                pass
            
            # More progress display stuff
            # TODO: Possibly do the update check every nth elements.
            #    That would have slightly less work per cycle.
            thisOffset = r.stream.offset
            thisTime = time.time()
            if thisTime > nextUpdateTime or thisOffset > nextUpdatePos:
                # Update progress bar
                updater(count=eventsRead,
                        percent=(thisOffset-firstDataPos)/dataSize)
                nextUpdatePos = thisOffset + ticSize
                nextUpdateTime = thisTime + updateInterval
             
            elementCount += 1
            
    except IOError as e:
        if e.errno is None:
            # The EBML library raises an empty IOError if it his EOF.
            # TODO: Handle other cases of empty IOError (lots in python-ebml)
            doc.fileDamaged = True
        else:
            updater(error=e)
        
        
    # finish progress bar
    updater(done=True, total=eventsRead)
        
    doc.loading = False
    return doc

