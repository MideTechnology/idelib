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
ch = (ch for ch in ds.channels.values()).next()
eventlist = ch.getSession()
session = eventlist.session
array = eventlist[:]

times = array[0]
values = array[1:]
utc_times = np.datetime64(session.utcStartTime, 's') + times.astype('timedelta64[us]')

ts = np.diff(times*1e-6).mean()
fs = 1/ts

norm_values = values - values.mean(axis=1).reshape(-1, 1)

freqs = np.fft.rfftfreq(values.shape[1], d=ts)
psd_values = np.abs(np.fft.rfft(norm_values, norm='ortho', axis=1))**2
f_argmax = np.argmax(psd_values, axis=1)

print(
    ds.filename,
    ds.recorderInfo['RecorderSerial'],
    ds.recorderInfo['PartNumber'],
    ch.name,
    np.datetime64(session.utcStartTime, 's'),
    np.datetime64(session.utcStartTime, 's') + np.array(session.lastTime-session.firstTime, dtype='timedelta64[us]'),
    # low Hz
    values.min(axis=1),
    values.mean(axis=1),
    values.max(axis=1),
    # high Hz
    norm_values.min(axis=1),
    norm_values.max(axis=1),
    values.std(axis=1),  # same as RMS
    freqs[f_argmax],
    psd_values[(np.arange(len(f_argmax)), f_argmax)],
)


ds.close()  # Remember to close your file after you're finished with it!
del ds, ch, eventlist, session  # These all depend on the internal file object
