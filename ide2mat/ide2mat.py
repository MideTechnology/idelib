'''
A utility for generating MATLAB .MAT files from Slam Stick X .IDE recordings.

Created on Oct 22, 2014

@author: dstokes
'''

from datetime import datetime
from itertools import izip
import locale
import os.path
# import struct
import sys

# from scipy.io.matlab import mio5_params as MP

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    import mide_ebml
except ImportError:
    sys.path.append('..')
    
from mide_ebml import matfile
from mide_ebml.matfile import MP
import mide_ebml.multi_importer as importer



class StreamedEventList(object):
    """ Replacement for standard `EventList` objects that streams data to a
        file instead of loading it.
        
        Note: If a channel has a bivariate polynomial calibration, the
        referenced channel needs to be written in the IDE file first.
    """
    
    def __init__(self, eventlist, writer=None):
        self.eventlist = eventlist
        self.lastEvent = None
        self.writer = writer
        
        # Hack to copy attributes. Not all are used.
        for att in ['DEFAULT_MEAN_SPAN', '_blockIdxTable', 
                    '_blockIdxTableSize', '_data', '_firstTime', 
                    '_hasSubsamples', '_lastTime', '_length', 'dataset', 
                    'displayRange', 'hasDisplayRange', 'hasMinMeanMax', 
                    'hasSubchannels', 'name', 'parent', 'removeMean', 
                    'rollingMeanSpan', 'session', 'units']:
                setattr(self, att, getattr(eventlist, att))

    def __len__(self):
        return len(self.eventlist)


    def append(self, block):
        # `append()` doesn't really append; it writes the data to a file.
        values = self.parent.parseBlock(block)
        if block.endTime is None:
            sampleTime = 0
        else:
            sampleTime = (block.endTime - block.startTime) / len(values)
        times = (block.startTime + (i * sampleTime) for i in xrange(len(values)))
        if self.hasSubchannels:
            for event in izip(times, values):
                # TODO: Refactor this ugliness
                # This is some nasty stuff to apply nested transforms
                event=[c._transform(f((event[-2],v),self.session), self.session) for f,c,v in izip(self.parent._transform, self.parent.subchannels, event[-1])]
                event=(event[0][0], tuple((e[1] for e in event)))
                if self.writer is not None:
                    self.writer(event)
        else:
            for event in izip(times, values):
                event = self.parent._transform(self.parent.parent._transform[self.parent.id](event, self.session))
                if self.writer is not None:
                    self.writer(event)
                
        self.lastEvent = event

#         print self.eventlist.parent.id, event


    def getValueAt(self, at, outOfRange=True):
        # Always gets the last value.
        if self.hasSubchannels:
            return self.lastEvent
        else:
            return self.lastEvent[-1][self.parent.id]
    

class DummyWriter(object):
    """ For testing purposes. """
    def __init__(self):
        self.data = []
    def __call__(self, event):
        self.data.append(event)
    
#===============================================================================
# 
#===============================================================================

def ideIterator(doc, writer, channelId=0, calChannelId=1, **kwargs):
    """
    """
    # Iterate over 'plots' (subchannels) to create empty Sessions.
    for p in doc.getPlots():
        p.getSession()
    
    # Import the data for the reference channel. This should be
    # relatively small; the temperature is 1 sample per data block.
    importer.readData(doc, onlyChannel=calChannelId)
    
    # Replace all the session EventLists with the 'stream' version,
    # except the one used as the bivariate polynomial calibration source.
    for channel in doc.channels.itervalues():
        if channel.id == calChannelId:
            continue
        w = writer if channelId == channel.id else None
        for sid, sess in channel.sessions.iteritems():
            channel.sessions[sid] = StreamedEventList(sess, w)
        for sc in channel.subchannels:
            for sid, sess in sc.sessions.iteritems():
                sc.sessions[sid] = StreamedEventList(sess)
    
    # "Import" the channel to export. It really just gets dumped to file.
    
    importer.readData(doc, onlyChannel=channelId, updateInterval=1.0, **kwargs)
    
    return doc

#===============================================================================
# 
#===============================================================================

class SimpleUpdater(object):
    """ A simple text-based progress updater.
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
        self.lastMsg = None
        
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
                msg = "%s samples exported %s" % (num, self.formatter % (percent*100))
                if msg != self.lastMsg:
                    self.dump(msg)
                    self.dump('\x08' * len(msg))
                    self.lastMsg = msg
            sys.stdout.flush()


#===============================================================================
# 
#===============================================================================

def ide2mat(ideFilename, matFilename=None, channelId=0, calChannelId=1, 
            dtype="double", nocal=False, raw=False, accelOnly=True,
            noTimes=False, maxSize=matfile.MatStream.MAX_SIZE, **kwargs):
    """
    """
    timeScalar =  1.0/(10**6)
    if raw:
        timeScalar = 1
        nocal = True
        if noTimes:
            _mtype = MP.mxINT16_CLASS
            _dtype = MP.miINT16
        else:
            _mtype = MP.mxINT64_CLASS
            _dtype = MP.miINT64
    elif dtype == 'single':
        _mtype = MP.mxDOUBLE_CLASS #MP.mxSINGLE_CLASS
        _dtype = MP.miSINGLE
    elif dtype == 'double':
        _mtype = MP.mxDOUBLE_CLASS 
        _dtype = MP.miDOUBLE
    else:
        # TODO: Make this based on system architecture
        _mtype = MP.mxDOUBLE_CLASS 
        _dtype = MP.miDOUBLE
        
    if matFilename is None:
        matFilename = os.path.splitext(ideFilename)[0] + ".mat"
    elif os.path.isdir(matFilename):
        matFilename = os.path.join(matFilename, os.path.splitext(os.path.basename(ideFilename))[0]+".mat")
        
    msg = "Initializing..."
    print (msg + ('\x08' * len(msg))),
    
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        for c in doc.channels.itervalues():
            c.raw = raw
            for sc in c.subchannels:
                sc.raw = raw or nocal
        
        mat = matfile.MatStream(matFilename, matfile.makeHeader(doc), timeScalar=timeScalar, maxFileSize=maxSize)
        mat.writeNames([c.name for c in doc.channels[0].subchannels])
        if len(doc.transforms) > 1:
            mat.writeStringArray("cal_polynomials", map(str, doc.transforms.values()[1:]))
            
        mat.startArray(doc.channels[0].name, len(doc.channels[0].subchannels),
                       mtype=_mtype, dtype=_dtype, noTimes=noTimes)
        
        try:
            print ("Channel %d: " % channelId),
            msg = "Initializing..."
            print (msg + ('\x08' * len(msg))),
            
            ideIterator(doc, mat.writeRow, **kwargs)
            mat.endArray()
            
            if not accelOnly:
                print ("Channel %d: " % calChannelId),
                mat.startArray(doc.channels[1].name, len(doc.channels[1].subchannels),
                               mtype=MP.mxDOUBLE_CLASS, dtype=MP.miDOUBLE, noTimes=noTimes)
                for evt in doc.channels[1].getSession():
                    mat.writeRow(evt)
                mat.endArray()
            
        except KeyboardInterrupt:
            pass
        mat.close()

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse
    from glob import glob
    
    argparser = argparse.ArgumentParser(description="Mide .IDE to .MAT Converter - Copyright (c) %d Mide Technology" % datetime.now().year)
    argparser.add_argument('-o', '--output', help="The output path to which to save the .MAT files. Defaults to the same as the source file.")
    argparser.add_argument('-t', '--type', choices=('single','double'), help="Force data to be saved as 'single' (32b) or 'double' (64b) values.")
    argparser.add_argument('-n', '--nocal', action="store_true", help="Do not apply temperature correction calibration to accelerometer data (faster).")
    argparser.add_argument('-r', '--raw', action="store_true", help="Write data in raw form: no calibration, integer ADC units. For expert users only.")
    argparser.add_argument('-s', '--noTimestamps', action="store_true", help="Save without sample time stamps. For expert users only.")
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
            print ('Converting "%s"...' % f),
            fsize = os.path.getsize(f)
            digits = max(0, min(2, (len(str(fsize))/2)-1))
            ide2mat(f, matFilename=args.output, dtype=args.type, 
                    nocal=args.nocal, raw=args.raw, accelOnly=args.accelOnly, 
                    noTimes=args.noTimestamps, maxSize=args.maxSize,
                    updater=SimpleUpdater(precision=digits))
    
        print "\nConversion complete! Total time: %s" % (datetime.now() - t0)
    except KeyboardInterrupt:
        print
        print "*** Conversion canceled! MAT version of %s may be incomplete." % f
