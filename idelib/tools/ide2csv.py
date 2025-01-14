"""
Batch .IDE Conversion Utility
"""

from datetime import datetime
from fnmatch import fnmatch
import locale
import os
import sys
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


def showIdeInfo(dataset, out=sys.stdout, extra=None, **kwargs):
    """ Show information about an IDE file.

        :param dataset: The IDE file to show.
        :param out: A filename or stream to which to write.
        :param extra: A dictionary of extra data to display (i.e. export
            settings).

        Other keyword arguments are passed to `importer.openFile`.
    """
    snFormats = (('W*-*D*', "W{:07d"),
                 ('S*-*D*', "S{:07d}"),
                 ('H*-*D*', "H{:07d}"),
                 ("SF-DR4-0[24]*", "S{:07d}"),
                 ("SF-DR4-0[13]*", "W{:07d}"),
                 ('LOG-0002*', "SSX{:07d}"),
                 ('LOG-0003*', "SSC{:07d}"),
                 ('LOG-0004*', "SSS{:07d}"),
                 ("*", "{07d}"))

    sep = '-' * 40

    if isinstance(out, str):
        with open(out, 'wt') as f:
            return showIdeInfo(dataset, out=f, extra=extra, **kwargs)

    print(dataset.filename, file=out)
    print("=" * 70, file=out)
    if len(dataset.sessions) > 0:
        st = dataset.sessions[0].utcStartTime
        if st:
            print(f'Start time: {datetime.utcfromtimestamp(st)} (UTC)', file=out)
    info = dataset.recorderInfo
    prodName = info.get('ProductName', 'Unknown Prduct Name')
    partNum = info.get('PartNumber', 'Unknown Part Number')
    sn = info.get('RecorderSerial') or 'Unknown'
    username = info.get('RecorderName')
    userdesc = info.get('RecorderDescription')

    if isinstance(sn, int):
        for match, fmt in snFormats:
            if fnmatch(partNum, match):
                sn = fmt.format(sn)
                break

    if prodName != partNum:
        prodName = f'{prodName} ({partNum})'
    print(f'Recorder: {prodName}, serial number {sn}', file=out)

    if username:
        print(f'Device name: {username}', file=out)
    if userdesc:
        print(f'Device description: {userdesc}', file=out)

    print("\nSensors\n" + sep, file=out)
    for s in sorted(dataset.sensors.values(), key=lambda x: x.id):
        print(f"  Sensor {s.id}: {s.name}", file=out)
        if s.traceData:
            for k, v in s.traceData.items():
                print(f"    {k}: {v}", file=out)

    print("\nChannels\n" + sep, file=out)
    for c in sorted(dataset.channels.values(), key=lambda x: x.id):
        print(f"  Channel {c.id}: {c.displayName}", file=out)
        for sc in c.subchannels:
            print(f"    Subchannel {c.id}.{sc.id}: {sc.displayName}", file=out)

    if extra:
        print("\nExport Options\n" + sep, file=out)
        if extra.get('headers'):
            print('  * Column headers', file=out)
        if extra.get('removeMean'):
            print('  * Total mean removed from analog channels', file=out)
        else:
            print('  * No mean removal from analog channels', file=out)

        if extra.get('useUtcTime'):
            if extra.get('useIsoFormat'):
                print('  * Timestamps in ISO format (yyyy-mm-ddThh:mm:ss.s', file=out)
            else:
                print("  * Timestamps in absolute UTC 'Unix' time", file=out)

    print("=" * 70, file=out, flush=True)


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
            outName = f'{outName}_{ch.displayName}'
        outName = f"{outName}_.{outputType}"

        print(f"  Exporting channel {ch.id} ({ch.name}) to {outName}...",
               file=out, flush=(out is not None))

        try:
            events = ch.getSession()
            if len(events) == 0:
                continue

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

        except None:
            pass

    doc.close()
    return numSamples


# ===========================================================================
#
# ===========================================================================

if __name__ == '__main__':
    import argparse
    from glob import glob

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

    # argparser.add_argument('-i', '--info', action='store_true',
    #                        help="Show information about the file and exit.")
    argparser.add_argument('source', nargs="+",
                           help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()

    sources = []
    for source in args.source:
        sources.extend(glob(source))

    if not sources:
        print("No source files found.", file=sys.stderr, flush=True)
        exit(1)

    try:
        print(f'Converting {len(sources)} file(s)...')
        totalSamples = 0
        t0 = datetime.now()
        updater = importer.SimpleUpdater()

        for source in sources:
            updater.precision = max(0, min(2, (len(str(os.path.getsize(source))) / 2) - 1))
            updater(starting=True)

            print(f'Converting {source}...')
            totalSamples += ideExport(source,
                                      outFilename=args.output,
                                      channels=args.channel,
                                      outputType=args.type,
                                      delimiter=delimiters.get(args.delimiter, ', '),
                                      updater=updater,
                                      headers=args.names,
                                      removeMean=args.removemean,
                                      useUtcTime=args.utc,
                                      useIsoFormat=args.isoformat,
                                      useNames=args.names)

        totalTime = datetime.now() - t0
        tstr = str(totalTime).rstrip('0.')
        sampSec = locale.format_string("%d", totalSamples/totalTime.total_seconds(), grouping=True)
        totSamp = locale.format_string("%d", totalSamples, grouping=True)
        print(f"Conversion complete! Exported {totSamp} samples in {tstr} ({sampSec} samples/sec.)")

    except KeyboardInterrupt:
        print("\n*** Conversion canceled! Export of may be incomplete.")
        sys.exit(0)
