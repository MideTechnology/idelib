'''
Created on Dec 3, 2014

@author: dstokes
'''

from datetime import datetime
from itertools import izip
import locale
import os.path
from StringIO import StringIO
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
    
    def __init__(self, writer):
        self.writer = writer
        self.numRows = 0
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
        vals= np.frombuffer(data, np.uint16).reshape((-1,3)).astype(np.int32) - 32767
        self.numRows += vals.shape[0]
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
        self.out = out
        self.cancelled = False
        self.startTime = None
        self.cancelAt = cancelAt
        self.estSum = None
        self.quiet = quiet
        self.lastMsg = ''
        
        if precision == 0:
            self.formatter = " %d%%"
        else:
            self.formatter = " %%.%df%%%%" % precision

        locale.setlocale(0,'English_United States.1252')

    def dump(self, s):
        if not self.quiet:
            self.out.write(s)
            self.out.flush()
    
    def __call__(self, count=0, total=None, percent=None, error=None, 
                 starting=False, done=False):
        if percent >= self.cancelAt:
            self.cancelled=True
        if self.startTime is None:
            self.startTime = datetime.now()
        if done:
            self.dump("Done!\n")
        else:
            if percent is not None:
                num = locale.format("%d", count, grouping=True)
                msg = "%s samples exported" % num
                if msg != self.lastMsg:
                    self.lastMsg = msg
                    msg = "%s (%s)" % (msg, self.formatter % (percent*100))
                    self.dump(msg)
                    self.dump('\x08' * len(msg))
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
    
    if matFilename is None:
        matFilename = os.path.splitext(ideFilename)[0] + ".mat"
    elif os.path.isdir(matFilename):
        matFilename = os.path.join(matFilename, os.path.splitext(os.path.basename(ideFilename))[0]+".mat")
        
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        mat = matfile.MatStream(matFilename, matfile.makeHeader(doc), maxFileSize=maxSize)
        mat.writeNames([c.name for c in doc.channels[0].subchannels])
        
        if len(doc.transforms) > 1:
            mat.writeStringArray("cal_polynomials", map(str, doc.transforms.values()[1:]))
        
        numAccelCh = len(doc.channels[0].subchannels)
        numTempCh = len(doc.channels[1].subchannels)
        
        mat.startArray(doc.channels[0].name, numAccelCh,
                       mtype=MP.mxINT16_CLASS, dtype=MP.miINT16, noTimes=True)

        accelDumper = AccelDumper(mat.writeRow)
        tempDumper = MPL3115Dumper(None)
        
        totalSize = os.path.getsize(ideFilename) + 0.0
        nextUpdate = time.time() + updateInterval
        
        try:
            print "Reading data...",
            for i, el in enumerate(doc.ebmldoc.iterroots()):
                if el.name == "ChannelDataBlock":
                    chId = el.value[0].value
                    if chId == 0:
                        accelDumper.write(el)
                    elif chId == 1:
                        tempDumper.write(el)
                if i % 100 == 0 or time.time() > nextUpdate:
                    count = (accelDumper.numRows*numAccelCh)+(tempDumper.numRows*numTempCh)
                    updater(count=count, total=None, percent=(stream.tell()/totalSize))
                    nextUpdate = time.time() + updateInterval
            mat.endArray()
            
            if not accelOnly:
                mat.startArray(doc.channels[1].name, numTempCh,
                       mtype=MP.mxSINGLE_CLASS, dtype=MP.miSINGLE, noTimes=True)
                for r in tempDumper.data:
                    mat.writeRow((0,r))
                mat.endArray()

            sampRates = [1000000.0/(((d.lastTime-d.firstTime)*ChannelDataBlock.timeScalar)/d.numRows) for d in (accelDumper, tempDumper)]
            
            mat.startArray("sampling_rates", )
            print sampRates
#             for i,d in enumerate((accelDumper, tempDumper)):
#                 print "Channel %d: rows: %d, firstTime=%s, lastTime=%s" % (i, d.numBuffers, d.firstTime, d.lastTime)
            
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
    argparser.add_argument('source', nargs="+", help="The source .IDE file(s) to split.")

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
        t0 = datetime.now()
        for f in sourceFiles:
            print ('Converting "%s"...' % f)
            fsize = os.path.getsize(f)
            digits = max(0, min(2, (len(str(fsize))/2)-1))
            raw2mat(f, matFilename=args.output, accelOnly=args.accelOnly, 
                    maxSize=args.maxSize, updater=SimpleUpdater(precision=digits))
    
        print "Conversion complete! Total time: %s" % (datetime.now() - t0)
    except KeyboardInterrupt:
        print "\n*** Conversion canceled! MAT version(s) of %s may be incomplete." % f

