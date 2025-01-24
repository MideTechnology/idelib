"""
IDE Info Viewer: A utility for displaying basic information about an
IDE file in a human-readable format.
"""

import datetime
from fnmatch import fnmatch
import os
import sys
from typing import Any, Dict, IO, List, Optional, Union

from idelib import __version__, __copyright__
from idelib.dataset import Dataset
from idelib import importer
from idelib import util


__all__ = ('showIdeInfo', 'batchInfo')


def showIdeInfo(dataset: Dataset,
                out: Optional[Union[str, IO]] = None,
                extra: Optional[Dict[str, Any]] = None):
    """ Show information about an IDE file.

        :param dataset: The IDE file to show.
        :param out: A filename or stream to which to write.
        :param extra: A dictionary containing extra data to display (i.e.
            export settings).
    """
    import locale
    locale.setlocale(locale.LC_ALL, '')

    # Serial number formats for different part numbers.
    snFormats = (('W*-*D*', "W{:07d}"),
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
            return showIdeInfo(dataset, out=f, extra=extra)

    filename = dataset.filename
    if not filename or not os.path.exists(filename):
        filename = None

    print(f'{"=" * 70}\n{dataset.filename or dataset.name}')
    print(f'{"-" * 70}', file=out)
    if filename:
        filesize = locale.format_string("%d", os.path.getsize(dataset.filename), grouping=True)
        print(f'File size: {filesize} bytes', file=out)
    if len(dataset.sessions) > 0:
        st = dataset.sessions[0].utcStartTime
        if st:
            print(f'Start time: {datetime.datetime.utcfromtimestamp(st)} (UTC)', file=out)
        if filename:
            start, end = util.getLength(dataset)
            print(f'Duration: {datetime.timedelta(microseconds=end - start)}', file=out)
        print(file=out)
    info = dataset.recorderInfo
    prodName = info.get('ProductName', 'Unknown Product Name')
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
        headers = extra.pop('headers', None)
        removeMean = extra.pop('removeMean', None)
        useUtcTime = extra.pop('useUtcTime', None)
        useIsoFormat = extra.pop('useIsoFormat', None)

        if headers:
            print('  * Column headers', file=out)
        if removeMean:
            print('  * Total mean removed from analog channels', file=out)
        else:
            print('  * No mean removal from analog channels', file=out)

        if useUtcTime:
            if useIsoFormat:
                print('  * Timestamps in ISO format (yyyy-mm-ddThh:mm:ss.s', file=out)
            else:
                print("  * Timestamps in absolute UTC 'Unix epoch' time (seconds)", file=out)

        if extra:
            print("\nAdditional Info\n{sep}", file=out)
            for k, v in extra.items():
                print(f"    {k}: {v}", file=out)

    print("=" * 70, file=out, flush=True)


def batchInfo(sources: List[str],
              out: Optional[IO] = None):
    """ Show information about a collection of IDE files.

        :param sources: A list of IDE files to view.
        :param out: A filename or stream to which to write. Defaults to `stdout`.
    """
    for source in sources:
        try:
            with importer.openFile(source) as doc:
                showIdeInfo(doc, out=out)
        except IOError as err:
            print(f'Error: {err}', file=out)


# ===========================================================================
#
# ===========================================================================

def main(argv=None):
    import argparse
    from glob import glob

    argparser = argparse.ArgumentParser(
        description=f"IDE Info Viewer v{__version__} - {__copyright__}")

    argparser.add_argument('-o', '--output',
        help="The output path to which to save the info text.")
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
        batchInfo(sources, out=args.output)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
