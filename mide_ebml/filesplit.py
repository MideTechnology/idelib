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
import os.path
import struct
import sys
import time

from ebml.schema.mide import MideDocument
import parsers
import util

from importer import nullUpdater

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
# Defaults
#===============================================================================

# XXX: Remove me before production.
testFile = 'C:\\Users\\dstokes\\workspace\\SSXViewer\\test_recordings\\Battery_Life_Tests\\1000_Hz.IDE'

# from parsers import AccelerometerParser


#===============================================================================
# 
#===============================================================================

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
# 
#===============================================================================

class ChannelDataBlockParser(parsers.ChannelDataBlockParser):
    """ Simplified data block parser that only corrects the timestamp modulus.
    """
    def _fixOverflow(self, block, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        channel = block.getHeader()[1]
        timestamp += self.timestampOffset.setdefault(channel, 0)
        # NOTE: This might need to just be '<' (for discontinuities)
        if timestamp <= self.lastStamp.get(channel,0):
            timestamp += block.maxTimestamp
            self.timestampOffset[channel] += block.maxTimestamp
        self.lastStamp[channel] = timestamp
        return timestamp * self.timeScalar
    
    def fixOverflow(self, block, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        channel = block.getHeader()[1]
        timestamp += self.timestampOffset.setdefault(channel, 0)
        # NOTE: This might need to just be '<' (for discontinuities)
        while timestamp <= self.lastStamp.get(channel,0):
            timestamp += block.maxTimestamp
            self.timestampOffset[channel] += block.maxTimestamp
        self.lastStamp[channel] = timestamp
        return timestamp * block.timeScalar
  
    def parse(self, element, sessionId=None):
        """ Create a (Simple)ChannelDataBlock from the given EBML element.
        
            @param element: A sample-carrying EBML element.
            @keyword sessionId: The session currently being read; defaults to
                whatever the Dataset says is current.
            @return: The number of subsamples read from the element's payload.
        """
        try:
            block = self.product(element)
            timestamp, _ = block.getHeader()
        except struct.error, e:
            raise parsers.ParsingError("Element would not parse: %s (ID %02x) @%d (%s)" % 
                               (element.name, element.id, element.stream.offset, e))
        
        block.startTime = int(self.fixOverflow(block, timestamp))
        if block.endTime is not None:
            block.endTime = int(self.fixOverflow(block, block.endTime))

        return block

#===============================================================================
# Parsers/Element Handlers
#===============================================================================

# Parser importer. These are taken from the module by type. We may want to 
# create the list of parser types 'manually' prior to release; it's marginally 
# safer.
elementParserTypes = [ChannelDataBlockParser]


#===============================================================================
# ACTUAL FILE READING HAPPENS BELOW
#===============================================================================

def splitDoc(doc, savePath=None, basename=None, maxSize=1024*1024*10, 
              updater=nullUpdater, numUpdates=500, updateInterval=1.0,
              parserTypes=elementParserTypes):
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
    try:
        if basename is None:
            basename = doc.stream.file.name
        name, ext = os.path.splitext(os.path.basename(basename))
        if savePath is None:
            savePath = os.path.dirname = os.path.dirname(basename)
    except NotImplementedError: #(TypeError, AttributeError, ValueError):
        name, ext = "Split", ".IDE"
        savePath = ""
    filename = os.path.join(savePath, "%s_%%03d%s" % (name, ext))
    
    
    elementParsers = dict([(f.elementName, f(None)) for f in parserTypes])

    elementCount = 0
    
    # For seeking and reading elements, separate from doc to prevent conflicts
    oldFile = open(doc.stream.file.name, 'rb')
    
    utcTime = 0
    i = doc.iterroots()
    el = None
    header = bytearray()
    while True:
        el = i.next()
        elementCount += 1
        if 'ChannelDataBlock' in el.name:
            break
        elif el.name == 'TimeBaseUTC':
            utcTime = el.value
        else:
            header.extend(util.getRawData(el, oldFile))
    
    newFile = True
    
    if utcTime == 0:
        utcTime = int(time.time())

    fileStartTime = None
    
    num = 0
    filesize = len(header)

    # dict of which channels have been written to a new file
    wroteFirst={}
    
    fs = None
    try:
        while True:
            raw = None
            if el.name == 'TimeBaseUTC':
                utcTime = el.value
                el = i.next()
                elementCount += 1
                continue
            if el.name == 'SimpleChannelDataBlock':
                el = i.next()
                elementCount += 1
                continue
            elif el.name in elementParsers:
                try:
                    parser = elementParsers[el.name]
                    block = parser.parse(el)
                    if not block:
                        el = i.next()
                        elementCount += 1
                        continue
                    if fileStartTime is None:
                        fileStartTime = int((block.startTime - (el.value[1].value * block.timeScalar)) / 1000000.0)
                    if num > 1 and not wroteFirst.setdefault(block.channel, False):
                        print "%d channel=%d num=%d, wroteFirstBlock=%r" % (elementCount, block.channel, num, wroteFirst)
                        wroteFirst[block.channel] = True
                        data = util.parse_ebml(el)[el.name][0]
                        data['StartTimeCodeAbsMod'] = int(block.startTime / parser.timeScalar)
                        if getattr(block, 'endTime', None):
                            data['EndTimeCodeAbsMod'] = int(block.endTime / parser.timeScalar)
                        raw = util.build_ebml(el.name, data)
                except parsers.ParsingError as err:
                    logger.error("Parsing error during import: %s" % err)

            if raw is None: 
                raw = util.getRawData(el, oldFile)
                
            if fs is None:
#                 print ".",
                print "%5d file start: %4d, %s, block start: %10d (%s), raw start: %10d" % (elementCount, fileStartTime, datetime.utcfromtimestamp(utcTime+fileStartTime).time(),block.startTime, datetime.utcfromtimestamp(utcTime+(block.startTime/1000000.0)).time(), el.value[1].value * parser.timeScalar)
                # New file
                num += 1
                if num > 3:
                    break
                fs = open(filename % num, 'wb')
                fs.write(header)
                filesize = len(header)
#                 if fileStartTime is not None:
                fs.write(util.build_ebml('TimeBaseUTC', utcTime))
#                 fs.write(util.build_ebml('TimeBaseUTC', utcTime + fileStartTime))
                fileStartTime = None
                        
            fs.write(raw)
            filesize += len(raw)
            
            if filesize >= maxSize:
                print "File size is %d, starting #%d" % (filesize, num)
                wroteFirst.clear()
                fs.close()
                fs = None

            el = i.next()
            elementCount += 1
            
    except IOError as e:
        if e.errno is None:
            # The EBML library raises an empty IOError if it hits EOF.
            # TODO: Handle other cases of empty IOError (lots in python-ebml)
            doc.fileDamaged = True
        else:
            updater(error=e)
    except StopIteration:
        pass
        
    try:
        fs.close()
    except (AttributeError, ValueError, IOError):
        pass
        
    oldFile.close()
    return num


def splitFile(filename=testFile, savePath='temp/', basename=None, 
              maxSize=1024*1024*10, updater=nullUpdater, numUpdates=500, 
              updateInterval=1.0, parserTypes=elementParserTypes):
    print "Splitting %s" % filename
    with open(filename, 'rb') as fp:
        doc = MideDocument(fp)
        return  splitDoc(doc, savePath, basename, maxSize, updater, numUpdates, updateInterval, parserTypes)

#===============================================================================
# 
#===============================================================================

from glob import glob
mergeTestFiles = glob(r"C:\Users\dstokes\workspace\SSXViewer\test_recordings\Combine_Files\SSX*.IDE")

def mergeFiles(filenames=mergeTestFiles, newName="Merged.IDE", maxSize=1024*1024*10, 
               updater=nullUpdater, numUpdates=500, updateInterval=1.0, 
               parserTypes=elementParserTypes):
    
    print "Merging %d files" % len(filenames)
    
    if not newName.lower().endswith('.ide'):
        newName += ".IDE"
    elementParsers = dict([(f.elementName, f(None)) for f in parserTypes])

    out = file(newName, 'wb')
    wroteHeader = False
    timeOffset = 0
    firstTime = None
    
    for filenum, filename in enumerate(filenames):
        print "\n\n=== %s" % filename
        with open(filename, 'rb') as fp:
            doc = MideDocument(fp)
            
            i = doc.iterroots()
            el = None #i.next()
            header = bytearray()
            while True:
                el = i.next()
                if el.name in ('ChannelDataBlock', 'SimpleChannelDataBlock'):
                    break
                elif el.name == "TimeBaseUTC":
                    if firstTime is None:
                        firstTime = el.value
                    else:
                        timeOffset = el.value - firstTime
                if not wroteHeader:
                    header.extend(util.getRawData(el))
            
            if not wroteHeader:
                out.write(header)
                wroteHeader = True
    
            try:
                while True:
#                     if el.name == "TimeBaseUTC":
#                         el = i.next()
#                         continue
                    raw = None
                    if filenum > 0 and el.name in elementParsers:
                        try:
                            block = elementParsers[el.name].parse(el)
                            data = util.parse_ebml(block.element)
                            payload = data[el.name][0]
                            oldStart = 0
                            if 'StartTimeCodeAbsMod' in payload:
                                oldStart = payload['StartTimeCodeAbsMod']
                                blockTime = timeOffset + (block.startTime * 0.000001)
                                payload['StartTimeCodeAbsMod'] += int((blockTime / block.timeScalar)+0.5)
                                print "channel %d block start: %s" % (block.channel,blockTime)
                            if 'EndTimeCodeAbsMod' in payload:
                                end = (payload['EndTimeCodeAbsMod'] - oldStart) + int(timeOffset / block.timeScalar) 
#                                 blockTime = timeOffset + (block.endTime * 0.000001)
                                payload['EndTimeCodeAbsMod'] = end
                            raw = util.build_ebml(el.name, payload)
                            
                        except parsers.ParsingError as err:
                            print "Crap: %s" % err
                            logger.error("Parsing error during import: %s" % err)
                    
                    if raw is None:
                        raw = util.getRawData(el)
#                     print "(%s %dB)" % (el.name, len(raw)),
                    out.write(raw)
                    el = i.next()
                    
            except StopIteration:
                pass
                
    out.close()    
