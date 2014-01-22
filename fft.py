'''
Created on Dec 18, 2013

@author: dstokes
'''

from collections import Iterable

import numpy as np
# TODO: See about removing the pylab dependency.
from pylab import hstack

import spectrum as spec


def from2diter(data, rows=None, cols=1):
    """ Build a 2D array from an iterator (e.g. what's produced by 
        `EventList.itervalues`). 
        
        @todo: This is not the best implementation; even though 
            'numpy.fromiter()` doesn't support 2D arrays, there may be something
            else in Numpy for doing this.
    """
    if rows is None:
        if hasattr(data, '__len__'):
            rows = len(data)
    
    # Build a 2D array. 
    # Numpy's `fromiter()` is 1D, but there's probably a better way to do this.
    dataIter = iter(data)
    row1 = dataIter.next()
    if isinstance(row1, Iterable):
        cols = len(row1)
        
    points = np.zeros(shape=(rows,cols), dtype=float)
    points[0,:] = row1
    
    for i, row in enumerate(dataIter,1):
        points[i,:] = row

    return points


def nextPow2(x):
    """ Round up to the nearest power-of-two.
    """
    if x & (x-1) == 0:
        # already a power of 2
        return x
    
    x -= 1
    for i in xrange(5):
        x |= x >> (x**i)
    return x+1


def generateFFTData(data, rows=None, cols=1, fs=5000, sliceSize=2**16):
    """ Compute 1D FFT from one or more channels of data, using Welch's
        method.
    
        @note: This is the implementation from the old viewer and does not
            scale well to massive datasets. This *will* run of of memory; the
            exact number of samples/RAM has yet to be determined.
            
        @param data: An iterable collection of event values (no times!). The
            data can have one or more channels (e.g. accelerometer X or XYZ
            together). This can be an iterator, generator, or array.
        @keyword rows: The number of rows (samples) in the set, if known.
        @keyword cols: The number of columns (channels) in the set; a default
            if the dataset does not contain multiple columns.
        @keyword fs: Frequency of sample, i.e. the sample rate (Hz)
        @keyword sliceSize: The size of the 'window' used to compute the FFTs
            via Welch's method. Should be a power of 2!
        @return: A multidimensional array, with the first column the frequency.
    """
    points = from2diter(data, rows, cols)
    rows, cols = points.shape
    shape = points.shape
    points.resize((max(nextPow2(shape[0]),sliceSize), shape[1]))
    
    # XXX: Copied verbatim from old viewer. Revisit whether or not all this
    #     shaping and stacking is really necessary.
    fftData = np.arange(0, sliceSize/2.0 + 1) * (fs/float(sliceSize))
    fftData = fftData.reshape(-1,1)
    
    scalar = (sliceSize/2.0)
    
    for i in xrange(cols):
        tmp_fft, freqs = spec.welch(points[:,i], NFFT=sliceSize, Fs=fs, 
                                    detrend=spec.detrend_mean, 
                                    noverlap=sliceSize/2, sides='onesided', 
                                    scale_by_freq=False, pad_to=sliceSize, 
                                    window=spec.window_hanning)
        
        tmp_fft = tmp_fft / scalar
        tmp_fft = tmp_fft.reshape(-1,1)
        fftData = hstack((fftData, tmp_fft))
        
        # Remove huge DC component from displayed data; so data of interest 
        # can be seen after auto axis fitting
        fftData[0,i] = 0
        fftData[1,i] = 0
        fftData[2,i] = 0
        
    return fftData

    