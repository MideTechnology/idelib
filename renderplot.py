'''
Created on Oct 14, 2014

@author: dstokes
'''
from collections import Iterable

import numpy as np; np=np
from numpy.core import hstack, vstack

import wx
import wx_lib_plot as P

from fft import FFTPlotCanvas, FFTView

class PlotView(FFTView):
    """
    """
    def initPlot(self):
        """
        """
#         self.content = PlotPanel(self)
#         self.canvas = FFTPlotCanvas(self.content)
#         self.content.canvas.Add(self.canvas, 1, wx.EXPAND)
#         self.canvas = P.PlotCanvas(self)
        self.canvas = FFTPlotCanvas(self)
        self.canvas.SetEnableAntiAliasing(True)
        self.canvas.SetFont(wx.Font(10,wx.SWISS,wx.NORMAL,wx.NORMAL))
        self.canvas.SetFontSizeAxis(10)
        self.canvas.SetFontSizeLegend(7)
        self.canvas.setLogScale(self.logarithmic)
        self.canvas.SetXSpec('min')
        self.canvas.SetYSpec('auto')
        self.canvas.SetEnableLegend(self.showLegend)
        self.canvas.SetEnableTitle(self.showTitle)
        self.canvas.SetEnableZoom(True)
        self.canvas.SetShowScrollbars(True)
        self.Fit()


    def initMenus(self):
        super(PlotView, self).initMenus()
        self.MenuBar.FindItemById(self.ID_EXPORT_IMG).Enable(False)
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_FREQ, checked=False, enabled=False)
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_AMP, checked=self.logarithmic[1])

    @classmethod
    def from2diter(cls, data, rows=None, cols=1):
        """ Build a 2D `numpy.ndarray` from an iterator (e.g. what's produced by 
            `EventList.itervalues`). 
            
            @todo: This is not the best implementation; even though 
                'numpy.fromiter()` doesn't support 2D arrays, there may be 
                something else in Numpy for doing this.
        """
        if rows is None:
            if hasattr(data, '__len__'):
                rows = len(data)
        
        points = np.zeros(shape=(rows,cols), dtype=float)
        for i, v in enumerate(data):
            points[i,0] = v[0] * 0.000001
            points[i,1:] = v[1]
    
        return points


    @classmethod
    def generateData(cls, data, rows=None, cols=None):
        """
        """
        return cls.from2diter(data, rows, cols)
        

    def makeLineList(self):
        """ Turn each column of data into its own line plot.
        """
        lines = []
        times = self.data[:,0].reshape(-1,1)

        for ch in self.subchannels:
            i = ch.id
            points = (hstack((times, self.data[:,i+1].reshape(-1,1))))
            name = self.subchannels[i-1].name
            lines.append(P.PolyLine(points, legend=name, 
                        colour=self.root.getPlotColor(self.subchannels[i-1])))
        
        self.lines = P.PlotGraphics(lines, title=self.GetTitle(), 
                                    xLabel=self.source.units[0], yLabel="Amplitude")

    def draw(self):
        """
        """
        self.lines = None
        if self.subchannels is not None:
            start, stop = self.source.getRangeIndices(*self.range)
            data = self.source.iterSlice(start, stop)
            self.data = self.from2diter(data, rows=min(len(self.source), stop-start), cols=len(self.subchannels)+1)
            
        if self.data is not None:
            self.makeLineList()

        if self.lines is not None:
            self.canvas.Draw(self.lines)

        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    #===========================================================================
    # 
    #===========================================================================
            
