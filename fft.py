'''
Created on Dec 18, 2013

@todo: Re-implement spectrum to reduce dependencies and make spec.welch()
    work using just the window instead of the full-size array.

@author: dstokes
'''

from collections import Iterable
import csv

import numpy as np
from numpy.core import hstack

import wx.lib.plot as P
import wx; wx = wx 

import spectrum as spec

from common import StatusBar

#===============================================================================
# 
#===============================================================================

class FFTView(wx.Frame):
    """
    """
    
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
        kwargs.setdefault("title", "FFT")
        self.root = kwargs.pop("root", None)
        self.sources = kwargs.pop("sources", None)
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
        
        
        self.lines = None
        
        if self.sources is not None:
            channel = self.sources[0].parent.getSession(self.root.session.sessionId)
            subchannelIds = [c.id for c in self.sources]
            start, stop = channel.getRangeIndices(*self.range)
            data = channel.itervalues(start, stop, subchannels=subchannelIds)
            # BUG: Calculation of actual sample rate is wrong. Investigate.
#             fs = (channel[stop][-2]-channel[start][-2]) / ((stop-start) + 0.0)
            fs = channel.getSampleRate()
            self.data = self.generateFFTData(data, stop-start, 
                                             len(self.sources), fs, 
                                             self.sliceSize)
            
        if self.data is not None:
            self.makeLineList()

        if self.lines is not None:
            self.canvas.Draw(self.lines)

        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        
    
    def initMenus(self):
        """
        """
        self.menubar = wx.MenuBar()
        fileMenu = wx.Menu()
        fileMenu.Append(self.ID_EXPORT_CSV, "&Export CSV...", "")
        fileMenu.Append(self.ID_EXPORT_IMG, "Export &Image...", "")
        fileMenu.AppendSeparator()
        fileMenu.Append(wx.ID_PRINT, "&Print...").Enable(False)
        fileMenu.Append(wx.ID_PRINT_SETUP, "Print Setup...").Enable(False)
        fileMenu.AppendSeparator()
        fileMenu.Append(wx.ID_CLOSE, "Close &Window")
        self.menubar.Append(fileMenu, "File")
        
        editMenu = wx.Menu()
        self.menubar.Append(editMenu, "Edit")
#         editMenu.Append(-1, "None of these work yet.", "")
        editMenu.Append(wx.ID_CUT, "Cut", "").Enable(False)
        editMenu.Append(wx.ID_COPY, "&Copy", "").Enable(False)
        editMenu.Append(wx.ID_PASTE, "Paste", "").Enable(False)

        viewMenu = wx.Menu()
        self.menubar.Append(viewMenu, "View")
        viewMenu.Append(-1, "None of these work yet.", "")
        
        helpMenu = wx.Menu()
        self.menubar.Append(helpMenu, "Help")
        viewMenu.Append(wx.ID_HELP_INDEX, "FFT View Help").Enable(False)
        
        self.SetMenuBar(self.menubar)
        self.Bind(wx.EVT_MENU, self.OnClose, id=wx.ID_CLOSE)
        self.Bind(wx.EVT_MENU, self.OnExportCsv, id=self.ID_EXPORT_CSV)
        self.Bind(wx.EVT_MENU, self.OnExportImage, id=self.ID_EXPORT_IMG)
        self.Bind(wx.EVT_MENU, self.OnHelp, id=wx.ID_HELP_INDEX)
    
    
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
            self.root.handleException(err, what="exporting FFT as CSV")
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
            self.root.handleException(err, what="exporting FFT as an image")
            return False
    
    
    def OnHelp(self, evt):
        self.root.ask("DEBUG", "Not implemented", style=wx.OK)


    def OnClose(self, evt):
        self.Close()
    
    #===========================================================================
    # 
    #===========================================================================
    
    def makeLineList(self):
        """ Turn each column of data into its own line plot.
        """
        lines = []
#         colors = "BLUE","GREEN","RED"
        # TODO: Read colors from viewer preferences
        colors = (wx.Colour(0,0,255,128),
                  wx.Colour(0,255,0,128),
                  wx.Colour(255,0,0,128),
                  )
        cols = self.data.shape[-1]-1
        
        freqs = self.data[:,0].reshape(-1,1)

        for i in range(cols):
            points = (hstack((freqs, self.data[:,i+1].reshape(-1,1))))
            name = self.sources[i-1].name

            lines.append(P.PolyLine(points, legend=name, colour=self.root.getPlotColor(self.sources[i-1])))#colors[i]))
            
        self.lines = P.PlotGraphics(lines, title=self.GetTitle(), 
                                    xLabel="Frequency", yLabel="Amplitude")
        
    
    
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
    
    
    def generateFFTData(self, data, rows=None, cols=1, fs=5000, 
                        sliceSize=2**16):
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
        
        def nextPow2(x):
            """ Round up to the next greater than or equal to power-of-two.
            """
            x = long(x)
            if x & (x-1L) == 0L:
                # already a power of 2
                return x
            x -= 1L
            for i in xrange(5):
                x |= x >> (2**long(i))
            return x+1L
    

        points = self.from2diter(data, rows, cols)
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

