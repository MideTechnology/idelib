'''
Created on Oct 22, 2014

@author: dstokes
'''

from datetime import datetime
from itertools import izip
import os.path
import sys

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    import mide_ebml
except ImportError:
    sys.path.append('..')
    
from mide_ebml import matfile
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

def ideIterator(doc, writer, channelId=0, calChannelId=1,  **kwargs):
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
    importer.readData(doc, onlyChannel=channelId)
    
    return doc

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
# 
#===============================================================================

def ide2mat(ideFilename, matFilename=None, channelId=0, calChannelId=1,  **kwargs):
    """
    """
    if matFilename is None:
        matFilename = os.path.splitext(ideFilename)[0] + ".mat"
    elif os.path.isdir(matFilename):
        matFilename = os.path.join(matFilename, os.path.splitext(os.path.basename(ideFilename))[0]+".mat")
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        
        recTime = datetime.utcfromtimestamp(doc.lastSession.utcStartTime)
        comment = "%s - Recorded %s (UTC)" % (os.path.basename(ideFilename),
                                              str(recTime)[:19])
        
        mat = matfile.MatStream(matFilename, comment)
        mat.startArray(doc.channels[0].name, len(doc.channels[0].subchannels))
        
        ideIterator(doc, mat.writeRow, **kwargs)
        mat.close()

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse
    from glob import glob
    
    argparser = argparse.ArgumentParser(description="Mide .IDE to .MAT Converter - Copyright (c) %d Mide Technology" % datetime.now().year)
    argparser.add_argument('-o', '--output', help="The output path to which to save the .MAT files. Defaults to the same as the source file.")
    argparser.add_argument('source', nargs="*", help="The source .IDE file(s) to split.")

    args = argparser.parse_args()
    sourceFiles = []
    for f in args.source:
        sourceFiles.extend(glob(f))
    
    for f in sourceFiles:
        print "Converting %s" % f
        ide2mat(f, matFilename=args.output)

    print "Conversion complete!"
        
