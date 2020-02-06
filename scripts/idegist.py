#!/usr/bin/env python
# coding: utf-8

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)  # Note: this runs in Python 2!

# code edits to make environment work
import sys
import datetime

import numpy as np

sys.path.append('C:\\Users\\bawqatty\\Documents\\GitHub\\SlamStickLab')
import idelib.importer


filename = 'test.IDE'  # use your own filename here

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

        freqs = np.fft.rfftfreq(len(values), d=ts)
        psd_values = np.abs(np.fft.rfft(norm_values, norm='ortho'))**2
        f_argmax = np.argmax(psd_values)

        print(
            ds.filename,
            ds.recorderInfo['RecorderSerial'],
            ds.recorderInfo['PartNumber'],
            subchannel.name,
            np.datetime64(session.utcStartTime, 's'),
            np.datetime64(session.utcStartTime, 's') + np.array(session.lastTime-session.firstTime, dtype='timedelta64[us]'),
            # low Hz
            values.min(),
            values.mean(),
            values.max(),
            # high Hz
            norm_values.min(),
            norm_values.max(),
            values.std(),  # same as RMS
            freqs[f_argmax],
            psd_values[f_argmax],
        )
        print()


ds.close()  # Remember to close your file after you're finished with it!
del ds, channel, subchannel, eventlist, session  # These all depend on the internal file object
