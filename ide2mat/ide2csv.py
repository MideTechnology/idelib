'''
Command-line utility to batch export IDE files as CSV or MAT. Intended for
small files.

Created on Jan 26, 2016

@author: dstokes
'''

from datetime import datetime
import importlib
import locale
import os.path
import platform
import sys
import time

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    _ = importlib.import_module('mide_ebml')
except ImportError:
    sys.path.append('..')

from mide_ebml import __version__ as ebml_version
from mide_ebml import importer
from mide_ebml.matfile import exportMat


from build_info import DEBUG, BUILD_NUMBER, VERSION, BUILD_TIME #@UnusedImport
__version__ = VERSION


timeScalar = 1.0/(10**6)

#===============================================================================
#
#===============================================================================

class CSVExportError(Exception):
    pass

#===============================================================================
#
#===============================================================================

def exportCsv(events, filename, **kwargs):
    """ Wrapper for CSV export, making it like MAT export.
    """
    with open(filename, 'wb') as f:
        return events.exportCsv(f, **kwargs)


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


#===============================================================================
#
#===============================================================================

def showInfo(ideFilename, toFile=False, **kwargs):
    """
    """
    if isinstance(toFile, basestring):
        base = os.path.splitext(os.path.basename(ideFilename))[0] + '_info.txt'
        filename = os.path.join(toFile, base)
        out = open(filename, 'wb')
    else:
        out = sys.stdout
    
    def _print(*s):
        out.write(' '.join(map(str, s)) + os.linesep)
        
    _print(ideFilename)
    out.write(("=" * 70) + os.linesep)
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        _print("Sensors")
        _print( "-" * 40)
        for s in sorted(doc.sensors.values()):
            _print( "  Sensor %d: %s" % (s.id, s.name))
            if s.traceData:
                for i in s.traceData.items():
                    _print("    %s: %s" % i)
        _print()
        _print("Channels")
        _print("-" * 40)
        for c in sorted(doc.channels.values()):
            _print("  Channel %d: %s" % (c.id, c.displayName))
            for sc in c.subchannels:
                _print("    Subchannel %d.%d: %s" % (c.id, sc.id, sc.displayName))
    _print("=" * 70)
    if out != sys.stdout:
        out.close()


#===============================================================================
#
#===============================================================================

def ideExport(ideFilename, outFilename=None, channels=None,
            startTime=0, endTime=None, updateInterval=1.5,  out=sys.stdout, 
            outputType=".csv", delimiter=', ', headers=False, **kwargs):
    """ The main function that handles generating MAT files from an IDE file.
    """
    updater = kwargs.get('updater', importer.nullUpdater)
#     maxSize = max(1024**2*16, min(matfile.MatStream.MAX_SIZE, 1024**2*maxSize))

    def _printStream(*args):
        out.write(" ".join(map(str, args)))
        out.flush()

    def _printNone(*args):
        pass

    if out is None:
        _print = _printNone
    else:
        _print = _printStream

    b = os.path.basename(ideFilename)

    if outFilename is None:
        outFilename = os.path.splitext(ideFilename)[0]
    elif os.path.isdir(outFilename):
        outFilename = os.path.join(outFilename, os.path.splitext(b)[0])

    if outputType.lower().endswith('mat'):
        exporter = exportMat
        exportArgs = {}
    else:
        exporter = exportCsv
        exportArgs = {'delimiter': delimiter}
        if outputType.lower().endswith('csv') and ',' not in delimiter:
            outputType = '.txt'

    doc = importer.importFile(ideFilename)

    if channels is None:
        exportChannels = doc.channels.values()
    else:
        exportChannels = [c for c in doc.channels.values if c.id in channels]


    numSamples = 0
    for ch in exportChannels:
        outName = "%s_Ch%02d.%s" % (outFilename, ch.id, outputType.strip('.'))
        print("  Exporting Channel %d (%s) to %s..." % (ch.id, ch.name, outName)),
        try:
            events = ch.getSession()
            numSamples += exporter(events, outName, callback=updater, 
                                   timeScalar=timeScalar, headers=headers,
                                   **exportArgs)[0]

        except None:
            pass

    doc.close()
    return numSamples


#===============================================================================
#
#===============================================================================

if __name__ == "__main__":
    import argparse
    from glob import glob

    argparser = argparse.ArgumentParser(description="Mide Batch .IDE Converter v%d.%d.%d - Copyright (c) 2016 Mide Technology")
    argparser.add_argument('-o', '--output', help="The output path to which to save the exported files. Defaults to the same as the source file.")
    argparser.add_argument('-n', '--names', action='store_true', help="Write channel names as the first row of text-based export (not applicable to MAT export).")
    argparser.add_argument('-d', '--delimiter', choices=('comma','tab','pipe'), help="The delimiting character (not applicable to MAT export).", default="comma")
    argparser.add_argument('-t', '--type', help="The type of file to export.", choices=('csv','mat','txt'), default="csv")
    argparser.add_argument('-c', '--channel', action='append', type=int, help="Export the specific channel. Can be used multiple times. If not used, all channels will export.")
    argparser.add_argument('-m', '--nomean', action='store_true', help="Do not remove mean from analog channels.")
    argparser.add_argument('-s', '--span', type=float, default=5.0, help="Length of rolling mean span (seconds) when removing the mean from analog channels. -1 will remove the total mean.")
    argparser.add_argument('-i', '--info', action='store_true', help="Show information about the file and exit.")
    argparser.add_argument('-v', '--version', action='store_true', help="Show detailed version information and exit.")
    argparser.add_argument('source', nargs="*", help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()

    if args.version is True:
        print argparser.description
        print "Converter version %d.%d.%d (build %d) %s, %s" % (VERSION + (BUILD_NUMBER, platform.architecture()[0], datetime.fromtimestamp(BUILD_TIME)))
        print "MIDE EBML library version %d.%d.%d" % ebml_version
        sys.exit(0)

    if len(args.source) == 0:
        print "Error: No source file(s) specified!"
        sys.exit(1)

    sourceFiles = []
    for f in args.source:
        sourceFiles.extend(glob(f))

    if not all(map(os.path.exists, sourceFiles)):
        # Missing a file.
        missing = map(lambda x: not os.path.exists(x), sourceFiles)
        print "Source file(s) could not be found:"
        print "\t" + "\n\t".join(missing)
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

    delimiter = {'tab': '\t', 'pipe': ' | '}.get(args.delimiter, ', ')

    removeMean = not args.nomean
    meanSpan = args.span
    if meanSpan == 0:
        removeMean = False
    elif meanSpan != -1:
        meanSpan /= timeScalar

    try:
        totalSamples = 0
        t0 = datetime.now()
        updater=SimpleUpdater()
        for f in sourceFiles:
            print ('Converting "%s"...' % f)
            if 'mat' not in args.type.lower():
                showInfo(f, toFile=args.output)
            updater.precision = max(0, min(2, (len(str(os.path.getsize(f)))/2)-1))
            updater(starting=True)
            totalSamples += ideExport(f,
                                      outFilename=args.output,
                                      channels=args.channel,
                                      outputType=args.type,
                                      delimiter=delimiter,
                                      updater=updater,
                                      headers=args.names,
                                      removeMean=removeMean,
                                      meanSpan=meanSpan)

        totalTime = datetime.now() - t0
        tstr = str(totalTime).rstrip('0.')
        sampSec = locale.format("%d", totalSamples/totalTime.total_seconds(), grouping=True)
        totSamp = locale.format("%d", totalSamples, grouping=True)
        print "Conversion complete! Exported %s samples in %s (%s samples/sec.)" % (totSamp, tstr, sampSec)
        sys.exit(0)
    except CSVExportError as err:
        print "*** Export error: %s" % err
        sys.exit(1)
    except KeyboardInterrupt:
        print "\n*** Conversion canceled! Export of %s may be incomplete." % f
        sys.exit(0)
    except None as err: #Exception as err:
        print "*** An unexpected %s occurred. Is source an IDE file?" % err.__class__.__name__
        if DEBUG:
            print "*** Message: %s" % err.message
        sys.exit(1)
#     except IOError as err: #Exception as err:
#         print "\n\x07*** Conversion failed! %r" % err
