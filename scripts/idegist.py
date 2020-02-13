#!/usr/bin/env python
# coding: utf-8

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)  # Note: this runs in Python 2!

# code edits to make environment work
import os
import sys
import csv
import datetime
from collections import namedtuple

import numpy as np

sys.path.append('C:\\Users\\bawqatty\\Documents\\GitHub\\SlamStickLab')
import idelib.importer


def ide_files_in(dirpath):
    return (
        filepath for filepath in (
            os.path.join(dirpath, filename)
            for filename in os.listdir(dirpath)
            # if you need to search a directory recursively, use `os.path.walk`
        )
        if os.path.isfile(filepath)
        and os.path.splitext(filepath)[-1].lower() == ".ide"
    )


CsvRowTuple = namedtuple('CsvRowTuple', [
    'filename',
    'device_serial',
    'device_part',
    'channel_name',
    'unit_type',
    'units',
    'utcStartTime',
    'utcEndTime',
    'sampling_frequency',
    'minimum_value',
    'maximum_value',
    'mean_value',
    'rms',
])


def summaries(filepaths):
    for filename in filepaths:  # use your own pathname here
        ds = idelib.importer.importFile(filename)

        for channel in ds.channels.values():
            for subchannel in channel.subchannels:
                eventlist = subchannel.getSession()
                session = eventlist.session
                array = eventlist[:]

                times = array[0]
                values = array[1]
                utc_times = np.datetime64(session.utcStartTime, 's') + times.astype('timedelta64[us]')

                ts = np.diff(times*1e-6).mean()
                fs = 1/ts

                norm_values = values - values.mean()

                yield CsvRowTuple(
                    filename=ds.filename,
                    device_serial=ds.recorderInfo['RecorderSerial'],
                    device_part=ds.recorderInfo['PartNumber'],
                    channel_name=subchannel.name,
                    unit_type=eventlist.units[0],
                    units=eventlist.units[1].replace(u'\xb0', u'degrees '),
                    utcStartTime=np.datetime64(session.utcStartTime, 's'),
                    utcEndTime=np.datetime64(session.utcStartTime, 's') + np.array(session.lastTime-session.firstTime, dtype='timedelta64[us]'),
                    sampling_frequency=fs,
                    minimum_value=values.min(),
                    maximum_value=values.max(),
                    mean_value=values.mean(),
                    rms=values.std(),
                )

        ds.close()  # Remember to close your file after you're finished with it!
        del ds, channel, subchannel, eventlist, session  # These all depend on the internal file object


def summarize_to_csv(csvpath, filepaths):
    with open(csvpath, 'wb') as csvfile:
        csv_writer = csv.writer(csvfile)

        # Writing column headers
        csv_writer.writerow(CsvRowTuple._fields)

        for file_summary in summaries(filepaths):
            csv_writer.writerow(file_summary)


def main():
    import argparse
    import glob

    parser = argparse.ArgumentParser(description='Summarize ide files.')
    parser.add_argument(
        'file_patterns',
        help='a set of filepaths / glob patterns of .IDE files to summarize',
        nargs='+',
    )
    parser.add_argument(
        '-o', '--outfile',
        help='the path for the output csv file',
        required=True,
    )

    args = parser.parse_args()

    ide_files = [
        filepath
        for file_pattern in args.file_patterns
        for filepath in glob.iglob(file_pattern)
        if os.path.isfile(filepath)
        and os.path.splitext(filepath)[1].lower() == '.ide'
    ]

    if len(ide_files) == 0:
        print('no .IDE files matching the input paths/patterns')
        return

    summarize_to_csv(args.outfile, ide_files)


if __name__ == "__main__":
    main()
