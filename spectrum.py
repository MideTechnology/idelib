"""
Helper functions for implementing Welch's method FFT-alikes (PSD/CSD and 
spectrogram). These functions are already present in (and directly copied 
from) matplotlib; they have been pulled into a separate callable file to 
avoid auto-spawning a Figure when called. Also, several bugs affecting 
amplitude scaling have been fixed here,  so these should be used in place of
the matplotlib functions wherever a proper amplitude scaling is required.
 
ALSO NOTE: I modified _spectral_helper to return amplitude spectra 
(sqrt(x*conj(x)) rather than power spectra (x*conj(x)).

This file is part of Slam Stick Viewer. It has been further modified to
remove dependencies on matplotlib.
"""

# License agreement for matplotlib 1.0.1
# 
# 1. This LICENSE AGREEMENT is between John D. Hunter ("JDH"), and the 
#    Individual or Organization ("Licensee") accessing and otherwise using 
#    matplotlib software in source or binary form and its associated 
#    documentation.
# 
# 2. Subject to the terms and conditions of this License Agreement, JDH hereby 
#    grants Licensee a non-exclusive, royalty-free, world-wide license to 
#    reproduce, analyze, test, perform and/or display publicly, prepare 
#    derivative works, distribute, and otherwise use matplotlib 1.0.1 alone or 
#    in any derivative version, provided, however, that JDH's License Agreement
#    and JDH's notice of copyright, i.e., "Copyright (c) 2002-2009 John D. 
#    Hunter; All Rights Reserved" are retained in matplotlib 1.0.1 alone or in
#    any derivative version prepared by Licensee.
# 
# 3. In the event Licensee prepares a derivative work that is based on or 
#    incorporates matplotlib 1.0.1 or any part thereof, and wants to make the 
#    derivative work available to others as provided herein, then Licensee 
#    hereby agrees to include in any such work a brief summary of the changes 
#    made to matplotlib 1.0.1.
# 
# 4. JDH is making matplotlib 1.0.1 available to Licensee on an "AS IS" basis. 
#    JDH MAKES NO REPRESENTATIONS OR WARRANTIES, EXPRESS OR IMPLIED. BY WAY OF 
#    EXAMPLE, BUT NOT LIMITATION, JDH MAKES NO AND DISCLAIMS ANY REPRESENTATION
#    OR WARRANTY OF MERCHANTABILITY OR FITNESS FOR ANY PARTICULAR PURPOSE OR
#    THAT THE USE OF MATPLOTLIB 1.0.1 WILL NOT INFRINGE ANY THIRD PARTY RIGHTS.
# 
# 5. JDH SHALL NOT BE LIABLE TO LICENSEE OR ANY OTHER USERS OF MATPLOTLIB 1.0.1
#    FOR ANY INCIDENTAL, SPECIAL, OR CONSEQUENTIAL DAMAGES OR LOSS AS A RESULT 
#    OF MODIFYING, DISTRIBUTING, OR OTHERWISE USING MATPLOTLIB 1.0.1, OR ANY 
#    DERIVATIVE THEREOF, EVEN IF ADVISED OF THE POSSIBILITY THEREOF.
# 
# 6. This License Agreement will automatically terminate upon a material breach
#    of its terms and conditions.
# 
# 7. Nothing in this License Agreement shall be deemed to create any 
#    relationship of agency, partnership, or joint venture between JDH and 
#    Licensee. This License Agreement does not grant permission to use JDH 
#    trademarks or trade name in a trademark sense to endorse or promote 
#    products or services of Licensee, or any third party.
# 
# 8. By copying, installing or otherwise using matplotlib 1.0.1, Licensee 
#    agrees to be bound by the terms and conditions of this License Agreement.


from __future__ import division
from collections import Iterable

import numpy as np
ma = np.ma

from common import nextPow2

def window_hanning(x):
    "return x times the hanning window of len(x)"
    return np.hanning(len(x))*x


def window_none(x):
    "No window function; simply return x"
    return x


def detrend(x, key=None):
    if key is None or key=='constant':
        return detrend_mean(x)
    elif key=='linear':
        return detrend_linear(x)


def demean(x, axis=0):
    "Return x minus its mean along the specified axis"
    x = np.asarray(x)
    if axis == 0 or axis is None or x.ndim <= 1:
        return x - x.mean(axis)
    ind = [slice(None)] * x.ndim
    ind[axis] = np.newaxis
    return x - x.mean(axis)[ind]


def detrend_mean(x):
    "Return x minus the mean(x)"
    return x - x.mean()


def detrend_none(x):
    "Return x: no detrending"
    return x


def detrend_linear(y):
    "Return y minus best fit line; 'linear' detrending "
    # This is faster than an algorithm based on linalg.lstsq.
    x = np.arange(len(y), dtype=np.float_)
    C = np.cov(x, y, bias=1)
    b = C[0,1]/C[0,0]
    a = y.mean() - b*x.mean()
    return y - (b*x + a)
    

#This is a helper function that implements the commonality between the
#psd, csd, and spectrogram.  It is *NOT* meant to be used outside of mlab
def _spectral_helper(x, y, NFFT=256, Fs=2, detrend=detrend_none,
        window=window_hanning, noverlap=0, pad_to=None, sides='default',
        scale_by_freq=None, abortEvent=None):
    #The checks for if y is x are so that we can use the same function to
    #implement the core of psd(), csd(), and spectrogram() without doing
    #extra calculations.  We return the unaveraged Pxy, freqs, and t.
    same_data = y is x

    #Make sure we're dealing with a numpy array. If y and x were the same
    #object to start with, keep them that way

    x = np.asarray(x)
    if not same_data:
        y = np.asarray(y)

    # zero pad x and y up to NFFT if they are shorter than NFFT
    if len(x)<NFFT:
        n = len(x)
        x = np.resize(x, (NFFT,))
        x[n:] = 0

    if not same_data and len(y)<NFFT:
        n = len(y)
        y = np.resize(y, (NFFT,))
        y[n:] = 0

    if pad_to is None:
        pad_to = NFFT

    if scale_by_freq is None:
        scale_by_freq = True

    # For real x, ignore the negative frequencies unless told otherwise
    if (sides == 'default' and np.iscomplexobj(x)) or sides == 'twosided':
        numFreqs = pad_to
        scaling_factor = 1.
    elif sides in ('default', 'onesided'):
        numFreqs = pad_to//2 + 1
        scaling_factor = 2.
    else:
        raise ValueError("sides must be one of: 'default', 'onesided', or "
            "'twosided'")

    # MATLAB divides by the sampling frequency so that density function
    # has units of dB/Hz and can be integrated by the plotted frequency
    # values. Perform the same scaling here.
    if scale_by_freq:
        scaling_factor /= Fs

    if isinstance(window, Iterable):
        assert(len(window) == NFFT)
        windowVals = window
    else:
        windowVals = window(np.ones((NFFT,), x.dtype))

    step = NFFT - noverlap
    ind = np.arange(0, len(x) - NFFT + 1, step)
    n = len(ind)
    Pxy = np.zeros((numFreqs,n), np.complex_)

    # do the ffts of the slices
    for i in range(n):
        if abortEvent is not None and abortEvent():
            return None, None, None
        
        thisX = x[ind[i]:ind[i]+NFFT]
        thisX = windowVals * detrend(thisX)
        fx = np.fft.fft(thisX, n=pad_to)

        if same_data:
            fy = fx
        else:
            thisY = y[ind[i]:ind[i]+NFFT]
            thisY = windowVals * detrend(thisY)
            fy = np.fft.fft(thisY, n=pad_to)
        #Pxy[:,i] = np.conjugate(fx[:numFreqs]) * fy[:numFreqs]
        Pxy[:,i] = np.sqrt(np.conjugate(fx[:numFreqs]) * fy[:numFreqs])

    # Scale the spectrum by the norm of the window to compensate for
    # windowing loss; see Bendat & Piersol Sec 11.5.2.
    # matplotlib BUG: want to scale by the average of the window coefficients, 
    # not the sum!
    #Pxy *= 1 / (np.abs(windowVals)**2).sum()
    Pxy *= 1 / (np.abs(windowVals)).mean()

    # Also include scaling factors for one-sided densities and dividing by the
    # sampling frequency, if desired. Scale everything, except the DC component
    # and the NFFT/2 component:
    #Pxy[1:-1] *= scaling_factor
#     print ("Fs: %d   " % Fs),
#     print ("Scaling_factor: %f  " % scaling_factor),
#     print "Inv. scaling: %f\r\n" % 1./scaling_factor

    #But do scale those components by Fs, if required
    if scale_by_freq:
        Pxy[[0,-1]] /= Fs

    t = 1./Fs * (ind + NFFT / 2.)
    freqs = float(Fs) / pad_to * np.arange(numFreqs)

    if (np.iscomplexobj(x) and sides == 'default') or sides == 'twosided':
        # center the frequency range at zero
        freqs = np.concatenate((freqs[numFreqs//2:] - Fs, freqs[:numFreqs//2]))
        
        Pxy = np.concatenate((Pxy[numFreqs//2:, :], Pxy[:numFreqs//2, :]), 0)

    return Pxy, freqs, t


# renamed from 'psd' because it is not the PSD anymore...
def welch(x, NFFT=256, Fs=2, detrend=detrend_none, window=window_hanning,
        noverlap=0, pad_to=None, sides='default', scale_by_freq=None,
        abortEvent=None):
    """
    The power spectral density by Welch's average periodogram method.
    The vector *x* is divided into *NFFT* length blocks.  Each block
    is detrended by the function *detrend* and windowed by the function
    *window*.  *noverlap* gives the length of the overlap between blocks.
    The absolute(fft(block))**2 of each segment are averaged to compute
    *Pxx*, with a scaling to correct for power loss due to windowing.

    If len(*x*) < *NFFT*, it will be zero padded to *NFFT*.

    *x*
        Array or sequence containing the data

    %(PSD)s

    Returns the tuple (*Pxx*, *freqs*).

    Refs:

        Bendat & Piersol -- Random Data: Analysis and Measurement
        Procedures, John Wiley & Sons (1986)

    """
    Pxx,freqs = csd(x, x, NFFT, Fs, detrend, window, noverlap, pad_to, sides,
        scale_by_freq, abortEvent=abortEvent)
    return Pxx.real,freqs


def csd(x, y, NFFT=256, Fs=2, detrend=detrend_none, window=window_hanning,
        noverlap=0, pad_to=None, sides='default', scale_by_freq=None,
        abortEvent=None):
    """
    The cross power spectral density by Welch's average periodogram
    method.  The vectors *x* and *y* are divided into *NFFT* length
    blocks.  Each block is detrended by the function *detrend* and
    windowed by the function *window*.  *noverlap* gives the length
    of the overlap between blocks.  The product of the direct FFTs
    of *x* and *y* are averaged over each segment to compute *Pxy*,
    with a scaling to correct for power loss due to windowing.

    If len(*x*) < *NFFT* or len(*y*) < *NFFT*, they will be zero
    padded to *NFFT*.

    *x*, *y*
        Array or sequence containing the data

    %(PSD)s

    Returns the tuple (*Pxy*, *freqs*).

    Refs:
        Bendat & Piersol -- Random Data: Analysis and Measurement
        Procedures, John Wiley & Sons (1986)
    """
    Pxy, freqs, _ = _spectral_helper(x, y, NFFT, Fs, detrend, window,
        noverlap, pad_to, sides, scale_by_freq)

    if len(Pxy.shape) == 2 and Pxy.shape[1]>1:
        Pxy = Pxy.mean(axis=1)
    return Pxy, freqs


#===============================================================================
# 
#===============================================================================

# def simplerFFT(data, start=0, end=None, NFFT=2**12, Fs=1000, window=np.hanning):
#     """
#     """
#     if window is None:
#         windowMult = np.ones(NFFT)
#     else:
#         windowMult = window(NFFT)
# 
#     end = len(data) if end is None else end
#     
#     total = 0
# #     total = abs(np.fft.fft(data[start:start+NFFT/2] * windowMult[NFFT/2:], NFFT)[:NFFT/2+1]/NFFT)
#     
#     print 'start/end/sliceSize: ', start, end, NFFT/2
#     for i in xrange(start, end, int(NFFT/2)):
#         chunk = data[i:i+NFFT]
#         chunkLen = len(chunk)
#         if chunkLen < NFFT:
#             chunk = np.concatenate((chunk, np.zeros(NFFT-chunkLen)))
#         total += 2*abs(np.fft.fft(chunk * windowMult, NFFT)[:NFFT/2+1]/chunkLen)
#         
# #     return total / (float(end-start) / (NFFT + 1.0))
#     return total / (float(end-start) / (NFFT/2))
# 
# 
# 
# def fft(data, NFFT=2**12, Fs=1000):
#     """ TEMPORARY.
#     """
#     sliceSize = min(len(data), NFFT)
#     return 2*abs(np.fft.fft(data, NFFT)/sliceSize)[:NFFT/2+1]