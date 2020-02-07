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


def psd(array, dt=1.):
    # Direct numpy function calls
    freqs = np.fft.fftfreq(len(array), d=dt)
    dft_norm = np.fft.fft(array, norm='ortho')

    # Calculate psd values
    psd = np.abs(dft_norm)**2

    # Combine negative aliased frequencies w/ non-negative counterparts
    n = len(psd)//2 + 1
    freqs_pos = np.abs(freqs[:n])

    psd_posfreq = psd[:n]
    psd_negfreq = psd[n:]
    psd_posfreq[1:1+len(psd)-n] += psd_negfreq[::-1]

    return freqs_pos, psd_posfreq


def bulk_summarize(dirpath):
    output_path = os.path.split(dirpath)[0] + '-summary.csv'
    with open(output_path, 'wb') as csvfile:
        csv_writer = csv.writer(csvfile)

        CsvRowTuple = namedtuple('CsvRowTuple', [
            'filename',
            'device_serial',
            'device_part',
            'channel_name',
            'utcStartTime',
            'utcEndTime',
            'sampling_frequency',
            'minimum_value',
            'maximum_value',
            'mean_value',
            'rms',
            'peak_frequency',
            'peak_frequency_power',
        ])

        # Writing column headers
        csv_writer.writerow(CsvRowTuple._fields)

        for filename in ide_files_in(dirpath):  # use your own pathname here
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

                    psd_freqs, psd_values = psd(values, dt=ts)
                    f_argmax = np.argmax(psd_values)

                    csv_writer.writerow(CsvRowTuple(
                        filename=ds.filename,
                        device_serial=ds.recorderInfo['RecorderSerial'],
                        device_part=ds.recorderInfo['PartNumber'],
                        channel_name=subchannel.name,
                        utcStartTime=np.datetime64(session.utcStartTime, 's'),
                        utcEndTime=np.datetime64(session.utcStartTime, 's') + np.array(session.lastTime-session.firstTime, dtype='timedelta64[us]'),
                        sampling_frequency=fs,
                        minimum_value=values.min(),
                        maximum_value=values.max(),
                        mean_value=values.mean(),
                        rms=values.std(),
                        peak_frequency=freqs[f_argmax],
                        peak_frequency_power=psd_values[f_argmax],
                    ))

            ds.close()  # Remember to close your file after you're finished with it!
            del ds, channel, subchannel, eventlist, session  # These all depend on the internal file object


bulk_summarize(".\\ide_files\\")
