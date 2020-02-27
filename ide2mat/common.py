'''
Module ide2mat.common

Created on Aug 16, 2016
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2016 Mide Technology Corporation"

from datetime import datetime
from glob import glob
import importlib
import locale
import os.path
import sys
import time

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    _ = importlib.import_module('idelib')
except ImportError:
    sys.path.append('..')


from idelib import importer
from idelib.parsers import ChannelDataBlock


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
    
    try:
        if args.duration:
            endTime = args.startTime + args.duration
        else:
            endTime = args.endTime
    except AttributeError:
        endTime = None

    try:
        startTime = args.startTime
        if isinstance(endTime, float) and endTime <= args.startTime:
            msg = ("Specified end time (%s) occurs at or before start time (%s).\n"
                   "(Did you mean to use the --duration argument instead of "
                   "--endTime?)" % (endTime, args.startTime))
            showError(msg)
    except AttributeError:
        startTime = None
    
    return sourceFiles, args.output, startTime, endTime



#===============================================================================
# 
#===============================================================================

def showIdeInfo(ideFilename, toFile=False, extra=None, **kwargs):
    """ Show information about an IDE file.
    
        @param ideFilename: The IDE file to show.
        @keyword toFile: if `True`, the info will be written to a file with
            the name of the IDE file plus ``_info.txt``.
        @keyword extra: A dictionary of extra data to display (i.e. export
            settings).
        
        Other keyword arguments are passed to `importer.openFile`.
    """
    ideFilename = os.path.realpath(ideFilename)
    if isinstance(toFile, basestring):
        base = os.path.splitext(os.path.basename(ideFilename))[0] + '_info.txt'
        filename = os.path.join(toFile, base)
        out = open(filename, 'wb')
    else:
        out = sys.stdout
    
    idsort = lambda x: x.id
    
    def _print(*s):
        out.write(' '.join(map(str, s)) + os.linesep)
        
    with open(ideFilename, 'rb') as stream:
        _print(ideFilename)
        out.write(("=" * 70) + os.linesep)
        doc = importer.openFile(stream, **kwargs)
        if len(doc.sessions) > 0:
            st = doc.sessions[0].utcStartTime
            if st:
                _print('Start time: %s UTC' % (datetime.utcfromtimestamp(st)))
        try:
            info = doc.recorderInfo
            partNum = info.get('PartNumber', '')
            sn = info.get('RecorderSerial')
            if partNum.startswith('LOG-0002'):
                info['RecorderSerial'] = "SSX%07d" % sn
            elif partNum.startswith('LOG-0003'):
                info['RecorderSerial'] = "SSC%07d" % sn
            _print('Recorder: %(ProductName)s, serial number %(RecorderSerial)s' % info)
        except KeyError:
            pass
        _print()
        
        _print("Sensors")
        _print( "-" * 40)
        for s in sorted(doc.sensors.values(), key=idsort):
            _print( "  Sensor %d: %s" % (s.id, s.name))
            if s.traceData:
                for i in s.traceData.items():
                    _print("    %s: %s" % i)
        _print()
        
        _print("Channels")
        _print("-" * 40)
        for c in sorted(doc.channels.values(), key=idsort):
            _print("  Channel %d: %s" % (c.id, c.displayName))
            for sc in c.subchannels:
                _print("    Subchannel %d.%d: %s" % (c.id, sc.id, sc.displayName))

        if extra is not None:
            _print()
            _print("Export Options")
            _print("-" * 40)
            if extra.get('headers'):
                _print("  * Column headers")
            if extra.get('removeMean'):
                if extra.get('meanSpan', 5.0) == -1:
                    ms = 'Total mean removal'
                else:
                    ms = 'Rolling mean removal (%0.2f s)' % extra['meanSpan']
                _print('  * %s on analog channels' % ms)
            else:
                _print('  * No mean removal from analog channels')
                
            if extra.get('useUtcTime'):
                if extra.get('useIsoFormat'):
                    _print('  * Timestamps in ISO format (yyyy-mm-ddThh:mm:ss.s')
                else:
                    _print("  * Timestamps in absolute UTC 'Unix' time")
        
    _print("=" * 70)
    if out != sys.stdout:
        out.close()



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


#===============================================================================
# 
#===============================================================================

class SimpleUpdater(object):
    """ A simple text-based progress updater. Simplified version of the one in
        `idelib.importer`
    """
    
    def __init__(self, cancelAt=1.0, quiet=False, out=sys.stdout, precision=0):
        """ Constructor.
            @keyword cancelAt: A percentage at which to abort the import. For
                testing purposes.
        """
        locale.setlocale(0,'English_United States.1252')
        self.outputFiles = set()
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
                 starting=False, done=False, **kwargs):
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

