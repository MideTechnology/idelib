'''
Module/utility for splitting an .IDE file into more manageable pieces.

@todo: Replace the per-element read/write with something that does it to all
    the data between two elements, in order to reduce read/write count.
'''

from datetime import datetime
from importlib import import_module
import math
import os.path
import struct
import sys

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    _ = import_module('mide_ebml')
except ImportError:
    sys.path.append('..')
    
from mide_ebml.ebml.schema.mide import MideDocument
from mide_ebml import parsers
from mide_ebml import util
from mide_ebml.importer import nullUpdater

#===============================================================================
# 
#===============================================================================

from mide_ebml.dataset import __DEBUG__

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
    
    def __init__(self, cancelAt=1.0, quiet=False, out=sys.stdout):
        """ Constructor.
            @keyword cancelAt: A percentage at which to abort the import. For
                testing purposes.
        """
        self.out = out
        self.cancelled = False
        self.startTime = None
        self.cancelAt = cancelAt
        self.estSum = None
        self.quiet = quiet
    
    def dump(self, s):
        if not self.quiet:
            self.out.write(s)
            self.out.flush()
    
    def __call__(self, count=0, total=None, percent=None, error=None, 
                 starting=False, done=False):
        
        if done:
            self.dump('\nSplitting complete!\n')
        else:
            self.dump('.')


#===============================================================================
# Modified parser and data block classes, simplified for splitting.
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
        while timestamp <= self.lastStamp.get(channel,0):
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


def splitDoc(doc, savePath=None, basename=None, startTime=0, endTime=None, maxSize=1024*1024*10, 
              numDigits=3, updater=nullUpdater, numUpdates=500, updateInterval=1.0,
              parserTypes=elementParserTypes):
    """ Import the data from a file into a Dataset.
    
        @param doc: The EBML document to split.
        @keyword savePath: The path to which to save the split files.
        @keyword basename: The base name of each file, if different from the
            original's.
        @keyword maxSize: The maximum size of each file.
        @keyword updater: A function (or function-like object) to notify as 
            work is done. It should take four keyword arguments: `count` (the 
            current line number), `total` (the total number of samples), `error` 
            (an unexpected exception, if raised during the import), and `done` 
            (will be `True` when the split is complete). If the updater object 
            has a `cancelled` attribute that is `True`, the import will be 
            aborted. The default callback is `None` (nothing will be notified).
        @keyword numUpdates: The minimum number of calls to the updater to be
            made. More updates will be made if the updates take longer than
            than the specified `updateInterval`. 
        @keyword updateInterval: The maximum number of seconds between calls to 
            the updater. More updates will be made if indicated by the specified
            `numUpdates`.
        @keyword parserTypes: A collection of `parsers.ElementHandler` classes.
    """
    startTime *= 1000000.0
    endTime = None if endTime is None else endTime * 1000000.0
    try:
        if basename is None:
            basename = doc.stream.file.name
        name, ext = os.path.splitext(os.path.basename(basename))
        if savePath is None:
            savePath = os.path.dirname = os.path.dirname(basename)
    except NotImplementedError: #(TypeError, AttributeError, ValueError):
        name, ext = "Split", ".IDE"
        savePath = ""
    filename = os.path.join(savePath, "%s_%%0%dd%s" % (name, numDigits, ext))
    
    elementParsers = dict([(f.elementName, f(None)) for f in parserTypes])

    elementCount = 0
    
    # For seeking and reading elements, separate from doc to prevent conflicts
    oldFile = open(doc.stream.file.name, 'rb')
    
    i = doc.iterroots()
    el = None
    header = bytearray()
    while True:
        el = i.next()
        elementCount += 1
        if 'ChannelDataBlock' in el.name:
            break
        else:
            header.extend(util.getRawData(el, oldFile))
    
    num = 0
    filesize = len(header)

    # dict of which channels have been written to a new file
    wroteFirst={}
    fileWrites = 0
    fs = None
    blockStart = 0

    try:
        while True:
            if fs is None or fs.closed:
                num += 1
                fs = open(filename % num, 'wb')
                fs.write(header)
                filesize = len(header)
                fileWrites = 0
            
            raw = None
        
            elementCount += 1
            if el.name in ('TimeBaseUTC', 'Sync','SimpleChannelDataBlock'):
                # Totally skip these
                el = i.next()
                continue
            elif el.name == 'ChannelDataBlock' and el.value[0].value in wroteFirst:
                # Don't bother parsing additional blocks, just copy verbatim
                pass
            elif el.name in elementParsers:
                try:
                    parser = elementParsers[el.name]
                    block = parser.parse(el)
                    if not block:
                        el = i.next()
                        continue
                    
                    blockStart = block.startTime
                    if blockStart < startTime:
                        el = i.next()
                        continue
                    
                    if endTime is not None and blockStart > endTime:
                        return
                    
#                     if (startTime > 0 or num > 1) and not wroteFirst.get(block.channel, False):
                    if not wroteFirst.get(block.channel, False):
                        wroteFirst[block.channel] = True
                        data = util.parse_ebml(el)[el.name][0]
                        data['StartTimeCodeAbsMod'] = int(blockStart/ parser.timeScalar)
                        if getattr(block, 'endTime', None):
                            blockEnd = int(block.endTime / parser.timeScalar)
                            data['EndTimeCodeAbsMod'] = blockEnd
                        else:
                            blockEnd = None
                        raw = util.build_ebml(el.name, data)
                except parsers.ParsingError as err:
                    logger.error("Parsing error during import: %s" % err)

            if raw is None:
                raw = util.getRawData(el, oldFile)
                
            fs.write(raw)
            filesize += len(raw)
            fileWrites += 1
            
            if filesize >= maxSize:
                fs.close()
                wroteFirst.clear()
                updater(count=num)

            el = i.next()
            
            # XXX: EXPERIMENTAL
            # NOTE: This is messing with internals of python_ebml. May change!
            doc.stream.substreams.clear()

    
    except IOError as e:
        if e.errno is None:
            # The EBML library raises an empty IOError if it hits EOF.
            # TODO: Handle other cases of empty IOError (lots in python-ebml)
            doc.fileDamaged = True
        else:
            updater(error=e)
    except (StopIteration, KeyboardInterrupt):
        pass
        
    try:
        fs.close()
    except (AttributeError, ValueError, IOError):
        pass
        
    oldFile.close()
    updater(done=True)
    return num


def splitFile(filename=testFile, savePath=None, basename=None, numDigits=3,
              startTime=0, endTime=None, maxSize=1024*1024*10, 
              updater=nullUpdater, numUpdates=500, updateInterval=1.0, 
              parserTypes=elementParserTypes):
    """ Wrapper function to split a file based on filename.
    
        @param filename: The name of the IDE file to split.
        @keyword savePath: The path to which to save the split files.
        @keyword basename: The base name of each file, if different from the
            original's.
        @keyword maxSize: The maximum size of each file.
        @keyword updater: A function (or function-like object) to notify as 
            work is done. It should take four keyword arguments: `count` (the 
            current line number), `total` (the total number of samples), `error` 
            (an unexpected exception, if raised during the import), and `done` 
            (will be `True` when the split is complete). If the updater object 
            has a `cancelled` attribute that is `True`, the import will be 
            aborted. The default callback is `None` (nothing will be notified).
        @keyword numUpdates: The minimum number of calls to the updater to be
            made. More updates will be made if the updates take longer than
            than the specified `updateInterval`. 
        @keyword updateInterval: The maximum number of seconds between calls to 
            the updater. More updates will be made if indicated by the specified
            `numUpdates`.
        @keyword parserTypes: A collection of `parsers.ElementHandler` classes.
    """
    
    with open(filename, 'rb') as fp:
        doc = MideDocument(fp)
        return splitDoc(doc, savePath=savePath, basename=basename, 
                        numDigits=numDigits, startTime=startTime, 
                        endTime=endTime, maxSize=maxSize, updater=updater, 
                        numUpdates=numUpdates, updateInterval=updateInterval, 
                        parserTypes=parserTypes)
 
 
if __name__ == '__main__':
    import argparse
    
    argparser = argparse.ArgumentParser(description="Mide .IDE File Splitter - Copyright (c) %d Mide Technology" % datetime.now().year)
    argparser.add_argument('-s', '--size', type=int, help="The maximum size of each generated file, in MB.", default=16)
    argparser.add_argument('-n', '--numSplits', type=int, help="The number of files to generate (overrides '--size').")
    argparser.add_argument('-o', '--output', help="The output path to which to save the split files. Defaults to the same as the source file.")
    argparser.add_argument('-t', '--startTime', type=int, help="The start of the time span to export (seconds from the beginning of the recording).", default=0)
    argparser.add_argument('-e', '--endTime', type=int, help="The end of the time span to export (seconds from the beginning of the recording).")
    argparser.add_argument('-d', '--duration', type=int, help="The length of time to export, relative to the --startTime. Overrides the specified --endTime")
    argparser.add_argument('source', help="The source .IDE file to split.")

    args = argparser.parse_args()
    sourceFile = os.path.abspath(args.source)

    if not os.path.isfile(args.source):
        sys.stderr.write("File '%s' does not exist!\n" % sourceFile)
        sys.exit(1)
    if args.numSplits is not None:
        numSplits = args.numSplits
        maxSize = int(math.ceil(os.path.getsize(sourceFile)/(numSplits+0.0)))
    else:
        maxSize = args.size * 1024 * 1024
        numSplits = int(math.ceil(os.path.getsize(sourceFile)/(maxSize+0.0)))
    
    if args.output is not None:
        savePath = args.output
    else:
        savePath = os.path.dirname(sourceFile)
    
    if args.duration:
        endTime = args.startTime + args.duration
    else:
        endTime = args.endTime

    if isinstance(endTime, float) and endTime <= args.startTime:
        print "Specified end time (%ss) occurs at or before start time (%ss). " % (endTime, args.startTime)
        print "(Did you mean to use the --duration argument instead of --endTime?)"
        sys.exit(1)
        
    numDigits = max(2, len(str(numSplits)))
    
    t0 = datetime.now()
    if args.startTime or args.endTime:
        # Can't estimate the size of a slice of time
        print "Splitting %s..." % os.path.basename(sourceFile)
    else:
        print "Splitting %s into %d files..." % (os.path.basename(sourceFile), numSplits)
    splitFile(sourceFile, savePath=savePath, startTime=args.startTime, endTime=endTime, maxSize=maxSize, numDigits=numDigits, updater=SimpleUpdater())
    print "Finished splitting in %s" % (datetime.now() - t0)
