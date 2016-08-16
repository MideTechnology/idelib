'''
Module ide2mat.common

Created on Aug 16, 2016
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2016 Mide Technology Corporation"

from datetime import datetime
from glob import glob
import importlib
import os.path
import sys

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    _ = importlib.import_module('mide_ebml')
except ImportError:
    sys.path.append('..')


from mide_ebml import importer
from mide_ebml.parsers import ChannelDataBlock
import devices

#===============================================================================
# 
#===============================================================================

def changeFilename(filename, ext=None, path=None):
    """ Modify the path or extension of a filename. 
    """
    if ext is not None:
        ext = ext.lstrip('.')
        filename = "%s.%s" % (os.path.splitext(filename)[0], ext)
    if path is not None:
        filename = os.path.join(path, os.path.basename(filename))
    return os.path.abspath(filename)


def streplace(string, old, new):
    """ Replace multiple substrings in a string with the same new substring.
    """
    for c in old:
        string = string.replace(c, new)
    return string


def multiReplace(string, *replacements):
    """ ``multiReplace(string, ('old1','new1') [, ('old2','new2')...])``
    
        Replace multiple substrings in a string. Replacement pairs can be
        either two-element list/tuples or two-character strings. Replacement
        happens in the order the pairs are specified; later pairs may change
        the replacements made by earlier pairs.
    """
    # Not the most efficient, but good enough for short strings.
    for old, new in replacements:
        string.replace(old, new)
    return string


def hasWildcards(name):
    """ Does a given string contain glob-like wildcard characters?
    """
    return any((c in name for c in "*?[]!"))


def showError(msg, items=None, exitCode=1, quiet=False):
    """ Simple error-displaying function.
    """
    if quiet:
        print "ERROR: %s" % msg
    else:
        print "\x07Error: %s" % msg
    
    try:
        print "\t" + "\n\t".join(map(str, items))
    except TypeError:
        pass
    
    if exitCode is not None:
        exit(exitCode)


def validateArguments(args):
    """ Perform the common validation and modification of command-line
        arguments: Get the source files (including wildcard expansion),
        validate output directory, validate start/end times.
    """
    if len(args.source) == 0:
        showError("ERROR: No source file(s) specified!")
    
    sourceFiles = []
    for f in args.source:
        if hasWildcards(f):
            sourceFiles.extend(glob(f))
        else:
            sourceFiles.append(f)

    if len(sourceFiles) == 0:
        showError("ERROR: No files found!")
    
    if not all(map(os.path.exists, sourceFiles)):
        # Missing one or more specified files.
        missing = filter(lambda x: not os.path.exists(x), sourceFiles)
        showError("Source file(s) could not be found:", missing)
    
    bad = filter(lambda x: not x.lower().endswith('.ide'), sourceFiles)
    if len(bad) > 0:
        showError("Only .IDE files are supported. Invalid files:", bad)
        
    if args.info is True:
        print "=" * 70
        for f in sourceFiles:
            showIdeInfo(f)
        sys.exit(0)
        
    if args.output is not None:
        if not os.path.exists(args.output):
            showError("Output path does not exist:", [args.output])
        if not os.path.isdir(args.output):
            showError("Specified output is not a directory:", [args.output])
    
    if args.duration:
        endTime = args.startTime + args.duration
    else:
        endTime = args.endTime

    if isinstance(endTime, float) and endTime <= args.startTime:
        msg = ("Specified end time (%s) occurs at or before start time (%s).\n"
               "(Did you mean to use the --duration argument instead of "
               "--endTime?)" % (endTime, args.startTime))
        showError(msg)
    
    return sourceFiles, args.output, args.startTime, endTime



#===============================================================================
# 
#===============================================================================

def showIdeInfo(ideFilename, **kwargs):
    """ Show properties of an IDE file.
    """
    print ideFilename
    print "=" * 70
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        rec = devices.fromRecording(doc)

        print "Recorder Info"
        print "-" * 40
        print "  Serial Number: %s" % rec.serial
        print "  Recorder Type: %s (%s)" % (rec.productName, rec.partNumber)
        if rec.birthday:
            print "  Date of Manufacture: %s" % datetime.fromtimestamp(rec.birthday)
        print "  Hardware Version: %s" % rec.hardwareVersion
        print "  Firmware Version: %s" % rec.firmwareVersion
        
        print
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

class TimestampFixer(object):
    """ Mix-in/base class for things that need to correct timestamp modulo. 
    """
    
    def __init__(self, maxTimestamp=ChannelDataBlock.maxTimestamp):
        
        self.maxTimestamp = maxTimestamp
        self.timestampOffset = 0
        self.lastStamp = 0
    

    def _fixOverflow(self, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
            XXX: OLD VERSION! REMOVE LATER!
        """
        timestamp += self.timestampOffset
        while timestamp < self.lastStamp:
            timestamp += self.maxTimestamp
            self.timestampOffset += self.maxTimestamp
        self.lastStamp = timestamp
        return timestamp


    def fixOverflow(self, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        modulus = self.maxTimestamp
        offset = self.timestampOffset
        
        if timestamp > modulus:
            # Timestamp is (probably) not modulo; will occur in split files.
            offset = timestamp - (timestamp % modulus)
            timestamp = timestamp % modulus
            self.timestampOffset = offset
        elif timestamp < self.lastStamp:
            # Modulo rollover (probably) occurred.
            offset += modulus
            self.timestampOffset = offset
            
        self.lastStamp = timestamp
        timestamp += self.timestampOffset
        return timestamp

