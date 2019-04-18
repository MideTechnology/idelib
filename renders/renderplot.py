'''
Created on Oct 14, 2014

@author: dstokes
'''

import numpy as np; np=np

import wx
# from renders.wx_lib_plot import PolyLine, PlotGraphics

from wx.lib.plot import PolyLine, PlotGraphics, PlotCanvas

from common import lesser
from renders.fft import FFTPlotCanvas, FFTView

class PlotView(FFTView):
    """
    """
    
    NAME = "Plot"
    FULLNAME = "Rendered Plot"
    TITLE_NAME = None
    
    def __init__(self, *args, **kwargs):
        super(PlotView, self).__init__(*args, **kwargs)
    

    def initPlot(self):
        """
        """
#         self.canvas = FFTPlotCanvas(self)
        self.canvas = PlotCanvas(self)
        self.canvas.enableAntiAliasing = True
        self.canvas.SetFont(wx.Font(10,wx.SWISS,wx.NORMAL,wx.NORMAL))
        self.canvas.fontSizeAxis = 10
        self.canvas.fontSizeLegend = 7
        self.canvas.logScale = self.logarithmic
        self.canvas.xSpec = 'min'
        self.canvas.ySpec = 'auto'
        self.canvas.enableLegend = self.showLegend
        self.canvas.enableTitle = self.showTitle
        self.SetGridColour(self.root.app.getPref('majorHLineColor', 'GRAY'))
        self.canvas.enableGrid = self.showGrid
        self.Fit()
        

    def initMenus(self):
        super(PlotView, self).initMenus()
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_FREQ, checked=False, enabled=False, label="X Axis: Logarithmic Scale")
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_AMP, checked=self.logarithmic[1], label="Y Axis: Logarithmic Scale")
        # Temporary(?) hack: just disable CSV export (it's in the main views already)
        self.setMenuItem(self.fileMenu, self.ID_EXPORT_CSV, enabled=False)


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
            rows = lesser(len(self.source), stop-start)
            
            points = [np.zeros(shape=(rows,2), dtype=float) for _ in self.subchannels]
            for row, evt in enumerate(self.source.iterSlice(start, stop, display=self.useConvertedUnits)):
                for col, ch in enumerate(self.subchannels):
                    if abortEvent is not None and abortEvent():
                        return
                    pts = points[col]
                    pts[row,0] = evt[0]*timeScalar
                    pts[row,1] = evt[1+ch.id]
            
            lines = [None]*len(self.subchannels)
            for col, ch in enumerate(self.subchannels):
                lines[col] = PolyLine(points[col], legend=ch.displayName, colour=self.root.getPlotColor(ch))
            yUnits = "%s%s" % (self.yLabel, self.yUnits)
            self.lines = PlotGraphics(lines, title=self.GetTitle(), 
                                    xLabel="Time (s)", yLabel=yUnits)
                            
            if self.removeMean:
                self.source.removeMean = oldMean
                self.source.rollingMeanSpan = oldSpan
            
#         if self.data is not None:
#             self.makeLineList()

        if self.lines is not None:
            self.canvas.Draw(self.lines)
            self.canvas.enableZoom = True
            self.canvas.showScrollbars = True

        self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))


    #===========================================================================
    # 
    #===========================================================================
    
    def SetGridColour(self, color):
        """
        """
        if not isinstance(color, wx.Colour):
            color = wx.Colour(color)
            
        pen = self.canvas.gridPen
        pen.SetColour(color)
        self.canvas.gridPen = pen
    
    
    #===========================================================================
    # 
    #===========================================================================
            
