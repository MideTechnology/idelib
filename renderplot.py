'''
Created on Oct 14, 2014

@author: dstokes
'''

import numpy as np; np=np

import wx
from wx_lib_plot import PolyLine, PlotGraphics

from fft import FFTPlotCanvas, FFTView

class PlotView(FFTView):
    """
    """
    
    NAME = "Plot"
    FULLNAME = "Rendered Plot"
    
    def __init__(self, *args, **kwargs):
        self.removeMean = kwargs.pop('removeMean', False)
        self.meanSpan = kwargs.pop('meanSpan', -1)
        super(PlotView, self).__init__(*args, **kwargs)
    

    def initPlot(self):
        """
        """
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
        self.canvas.SetGridColour(self.root.app.getPref('majorHLineColor', 'GRAY'))
        self.canvas.SetEnableGrid(self.showGrid)
        self.Fit()
        

    def initMenus(self):
        super(PlotView, self).initMenus()
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_FREQ, checked=False, enabled=False, label="X Axis: Logarithmic Scale")
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_AMP, checked=self.logarithmic[1], label="Y Axis: Logarithmic Scale")


    def _draw(self, abortEvent=None):
        """
        """
        self.lines = None
        if self.subchannels is not None:
            timeScalar = self.root.timeScalar
            if self.removeMean:
                oldMean = self.source.removeMean
                oldSpan = self.source.rollingMeanSpan
                self.source.removeMean = self.removeMean
                self.source.rollingMeanSpan = self.meanSpan
            start, stop = self.source.getRangeIndices(*self.range)
            rows = min(len(self.source), stop-start)
            
            points = [np.zeros(shape=(rows,2), dtype=float) for _ in self.subchannels]
            for row, evt in enumerate(self.source.iterSlice(start, stop)):
                for col, ch in enumerate(self.subchannels):
                    if abortEvent is not None and abortEvent():
                        return
                    pts = points[col]
                    pts[row,0] = evt[0]*timeScalar
                    pts[row,1] = evt[1][ch.id]
            
            lines = [None]*len(self.subchannels)
            for col, ch in enumerate(self.subchannels):
                lines[col] = PolyLine(points[col], legend=ch.name, colour=self.root.getPlotColor(ch))
            yUnits = "%s (%s)" % self.subchannels[0].units
            self.lines = PlotGraphics(lines, title=self.GetTitle(), 
                                    xLabel="Time (s)", yLabel=yUnits)
                            
            if self.removeMean:
                self.source.removeMean = oldMean
                self.source.rollingMeanSpan = oldSpan
            
#         if self.data is not None:
#             self.makeLineList()

        if self.lines is not None:
            self.canvas.Draw(self.lines)

        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    #===========================================================================
    # 
    #===========================================================================
            
