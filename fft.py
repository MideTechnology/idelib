'''
Created on Dec 18, 2013

@todo: Re-implement spectrum to reduce dependencies and make spec.welch()
    work using just the window instead of the full-size array.

@author: dstokes
'''

from collections import Iterable
import csv
from itertools import izip

import numpy as np
from numpy.core import hstack

import wx.lib.plot as P
import wx; wx = wx 

import spectrum as spec

from base import MenuMixin
from common import StatusBar, nextPow2

#===============================================================================
# 
#===============================================================================

class FFTView(wx.Frame, MenuMixin):
    """
    """
    NAME = "FFT"
    FULLNAME = "FFT View"
    
    ID_EXPORT_CSV = wx.NewId()
    ID_EXPORT_IMG = wx.NewId()
    
    IMAGE_FORMATS = "Windows Bitmap (*.bmp)|*.bmp|" \
                     "JPEG (*.jpg)|*.jpg|" \
                     "Portable Network Graphics (*.png)|*.png" 

    
    def __init__(self, *args, **kwargs):
        """ FFT view main panel. Takes standard wx.Window arguments plus:
        
            @keyword root: The parent viewer window
            @keyword sources: A list of subchannels
            @keyword start: The start of the time interval to render
            @keyword end: The end of the time interval to render
        """
        kwargs.setdefault("title", self.FULLNAME)
        self.root = kwargs.pop("root", None)
        self.source = kwargs.pop("source", None)
        self.subchannels = kwargs.pop("subchannels", None)
        self.range = (kwargs.pop("start",0), kwargs.pop("end",-1))
        self.data = kwargs.pop("data",None)
        self.sliceSize = kwargs.pop("sliceSize", 2**16)
        
        super(FFTView, self).__init__(*args, **kwargs)
        
        self.canvas = P.PlotCanvas(self)
        self.canvas.SetEnableAntiAliasing(True)
        self.canvas.SetFont(wx.Font(10,wx.SWISS,wx.NORMAL,wx.NORMAL))
        self.canvas.SetFontSizeAxis(10)
        self.canvas.SetFontSizeLegend(7)
        self.canvas.setLogScale((False,False))
        self.canvas.SetXSpec('min')
        self.canvas.SetYSpec('auto')
        
        self.initMenus()
        
        self.statusBar = StatusBar(self)
        self.statusBar.stopProgress()
        self.SetStatusBar(self.statusBar)
        
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
        self.Show(True)
        self.Update()
        
        if self.source is None and self.subchannels is not None:
            self.source = self.subchannels[0].parent.getSession(
                                                    self.root.session.sessionId)
        
        self.draw()


    def draw(self):
        self.lines = None
        if self.subchannels is not None:
            subchannelIds = [c.id for c in self.subchannels]
            start, stop = self.source.getRangeIndices(*self.range)
            data = self.source.itervalues(start, stop, subchannels=subchannelIds)
            # BUG: Calculation of actual sample rate is wrong. Investigate.
#             fs = (channel[stop][-2]-channel[start][-2]) / ((stop-start) + 0.0)
            fs = self.source.getSampleRate()
            self.data = self.generateData(data, stop-start, 
                                             len(self.subchannels), fs, 
                                             self.sliceSize)
            
        if self.data is not None:
            self.makeLineList()

        if self.lines is not None:
            self.canvas.Draw(self.lines)

        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        
    
    def initMenus(self):
        """
        """
        helpText = "%s Help" % self.FULLNAME
        
        self.menubar = wx.MenuBar()
        fileMenu = wx.Menu()
        self.addMenuItem(fileMenu, self.ID_EXPORT_CSV, "&Export CSV...", "", 
                         self.OnExportCsv)
        self.addMenuItem(fileMenu, self.ID_EXPORT_IMG, "Export &Image...", "", 
                         self.OnExportImage)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_PRINT, "&Print...", "", 
                         None, False)
        self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, "Print Setup...", "", 
                         None, False)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_CLOSE, "Close &Window", "", 
                         self.OnClose)
        self.menubar.Append(fileMenu, "File")
        
        editMenu = wx.Menu()
        self.addMenuItem(editMenu, wx.ID_CUT, "Cut", "", None, False)
        self.addMenuItem(editMenu, wx.ID_COPY, "&Copy", "", None, False)
        self.addMenuItem(editMenu, wx.ID_PASTE, "Paste", "", None, False)
        self.menubar.Append(editMenu, "Edit")

        viewMenu = wx.Menu()
        viewMenu.Append(-1, "None of these work yet.", "")
        self.menubar.Append(viewMenu, "View")
        
        helpMenu = wx.Menu()
        self.addMenuItem(helpMenu, wx.ID_HELP_INDEX, helpText, '', self.OnHelp)
        self.menubar.Append(helpMenu, "Help")
        
        self.SetMenuBar(self.menubar)
    
    
    def OnExportCsv(self, evt):
        filename = None
        dlg = wx.FileDialog(self, 
            message="Export CSV...", 
#             defaultDir=defaultDir,  defaultFile=defaultFile, 
            wildcard='|'.join(self.root.app.getPref('exportTypes')), 
            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
        
        if filename is None:
            return False
        
        try:
            out = open(filename, "wb")
            writer = csv.writer(out)
            writer.writerows(self.data)
            out.close()
            return True
        except Exception as err:
            what = "exporting %s as CSV" % self.NAME
            self.root.handleException(err, what=what)
            return False
        
    
    def OnExportImage(self, event):
        filename = None
        dlg = wx.FileDialog(self, 
            message="Export Image...", 
            wildcard=self.IMAGE_FORMATS, 
            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
        
        if filename is None:
            return False
        
        try:
            return self.canvas.SaveFile(filename)
        except Exception as err:
            what = "exporting %s as an image" % self.NAME
            self.root.handleException(err, what=what)
            return False
    
    
    def OnHelp(self, evt):
        self.root.ask("FFT Help not implemented!", "TODO:", style=wx.OK, parent=self)


    def OnClose(self, evt):
        self.Close()
    
    #===========================================================================
    # 
    #===========================================================================
    
    def makeLineList(self):
        """ Turn each column of data into its own line plot.
        """
        lines = []
        cols = self.data.shape[-1]-1
        
        freqs = self.data[:,0].reshape(-1,1)

        for i in range(cols):
            points = (hstack((freqs, self.data[:,i+1].reshape(-1,1))))
            name = self.subchannels[i-1].name

            lines.append(P.PolyLine(points, legend=name, colour=self.root.getPlotColor(self.subchannels[i-1])))#colors[i]))
            
        self.lines = P.PlotGraphics(lines, title=self.GetTitle(), 
                                    xLabel="Frequency", yLabel="Amplitude")
        
    
    @classmethod
    def from2diter(self, data, rows=None, cols=1):
        """ Build a 2D `numpy.ndarray` from an iterator (e.g. what's produced by 
            `EventList.itervalues`). 
            
            @todo: This is not the best implementation; even though 
                'numpy.fromiter()` doesn't support 2D arrays, there may be 
                something else in Numpy for doing this.
        """
        if rows is None:
            if hasattr(data, '__len__'):
                rows = len(data)
        
        # Build a 2D array. Numpy's `fromiter()` is 1D, but there's probably a 
        # better way to do this.
        dataIter = iter(data)
        row1 = dataIter.next()
        if isinstance(row1, Iterable):
            cols = len(row1)
            
        points = np.zeros(shape=(rows,cols), dtype=float)
        points[0,:] = row1
        
        for i, row in enumerate(dataIter,1):
            points[i,:] = row
    
        return points
    
    
    @classmethod
    def generateData(cls, data, rows=None, cols=1, fs=5000, sliceSize=2**16):
        """ Compute 1D FFT from one or more channels of data, using Welch's
            method.
        
            @note: This is the implementation from the old viewer and does not
                scale well to massive datasets. This *will* run of of memory; 
                the exact number of samples/RAM has yet to be determined.
                
            @param data: An iterable collection of event values (no times!). The
                data can have one or more channels (e.g. accelerometer X or XYZ
                together). This can be an iterator, generator, or array.
            @keyword rows: The number of rows (samples) in the set, if known.
            @keyword cols: The number of columns (channels) in the set; a 
                default if the dataset does not contain multiple columns.
            @keyword fs: Frequency of sample, i.e. the sample rate (Hz)
            @keyword sliceSize: The size of the 'window' used to compute the 
                FFTs via Welch's method. Should be a power of 2!
            @return: A multidimensional array, with the first column the 
                frequency.
        """
        
        points = cls.from2diter(data, rows, cols)
        rows, cols = points.shape
        shape = points.shape
        points.resize((max(nextPow2(shape[0]),sliceSize), shape[1]))
        
        # NOTE: Copied verbatim from old viewer. Revisit whether or not all this
        #     shaping and stacking is really necessary.
        fftData = np.arange(0, sliceSize/2.0 + 1) * (fs/float(sliceSize))
        fftData = fftData.reshape(-1,1)
        
        scalar = (sliceSize/2.0)
        
        for i in xrange(cols):
            # Returns (FFT data, frequencies)
            tmp_fft, _ = spec.welch(points[:,i], NFFT=sliceSize, Fs=fs, 
                                    detrend=spec.detrend_mean, 
                                    noverlap=sliceSize/2, sides='onesided', 
                                    scale_by_freq=False, pad_to=sliceSize, 
                                    window=spec.window_hanning)
            tmp_fft = tmp_fft / scalar
            tmp_fft = tmp_fft.reshape(-1,1)
            fftData = hstack((fftData, tmp_fft))
            
            # Remove huge DC component from displayed data; so data of interest 
            # can be seen after auto axis fitting
            thisCol = i+1
            fftData[0,thisCol] = 0
            fftData[1,thisCol] = 0
            fftData[2,thisCol] = 0
        
        return fftData



#===============================================================================
# 
#===============================================================================
import colorsys
import Image

class SpectrogramView(FFTView):
    """
    """
    NAME = "Spectrogram"
    FULLNAME = "Spectrogram View"
    
    @classmethod
    def getColorFromNorm(self, n):
        try:
#             return tuple(map(lambda x: int(x*255), colorsys.hsv_to_rgb(n*.835,1,1)))
            return tuple(map(lambda x: int(x*255), colorsys.hsv_to_rgb(n,1.0,1.0)))
        except ValueError:
            print "problem with color for %s", n
            return (0,0,0)
#         b = int(255*n)
#         return b,b,b
    
    @classmethod
    def makeLineList(self, data):
        """
        """
        minAmp = min([np.amin(np.log10(d[0])) for d in data])
        maxAmp = max([np.amax(np.log10(d[0])) for d in data])
        
        # Create a mapped function to normalize a numpy.ndarray
        norm = np.vectorize(lambda x: (x-minAmp)/(maxAmp-minAmp))
        
        images = []
        # XXX: THIS IS AN UGLY HACK AND IT WANTS TO DIE
        fooimg = wx.Image('ssx.ico').Copy()
        b = fooimg.GetDataBuffer()
        for i in xrange(len(b)):
            b[i]=chr(0)
        fooimg.Rescale(data[0][0].shape[1],data[0][0].shape[0])
        for amps, _freqs, _bins in data:
            img = fooimg.Copy()#wx.EmptyBitmap(*data[0][0].shape)
            buf = img.GetDataBuffer()
            print img.HasAlpha()
#             abuf = img.GetAlphaBuffer()
            idx = 0
            for p in norm(np.log10(amps)).reshape((1,-1)):
                color = self.getColorFromNorm(p[0])
                buf[idx]=chr(color[0])
                buf[idx+1]=chr(color[1])
                buf[idx+2]=chr(color[2])
#                 abuf[idx/3]=chr(255)
                if idx == 0:
                    print color, map(repr, [buf[0], buf[1], buf[2]])
                idx += 3
            images.append(img)
            
        return images
                
   
    @classmethod
    def dumpImg(self, data):
        """
        """
        minAmp = min([np.amin(np.log10(d[0])) for d in data])
        maxAmp = max([np.amax(np.log10(d[0])) for d in data])
        
        print "minAmp:",minAmp," maxAmp:",maxAmp
        for d in data:
            print "mean:", d[0].mean()
        # Create a mapped function to normalize a numpy.ndarray
        norm = np.vectorize(lambda x: 255*((x-minAmp)/(maxAmp-minAmp)))
        imgsize = data[0][0].shape[1], data[0][0].shape[0]
        images = []
        for amps, _freqs, _bins in data:
            img = Image.new("L", imgsize, 0)
            img.putdata(norm(np.log10(amps)).reshape((1,-1))[0,:])
            images.append(img.transpose(Image.FLIP_TOP_BOTTOM))
            
        return images
   

    @classmethod
    def dumpImg2(self, data):
        """
        """
        mins = []
        maxes = []
        means = []
        for d in data:
            dlog = 10.0*np.log10(np.abs(d[0]))
#             dlog = dlog - np.mean(dlog)
            mins.append(np.amin(dlog))
            maxes.append(np.amax(dlog))
            means.append(np.mean(dlog))
        minAmp = min(mins)
        maxAmp = max(maxes)
        meanAmp = np.mean(means)
        
        print "minAmp:",minAmp," maxAmp:",maxAmp," meanAmp:",meanAmp
#         minAmp = meanAmp
        
        for d in data:
            print "mean:", d[0].mean()
        # Create a mapped function to normalize a numpy.ndarray
#         norm = np.vectorize(lambda x: max(0,255*((x-minAmp)/(maxAmp-minAmp))))
        norm = np.vectorize(lambda x: 255*((x-minAmp)/(maxAmp-minAmp)))
        imgsize = data[0][0].shape[1], data[0][0].shape[0]
        images = []
        for amps, _freqs, _bins in data:
            img = Image.new("L", imgsize, 0)
            img.putdata(norm(10.0*np.log10(np.abs(amps))).reshape((1,-1))[0,:])
            images.append(img.transpose(Image.FLIP_TOP_BOTTOM))
            
        return images
   

    @classmethod
    def dumpColorImg(self, data):
        """
        """
#         minAmp = min([np.amin(np.log10(d[0])) for d in data])
#         maxAmp = max([np.amax(np.log10(d[0])) for d in data])
        
        mins = []
        maxes = []
        means = []
        for d in data:
            dlog = np.log10(d[0])
            dlog = dlog - np.mean(dlog)
            mins.append(np.amin(dlog))
            maxes.append(np.amax(dlog))
            means.append(np.mean(dlog))
        minAmp = min(mins)
        maxAmp = max(maxes)
        meanAmp = np.mean(means)
        
        print "minAmp:",minAmp," maxAmp:",maxAmp, " meanAmp:", meanAmp

        # Create a mapped function to normalize a numpy.ndarray
        norm = np.vectorize(lambda x: ((x-minAmp)/(maxAmp-minAmp)))
        imgsize = data[0][0].shape[1], data[0][0].shape[0]
        images = []
        for amps, _freqs, _bins in data:
            buf = []
            img = Image.new("RGB", imgsize, 0)
            for val in norm(np.log10(amps).reshape((1,-1)))[0,:]:
                buf.append(self.getColorFromNorm(val))
            img.putdata(buf)
            images.append(img.transpose(Image.FLIP_TOP_BOTTOM))
            
        return images

    
    def draw(self):
        """
        """
        # self.canvas is the plot canvas
        self.lines = None
        if self.subchannels is not None:
            subchannelIds = [c.id for c in self.subchannels]
            start, stop = self.source.getRangeIndices(*self.range)
            data = self.source.itervalues(start, stop, subchannels=subchannelIds)
            # BUG: Calculation of actual sample rate is wrong. Investigate.
#             fs = (channel[stop][-2]-channel[start][-2]) / ((stop-start) + 0.0)
            fs = self.source.getSampleRate()
            self.data = self.generateData(data, rows=stop-start, 
                                          cols=len(self.subchannels), fs=fs, 
                                          sliceSize=self.sliceSize,
                                          slicesPerSec=4.0)
        
        # XXX: THESE LINES NEED TO BE REWRITTEN
#         if self.data is not None:
#             self.makeLineList()
# 
#         if self.lines is not None:
#             self.canvas.Draw(self.lines)

        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    
    def OnHelp(self, evt):
        self.root.ask("Spectrogram Help not implemented!", "TODO:", style=wx.OK, parent=self)


    @classmethod
    def generateData(cls, data, rows=None, cols=1, fs=5000, sliceSize=2**16, 
                     slicesPerSec=4.0, recordingTime=None):
        """ Compute 2D FFT from one or more channels of data.
        
            @note: This is the implementation from the old viewer and does not
                scale well to massive datasets. This *will* run of of memory; 
                the exact number of samples/RAM has yet to be determined.
                
            @param data: An iterable collection of event values (no times!). The
                data can have one or more channels (e.g. accelerometer X or XYZ
                together). This can be an iterator, generator, or array.
            @keyword rows: The number of rows (samples) in the set, if known.
            @keyword cols: The number of columns (channels) in the set; a 
                default if the dataset does not contain multiple columns.
            @keyword fs: Frequency of sample, i.e. the sample rate (Hz)
            @keyword sliceSize: The size of the 'window' used to compute the 
                FFTs via Welch's method. Should be a power of 2!
            @return: A multidimensional array, with the first column the 
                frequency.
        """
#               self.myplot.specgram(theData[:,i], NFFT=self.specgram_nfft, Fs=fs, Fc=0, detrend=mlab.detrend_none,
#                   window=mlab.window_hanning, noverlap=self.specgram_nfft/2,
#                   cmap=cm.spectral, xextent=None, pad_to=None, sides='onesided',
#                   scale_by_freq=None, figure=self.figure)
    
        points = cls.from2diter(data, rows, cols)
        rows, cols = points.shape
#         points.resize((max(nextPow2(rows),sliceSize), cols))
#         recordingTime = (points[-1,0] - points[0,0]) * timeScalar
        
        specgram_nfft = int(rows/(recordingTime*slicesPerSec))
        
        print "recordingTime:",recordingTime
        print "specgram_nfft:",specgram_nfft
        specData = []
                
        for i in xrange(cols):
            pts = points[:,i]
            # This is basically what matplotlib.mlab.specgram does
            Pxx, freqs, bins = spec._spectral_helper(pts, pts, 
                NFFT=specgram_nfft, Fs=fs, detrend=spec.detrend_none, 
                window=spec.window_hanning, noverlap=specgram_nfft/2, 
                pad_to=None, sides='onesided', scale_by_freq=None)
            Pxx = Pxx.real
    
            Z = 10. * np.log10(Pxx)
            Z = np.flipud(Z)

            xmin, xmax = 0, np.amax(bins)
        
            specData.append((Pxx, freqs, bins))
            
        return specData
        

