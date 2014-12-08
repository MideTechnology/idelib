'''
Created on Dec 3, 2014

@author: dstokes
'''

from datetime import datetime
import locale
import os.path
import sys
import time

import numpy as np

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    import mide_ebml
except ImportError:
    sys.path.append('..')
    
from mide_ebml import matfile
from mide_ebml.matfile import MP
from mide_ebml.importer import nullUpdater
import mide_ebml.multi_importer as importer
from mide_ebml.parsers import MPL3115PressureTempParser, ChannelDataBlock

#===============================================================================
# 
#===============================================================================


class AccelDumper(object):
    maxTimestamp = ChannelDataBlock.maxTimestamp
    
    def __init__(self, numCh, writer=None):
        self.writer = writer
        self.numCh = numCh
        self.numRows = 0
        self.numSamp = 0
        self.firstTime = None
        self.lastTime = 0
    
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
        if self.firstTime is None:
            self.firstTime = self.fixOverflow(el.value[1].value)
        self.lastTime = self.fixOverflow(el.value[2].value)
        
        data = el.value[-1].value 
        vals= np.frombuffer(data, np.uint16).reshape((-1,3))
        self.numRows += vals.shape[0]
        self.numSamp += vals.shape[0] * self.numCh
        for v in vals:
            self.writer((0,v))


class MPL3115Dumper(AccelDumper):
    tempParser = MPL3115PressureTempParser()
    
    def __init__(self, *args, **kwargs):
        super(MPL3115Dumper, self).__init__(*args, **kwargs)
        self.data = []
    
    def write(self, el):
        self.lastTime = self.fixOverflow(el.value[1].value)
        if self.firstTime is None:
            self.firstTime = self.lastTime
        
        self.numRows += 1
        self.numSamp += self.numCh
        self.data.append(self.tempParser.unpack_from(el.value[-1].value))


#===============================================================================
# 
#===============================================================================

class SimpleUpdater(object):
    """ A simple text-based progress updater. Simplifed version of the one in
        mide_ebml.importer
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
            noTimes=False, maxSize=matfile.MatStream.MAX_SIZE, 
            updateInterval=1.5, **kwargs):
    """
    """
    
    updater = kwargs.get('updater', nullUpdater)
    maxSize = max(1024*1024*16, maxSize)
    
    if matFilename is None:
        matFilename = os.path.splitext(ideFilename)[0] + ".mat"
    elif os.path.isdir(matFilename):
        matFilename = os.path.join(matFilename, os.path.splitext(os.path.basename(ideFilename))[0]+".mat")
        
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        mat = matfile.MatStream(matFilename, matfile.makeHeader(doc), maxFileSize=maxSize)
        mat.writeNames([c.name for c in doc.channels[0].subchannels])
        
        # Write calibration polynomials as strings
        mat.writeCalibration(doc.transforms)
        
        numAccelCh = len(doc.channels[0].subchannels)
        numTempCh = len(doc.channels[1].subchannels)
        
        totalSize = os.path.getsize(ideFilename) + 0.0
        nextUpdate = time.time() + updateInterval
        
        try:
            mat.writeRecorderInfo(doc.recorderInfo)
            if doc.sessions[0].utcStartTime:
                mat.writeValue('start_time_utc', doc.sessions[0].utcStartTime, MP.miINT64)
            mat.startArray(doc.channels[0].name, numAccelCh, dtype=MP.miUINT16, noTimes=True)
    
            dumpers = (AccelDumper(3, mat.writeRow), MPL3115Dumper(2))
            
            lastMat = ''
            writeMsg = '' 
            
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
                            dumpers[chId].write(el)
                            
                        # EXPERIMENTAL!
#                         for chEl in el.value:
#                             try:
#                                 del chEl.cached_value
#                             except AttributeError:
#                                 pass
#                             del chEl.stream
#                             del chEl
#                         del el.stream
                        
                    if i % 250 == 0 or time.time() > nextUpdate:
                        count = sum((x.numSamp for x in dumpers))
                        updater(count=count, total=None, percent=(stream.tell()/totalSize))
                        nextUpdate = time.time() + updateInterval
                    
#                     try:
#                         del el.stream
#                         del el.cached_value
#                     except AttributeError:
#                         pass
                    
                    doc.ebmldoc.stream.substreams.clear()
                    del el
            except IOError:
                pass
                
            mat.endArray()
            
            if not accelOnly:
                mat.startArray(doc.channels[1].name, numTempCh,
                       dtype=MP.miSINGLE, noTimes=True)
                for r in dumpers[1].data:
                    mat.writeRow((0,r))
                mat.endArray()

            # Calculate actual sampling rate based on total count and total time
            sampRates = [1000000.0/(((d.lastTime-d.firstTime)*ChannelDataBlock.timeScalar)/d.numRows) for d in dumpers]
            mat.startArray("sampling_rates", len(sampRates), dtype=MP.miSINGLE, noTimes=True)
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
    
    argparser = argparse.ArgumentParser(description="Mide Raw .IDE to .MAT Converter - Copyright (c) %d Mide Technology" % datetime.now().year)
    argparser.add_argument('-o', '--output', help="The output path to which to save the .MAT files. Defaults to the same as the source file.")
    argparser.add_argument('-a', '--accelOnly', action='store_true', help="Export only accelerometer data.")
    argparser.add_argument('-m', '--maxSize', type=int, default=matfile.MatStream.MAX_SIZE, help="The maximum MAT file size in bytes. Must be less than 2GB.")
    argparser.add_argument('source', nargs="+", help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()
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
                updater=updater)
            updater(done=True)
    
        totalTime = datetime.now() - t0
        tstr = str(totalTime).rstrip('0.')
        sampSec = locale.format("%d", totalSamples/totalTime.total_seconds(), grouping=True)
        print "Conversion complete! Total time: %s (%s samples/sec.)" % (tstr, sampSec)
    except KeyboardInterrupt:
        print "\n*** Conversion canceled! MAT version(s) of %s may be incomplete." % f
#     except IOError as err: #Exception as err:
#         print "\n\x07*** Conversion failed! %r" % err

