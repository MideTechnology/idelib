'''
Command-line utility to batch export IDE files as CSV or MAT. Intended for
small files.

Created on Jan 26, 2016

@author: dstokes
'''
from __future__ import absolute_import

from datetime import datetime
import importlib
import locale
import os.path
import platform
import sys

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    _ = importlib.import_module('mide_ebml')
except ImportError:
    sys.path.append('..')

from mide_ebml import __version__ as ebml_version
from mide_ebml import importer
from mide_ebml.matfile import exportMat

from common import sanitizeFilename

from .common import showIdeInfo, SimpleUpdater, validateArguments
from .build_info_ide2csv import DEBUG, BUILD_NUMBER, VERSION, BUILD_TIME

__version__ = VERSION

#===============================================================================
# 
#===============================================================================

timeScalar = 1.0/(10**6)

#===============================================================================
#
#===============================================================================

class CSVExportError(Exception):
    pass


#===============================================================================
#
#===============================================================================

def exportCsv(events, filename, callback=None, **kwargs):
    """ Wrapper for CSV export, making it like MAT export.
    """
    # MAT export updates the callback with exported filenames, exportCSV does
    # not. Add the filename to the list 'manually.'
    if callback is not None:
        callback.outputFiles.add(filename)
        
    with open(filename, 'wb') as f:
        return events.exportCsv(f, callback=callback, **kwargs)


#===============================================================================
#
#===============================================================================

def ideExport(ideFilename, outFilename=None, channels=None,
            startTime=0, endTime=None, updateInterval=1.5,  out=sys.stdout, 
            outputType=".csv", delimiter=', ', headers=False, 
            removeMean=True, meanSpan=5.0, useUtcTime=False,
            useIsoFormat=False, noBivariates=False, useNames=False,
            **kwargs):
    """ The main function that handles generating text files from an IDE file.
        
        @param ideFilename: The name of the source IDE file.
        @keyword outFilename: The output path and/or base filename.
        @keyword channels: The channels to export. Defaults to all.
        @keyword startTime: The start of the export range.
        @keyword endTime: The end of the export range.
        @keyword updateInterval: The maximum time between progress updates,
            in seconds.
        @keyword out: The output stream for messages, etc.
        @keyword outputType: The file extension of the export type.
        @keyword delimiter: The string to use to separate values in text
            output formats (CSV, TXT, etc.)
        @keyword headers: If `True`, write column headers to the first row of
            text output.
        @keyword removeMean: If `True`, remove the mean from the data. Only
            applicable to channels with min/mean/max data.
        @keyword meanSpan: The rolling mean span, if `removeMean` is `True`.
            ``-1`` for total mean removal.
        @keyword useUtcTime: If `True`, export timestamps (the first column)
            using absolute UTC 'epoch' values.
        @keyword useIsoFormat: If `True`, write timestamps as ISO date/time
            strings.
        @keyword noBivariates: If `True`, disable bivariate references.
        @keyword useNames: If `True`, include the channel name in the exported
            filenames, not just channel ID number.
    """
    updater = kwargs.get('updater', importer.nullUpdater)

    if removeMean:
        if meanSpan != -1:
            meanSpan /= timeScalar
    else:
        meanSpan = None

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

    # Common keyword arguments for the exports
    exportArgs = dict(callback=updater, 
                      timeScalar=timeScalar, 
                      headers=headers,
                      removeMean=removeMean, 
                      meanSpan=meanSpan,
                      useUtcTime=useUtcTime)

    if outputType.lower().endswith('mat'):
        exporter = exportMat
    else:
        exporter = exportCsv
        exportArgs.update({'delimiter': delimiter,
                           'useIsoFormat': useIsoFormat})
        if outputType.lower().endswith('csv') and ',' not in delimiter:
            outputType = '.txt'

    doc = importer.importFile(ideFilename)

    if channels is None:
        exportChannels = doc.channels.values()
    else:
        exportChannels = [c for c in doc.channels.values() if c.id in channels]

    numSamples = 0
    for ch in exportChannels:
        outName = "%s_Ch%02d" % (outFilename, ch.id)
        if useNames:
            outName = "%s_%s" % (outName, sanitizeFilename(ch.displayName, keepPaths=False))
        outName = "%s.%s" % (outName, outputType.strip('.'))
        
        _print("  Exporting Channel %d (%s) to %s..." % (ch.id, ch.name, outName)),
        
        try:
            events = ch.getSession()
            events.noBivariates = noBivariates
            
            if len(events) == 0: 
                continue
            
            startIdx, stopIdx = events.getRangeIndices(startTime, endTime)

            numSamples += (exporter(events, outName, 
                                    start=startIdx, stop=stopIdx, 
                                    **exportArgs)[0] * len(ch.children))

        except None:
            pass

    doc.close()
    doc = None
    events = None
    return numSamples 


#===============================================================================
#
#===============================================================================

if __name__ == "__main__":
    import argparse

    argparser = argparse.ArgumentParser(description="Mide Batch .IDE Converter v%d.%d.%d - Copyright (c) 2016 Mide Technology" % VERSION)
    argparser.add_argument('-o', '--output', help="The output path to which to save the exported files. Defaults to the same as the source file.")
    argparser.add_argument('-t', '--type', help="The type of file to export.", choices=('csv','mat','txt'), default="csv")
    argparser.add_argument('-c', '--channel', action='append', type=int, help="Export the specific channel. Can be used multiple times. If not used, all channels will export.")
    argparser.add_argument('-m', '--meanspan', type=float, default=5.0, help="Length (in seconds) of rolling mean span (DC offset) when removing the mean from analog channels. -1 will remove the total mean. 0 will disable mean removal. Defaults to 5 seconds.")
    argparser.add_argument('-u', '--utc', action='store_true', help="Write timestamps as UTC 'Unix epoch' time.")
    argparser.add_argument('-n', '--names', action='store_true', help="Include channel names in exported filenames.")
    
    txtargs = argparser.add_argument_group("Text Export Options (CSV, TXT, etc.)")
    txtargs.add_argument('-r', '--headers', action='store_true', help="Write 'header' information (column names) as the first row of text-based export.")
    txtargs.add_argument('-d', '--delimiter', choices=('comma','tab','pipe'), help="The delimiting character.", default="comma")
    txtargs.add_argument('-f', '--isoformat', action='store_true', help="Write timestamps as ISO-formatted UTC.")
    
    argparser.add_argument('-i', '--info', action='store_true', help="Show information about the file and exit.")
    argparser.add_argument('-v', '--version', action='store_true', help="Show detailed version information and exit.")
    argparser.add_argument('source', nargs="+", help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()

    if args.version is True:
        print argparser.description
        print "Converter version %d.%d.%d (build %d) %s, %s" % (VERSION + (BUILD_NUMBER, platform.architecture()[0], datetime.fromtimestamp(BUILD_TIME)))
        print "MIDE EBML library version %d.%d.%d" % ebml_version
        sys.exit(0)

    sourceFiles, output, startTime, endTime = validateArguments(args)

    delimiter = {'tab': '\t', 'pipe': ' | '}.get(args.delimiter, ', ')

    meanSpan = args.meanspan
    removeMean = meanSpan != 0
    
    useUtcTime = args.utc
    useIsoFormat = args.isoformat
    if 'mat' not in args.type.lower():
        useUtcTime = useUtcTime or useIsoFormat
    else:
        useIsoFormat = False
    
    try:
        totalSamples = 0
        t0 = datetime.now()
        updater=SimpleUpdater()
        for f in sourceFiles:
            print ('Converting "%s"...' % f)
            
            exportArgs = dict(outFilename=args.output,
                              channels=args.channel,
                              outputType=args.type,
                              delimiter=delimiter,
                              updater=updater,
                              headers=args.names,
                              removeMean=removeMean,
                              meanSpan=meanSpan,
                              useUtcTime=useUtcTime,
                              useIsoFormat=useIsoFormat,
                              useNames=args.names)
            
            showIdeInfo(f, toFile=args.output, extra=exportArgs)
                
            updater.precision = max(0, min(2, (len(str(os.path.getsize(f)))/2)-1))
            updater(starting=True)
            
            totalSamples += ideExport(f, **exportArgs)

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
