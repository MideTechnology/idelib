'''
Created on Dec 3, 2014

@author: dstokes
'''

from datetime import datetime
from itertools import izip
import importlib
import locale
import os.path
import platform
import sys
import tempfile
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
from mide_ebml.parsers import ChannelDataBlock
from mide_ebml.calibration import CombinedPoly, PolyPoly


from devices import SlamStickX

from build_info import DEBUG, BUILD_NUMBER, VERSION, BUILD_TIME #@UnusedImport
__version__ = VERSION

#===============================================================================
# 
#===============================================================================

class MATExportError(Exception):
    pass

#===============================================================================
# 
#===============================================================================

class AccelDumper(object):
    """ Parser replacement that dumps accelerometer data as read. 
    """
    maxTimestamp = ChannelDataBlock.maxTimestamp
    timeScalar = 1000000.0 / 2**15
    
    def __init__(self, source, writer=None, startTime=0, endTime=None):
        self.writer = writer
        self.source = source
        self.numCh = len(source.subchannels)
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
        vals= np.frombuffer(data, np.uint16).reshape((-1,self.numCh))
        self.numRows += vals.shape[0]
        self.numSamp += vals.shape[0] * self.numCh
        times = np.linspace(blockStart, blockEnd, vals.shape[0]) * self.timeScalar
        for r in zip(times, vals):
            self.writer(r)
            
        return True


class GenericDumper(AccelDumper):
    """ Parser replacement that dumps temperature/pressure data as read.
        This accumulates data rather than writing it directly.
    """
    
    def __init__(self, *args, **kwargs):
        super(GenericDumper, self).__init__(*args, **kwargs)
        self.unpacker = self.source.parser.unpack_from
        self.data = []
        self.data_append = self.data.append
        
        if self.source.transform is not None or not all([c.transform is None for c in self.source.subchannels]):
            self.source.dataset.updateTransforms()
            self.xform = PolyPoly([CombinedPoly(c.transform, x=self.source.transform) for c in self.source.subchannels])
        else:
            self.xform = None

    def write(self, el):
        self.lastTime = self.fixOverflow(el.value[1].value)
        if self.firstTime is None:
            self.firstTime = self.lastTime
        
        if self.lastTime < self.startTime:
            return False
        
        self.numRows += 1
        self.numSamp += self.numCh
        if self.xform is not None:
            self.data_append(self.xform.function(*self.unpacker(el.value[-1].value)))
        else:
            self.data_append(self.unpacker(el.value[-1].value))
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
                msg = "%s samples read" % num
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

class TempWriter(object):
    """ Thing to write data to a temporary file.
    """
    def __init__(self, stream):
        self.stream = stream
    
    def writerow(self, r):
        self.stream.write('%d, %r\n' % (r[0], list(r[1])))

#===============================================================================
# 
#===============================================================================

def showInfo(ideFilename, **kwargs):
    """
    """
    print ideFilename
    print "=" * 70
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        print "Sensors"
        print "-" * 40
        for s in sorted(doc.sensors.values()):
            print "  Sensor %d: %s" % (s.id, s.name)
            if s.traceData:
                for i in s.traceData.items():
                    print "    %s: %s" % i
        print 
        print "Channels"
        print "-" * 40
        for c in sorted(doc.channels.values()):
            print "  Channel %d: %s" % (c.id, c.displayName)
            for sc in c.subchannels:
                print "    Subchannel %d.%d: %s" % (c.id, sc.id, sc.displayName)
    print "=" * 70


#===============================================================================
# 
#===============================================================================

def raw2mat(ideFilename, matFilename=None, dtype="double", channels=None,
            noTimes=False, startTime=0, endTime=None, updateInterval=1.5,  
            maxSize=matfile.MatStream.MAX_SIZE, **kwargs):
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

        ssx = SlamStickX.fromRecording(doc)
        accelCh = ssx.getAccelChannel()
        accelChId = accelCh.id
        pressTempCh = ssx.getTempChannel().parent
        pressTempChId = pressTempCh.id
        
        dcAccelCh = ssx.getAccelChannel(dc=True)
        dcAccelChId = dcAccelCh.id if dcAccelCh is not None else None
        
        numAccelCh = len(accelCh.subchannels)
        numTempCh = len(pressTempCh.subchannels)
        numDcAccelCh = 0 if dcAccelCh is None else len(dcAccelCh.subchannels)
        
        totalSize = os.path.getsize(ideFilename) + 0.0
        nextUpdate = time.time() + updateInterval
        
        if channels is None:
            channels = doc.channels.keys()
        else:
            missing = [str(c) for c in channels if c not in doc.channels]
            if missing:
                raise MATExportError("Unknown channel(s): %s" % (', '.join(missing)))
        
        try:
            mat.startArray(accelCh.name, numAccelCh, dtype=MP.miUINT16, 
                           noTimes=True, colNames=[c.displayName for c in accelCh.subchannels])
    
#             dumpers = {accelChId: AccelDumper(accelCh, mat.writeRow, startTime, endTime), 
#                        pressTempChId: GenericDumper(pressTempCh, None, startTime, endTime)}
            dumpers = {}

            # TODO: Make this all more generic, to work with any future recorder
            if accelChId in channels:
                dumpers[accelChId] = AccelDumper(accelCh, mat.writeRow, startTime, endTime)
            if pressTempChId in channels:
                dumpers[pressTempChId] = GenericDumper(pressTempCh, None, startTime, endTime)
            if dcAccelChId in channels:
                tempFile = open(os.path.join(tempfile.gettempdir(), 'ch%d_temp.csv' % dcAccelChId), 'wb')
                tempWriter = TempWriter(tempFile) #csv.writer(tempFile)
                dumpers[dcAccelChId] = AccelDumper(dcAccelCh, tempWriter.writerow, startTime, endTime)
                    
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
                        if chId in dumpers:
                            wroteData = dumpers[chId].write(el)
                            
                            # First block written; base the 
                            if wroteData and not isWriting:
                                offset = stream.tell()
                                totalSize -= offset
                                isWriting = True
                            
                    if i % 250 == 0 or time.time() > nextUpdate:
                        count = sum((x.numSamp for x in dumpers.itervalues()))
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
            
            if pressTempChId in channels:
                d = dumpers[pressTempChId]
                mat.startArray(pressTempCh.name, numTempCh, dtype=MP.miSINGLE, 
                               noTimes=True, colNames=[c.displayName for c in pressTempCh.subchannels])
                for r in izip(np.linspace(d.firstTime, d.lastTime, len(d.data)), d.data):
                    mat.writeRow(r)
                mat.endArray()

            if dcAccelCh is not None and dcAccelChId in channels:
                tempFile.close()
                d = dumpers[dcAccelChId]
                mat.startArray(dcAccelCh.name, numDcAccelCh, dtype=MP.miUINT16, 
                               noTimes=True, colNames=[c.displayName for c in dcAccelCh.subchannels])
                with open(tempFile.name, 'rb') as f:
                    for r in f:
                        mat.writeRow(eval(r))
                mat.endArray()

            # Calculate actual sampling rate based on total count and total time
            # TODO: Write this for each MAT file.
            # TODO: Write the time range in each file (reset parser.firstTime)
            sampRates = [1000000.0/(((d.lastTime-d.firstTime)*ChannelDataBlock.timeScalar)/d.numRows) for d in dumpers.itervalues()]
            mat.startArray("sampling_rates", len(sampRates), dtype=MP.miSINGLE, noTimes=True, hasTimes=False)
            mat.writeRow((0,sampRates))
            mat.endArray()
            
            mat.close()
            return sum((x.numSamp for x in dumpers.itervalues()))
        
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
    argparser.add_argument('-c', '--channel', action='append', type=int, help="Export the specific channel. Can be used multiple times. If not used, all channels will export.")
    argparser.add_argument('-m', '--maxSize', type=int, default=matfile.MatStream.MAX_SIZE, help="The maximum MAT file size in bytes. Must be less than 2GB.")
    argparser.add_argument('-t', '--startTime', type=float, help="The start of the time span to export (seconds from the beginning of the recording).", default=0)
    argparser.add_argument('-e', '--endTime', type=float, help="The end of the time span to export (seconds from the beginning of the recording).")
    argparser.add_argument('-d', '--duration', type=float, help="The length of time to export, relative to the --startTime. Overrides the specified --endTime")
    argparser.add_argument('-i', '--info', action='store_true', help="Show information about the file and exit.")
    argparser.add_argument('-v', '--version', action='store_true', help="Show detailed version information and exit.")
    argparser.add_argument('source', nargs="*", help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()
    
    if args.version is True:
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

    if args.info is True:
        print "=" * 70
        for f in sourceFiles:
            showInfo(f)
        sys.exit(0)
        
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
                                    channels=args.channel, maxSize=args.maxSize,
                                    startTime=args.startTime, endTime=endTime, 
                                    updater=updater)
            updater(done=True)
    
        totalTime = datetime.now() - t0
        tstr = str(totalTime).rstrip('0.')
        sampSec = locale.format("%d", totalSamples/totalTime.total_seconds(), grouping=True)
        totSamp = locale.format("%d", totalSamples, grouping=True)
        print "Conversion complete! Exported %s samples in %s (%s samples/sec.)" % (totSamp, tstr, sampSec)
    except MATExportError as err:
        print "*** Export error: %s" % err
        exit(1)
    except KeyboardInterrupt:
        print "\n*** Conversion canceled! MAT version(s) of %s may be incomplete." % f
#     except IOError as err: #Exception as err:
#         print "\n\x07*** Conversion failed! %r" % err

