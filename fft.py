'''
Created on Dec 18, 2013

@author: dstokes
'''

from collections import Iterator, Iterable

import numpy as np

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
        return x
    # TODO: Replace this!
    return 2**(len(bin(x))-2)


def generateFFTData(data, rows=None, cols=1, fs=5000, sliceSize=2**16):
    """
    """
    points = from2diter(data, rows, cols)
    shape = points.shape
    points.reshape((max(nextPow2(shape[0]),sliceSize), shape[1]))
    
    for i in xrange(cols):
        tmp_fft, freqs = spec.welch(points[:,i], NFFT=sliceSize, Fs=fs, 
                                    detrend=spec.detrend_mean, 
                                    noverlap=sliceSize/2, sides='onesided', 
                                    scale_by_freq=False, pad_to=sliceSize, 
                                    window=spec.window_hanning)

    # XXX: STOPPING FOR THE NIGHT. 
    