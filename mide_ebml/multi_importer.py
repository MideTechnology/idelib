'''
@todo: These revised versions of openFile() and readData() should replace the
    originals. 


'''
import fnmatch
import os.path
import time

from dataset import Dataset
from importer import elementParserTypes, default_sensors, createDefaultSensors
from importer import nullUpdater #, SimpleUpdater, testFile
from parsers import ParsingError

# TODO: Remove this testing stuff.
import glob
testFiles = glob.glob(r"C:\Users\dstokes\workspace\SSXViewer\test_recordings\Combine_Files\*.ide")

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

def openFile(stream, updater=nullUpdater, parserTypes=elementParserTypes,  
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
    if isinstance(stream, basestring):
        stream = open(stream, 'rb')
    doc = Dataset(stream, name=name, quiet=quiet)
    doc.addSession()

    parsers = dict([(f.elementName, f(doc)) for f in parserTypes])
        
    try:
        for r in doc.ebmldoc.iterroots():
            if getattr(updater, "cancelled", False):
                doc.loadCancelled = True
                break
            if r.name not in parsers:
                pass
            parser = parsers[r.name]
            if parser.makesData():
                break
            parser.parse(r) 
            
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


def readData(doc, source=None, updater=nullUpdater, numUpdates=500, updateInterval=.1,
             total=None, bytesRead=0, samplesRead=0, parserTypes=elementParserTypes,
             sessionId=0, onlyChannel=None, **kwargs):
    """ Import the data from a file into a Dataset.
    
        @param doc: The Dataset document into which to import the data.
        @param source: An alternate Dataset to merge into the main one.
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
        @keyword total: The total number of bytes in the file(s) being imported.
            Defaults to the size of the current file, but can be used to
            display an overall progress when merging multiple recordings.
        @keyword bytesRead: The number of bytes already imported. Mainly for
            merging multiple recordings.
        @keyword samplesRead: The total number of samples imported. Mainly for
            merging multiple recordings.
        @keyword parserTypes: A collection of `parsers.ElementHandler` classes.
        @keyword defaultSensors: A nested dictionary containing a default set 
            of sensors, channels, and subchannels. These will only be used if
            the dataset contains no sensor/channel/subchannel definitions.
            
        @keyword onlyChannel: If a number, only the channel specified will
            be imported. Kind of a hack, to be redone later.
    """
    
    parsers = dict([(f.elementName, f(doc)) for f in parserTypes])

    elementCount = 0
    eventsRead = 0
    
    # Progress display stuff
    if total is None:
        total = doc.ebmldoc.stream.size + bytesRead
        
    dataSize = total
    
    if numUpdates > 0:
        ticSize = total / numUpdates 
    else:
        # An unreachable file position effectively disables the updates.
        ticSize = total+1
    
    if updateInterval > 0:
        nextUpdateTime = time.time() + updateInterval
    else:
        # An update time 24 hours in the future should mean no updates.
        nextUpdateTime = time.time() + 5184000
    
    firstDataPos = 0
    nextUpdatePos = bytesRead + ticSize
    
    timeOffset = 0
    
    # Actual importing ---------------------------------------------------------
    if source is None:
        source = doc
    try:    
        # This just skips 'header' elements. It could be more efficient, but
        # the size of the header isn't significantly large; savings are minimal.
        for r in source.ebmldoc.iterroots():
            doc.loadCancelled = getattr(updater, "cancelled", False)
            if doc.loadCancelled:
                break
            
            if r.name not in parsers:
                # Unknown block type, but probably okay.
                logger.info("unknown block %r (ID 0x%02x) @%d" % \
                            (r.name, r.id, r.stream.offset))
                continue
            
            # HACK: Not the best implementation. Should be moved somewhere.
            if onlyChannel is not None and r.name == "ChannelDataBlock":
                if r.value[0].value != onlyChannel:
                    continue 
            
            if source != doc and r.name == "TimeBaseUTC":
                timeOffset = (r.value - doc.lastSession.utcStartTime) * 1000000.0
                continue
                
            try:
                parser = parsers[r.name]
                if not parser.isHeader:
                    added = parser.parse(r, timeOffset=timeOffset)
                    if isinstance(added, int):
                        eventsRead += added
                    
            except ParsingError as err:
                # TODO: Error messages
                logger.error("Parsing error during import: %s" % err)
                continue

            elementCount += 1
            
            # More progress display stuff -------------------------------------
            # FUTURE: Possibly do the update check every nth elements; that
            # would have slightly less work per cycle.
            thisOffset = r.stream.offset + bytesRead
            thisTime = time.time()
            if thisTime > nextUpdateTime or thisOffset > nextUpdatePos:
                # Update progress bar
                updater(count=eventsRead+samplesRead,
                        percent=(thisOffset-firstDataPos+0.0)/dataSize)
                nextUpdatePos = thisOffset + ticSize
                nextUpdateTime = thisTime + updateInterval
            
    except IOError as e:
        if e.errno is None:
            # The EBML library raises an empty IOError if it hits EOF.
            # TODO: Handle other cases of empty IOError (lots in python-ebml)
            doc.fileDamaged = True
        else:
            updater(error=e)
        
    doc.loading = False
    return eventsRead


#===============================================================================
# 
#===============================================================================

def crawlFiles(sources, pattern="*.ide", maxDepth=-1):
    """ Recursively find all recording files in one or more paths.
    """
    results = []
    if isinstance(sources, basestring):
        sources = [sources]
    for s in sources:
        s = os.path.abspath(s)
        if not os.path.exists(s):
            continue
        startDepth = s.count(os.path.sep)
            
        if os.path.isfile(s) and fnmatch.fnmatch(s,pattern):
            results.append(s)
            continue
        for root, dirs, files in os.walk(s):
            if root.count(os.path.sep) - startDepth == maxDepth:
                dirs[:] = []
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    fullname = os.path.abspath(os.path.join(root, f))
                    results.append(fullname)
            
            for bad in ('CVS', 'SYSTEM', '.git'):
                if bad in dirs:
                    dirs.remove(bad)

            for d in dirs:
                if d.startswith('.'):
                    dirs.remove(d)

    return filter(os.path.isfile, results)


def openFiles(filenames, **kwargs):
    """ Opens multiple recording files, and returns a list of Dataset objects,
        sorted by their UTC timestamp data.
    """
    result = [openFile(f, **kwargs) for f in filenames]
    result.sort(key=lambda x: x.lastSession.utcStartTime)
    return result


def multiOpen(streams, updater=nullUpdater, **kwargs):
    """ Create a `Dataset` instance and read the header data (i.e. non-sample-
        data). When called by a GUI, this function should be considered 'modal,' 
        in that it shouldn't run in a background thread, unlike `readData()`. 
        
        @param streams: A set of file-like streams containing EBML recordings.
        @keyword parserTypes: A collection of `parsers.ElementHandler` classes.
        @keyword defaultSensors: A nested dictionary containing a default set 
            of sensors, channels, and subchannels. These will only be used if
            the dataset contains no sensor/channel/subchannel definitions. 
        @keyword name: An optional name for the Dataset. Defaults to the
            base name of the file (if applicable).
        @keyword quiet: If `True`, non-fatal errors (e.g. schema/file
            version mismatches) are suppressed. 
    """
    updater(0)
    
    docs = [openFile(f, **kwargs) for f in streams]
    docs.sort(key=lambda x: x.lastSession.utcStartTime)
    mainDoc = docs[0]
    mainDoc.subsets = docs[1:]
    
#     mainDoc = openFile(streams[0], **kwargs)
#     mainDoc.subsets = [openFile(f, **kwargs) for f in streams[1:]]
    return mainDoc


def multiRead(doc, updater=nullUpdater, **kwargs):
    """ Import the data from a file into a Dataset, including the data from 
        its subsets.
    
        @param doc: The Dataset document into which to import the data. It
            should have `subset` Datasets.
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
    
    kwargs['numUpdates'] = kwargs.get('numUpdates', 500) / (len(doc.subsets)+1)
    totalSize = sum([x.ebmldoc.stream.size for x in doc.subsets])
    bytesRead = doc.ebmldoc.stream.size
    samplesRead = readData(doc, total=totalSize, **kwargs)
    if not doc.loadCancelled:
        for f in doc.subsets:
            if doc.loadCancelled:
                break
            samplesRead += readData(doc, source=f, total=totalSize, 
                                    bytesRead=bytesRead, samplesRead=samplesRead, 
                                    **kwargs)
            bytesRead += f.ebmldoc.stream.size
            updater(count=bytesRead, total=totalSize, 
                    percent=bytesRead/(totalSize+0.0))
        
    updater(done=True, total=samplesRead)
    return doc
    

def multiImport(filenames=testFiles, **kwargs):
    """ Import multiple files into one Dataset.
    """
    streams = [open(f,'rb') for f in filenames]
    return multiRead(multiOpen(streams, **kwargs), **kwargs)

