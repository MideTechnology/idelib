"""
Batch .IDE Conversion Utility: Export IDE files in various formats.
"""

import datetime
import os
import sys
from typing import Callable, IO, List, Optional, Tuple

from idelib import __version__, __copyright__
from idelib.dataset import EventArray
from idelib import importer
from idelib.matfile import exportMat
from idelib.tools.ideinfo import showIdeInfo

# try:
#     import tqdm.auto
#     Updater = importer.TQDMUpdater
# except ModuleNotFoundError:
#     Updater = importer.SimpleUpdater

Updater = importer.SimpleUpdater


# ===========================================================================
#
# ===========================================================================

def sanitizeFilename(filename):
    """ A blunt instrument for coercing filenames into validity. It replaces
        commonly disallowed characters with underscores.

        :param filename: The filename to sanitize.
        :returns: The sanitized filename.
    """
    for c in """*?!;&$/\\:"', <>|""":
        filename = filename.replace(c, '_')

    while '__' in filename:
        filename = filename.replace('__', '_')

    return filename


def exportCsv(events: EventArray,
              filename: str,
              callback: Optional = None,
              **kwargs):
    """ Wrapper for CSV export, making it like MAT export.
    """
    # MAT export updates the callback with exported filenames, exportCSV does
    # not. Add the filename to the list 'manually.'
    if callback is not None:
        callback.outputFiles.add(filename)

    with open(filename, 'wt') as f:
        return events.exportCsv(f, callback=callback, **kwargs)


def ideExport(ideFilename: str,
              outFilename: Optional[str] = None,
              channels: Optional[List[int]] = None,
              visibility: int = 10,
              startTime: Optional[int] = None,
              endTime: Optional[int] = None,
              out: Optional[IO] = None,
              outputType: str = "csv",
              delimiter: str = ', ',
              headers: bool = False,
              removeMean: bool = True,
              useUtcTime: bool = False,
              useIsoFormat: bool = False,
              noBivariates: bool = False,
              useNames: bool = False,
              updater: Optional[Callable] = None,
              timeScalar: float = 1.0,
              saveInfo: bool = True) -> int:
    """ The main function that handles generating text files from an IDE file.

        :param ideFilename: The name of the source IDE file.
        :param outFilename: The output path and/or base filename.
        :param channels: The channels to export. Defaults to all.
        :param visibility: The maximum channel visibility to export. Defaults
            to 0 (standard data sources, diagnostic channels excluded).
            Channels with any visible SubChannels will be exported. See
            `idelib.dataset.Dataset.getPlots()` for info on visibility
            values.
        :param startTime: The start of the export range, in microseconds.
        :param endTime: The end of the export range, in microseconds.
        :param out: The output stream for messages, etc.
        :param outputType: The file extension of the export type.
        :param delimiter: The string to use to separate values in text
            output formats (CSV, TXT, etc.).
        :param headers: If `True`, write column headers to the first row of
            text output.
        :param removeMean: If `True`, remove the mean from the exported data.
            Only applicable to accelerometer and analogchannels with
            min/mean/max data.
        :param useUtcTime: If `True`, export timestamps (the first column)
            using absolute UTC 'epoch' values.
        :param useIsoFormat: If `True`, write timestamps as ISO date/time
            strings. Only applicable to text-based export formats.
        :param noBivariates: If `True`, disable bivariate references.
        :param useNames: If `True`, include the channel name in the exported
            filenames, not just channel ID number.
        :param updater: Optional 'updater' object; see `idelib.importer`.
        :param timeScalar: The scaling factor for exported timestamps, if
            not exporting in ISO format. For scaling native microseconds to
            seconds, etc.
        :param saveInfo: If `True`, save a text file with key recording
            metadata and summary info.
    """
    b = os.path.basename(ideFilename)
    outputType = outputType.strip('.')

    if outFilename is None:
        outFilename = os.path.splitext(ideFilename)[0]
    elif os.path.isdir(outFilename):
        outFilename = os.path.join(outFilename, os.path.splitext(b)[0])

    doc = importer.openFile(ideFilename, updater=updater)
    if saveInfo:
        with open(f'{outFilename}_info.txt', 'wt') as f:
            showIdeInfo(doc, out=f, extra={'headers': headers,
                                            'removeMean': removeMean,
                                            'useUtcTime': useUtcTime,
                                            'useIsoFormat': useIsoFormat})

    if not channels:
        channels = [c.id for c in doc.channels.values()
                    if any(sc.visibility < visibility for sc in c.subchannels)]

    loadedChannels = set(channels)

    if 8 in channels:
        # Analog sensor in export; make sure temperature included.
        # FUTURE: Make this list based on bivariate polynomials.
        loadedChannels.update([20, 36])

    importer.readData(doc,
                      channels=sorted(loadedChannels),
                      startTime=startTime,
                      endTime=endTime,
                      updater=updater)

    exportChannels = [doc.channels[cid] for cid in channels
                      if cid in doc.channels]

    if outputType.lower().endswith('mat'):
        exporter = exportMat
    else:
        exporter = exportCsv
        if outputType.lower().endswith('csv') and ',' not in delimiter:
            outputType = 'txt'

    numSamples = 0
    for ch in exportChannels:
        outName = f'{outFilename}_Ch{ch.id:02d}'
        if useNames:
            outName = f'{outName}_{sanitizeFilename(ch.displayName)}'
        outName = f"{outName}.{outputType}"

        print(f"  Exporting channel {ch.id} ({ch.name}) to {outName}...",
               file=out, flush=(out is not None))

        events = ch.getSession()
        if len(events) == 0:
            continue

        if ch.allowMeanRemoval:
            events.removeMean = removeMean

        num, _dt = exporter(events, outName,
                            callback=updater,
                            timeScalar=timeScalar,
                            headers=headers,
                            removeMean=removeMean,
                            useUtcTime=useUtcTime,
                            delimiter=delimiter,
                            useIsoFormat=useIsoFormat,
                            noBivariates=noBivariates)

        numSamples += num * len(ch.children)

    doc.close()
    return numSamples


# ===========================================================================
#
# ===========================================================================

def batchExport(sources: List[str],
                out=None,
                updater=None,
                **kwargs) -> Tuple[datetime.timedelta, int]:
    """ Batch export a collection of IDE files. See `ideExport()` for
        all keyword arguments.

        :param sources: A list of IDE files to export.
        :param out: The output stream for messages, etc.
        :param updater: Optional 'updater' object; see `idelib.importer`.
    """

    totalSamples = 0
    t0 = datetime.datetime.now()

    for n, source in enumerate(sources, 1):
        if updater:
            updater(starting=True)

        print(f'Converting {source} ({n}/{len(sources)})...', file=out)

        try:
            totalSamples += ideExport(source, out=out, updater=updater, **kwargs)
        except IOError as err:
            print(f'Error: {err}', file=out)

    return datetime.datetime.now() - t0, totalSamples


# ===========================================================================
#
# ===========================================================================

def main(argv=None):
    import argparse
    from glob import glob
    import locale

    locale.setlocale(locale.LC_ALL, '')

    delimiters = {'comma': ', ',
                  'tab': '\t',
                  'pipe': ' | '}

    types = ('csv', 'mat', 'txt')

    argparser = argparse.ArgumentParser(
        description=f"Batch IDE Conversion Utility v{__version__} - {__copyright__}")

    argparser.add_argument('-o', '--output',
        help="The output path to which to save the exported files. Defaults to the same "
             "location as the source file.")
    argparser.add_argument('-t', '--type', choices=types, default="csv",
        help="The type of file to export.")
    argparser.add_argument('-c', '--channel', action='append', type=int,
        help="Export the specific channel. Can be used multiple times. If not used, "
             "all channels will export.")
    argparser.add_argument('-m', '--removemean', action='store_true',
        help="Remove the mean from accelerometer data.")
    argparser.add_argument('-u', '--utc', action='store_true',
        help="Write timestamps as UTC 'Unix epoch' time.")
    argparser.add_argument('-n', '--names', action='store_true',
        help="Include channel names in exported filenames.")

    txtargs = argparser.add_argument_group("Text Export Options (CSV, TXT, etc.)")
    txtargs.add_argument('-r', '--headers', action='store_true',
        help="Write 'header' information (column names) as the first row of text-based export.")
    txtargs.add_argument('-d', '--delimiter', choices=list(delimiters), default="comma",
        help="The delimiting character, for exporting non-CSV text-based files.")
    txtargs.add_argument('-f', '--isoformat', action='store_true',
        help="Write timestamps as ISO-formatted UTC.")

    argparser.add_argument('source', nargs="+", metavar="FILENAME.IDE",
        help="The source .IDE file(s) to convert. Wildcards permitted.")

    args = argparser.parse_args(argv)

    sources = []
    for source in args.source:
        sources.extend([s for s in glob(source) if os.path.isfile(s)])

    if not sources:
        print("No source files found.", file=sys.stderr, flush=True)
        exit(1)

    try:
        delimiter = delimiters.get(args.delimiter, ', ')
        updater = None  # Updater()
        tt, ts = batchExport(sources,
                             outFilename=args.output,
                             channels=args.channel,
                             outputType=args.type,
                             delimiter=delimiter,
                             headers=args.names,
                             removeMean=args.removemean,
                             useUtcTime=args.utc,
                             useIsoFormat=args.isoformat,
                             useNames=args.names,
                             updater=updater)

        numfiles = f'{len(sources)} file' + ('s' if len(sources) > 1 else '')
        tstr = str(tt).rstrip('0.')
        sampSec = locale.format_string("%d", ts//tt.total_seconds(), grouping=True)
        totSamp = locale.format_string("%d", ts, grouping=True)
        print(f"Conversion complete! Exported {totSamp} samples from {numfiles} "
              f"in {tstr} ({sampSec} samples/sec.)")

    except KeyboardInterrupt:
        print("\n*** Conversion canceled!")
        sys.exit(0)


if __name__ == '__main__':
    main()
