"""
================================================================================
Example IDE parsing
============================================================================
(c) 2020 Mide Technology Corp.

    This example will demonstrate how to:
      - load an IDE file
      - examine the available channels in the file
      - find metadata about the file and channels in the file
      - extract and plot data from the file

Requirements
------------
Python 3.5+
numpy 1.16.6+
matplotlib

Requirements can be installed with:
  $ pip install .[example]
"""

import matplotlib
matplotlib.use('tkagg')
import matplotlib.pyplot as plt
import numpy as np

import idelib

__author__ = 'Connor Flanigan'
__copyright__ = 'Copyright 2020, Mide Technology Corp'
__credits__ = ['Connor Flanigan']

# Loading an ide file is very simple, the supporting files are defined by
# default in idelib-archive.  This function returns a Document object which contains
# the data for the given file
doc = idelib.importFile('../test.ide')


# The channels in a document are contained in an easily accessed dictionary
print("file: {0}".format(doc.name))
for chID in doc.channels:
    chObj = doc.channels[chID]
    print("    Channel: {0}".format(chObj))
    for schId, schObj in enumerate(chObj.subchannels):
        print("        SubChannel: {0}".format(schObj))
        print("            Data Type: {0}, units: {1}".format(*schObj.units))


# Channel 8 is the accelerometer data, so we'll start with that.
# First, we get the EventArray
ch8EventArray = doc.channels[8].getSession()

# The EventArray object has several methods to access data, but the simplest is
# EventArray.arraySlice, which returns a numpy ndarray where the first row is
# the time in microseconds, and the following rows are the subchannels in order
ch8Data = ch8EventArray.arraySlice()
ch8Time = ch8Data[0, :]/1e6
ch8NSubchannels = len(doc.channels[8].subchannels)


# Now we can plot the data
fig = plt.figure()
fig.suptitle(doc.channels[8].displayName)


# for every subchannel, add a subplot, plot the data, and label the axes with
# the name of the subchannel and its units
axes = fig.subplots(ch8NSubchannels, 1,
                    sharex='all',
                    sharey='all',
                    gridspec_kw={
                        'hspace': 0.5
                        })
for i, ax, sch in zip(range(1, ch8NSubchannels + 1), axes, doc.channels[8].subchannels):
    ax.plot(ch8Time, ch8Data[i, :])
    ax.set_title(sch.displayName)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('{0} ({1})'.format(*sch.units))


# We can repeat the process with channel 36, which has heterogeneous data


ch36EventArray = doc.channels[36].getSession()

ch36Data = ch36EventArray.arraySlice()
ch36Time = ch36Data[0, :]/1e6
ch36NSubchannels = len(doc.channels[36].subchannels)


fig = plt.figure()
fig.suptitle(doc.channels[36].displayName)

axes = fig.subplots(ch36NSubchannels, 1,
                    sharex='all',
                    gridspec_kw={
                        'hspace': 0.5
                        })
for i, ax, sch in zip(range(1, ch36NSubchannels + 1), axes, doc.channels[36].subchannels):
    ax.plot(ch36Time, ch36Data[i, :])
    ax.set_title(sch.displayName)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('{0} ({1})'.format(*sch.units))



plt.show()
