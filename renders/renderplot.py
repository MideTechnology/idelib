'''
Created on Oct 14, 2014

@author: dstokes
'''

import time

import numpy as np; np=np

import wx
from wx.lib.plot import PolyLine, PlotGraphics
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas

from common import lesser
from logger import logger
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
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_autoscale_on(True)
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.axes.set_title(self.title)

        self.Fit()

        return

        self.canvas = FFTPlotCanvas(self)
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


    def _draw(self):
        """
        """

        logger.info( "Starting %s._draw() in new thread." % self.__class__.__name__ )
        drawStart = time.time()

        self.lines = None
        if self.subchannels is not None:
            subchannelIds = [c.id for c in self.subchannels]
            start, stop = self.source.getRangeIndices(*self.range)
            data = self.source.arrayValues(start,stop,subchannels=subchannelIds,display=self.useConvertedUnits)
            fs = self.source.getSampleRate()
            self.data = self.generateData(data, rows=stop-start,
                                          cols=len(self.subchannels), fs=fs,
                                          sliceSize=self.sliceSize)

        if self.data is not None:
            for i in range(data.shape[0]):
                self.axes.plot(self.data[:, 0], self.data[:, i+1], antialiased=True, linewidth=0.5,
                               label=self.subchannels[i-1].name, color=[float(x)/255. for x in self.root.getPlotColor(self.subchannels[i-1])])
            bbox = self.axes.dataLim
            self.axes.set_xlim(bbox.xmin, bbox.xmax)
            self.axes.set_ylim(bbox.ymin, bbox.ymax)
            self.axes.legend()
            self.axes.grid(True)
            self.canvas.draw()
            self.Fit()
        else:
            logger.info("No data for %s!" % self.FULLNAME)
            self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
            return

        logger.info("%d samples x%d columns calculated. Elapsed time (%s): %0.6f s." % (stop-start, len(self.subchannels), self.FULLNAME, time.time() - drawStart))

        if self.lines is not None:
            self.canvas.Draw(self.lines)
            logger.info("Completed drawing %d lines. Elapsed time (%s): %0.6f s." % (self.data.shape[0]*self.data.shape[1], self.FULLNAME, time.time() - drawStart))
        else:
            logger.info("No lines to draw!. Elapsed time (%s): %0.6f s." % (self.FULLNAME, time.time() - drawStart))

        self.canvas.enableZoom = True
        # self.canvas.SetShowScrollbars(True)

        self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))


    @classmethod
    def generateData(cls, data, rows=None, cols=1, fs=5000, sliceSize=2 ** 16,
                     abortEvent=None, forPsd=False, useWelch=False):
        """ Format channel data for one or more channels.

            @param data: An iterable collection of event values (no times!). The
                data can have one or more channels (e.g. accelerometer X or XYZ
                together). This can be an iterator, generator, or array.
            @keyword rows: The number of rows (samples) in the set, if known.
            @keyword cols: The number of columns (channels) in the set; a
                default if the dataset does not contain multiple columns.
            @return: A multidimensional array, with the first column the
                frequency.
        """
        cols, rows = data.shape
        t = np.arange(0, rows/fs, 1/fs)
        return np.vstack((t, data)).T


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
            
