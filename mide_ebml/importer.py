'''

FOR TESTING: 

From outside the mide_ebml directory:

Read entire file:
from mide_ebml import importer; doc=importer.importFile(updater=importer.SimpleUpdater()); ax=doc.channels[0][2].getSession(0)

Read 25%
from mide_ebml import importer; doc=importer.importFile(updater=importer.SimpleUpdater(0.25)); ax=doc.channels[0][2].getSession(0)

profiling: 
import cProfile; cProfile.run('list(ax.iterResampledRange(566293, 2350113, 2250.0, padding=1))', sort='cumtime')

Time to read file:
From Slam Stick X: 0:06:47.506000
'''

from datetime import datetime
import struct
import sys
import time

import calibration
from dataset import Dataset
import parsers

#===============================================================================
# 
#===============================================================================

from dataset import __DEBUG__

import logging
logger = logging.getLogger('mide_ebml')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")

if __DEBUG__:
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.ERROR)

#===============================================================================
# Parsers/Element Handlers
#===============================================================================

# Parser importer. These are taken from the module by type. We may want to 
# create the list of parser types 'manually' prior to release; it's marginally 
# safer.
elementParserTypes = parsers.getElementHandlers()

#===============================================================================
# Defaults
#===============================================================================

# XXX: Remove me before production.
# testFile = "P:\\WVR_RIF\\06_Testing_Calibration\\08_Pressure_Tests\\01_Test_to_28000ft\\Slamstick_Data\\VIB00014.IDE"
# testFile= "\\\\MIDE2007\\projects\\WVR_RIF\\06_Testing_Calibration\\20140127_SNAKE_Prototype_Test\\20140127_y_sweep.IDE"
# testFile = r"P:\WVR_RIF\04_Design\Electronic\Software\testing\20140328_auto_rearm\VIB00001.IDE"
#testFile= "Firmware20140328.IDE"
testFile = r"P:\WVR_RIF\04_Design\Electronic\Software\testing\test_ebml_files\20140423_stats_newformat.ide"
# testFile= "C:\\Users\\dstokes\\workspace\\SSXViewer\\20140501_Mean_Removal\\VIB00000.IDE"

# from parsers import AccelerometerParser

# Hard-coded sensor/channel mapping. Will eventually be read from EBML file,
# but these should be default for the standard Slam Stick X.
# TODO: Base default sensors on the device type UID.
default_sensors = {
    0x00: {"name": "SlamStick Combined Sensor", 
           "channels": {
                0x00: {"name": "Accelerometer XYZ",
                       "parser": parsers.AccelerometerParser(),
                       "transform": (calibration.AccelTransform(),
                                     calibration.AccelTransform(),
                                     calibration.AccelTransform()),
                       "subchannels":{0: {"name": "Accelerometer Z", 
                                          "units":('g','g'),
                                          "displayRange": (-100.0,100.0),
                                          "transform": 3,
                                         },
                                      1: {"name": "Accelerometer Y", 
                                          "units":('g','g'),
                                          "displayRange": (-100.0,100.0),
                                          "transform": 2,
                                          },
                                      2: {"name": "Accelerometer X", 
                                          "units":('g','g'),
                                          "displayRange": (-100.0,100.0),
                                          "transform": 1,
                                          },
                                    },
                       },
                0x01: {"name": "Pressure/Temperature",
                       "parser": parsers.MPL3115PressureTempParser(),
                       "subchannels": {0: {"name": "Pressure", 
                                           "units":('Pa','Pa'),
                                           "displayRange": (0.0,120000.0),
                                           },
                                       1: {"name": "Temperature", 
                                           "units":(u'\xb0C',u'\xb0C'),
                                           "displayRange": (-40.0,80.0),
                                           }
                                       },
                       "cache": True,
                       },
                },
           },
}


# if __DEBUG__:
#     default_sensors[0x00]["channels"].update({
#                     0x43: {"name": "DEBUG Crystal Drift",
#                            "parser": struct.Struct(">II")},
#                     0x45: {"name": "DEBUG Gain/Offset",
#                            "parser": struct.Struct("<i")},
#     })


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
                                        transform=chInfo.get('transform',None),
                                        cache=chInfo.get('cache', False))
            if 'subchannels' not in chInfo:
                continue
            for subChId, subChInfo in chInfo['subchannels'].iteritems():
                channel.addSubChannel(subChId, **subChInfo)
    


#===============================================================================
# Updater callbacks
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
        """ Constructor.
            @keyword cancelAt: A percentage at which to abort the import. For
                testing purposes.
        """
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
            logger.info("Import started at %s" % self.startTime)
            return
        if done:
            logger.info("Import completed in %s" % (datetime.now() - self.startTime))
            logger.info("Original estimate was %s" % self.estSum)
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

def importFile(filename=testFile, updater=nullUpdater, numUpdates=500, 
               updateInterval=1.0, parserTypes=elementParserTypes, 
               defaultSensors=default_sensors, name=None, quiet=False):
    """ Create a new Dataset object and import the data from a MIDE file. 
        Primarily for testing purposes. The GUI does the file creation and 
        data loading in two discrete steps, as it will need a reference to 
        the new document before the loading starts.
        @see: `readData`
    """
    stream = open(filename, "rb")
    doc = Dataset(stream, name=name, quiet=quiet)
    readData(doc, updater=updater, numUpdates=numUpdates, 
             updateInterval=updateInterval, parserTypes=parserTypes, 
             defaultSensors=defaultSensors)
    return doc


def readData(doc, updater=nullUpdater, numUpdates=500, updateInterval=1.0,
             parserTypes=elementParserTypes, defaultSensors=default_sensors):
    """ Import the data from a file into a Dataset.
    
        @param doc: The Dataset document into which to import the data.
        @keyword updater: A function (or function-like object) to notify as 
            work is done. It should take four keyword arguments: `count` (the 
            current line number), `total` (the total number of samples), `error` 
            (an unexpected exception, if raised during the import), and `done` 
            (will be `True` when the export is complete). If the updater object 
            has a `cancelled` attribute that is `True`, the import will be 
            aborted. The default callback is `None` (nothing will be notified).
        @keyword numUpdates: The minimum number of calls to the updater to be
            made. More updates will be made if the updates take longer than
            than the specified `updateInterval`. 
        @keyword updateInterval: The maximum number of seconds between calls to 
            the updater. More updates will be made if indicated by the specified
            `numUpdates`.
        @keyword parserTypes: A collection of `parsers.ElementHandler` classes.
        @keyword defaultSensors: A nested dictionary containing a default set 
            of sensors, channels, and subchannels. These will only be used if
            the dataset contains no sensor/channel/subchannel definitions. 
    """
    
    elementParsers = dict([(f.elementName, f(doc)) for f in parserTypes])

    doc.addSession(0)

    elementCount = 0
    eventsRead = 0
    
    # Progress display stuff
    filesize = doc.ebmldoc.stream.size
    dataSize = filesize
    
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
                try:
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
                
                    added = parser.parse(r)
                    if isinstance(added, int):
                        eventsRead += added
                        
                except parsers.ParsingError as err:
                    # TODO: Error messages
                    logger.error("Parsing error during import: %s" % err)
                    continue

            else:
                # Unknown block type
                logger.warning("unknown block %r (ID 0x%02x) @%d" % \
                               (r.name, r.id, r.stream.offset))
                continue
            
            # More progress display stuff
            # TODO: Possibly do the update check every nth elements; that would
            #    have slightly less work per cycle.
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
            # The EBML library raises an empty IOError if it hits EOF.
            # TODO: Handle other cases of empty IOError (lots in python-ebml)
            doc.fileDamaged = True
        else:
            updater(error=e)
        
        
    # finish progress bar
    updater(done=True, total=eventsRead)
        
    doc.loading = False
    return doc

