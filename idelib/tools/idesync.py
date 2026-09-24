"""
Batch .IDE Synchronization Utility: Add sync info to IDE files.

Note: This utility modifies the files its synchronizes, adding or changing
existing userdata appended to the end of the recordings.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import List, Tuple, Union

from idelib import __version__, __copyright__
from idelib import importer
from idelib import sync
from idelib import userdata


# ===========================================================================
#
# ===========================================================================

def syncFiles(reference: Union[str, Path],
              *recordings:  Union[str, Path],
              inherit: bool = False,
              gps: bool = False,
              verbose: bool = True) -> Tuple[List[str], List[str]]:
    """ Synchronize recording files, writing the sync info in their userdata
        for later use.

        :param reference: The 'reference' IDE filename, to which the other
            recordings will be synchronized.
        :param recordings: The IDE filenames to sync to the reference. These
            are optionl if `gps` is `True`.
        :param inherit: If `True`, information in the reference syncing it
            to another recording will be used to sync the other files, as
            opposed to syncing them to the reference itself.
        :param gps: If `True`, update the reference file's starting time
            using the GPS/GNSS it contains. The new time base will be
            written to the reference file's user data.
        :returns: A tuple of two lists of filenames: successfully synced
            and failures. Note that the utility doesn't really use the
            return values; they're primarily for testing.
    """
    successes, failures = [], []
    synced = set()

    if verbose:
        refName = reference
    else:
        refName = os.path.basename(reference)

    with importer.importFile(reference) as ref:
        synced.add(ref.fingerprint)
        sync.loadSyncInfo(ref)
        if gps:
            if inherit:
                raise sync.SyncError('Arguments gps and inherit are mutually exclusive')
            try:
                old, new = sync.applyGNSSTime(ref, clear=True)
                sync.updateUserdata(ref)
                userdata.saveUserData(ref)
                olddt = datetime.fromtimestamp(old, timezone.utc)
                newdt = datetime.fromtimestamp(new, timezone.utc)
                dt1, dt2 = sorted((olddt, newdt))
                diff = f"{'-' if old < new else ''}{dt2 - dt1}"
                print(f'GPS/GNSS time base applied to reference file {refName}; '
                      f'now {newdt.isoformat()} UTC ({diff} difference)',
                      file=sys.stdout, flush=True)
                successes.append(reference)
            except sync.SyncError:
                raise sync.SyncError(f'No GPS/GNSS data found in {refName}')
        elif inherit:
            info = sync.getSyncInfo(ref)
            if not sync.hasSyncReferenceInfo(info):
                raise sync.SyncError('Reference file has no sync info to inherit')

        for filename in recordings:
            fname = filename if verbose else os.path.basename(filename)
            with importer.importFile(filename) as doc:
                if doc.fingerprint in synced:
                    continue
                synced.add(doc.fingerprint)
                try:
                    sync.loadSyncInfo(doc)
                    sync.sync(ref, doc, inherit=inherit)
                    sync.updateUserdata(doc)
                    userdata.saveUserData(doc)
                    successes.append(filename)
                    print(f'Synced {fname} to {refName}', file=sys.stdout, flush=True)
                except (IOError, sync.SyncError) as err:
                    failures.append(filename)
                    print(f'Could not sync {fname} to {refName}: {err}', file=sys.stderr, flush=True)

        return successes, failures


# ===========================================================================
#
# ===========================================================================

def main(argv=None):
    import argparse
    from glob import glob
    import locale

    locale.setlocale(locale.LC_ALL, '')

    argparser = argparse.ArgumentParser(
        description=f"Batch IDE Synchronization Utility v{__version__} - {__copyright__}")

    argparser.add_argument('-g', '--gps', action='store_true',
        help=("Update the reference recording's start time using its GPS/GNSS data. "
              "Cannot be used in conjunction wtih --inherit."))
    argparser.add_argument('-i', '--inherit', action='store_true',
        help=("If the reference recording has been synced to another, sync "
              "the other datasets to that (rather than the reference itself). "
              "Cannot be used in conjunction with --gps."))
    argparser.add_argument('-v', '--verbose', action='store_true',
        help=("Show additional information (complete file paths in messages, etc.)."))
    argparser.add_argument('recordings', nargs='+', metavar="FILENAME.IDE",
        help=("Recordings to sync. If more than one is supplied, the first "
              "will be used as the reference to which the others are synced. "
              "Only one recording is required if --gps is used."))

    args = argparser.parse_args(argv)

    if args.gps and args.inherit:
        print("ERROR: --gps and --inhert cannot be used together",
              file=sys.stderr, flush=True)
        exit(1)

    recordings = []
    for source in args.recordings:
        recordings.extend([s for s in glob(source) if os.path.isfile(s)])

    if len(recordings) < 2 and not args.gps:
        print("ERROR: Nothing to do; no change to the reference file, no other files found.",
              file=sys.stderr, flush=True)
        exit(1)

    try:
        syncFiles(*recordings, gps=args.gps, inherit=args.inherit,
                  verbose=args.verbose)

    except sync.SyncError as err:
        print(f"ERROR: {err}", file=sys.stderr, flush=True)
        exit(1)

    except KeyboardInterrupt:
        print("\n*** Conversion canceled!", file=sys.stdout, flush=True)
        sys.exit(0)


if __name__ == '__main__':
    main()
