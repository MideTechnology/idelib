'''
Sub-module for generating and manipulating FFT data from a set of sensor
data. 

This module requires Numpy.

@author: dstokes
'''

try:
    import numpy as np
except ImportError:
    raise ImportError("mide_ebml.fft requires Numpy")

#try:
#    from pyfft.builders import rfft
#except ImportError:
#    raise ImportError("mide_ebml.fft requires pyfftw")


#===============================================================================
# 
#===============================================================================

"""



__len__
__getitem__
__iter__
iterResampledRange()
hasDisplayRange()
exportCsv()
getRangeIndices() - used by viewer exportCSV()
displayRange
name
units
"""
def rfft(events, length=None):
    if hasattr(events, '__len__') and length is None:
        length = len(events)
    # http://mail.scipy.org/pipermail/numpy-discussion/2007-August/028898.html
    i = np.fromiter((e[-1] for e in events), float, count=length)
#    fft_obj = rfft(i)
#    return fft_obj()
    return np.fft.rfft(i)

#===============================================================================
# 
#===============================================================================

class detrend:
    """ Namespace class containing functions for 'de-trending' data.
    """
    
    @staticmethod
    def mean(x):
        """
        """
        return x - x.mean()
    
    @staticmethod
    def linear(y):
        "Return y minus best fit line; 'linear' detrending "
        # This is faster than an algorithm based on linalg.lstsq.
        x = np.arange(len(y), dtype=np.float_)
        C = np.cov(x, y, bias=1)
        b = C[0,1]/C[0,0]
        a = y.mean() - b*x.mean()
        return y - (b*x + a)

    @staticmethod
    def none(x):
        return x


class windows:
    """ Namespace class containing tapering functions for windowed FFT. 
    """
    
    @staticmethod
    def boxcar(x):
        """ Create a rectangular ('boxcar') set of window multiplier values
            of a given length.
        """
        return np.ones(x)
    
    @staticmethod
    def hanning(x):
        """ Create a parabolic set of window multiplier values of a given
            length.
        """
        return np.hanning(x)
    

#===============================================================================
# FFTList
#===============================================================================

class FFTList(object):
    """ A set of FFT data rendered from a sensor channel's output. It
        presents as a list-like object similar to an `EventList`. Code
        that utilizes `EventList` data (plotting, etc.) should work for
        `FFTList` objects without much refactoring.
        
        @see: `mide_ebml.dataset.EventList`
    """
    
    defaultWindowSize = 65536.0 
    computed = False
    
    def __init__(self, source, subset=None, windowSize=defaultWindowSize,
                 overlap=0.5, detrend=detrend.mean, windowFunction=windows.hanning,
                 computeNow=True):
        """
        """
        self.fftData = None
        self.computed = False
        self.source = source
        self.subset = (0, len(source)) if subset is None else subset
        self.windowSize = windowSize
        self.overlap = overlap
        self.detrend = detrend
        self.windowFunction = windowFunction

        self.hasDisplayRange = False
        self.units = ('','')
        self.xUnits = ('Hz', 'Hz')
        
        try:
            self.Fs = source.getSampleRate()
        except AttributeError:
            self.Fs = 1
        
        if computeNow:
            self.compute()
            
        pass
    
    
    def __len__(self):
        return len(self.fftData)


    def rfft(self, events):
        """ Simple real FFT. Copied here for reference. Remove me. """
        i = np.fromiter((e[-1] for e in events), float, count=len(events))
#        fft_obj = rfft(i)
#        return fft_obj()
        return np.fft.rfft(i)
    
    
    def compute(self):
        """
        """
        # The number of FFTs to collect before computing their mean
        numSubsamples = 256
        windowSize = int(self.windowSize)
        
        numFreqs = self.windowSize // 2 + 1
        
        result = np.zeros((numFreqs, numSubsamples), np.complex_)
        
        window = self.windowFunction(windowSize)
        
        realIdx = lambda x: x if x >= 0 else len(self.source) + x
        start, stop  = realIdx(self.subset[0]), realIdx(self.subset[1])
        step = windowSize/2
        
        col = 0
        print "len(self.source) =",len(self.source)
        print "windowSize =",windowSize
        for i in xrange(start, stop, step):
            print "i =", i 
            vals = np.fromiter(self.source.itervalues(i, i+windowSize),
                                  float, min(windowSize, len(self.source)-i))
            if len(vals) < windowSize:
                vals.resize(windowSize)
            thisWindowVals = self.detrend(vals) * window
#            fft_obj = rfft(thisWindowVals, n=windowSize)
#            result[:, col] = fft_obj()[:numFreqs]
            result[:, col] = np.fft.fft(thisWindowVals, n=windowSize)[:numFreqs]
            col += 1
            if col == numSubsamples:
                means = result.mean(axis=1)
                result = np.zeros((numFreqs, numSubsamples), np.complex_)
                result[:,0] = means
                col = 1
        
        self.fftData = result[:,0]
        self.fftData = np.sqrt(self.fftData * np.conjugate(self.fftData))
        self.fftData *= 1 / (np.abs(window)).mean()
        self.fftData = self.fftData.real / (self.windowSize / 2.0)
        self.computed = True
        return self.fftData
        
        
        
    #===========================================================================
    # 
    #===========================================================================
     
    def __getitem__(self, idx):
        if not self.computed:
            raise RuntimeError("FFT data accessed before computation")
        if self.source.hasSubchannels:
            pass
        else:
            pass
        pass
    
    
    def __iter__(self):
        if not self.computed:
            raise RuntimeError("FFT data accessed before computation")
        if self.source.hasSubchannels:
            pass
        else:
            pass
        pass
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    def iterResampledRange(self, startTime, stopTime, maxPoints, padding=0,
                           jitter=0):
        """
        """
        if not self.computed:
            raise RuntimeError("FFT data accessed before computation")
        
        pass
    
    
    def exportCsv(self, stream, start=0, stop=-1, step=1, subchannels=True,
                  callback=None, callbackInterval=0.01, timeScalar=1,
                  raiseExceptions=False):
        """
        """
        if not self.computed:
            raise RuntimeError("FFT data accessed before computation")

        pass



#===============================================================================
# TESTING 
#===============================================================================

class FakeEventList(list):
    hasSubchannels = False
    def getSampleRate(self):
        return 1.0 / self[1][0]
    def itervalues(self, start=0, stop=-1, step=1):
        return (x[1] for x in self)

def importTestData(dataFile="test_files/vibration-time.csv", 
                   fftFile="test_files/vibration-fft.csv"):
    import csv
    with open(dataFile, 'rb') as f:
        rawData = [map(float, r) for r in csv.reader(f)]
    with open(fftFile, 'rb') as f:
        fftData = [map(float, r) for r in csv.reader(f)]
    return rawData, fftData

rawData, fftData = importTestData()
rawEvents = FakeEventList(rawData)