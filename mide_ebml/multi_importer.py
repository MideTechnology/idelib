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
import time

from ebml.schema.mide import MideDocument

import calibration
from dataset import Dataset
import parsers

from importer import elementParserTypes, default_sensors, createDefaultSensors
from importer import nullUpdater, SimpleUpdater, testFile

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


HEADER_ELEMENTS = ("RecordingProperties", "CalibrationList", "RecorderConfiguration")
DATA_ELEMENTS = ("ChannelDataBlock", "SimpleChannelDataBlock")

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


def openFile(stream, updater=nullUpdater, elementParsers=None, 
             parserTypes=elementParserTypes, 
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
    doc = Dataset(stream, name=name, quiet=quiet)
    doc.addSession(0)
    
    if elementParsers is None:
        elementParsers = dict([(f.elementName, f(doc)) for f in parserTypes])
        
    try:
        for r in doc.ebmldoc.iterroots():
            if getattr(updater, "cancelled", False):
                doc.loadCancelled = True
                break
            if r.name not in elementParsers:
                pass
            parser = elementParsers[r.name]
            if parser.makesData():
                break
            
    except IOError as e:
        if e.errno is None:
            # The EBML library raises an empty IOError if it hits EOF.
            # TODO: Handle other cases of empty IOError (lots in python-ebml)
            doc.fileDamaged = True
        else:
            updater(error=e)
        
    if not doc.sensors:
        # Got data before the recording props; use defaults.
        if defaultSensors is not None:
            createDefaultSensors(doc, defaultSensors)
    return doc


def readData(doc, updater=nullUpdater, numUpdates=500, updateInterval=1.0,
             timeOffset=0, elementParsers=None, parserTypes=elementParserTypes,
             sessionId=-1):
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
    
    if elementParsers is None:
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
    
    try:    
        # This just skips 'header' elements. It could be more efficient, but
        # the size of the header isn't significantly large; savings are minimal.
        for r in doc.ebmldoc.iterroots():
            if getattr(updater, "cancelled", False):
                doc.loadCancelled = True
                break
            if r.name not in elementParsers:
                # Unknown block type, but probably okay.
                logger.info("unknown block %r (ID 0x%02x) @%d" % \
                               (r.name, r.id, r.stream.offset))
                continue
            
            parser = elementParsers[r.name]
            if getattr(parser, "isHeader", False):
                continue 

            try:
                added = parser.parse(r, timeOffset=timeOffset)
                if isinstance(added, int):
                    eventsRead += added
                    
            except parsers.ParsingError as err:
                # TODO: Error messages
                logger.error("Parsing error during import: %s" % err)
                continue
            
            # More progress display stuff
            # FUTURE: Possibly do the update check every nth elements; that
            # would have slightly less work per cycle.
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


#===============================================================================
# 
#===============================================================================

def openFiles(filenames):
    result = []
    for filename in filenames:
        fp = open(filename, 'rb')
        utcTime = None
        doc = MideDocument(fp)
        i = doc.iterroots()
        el = i.next()
        while el.name != 'TimeBaseUTC':
            el = i.next()
        utcTime = el.value
        result.append([utcTime, doc, i])
    result.sort(key=lambda x: x[0])
    firstTime = result[0][0]
    for x in result:
        x[0] -= firstTime
    return result

def appendData(doc, docs):
    ""
    
