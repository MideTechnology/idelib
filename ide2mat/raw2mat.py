'''
Created on Dec 3, 2014

@author: dstokes
'''

from datetime import datetime
from itertools import izip
import importlib
import locale
import os.path
import sys
import time

import numpy as np

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    _ = importlib.import_module('mide_ebml')
except ImportError:
    sys.path.append('..')

from mide_ebml import __version__ as ebml_version    
from mide_ebml import matfile
from mide_ebml import importer
from mide_ebml.matfile import MP
from mide_ebml.parsers import MPL3115PressureTempParser, ChannelDataBlock

from build_info import DEBUG, BUILD_NUMBER, VERSION, BUILD_TIME
__version__ = VERSION

#===============================================================================
# 
#===============================================================================

class AccelDumper(object):
    """ Parser replacement that dumps accelerometer data as read. """
    maxTimestamp = ChannelDataBlock.maxTimestamp
    timeScalar = 1000000.0 / 2**15
    
    def __init__(self, numCh, writer=None, startTime=0, endTime=None):
        self.writer = writer
        self.numCh = numCh
        self.numRows = 0
        self.numSamp = 0
        self.firstTime = None
        self.lastTime = 0
        self.startTime = startTime * 2**15
        self.endTime = None if endTime is None else (endTime * 2**15)
    
        self.timestampOffset = 0
        self.lastStamp = 0
    

    def fixOverflow(self, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        timestamp += self.timestampOffset
        while timestamp < self.lastStamp:
            timestamp += self.maxTimestamp
            self.timestampOffset += self.maxTimestamp
        self.lastStamp = timestamp
        return timestamp


    def write(self, el):
        """ Parse the element and write the data.
            @param el: DataBlock element
            @return: `True` if data was written, `False` if not. Data will not
                be written if the block is outside of the specified start
                and end times.
        """
        blockStart = self.fixOverflow(el.value[1].value)
        blockEnd = self.fixOverflow(el.value[2].value)
        if self.firstTime is None:
            self.firstTime = blockStart
        self.lastTime = blockEnd

        if blockStart < self.startTime:
            return False
        
        if self.endTime is not None and blockStart > self.endTime:
            raise StopIteration
        
        data = el.value[-1].value 
        vals= np.frombuffer(data, np.uint16).reshape((-1,3))
        self.numRows += vals.shape[0]
        self.numSamp += vals.shape[0] * self.numCh
        times = np.linspace(blockStart, blockEnd, vals.shape[0]) * self.timeScalar
        for r in zip(times, vals):
            self.writer(r)
            
        return True


class MPL3115Dumper(AccelDumper):
    """ Parser replacement that dumps temperature/pressure data as read.
        This accumulates data rather than writing it directly.
    """
    tempParser = MPL3115PressureTempParser()
    
    def __init__(self, *args, **kwargs):
        super(MPL3115Dumper, self).__init__(*args, **kwargs)
        self.data = []
    
    def write(self, el):
        self.lastTime = self.fixOverflow(el.value[1].value)
        if self.firstTime is None:
            self.firstTime = self.lastTime
        
        if self.lastTime < self.startTime:
            return False
        
        self.numRows += 1
        self.numSamp += self.numCh
        self.data.append(self.tempParser.unpack_from(el.value[-1].value))
        return True

#===============================================================================
# 
#===============================================================================

class SimpleUpdater(object):
    """ A simple text-based progress updater. Simplified version of the one in
        `mide_ebml.importer`
    """
    
    def __init__(self, cancelAt=1.0, quiet=False, out=sys.stdout, precision=0):
        """ Constructor.
            @keyword cancelAt: A percentage at which to abort the import. For
                testing purposes.
        """
        locale.setlocale(0,'English_United States.1252')
        self.out = out
        self.cancelAt = cancelAt
        self.quiet = quiet
        self.precision = precision
        self.reset()


    def reset(self):
        self.startTime = None
        self.cancelled = False
        self.estSum = None
        self.lastMsg = ''
        
        if self.precision == 0:
            self.formatter = " %d%%"
        else:
            self.formatter = " %%.%df%%%%" % self.precision

    def dump(self, s):
        if not self.quiet:
            self.out.write(s)
            self.out.flush()
    
    def __call__(self, count=0, total=None, percent=None, error=None, 
                 starting=False, done=False):
        if starting:
            self.reset()
            return
        if percent >= self.cancelAt:
            self.cancelled=True
        if self.startTime is None:
            self.startTime = time.time()
        if done:
            self.dump(" Done.".ljust(len(self.lastMsg))+'\n')
            self.reset()
        else:
            if percent is not None:
                num = locale.format("%d", count, grouping=True)
                msg = "%s samples exported" % num
                if msg != self.lastMsg:
                    self.lastMsg = msg
                    msg = "%s (%s)" % (msg, self.formatter % (percent*100))
                    dt = time.time() - self.startTime
                    if dt > 0:
                        sampSec = count/dt
                        msg = "%s - %s samples/sec." % (msg, locale.format("%d", sampSec, grouping=True))
                    self.dump(msg)
                    self.dump('\x08' * len(msg))
                    self.lastMsg = msg
                if percent >= self.cancelAt:
                    self.cancelled=True
            sys.stdout.flush()


    
#===============================================================================
# 
#===============================================================================

def raw2mat(ideFilename, matFilename=None, channelId=0, calChannelId=1, 
            dtype="double", nocal=False, raw=False, accelOnly=True,
            noTimes=False, startTime=0, endTime=None, 
            maxSize=matfile.MatStream.MAX_SIZE, updateInterval=1.5, **kwargs):
    """ The main function that handles generating MAT files from an IDE file.
    """
    
    updater = kwargs.get('updater', importer.nullUpdater)
#     maxSize = max(1024**2*16, min(matfile.MatStream.MAX_SIZE, 1024**2*maxSize))
    maxSize =1024*maxSize
    
    if matFilename is None:
        matFilename = os.path.splitext(ideFilename)[0] + ".mat"
    elif os.path.isdir(matFilename):
        matFilename = os.path.join(matFilename, os.path.splitext(os.path.basename(ideFilename))[0]+".mat")
        
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        mat = matfile.MatStream(matFilename, doc, maxFileSize=maxSize,  writeCal=True, writeStart=True, writeInfo=True)
        
        numAccelCh = len(doc.channels[0].subchannels)
        numTempCh = len(doc.channels[1].subchannels)
        
        totalSize = os.path.getsize(ideFilename) + 0.0
        nextUpdate = time.time() + updateInterval
        
        try:
            mat.startArray(doc.channels[0].name, numAccelCh, dtype=MP.miUINT16, noTimes=True, colNames=[c.name for c in doc.channels[0].subchannels])
    
            dumpers = (AccelDumper(3, mat.writeRow, startTime, endTime), 
                       MPL3115Dumper(2, None, startTime, endTime))
            
            lastMat = ''
            writeMsg = '' 
            isWriting = False
            offset = 0
            
            try:
                for i, el in enumerate(doc.ebmldoc.iterroots()):
                    if mat.filename != lastMat:
                        lastMat = mat.filename
                        msgLen = len(writeMsg)
                        writeMsg = "  Writing %s... " % os.path.basename(lastMat)
                        print "%s%s" % ('\x08'*msgLen, writeMsg),
                        nextUpdate = 0
    
                    if el.name == "ChannelDataBlock":
                        chId = el.value[0].value
                        if chId < 2:
                            wroteData = dumpers[chId].write(el)
                            
                            # First block written; base the 
                            if wroteData and not isWriting:
                                offset = stream.tell()
                                totalSize -= offset
                                isWriting = True
                            
                    if i % 250 == 0 or time.time() > nextUpdate:
                        count = sum((x.numSamp for x in dumpers))
                        updater(count=count, total=None, percent=((stream.tell()-offset)/totalSize))
                        nextUpdate = time.time() + updateInterval

                    # Remove per-element substreams. Saves memory; a large
                    # file may contain tens of thousands.
                    # NOTE: This may change if the underlying EMBL library does.
                    doc.ebmldoc.stream.substreams.clear()
                    del el
                    
            except (IOError, StopIteration):
                pass
                
            mat.endArray()
            
            if not accelOnly:
                d = dumpers[1]
                mat.startArray(doc.channels[1].name, numTempCh,
                       dtype=MP.miSINGLE, noTimes=True)
                for r in izip(np.linspace(d.firstTime, d.lastTime, len(d.data)), d.data):
                    mat.writeRow(r)
                mat.endArray()

            # Calculate actual sampling rate based on total count and total time
            # TODO: Write this for each MAT file.
            # TODO: Write the time range in each file (reset parser.firstTime)
            sampRates = [1000000.0/(((d.lastTime-d.firstTime)*ChannelDataBlock.timeScalar)/d.numRows) for d in dumpers]
            mat.startArray("sampling_rates", len(sampRates), dtype=MP.miSINGLE, noTimes=True, hasTimes=False)
            mat.writeRow((0,sampRates))
            mat.endArray()
            
            mat.close()
            return sum((x.numSamp for x in dumpers))
        
        except IOError:
            mat.close()
            
        except KeyboardInterrupt as ex:
            mat.close()
            raise ex

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse
    from glob import glob
    
    argparser = argparse.ArgumentParser(description="Mide Raw .IDE to .MAT Converter v%d.%d.%d - Copyright (c) %d Mide Technology" % (VERSION+(datetime.now().year,)))
    argparser.add_argument('-o', '--output', help="The output path to which to save the .MAT files. Defaults to the same as the source file.")
    argparser.add_argument('-a', '--accelOnly', action='store_true', help="Export only accelerometer data.")
    argparser.add_argument('-m', '--maxSize', type=int, default=matfile.MatStream.MAX_SIZE, help="The maximum MAT file size in bytes. Must be less than 2GB.")
    argparser.add_argument('-t', '--startTime', type=float, help="The start of the time span to export (seconds from the beginning of the recording).", default=0)
    argparser.add_argument('-e', '--endTime', type=float, help="The end of the time span to export (seconds from the beginning of the recording).")
    argparser.add_argument('-d', '--duration', type=float, help="The length of time to export, relative to the --startTime. Overrides the specified --endTime")
    argparser.add_argument('-v', '--version', action='store_true', help="Show detailed version information and exit.")
    argparser.add_argument('source', nargs="*", help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()
    if args.version is True:
        import platform
        print argparser.description
        print "Converter version %d.%d.%d (build %d) %s, %s" % (VERSION + (BUILD_NUMBER, platform.architecture()[0], datetime.fromtimestamp(BUILD_TIME)))
        print "MIDE EBML library version %d.%d.%d" % ebml_version
        exit(0)
    
    if len(args.source) == 0:
        print "Error: No source file(s) specified!"
        exit(1)
    
    sourceFiles = []
    for f in args.source:
        sourceFiles.extend(glob(f))
    
    if not all(map(os.path.exists, sourceFiles)):
        # Missing a file.
        missing = map(lambda x: not os.path.exists(x), sourceFiles)
        print "Source file(s) could not be found:"
        print "\n\t".join(missing)
        sys.exit(1)
        
    if args.output is not None:
        if not os.path.exists(args.output):
            print "Output path does not exist: %s" % args.output
            sys.exit(1)
        if not os.path.isdir(args.output):
            print "Specified output is not a directory: %s" % args.output
            sys.exit(1)
    
    if args.duration:
        endTime = args.startTime + args.duration
    else:
        endTime = args.endTime

    if isinstance(endTime, float) and endTime <= args.startTime:
        print "Specified end time (%s) occurs at or before start time (%s). " % (endTime, args.startTime)
        print "(Did you mean to use the --duration argument instead of --endTime?)"
        sys.exit(1)
    
    try:
        totalSamples = 0
        t0 = datetime.now()
        updater=SimpleUpdater()
        for f in sourceFiles:
            print ('Converting "%s"...' % f)
            updater.precision = max(0, min(2, (len(str(os.path.getsize(f)))/2)-1))
            updater(starting=True)
            totalSamples += raw2mat(f, matFilename=args.output, 
                accelOnly=args.accelOnly, maxSize=args.maxSize,
                startTime=args.startTime, endTime=endTime, 
                updater=updater)
            updater(done=True)
    
        totalTime = datetime.now() - t0
        tstr = str(totalTime).rstrip('0.')
        sampSec = locale.format("%d", totalSamples/totalTime.total_seconds(), grouping=True)
        totSamp = locale.format("%d", totalSamples, grouping=True)
        print "Conversion complete! Exported %s samples in %s (%s samples/sec.)" % (totSamp, tstr, sampSec)
    except KeyboardInterrupt:
        print "\n*** Conversion canceled! MAT version(s) of %s may be incomplete." % f
#     except IOError as err: #Exception as err:
#         print "\n\x07*** Conversion failed! %r" % err

