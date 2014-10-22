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
import sys
from time import time as time_time

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
testFile = "C:\\Users\\dstokes\\workspace\\SSXViewer\\test_recordings\\Calibrated_Z_Tape.IDE"

# from parsers import AccelerometerParser

# Hard-coded sensor/channel mapping. Will eventually be read from EBML file,
# but these should be default for the standard Slam Stick X.
# TODO: Base default sensors on the device type UID.
default_sensors = {
    0x00: {"name": "SlamStick X Combined Sensor", 
           "channels": {
                0x00: {"name": "Accelerometer ZYX",
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
    if doc.recorderInfo:
        # TODO: Move device-specific stuff out of the main importer
        rtype = doc.recorderInfo.get('RecorderTypeUID', 0x10)
        if rtype | 0xff == 0xff:
            # SSX recorders have UIDs that are zero except the least byte.
            SSX_ACCEL_RANGES = {
               0x10: (-25,25),
               0x12: (-100,100),
               0x13: (-200,200),
               0x14: (-500, 500),
            }
            rrange = SSX_ACCEL_RANGES.get(rtype & 0xff, 0x10)
            transform = calibration.AccelTransform(*rrange)
            sensors = sensors.copy()
            ch0 = sensors[0x00]['channels'][0x00]
            ch0['transform'] = (transform,)*3
            for i in range(3):
                ch0['subchannels'][i]['displayRange'] = rrange

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
    """
    
    def __init__(self, cancelAt=1.0, quiet=False):
        """ Constructor.
            @keyword cancelAt: A percentage at which to abort the import. For
                testing purposes.
        """
        self.cancelled = False
        self.startTime = None
        self.cancelAt = cancelAt
        self.estSum = None
        self.quiet = quiet
    
    def dump(self, s):
        if not self.quiet:
            sys.stdout.write(s)
    
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
            self.dump('\x0d%s samples read' % count)
            if percent is not None:
                p = int(percent*100)
                self.dump(' (%d%%)' % p)
                if p > 0 and p < 100:
                    d = ((datetime.now() - self.startTime) / p) * (100-p)
                    self.dump(' - est. completion in %s' % d)
                    if self.estSum is None:
                        self.estSum = d
                else:
                    self.dump(' '*25)
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
        @see: `readData()`
    """
    stream = open(filename, "rb")
    doc = Dataset(stream, name=name, quiet=quiet)
    readData(doc, updater=updater, numUpdates=numUpdates, 
             updateInterval=updateInterval, parserTypes=parserTypes, 
             defaultSensors=defaultSensors)
    return doc


def openFile(stream, parserTypes=elementParserTypes, 
             defaultSensors=default_sensors, name=None, quiet=False):
    """ Create a `Dataset` instance and read the header data (i.e. non-sample-
        data). When called by a GUI, this function should be considered 'modal,' 
        in that it shouldn't run in a background thread, unlike `readData()`. 
        
        @note: This is (currently) just a stub; all the importing is done by
            the `readData()` function alone.
        @todo: Split everything that's not reading sensor data (loading
            calibration, building the sensor list, creating the session catalog)
            out of `readData()`.

        @keyword parserTypes: A collection of `parsers.ElementHandler` classes.
        @keyword defaultSensors: A nested dictionary containing a default set 
            of sensors, channels, and subchannels. These will only be used if
            the dataset contains no sensor/channel/subchannel definitions. 
        @keyword name: An optional name for the Dataset. Defaults to the
            base name of the file (if applicable).
        @keyword quiet: If `True`, non-fatal errors (e.g. schema/file
            version mismatches) are suppressed. 
    """
    # Just a stub (for the moment). In the future, this function will read the
    # 'header' information (i.e. non-sample-data) and catalog the sessions.
    doc = Dataset(stream, name=name, quiet=quiet)
    return doc


def readData(doc, updater=nullUpdater, numUpdates=500, updateInterval=1.0,
             parserTypes=elementParserTypes, defaultSensors=default_sensors,
             sessionId=-1):
    """ Import the data from a file into a Dataset.
    
        @todo: Remove the metadata-reading parts and put them in `openFile()`.
            Also move the defaultSensors there as well.
    
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

    doc.addSession()

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
        nextUpdateTime = time_time() + updateInterval
    else:
        # An update time 24 hours in the future should mean no updates.
        nextUpdateTime = time_time() + 5184000
    
    firstDataPos = 0
    nextUpdatePos = ticSize
    
    readRecordingProperties = False
    readingData = False
    
    try:    
        for r in doc.ebmldoc.iterroots():
            if getattr(updater, "cancelled", False):
                doc.loadCancelled = True
                break
            
            # OPTIMIZATION: local variables
            r_name = r.name
            r_stream_offset = r.stream.offset
            
            if r_name in elementParsers:
                try:
                    readRecordingProperties = (readRecordingProperties or 
                                               r_name == "RecordingProperties") 
                    parser = elementParsers[r_name]
                    
                    if not readingData and parser.makesData():
                        # The first data has been read. Notify the updater!
                        updater(0)
                        if not doc.sensors:
                            # Got data before the recording props; use defaults.
                            if defaultSensors is not None:
                                createDefaultSensors(doc, defaultSensors)
                            readRecordingProperties = True
                        firstDataPos = r_stream_offset
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
                               (r.name, r.id, r_stream_offset))
                continue
            
            # More progress display stuff
            # FUTURE: Possibly do the update check every nth elements; that
            # would have slightly less work per cycle.
            thisOffset = r_stream_offset
            thisTime = time_time()
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

