"""
Batch .IDE Conversion Utility
"""

import argparse
import os
from typing import Optional

from idelib import __version__, __copyright__
from idelib.dataset import EventArray
from idelib import importer
from idelib.matfile import exportMat


# ===========================================================================
#
# ===========================================================================

def sanitizeFilename(filename, keepPaths=True):
    """ A blunt instrument for coercing filenames into validity.

        :param filename: The filename to sanitize.
        :param keepPaths: If `True`, only the base filename will be sanitized.
            If `False`, the file's path will also be sanitized.
        :returns: The sanitized filename.
    """
    if keepPaths:
        path, name = os.path.split(filename)
    else:
        path, name = "", filename

    for c in """*?!;&$/\\:"', <>|""":
        name = name.replace(c, '_')

    while '__' in name:
        name = name.replace('__', '_')

    return os.path.join(path, name)


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
              channels: Optional[list[int]] = None,
              visibility: int = 0,
              startTime: Optional[int] = None,
              endTime: Optional[int] = None,
              out=None,
              outputType: str = ".csv",
              delimiter: str = ', ',
              headers: bool = False,
              removeMean: bool = True,
              useUtcTime: bool = False,
              useIsoFormat: bool = False,
              noBivariates: bool = False,
              useNames: bool = False,
              updater=None,
              timeScalar: float = 1.0) -> int:
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
            not exporting in ISO format.
    """
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
                      useUtcTime=useUtcTime)

    if outputType.lower().endswith('mat'):
        exporter = exportMat
    else:
        exporter = exportCsv
        exportArgs.update({'delimiter': delimiter,
                           'useIsoFormat': useIsoFormat})
        if outputType.lower().endswith('csv') and ',' not in delimiter:
            outputType = '.txt'

    doc = importer.openFile(ideFilename, updater=updater)

    if channels is None:
        channels = [c.id for c in doc.channels.values()
                    if any(sc.visibility < visibility for sc in c.subchannels)]

    if 8 in channels and 32 not in channels:
        channels.append(8)

    importer.readData(doc,
                      channels=channels,
                      starTime=startTime,
                      endTime=endTime,
                      updater=updater)

    exportChannels = [doc.channels[cid] for cid in channels
                      if cid in doc.channels]

    numSamples = 0
    for ch in exportChannels:
        outName = f'{outFilename}_Ch{ch.id:02d}'
        if useNames:
            outName = f'{outName}_{ch.displayName}'
        outName = f"{outName}_{outputType.strip('.')}"

        print(f"  Exporting channel {ch.id} ({ch.name}) to {outName}...",
               file=out, flush=(out is not None)),

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
    return numSamples


# ===========================================================================
#
# ===========================================================================

if __name__ == '__main__':
    delimiters = {'comma': ', ',
                  'tab': '\t',
                  'pipe': ' | '}

    argparser = argparse.ArgumentParser(
        description=f"Mide Batch .IDE Converter {__version__} - {__copyright__}")

    argparser.add_argument('-o', '--output',
                           help=("The output path to which to save the exported files. "
                                 "Defaults to the same as the source file."))
    argparser.add_argument('-t', '--type', choices=('csv', 'mat', 'txt'), default="csv",
                           help="The type of file to export.")
    argparser.add_argument('-c', '--channel', action='append', type=int,
                           help=("Export the specific channel. Can be used multiple times. "
                                 "If not used, all channels will export."))
    argparser.add_argument('-m', '--removemean', action='store_true',
                           help="Remove the mean from accelerometer data.")
    argparser.add_argument('-u', '--utc', action='store_true',
                           help="Write timestamps as UTC 'Unix epoch' time.")
    argparser.add_argument('-n', '--names', action='store_true',
                           help="Include channel names in exported filenames.")

    txtargs = argparser.add_argument_group("Text Export Options (CSV, TXT, etc.)")
    txtargs.add_argument('-r', '--headers', action='store_true',
                         help=("Write 'header' information (column names) as the first row "
                               "of text-based export."))
    txtargs.add_argument('-d', '--delimiter', choices=list(delimiters), default="comma",
                         help="The delimiting character.")
    txtargs.add_argument('-f', '--isoformat', action='store_true',
                         help="Write timestamps as ISO-formatted UTC.")

    argparser.add_argument('-i', '--info', action='store_true',
                           help="Show information about the file and exit.")
    argparser.add_argument('-v', '--version', action='store_true',
                           help="Show detailed version information and exit.")
    argparser.add_argument('source', nargs="+",
                           help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()
