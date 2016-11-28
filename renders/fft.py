'''
Created on Dec 18, 2013

@todo: Re-implement spectrum to reduce dependencies and make spec.welch()
    work using just the window instead of the full-size array.

@todo: Run in another thread in order to keep the GUI from appearing to have
    hung. Possibly `wx.lib.delayedresult`?

@author: dstokes
'''

from collections import Iterable
import colorsys
import os.path
import sys
import time

import numpy as np; np=np
from numpy.core import hstack, vstack
#from pyfftw.builders import rfft

# from wx.lib.plot import PolyLine, PlotGraphics, PlotCanvas
from wx_lib_plot import PolyLine, PlotGraphics, PlotCanvas
from wx import aui
import wx; wx = wx 
import wx.lib.delayedresult as delayedresult

import spectrum as spec

from base import MenuMixin
from common import mapRange, nextPow2, sanitizeFilename
from widgets.shared import StatusBar

from build_info import DEBUG
from logger import logger

FOREGROUND = False

if DEBUG:
    import logging
    logger.setLevel(logging.INFO)

#     import socket
#     if socket.gethostname() == 'DEDHAM':
#         FOREGROUND = True
    
#===============================================================================
# 
#===============================================================================

# class PlotPanel(wx.Panel):
#     """
#     """
#     def __init__(self, *args, **kwargs):
#         super(PlotPanel, self).__init__(*args, **kwargs)
#         self.canvas = None
#         
#         self.sizer = wx.FlexGridSizer(2,2,0,0)
#         self.canvas = wx.BoxSizer(wx.HORIZONTAL)
#         self.vScrollbar = wx.ScrollBar(self, style=wx.SB_VERTICAL)
#         self.hScrollbar = wx.ScrollBar(self, style=wx.SB_HORIZONTAL)
#         
#         self.sizer.Add(self.canvas, 1, wx.EXPAND)
#         self.sizer.Add(self.vScrollbar, 0, wx.EXPAND)
#         self.sizer.Add(self.hScrollbar, 0, wx.EXPAND)
#         self.sizer.Add(wx.BoxSizer(wx.HORIZONTAL), -1, wx.EXPAND)
#         
#         self.sizer.AddGrowableCol(0)
#         self.sizer.AddGrowableRow(0)
#         self.SetSizerAndFit(self.sizer)

#===============================================================================
# 
#===============================================================================

class FFTPlotCanvas(PlotCanvas):
        
    def _Draw(self, graphics, xAxis = None, yAxis = None, dc = None):
        """ Zoom on the plot
            Centers on the X,Y coords given in Center
            Zooms by the Ratio = (Xratio, Yratio) given
        """
        if xAxis is not None:
            x_range = self.GetXMaxRange()
            xAxis = (max(x_range[0], xAxis[0]), min(x_range[1], xAxis[1]))
            if xAxis[1]-xAxis[0] < 0.00001:
                xAxis= self.last_draw[1]
        if yAxis is not None:
            y_range = self.GetYMaxRange()
            yAxis = (max(y_range[0], yAxis[0]), min(y_range[1], yAxis[1]))
            if yAxis[1]-yAxis[0] < 0.00001:
                yAxis= self.last_draw[2]
        
        try:
            super(FFTPlotCanvas, self)._Draw(graphics, xAxis, yAxis, dc)
        except OverflowError:
            # XXX: THIS IS A HACK TO GET AROUND SPORADIC 'FLOAT INFINITY' ISSUE
            pass

    def _drawAxes(self, dc, p1, p2, scale, shift, xticks, yticks):
        # Standard PlotCanvas uses same color for grid, ticks and border.
        # This will now always draw the border in black, with black ticks
        # if the grid is disabled. This also uses DrawLineList, which
        # should be slightly more efficient.

        # increases thickness for printing only
        penWidth = self.printerScale * self._pointSize[0]
        
        gridPen = wx.Pen(self._gridColour, penWidth)
        blackPen = wx.Pen(wx.NamedColour("BLACK"), penWidth)
        
        lines = []
        # set length of tick marks--long ones make grid
        if self._gridEnabled is not False:
            x, y, width, height = self._point2ClientCoord(p1, p2)
            if self._gridEnabled == 'Horizontal':
                yTickLength = (width / 2.0 + 1) * self._pointSize[1]
                xTickLength = 3 * self.printerScale * self._pointSize[0]
            elif self._gridEnabled == 'Vertical':
                yTickLength = 3 * self.printerScale * self._pointSize[1]
                xTickLength = (height / 2.0 + 1) * self._pointSize[0]
            else:
                yTickLength = (width / 2.0 + 1) * self._pointSize[1]
                xTickLength = (height / 2.0 + 1) * self._pointSize[0]
            dc.SetPen(gridPen)
        else:
            # lengthens lines for printing
            yTickLength = 3 * self.printerScale * self._pointSize[1]
            xTickLength = 3 * self.printerScale * self._pointSize[0]
            dc.SetPen(blackPen)

        if self._xSpec is not 'none':
            lower, upper = p1[0], p2[0]
            text = 1
            # miny, maxy and tick lengths
            for y, d in [(p1[1], -xTickLength), (p2[1], xTickLength)]:
                for x, label in xticks:
                    pt = scale * np.array([x, y]) + shift
                    # draws tick mark d units
                    lines.append((pt[0], pt[1], pt[0], pt[1] + d))
                    if text:
                        dc.DrawText(label, pt[0], 
                                    pt[1] + 2 * self._pointSize[1])
                a1 = scale * np.array([lower, y]) + shift
                a2 = scale * np.array([upper, y]) + shift
                # draws upper and lower axis line
                lines.append((a1[0], a1[1], a2[0], a2[1]))
                text = 0  # axis values not drawn on top side

        if self._ySpec is not 'none':
            lower, upper = p1[1], p2[1]
            text = 1
            h = dc.GetCharHeight()
            for x, d in ((p1[0], -yTickLength), (p2[0], yTickLength)):
                for y, label in yticks:
                    pt = scale * np.array([x, y]) + shift
                    lines.append((pt[0], pt[1], pt[0] - d, pt[1]))
                    if text:
                        dc.DrawText(label, 
                                    pt[0] - dc.GetTextExtent(label)[0] - 3 * self._pointSize[0],
                                    pt[1] - 0.75 * h)
                a1 = scale * np.array([x, lower]) + shift
                a2 = scale * np.array([x, upper]) + shift
                lines.append((a1[0], a1[1], a2[0], a2[1]))
                text = 0    # axis values not drawn on right side

        dc.DrawLineList(lines)
        
        # Always draw border in black
        if self._gridEnabled is not False:
            y1 = scale[1] * p1[1] + shift[1]
            y2 = scale[1] * p2[1] + shift[1]
            x1 = scale[0] * p1[0] + shift[0]
            x2 = scale[0] * p2[0] + shift[0]
    
            dc.DrawLineList([(x1, y1, x2, y1),(x1, y2, x2, y2),
                             (x1, y1, x1, y2),(x2, y1, x2, y2)],
                             blackPen)        

        
#===============================================================================
# 
#===============================================================================

class FFTView(wx.Frame, MenuMixin):
    """
    """
    NAME = TITLE_NAME = "FFT"
    FULLNAME = "FFT View"
    xLabel = "Frequency"
    yLabel = "Amplitude"
    
    ID_EXPORT_CSV = wx.NewId()
    ID_EXPORT_IMG = wx.NewId()
    ID_DATA_LOG_AMP = wx.NewId()
    ID_DATA_LOG_FREQ = wx.NewId()
    ID_VIEW_SHOWTITLE = wx.NewId()
    ID_VIEW_SHOWLEGEND = wx.NewId()
    ID_VIEW_SHOWGRID = wx.NewId()
    ID_VIEW_ANTIALIAS = wx.NewId()
    ID_VIEW_CHANGETITLE = wx.NewId()
    
    IMAGE_FORMATS = "Windows Bitmap (*.bmp)|*.bmp|" \
                     "JPEG (*.jpg)|*.jpg|" \
                     "Portable Network Graphics (*.png)|*.png" 


    def makeTitle(self):
        """ Helper method to generate a nice-looking title.
        """
        try:
            timeScalar = self.root.timeScalar
            places = wx.GetApp().getPref("precisionX", 4)
        except AttributeError:
            timeScalar = 1.0/(10**6)
            places = 4
        
        start = ("%%.%df" % places) % (self.range[0] * timeScalar)
        end = ("%%.%df" % places) % (self.range[1] * timeScalar)

        # Smart plot naming: use parent channel name if all children plotted.
        events = [c.getSession(self.root.session.sessionId) for c in self.subchannels]
        units = [el.units[0] for el in events if el.units[0] != events[0].units[0]]
        if len(units) == 0:
            title = "%s %s" % (events[0].units[0], ', '.join([c.name for c in self.subchannels]))
        else:
            title = ", ".join([c.displayName for c in self.subchannels])

#         if len(self.subchannels) != len(self.source.parent.subchannels):
#             title = ", ".join([c.name for c in self.subchannels])
#         else:
#             title = self.source.parent.name
        
        if self.TITLE_NAME:
            return "%s: %s (%ss to %ss)" % (self.NAME, title, start, end)
        return "%s (%ss to %ss)" % (title, start, end)


    def __init__(self, *args, **kwargs):
        """ FFT view main panel. Takes standard wx.Window arguments plus
            additional keyword arguments. Note that the FFT view doesn't use
            them all; some are applicable only to FFTView subclasses.
        
            @keyword root: The parent viewer window
            @keyword source: 
            @keyword subchannels: A list of subchannels
            @keyword start: The start of the time interval to render
            @keyword end: The end of the time interval to render
            @keyword windowSize: 
            @keyword removeMean: 
            @keyword meanSpan: 
            @keyword logarithmic: 
            @keyword param: 
            @keyword exportPrecision: 
            @keyword yUnits: 
            @keyword indexRange: 
            @keyword numRows: 
        """
        self.root = kwargs.pop("root", None)
        self.source = kwargs.pop("source", None)
        self.subchannels = kwargs.pop("subchannels", None)
        self.range = (kwargs.pop("startTime",0), kwargs.pop("endTime",-1))
        self.data = kwargs.pop("data",None)
        self.sliceSize = kwargs.pop("windowSize", 2**16)
        self.removeMean = kwargs.pop('removeMean', True)
        self.meanSpan = kwargs.pop('meanSpan', -1)
        self.logarithmic = kwargs.pop('logarithmic', (False, False))
        self.exportPrecision = kwargs.pop('exportPrecision', 6)
        self.useConvertedUnits = kwargs.pop('display', True)
        self.yUnits = kwargs.pop('yUnits', None)#self.subchannels[0].units[1])
        self.indexRange = kwargs.pop('start', 0), kwargs.pop('stop', -1)
        self.numRows = kwargs.pop('numRows')
        self.noBivariates = kwargs.pop('noBivariates', False)
        self.useWelch = kwargs.pop('useWelch', False)
        if self.useWelch:
            self.NAME = self.TITLE_NAME = "Welch's PSD"


        # Callback. Not currently used.
        self.callback = kwargs.pop('callback', None)
        self.callbackInterval = kwargs.pop('callbackInterval', 0.0005)
        
        sessionId = self.root.session.sessionId
        
        if self.yUnits is None:
            if self.useConvertedUnits:
                self.yLabel, self.yUnits = self.subchannels[0].getSession(sessionId).units
            else:
                self.yLabel, self.yUnits = self.subchannels[0].units
        
        
        if self.source is None and self.subchannels is not None:
            self.source = self.subchannels[0].parent.getSession(sessionId)

        self.source = self.source.copy()
        self.source.allowMeanRemoval = self.source.hasMinMeanMax
        self.source.noBivariates = self.noBivariates

        kwargs.setdefault('title', self.makeTitle())
        super(FFTView, self).__init__(*args, **kwargs)
        
        self.abortEvent = delayedresult.AbortEvent()
        
        self.SetMinSize((640,480))
        self.yUnits = (" (%s)" % self.yUnits) if self.yUnits else ""
        self.formatter = "%%.%df" % self.exportPrecision
        self.showTitle = self.root.app.getPref('fft.showTitle', True)
        self.showLegend = self.root.app.getPref('fft.showLegend', True)
        self.showGrid = self.root.app.getPref('fft.showGrid', True)
        self.timeScalar = getattr(self.root, "timeScalar", 1.0/(6**10))
        self.statusBar = StatusBar(self)
        self.statusBar.stopProgress()
        self.SetStatusBar(self.statusBar)
        
        self.initMenus()
        self.initPlot()

        self.Show(True)
        self.Update()

        self.Bind(wx.EVT_CLOSE, self.OnClose)

        self.draw()


    def initPlot(self):
        """ Set up the drawing area.
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
        self.canvas.SetGridColour(self.root.app.getPref('majorHLineColor', 'GRAY'))
        self.canvas.SetEnableGrid(self.showGrid)
        self.Fit()


    def finishDraw(self, arg):
        """ Callback executed when the background drawing thread completes.
        """
        try:
            self.source.removeMean = self.oldRemoveMean
            self.source.rollingMeanSpan = self.oldRollingMeanSpan
            self.statusBar.stopProgress()
            for i in range(4):
                self.menubar.EnableTop(i, True)
            self.Update()
            self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        except wx.PyDeadObjectError:
            pass


    def draw(self):
        """ Initiates the background calculation/drawing thread.
        """
        self.drawStart = time.time()
        self.oldRemoveMean = self.source.removeMean
        self.oldRollingMeanSpan = self.source.rollingMeanSpan
        self.source.removeMean = self.removeMean
        self.source.rollingMeanSpan = self.meanSpan
        
        for i in range(4):
            self.menubar.EnableTop(i, False)
            
        if FOREGROUND:
            self._draw()
            return self.finishDraw(None)

        self.statusBar.startProgress(label="Calculating...", initialVal=-1, cancellable=False, delay=100)
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
        t = delayedresult.startWorker(self.finishDraw, self._draw, daemon=True)
        t.setName("%sThread" % self.NAME)
        

    def _draw(self):
        """
        """
        if FOREGROUND:
            logger.info( "Starting %s._draw() in foreground process." % self.__class__.__name__ )
        else:
            logger.info( "Starting %s._draw() in new thread." % self.__class__.__name__ )
        drawStart = time.time()
            
        try:
            self.lines = None
            if self.subchannels is not None:
                subchannelIds = [c.id for c in self.subchannels]
                start, stop = self.source.getRangeIndices(*self.range)
                data = self.source.itervalues(start, stop, subchannels=subchannelIds, display=self.useConvertedUnits)
                # BUG: Calculation of actual sample rate is wrong. Investigate.
    #             fs = (channel[stop][-2]-channel[start][-2]) / ((stop-start) + 0.0)
                fs = self.source.getSampleRate()
                self.data = self.generateData(data, rows=stop-start,
                                              cols=len(self.subchannels), fs=fs, 
                                              sliceSize=self.sliceSize, useWelch=self.useWelch)
                
            if self.data is not None:
                self.makeLineList()
            else:
                logger.info("No data for %s!" % self.FULLNAME)
                self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
                return

            logger.info("%d samples x%d columns calculated. Elapsed time (%s): %0.6f s." % (stop-start, len(self.subchannels), self.FULLNAME, time.time() - drawStart))
    
            if self.lines is not None:
                self.canvas.Draw(self.lines)
                logger.info("Completed drawing %d lines. Elapsed time (%s): %0.6f s." % (self.data.shape[0]*self.data.shape[1], self.FULLNAME, time.time() - drawStart))
            else:
                logger.info("No lines to draw!. Elapsed time (%s): %0.6f s." % (self.FULLNAME, time.time() - drawStart))
    
            self.canvas.SetEnableZoom(True)
#             self.canvas.SetShowScrollbars(True)

            self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
            
        except wx.PyDeadObjectError:
            pass

        
    
    def initMenus(self):
        """ Install and set up the main menu.
        """
        self.menubar = wx.MenuBar()
        
        fileMenu = self.fileMenu = wx.Menu()
        self.addMenuItem(fileMenu, self.ID_EXPORT_CSV, "&Export CSV...", "", 
                         self.OnExportCsv)
        self.addMenuItem(fileMenu, self.ID_EXPORT_IMG, "&Save Image...\tCtrl+S", "", 
                         self.OnExportImage, True)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_PRINT, "&Print...\tCtrl+P", "", 
                         self.OnFilePrint)
        self.addMenuItem(fileMenu, wx.ID_PREVIEW, "Print Preview...", "", 
                         self.OnFilePrintPreview)
        self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, "Print Setup...", "", 
                         self.OnFilePageSetup)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_CLOSE, "Close &Window\tCtrl+W", "", 
                         self.OnMenuFileClose)
        self.menubar.Append(fileMenu, "File")
        
        editMenu = wx.Menu()
        self.addMenuItem(editMenu, wx.ID_CUT, "Cut", "", None, False)
        self.addMenuItem(editMenu, wx.ID_COPY, "&Copy", "", None, False)
        self.addMenuItem(editMenu, wx.ID_PASTE, "Paste", "", None, False)
        self.menubar.Append(editMenu, "Edit")

        viewMenu = wx.Menu()
        self.addMenuItem(viewMenu, wx.ID_ZOOM_IN, "Zoom Out\tCtrl+-", "", 
                         self.OnZoomOut)
        self.addMenuItem(viewMenu, wx.ID_ZOOM_OUT, "Zoom In\tCtrl+=", "", 
                         self.OnZoomIn)
        self.addMenuItem(viewMenu, wx.ID_RESET, "Zoom to Fit\tCtrl+0", "", 
                         self.OnMenuViewReset)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_SHOWLEGEND, 
                         "Show Legend\tCtrl+L", "", self.OnMenuViewLegend, 
                         kind=wx.ITEM_CHECK, checked=self.showLegend)
        self.addMenuItem(viewMenu, self.ID_VIEW_SHOWTITLE, 
                         "Show Title\tCtrl+T", "", self.OnMenuViewTitle, 
                         kind=wx.ITEM_CHECK, checked=self.showTitle)
        self.addMenuItem(viewMenu, self.ID_VIEW_SHOWGRID, 
                         "Show Grid\tCtrl+G", "", self.OnMenuViewGrid, 
                         kind=wx.ITEM_CHECK, checked=self.showGrid)

        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_CHANGETITLE,
                         "Edit Title...", "", self.OnViewChangeTitle)
        self.menubar.Append(viewMenu, "View")
        self.viewMenu = viewMenu
        
        dataMenu = wx.Menu()
        self.logFreq = self.addMenuItem(dataMenu, self.ID_DATA_LOG_FREQ, 
                         "%s: Logarithmic Scale" % self.xLabel, "", self.OnMenuDataLog,
                         kind=wx.ITEM_CHECK, checked=self.logarithmic[0])
        self.logAmp = self.addMenuItem(dataMenu, self.ID_DATA_LOG_AMP, 
                         "%s: Logarithmic Scale" % self.yLabel, "", self.OnMenuDataLog,
                         kind=wx.ITEM_CHECK, checked=self.logarithmic[1])
        self.menubar.Append(dataMenu, "Data")
        self.dataMenu = dataMenu
        
        helpMenu = wx.Menu()
        self.addMenuItem(helpMenu, wx.ID_ABOUT, 
            "About %s..." % self.root.app.fullAppName, "", 
             self.root.OnHelpAboutMenu)
        self.menubar.Append(helpMenu, "Help")
        
        self.SetMenuBar(self.menubar)
    
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    def makeLineList(self):
        """ Turn each column of data into its own line plot.
        """
        if self.data is None:
            return
        
        lines = []
        cols = self.data.shape[-1]-1
        
        freqs = self.data[:,0].reshape(-1,1)

        for i in range(cols):
            points = (hstack((freqs, self.data[:,i+1].reshape(-1,1))))
            name = self.subchannels[i].name

            lines.append(PolyLine(points, legend=name, 
                        colour=self.root.getPlotColor(self.subchannels[i])))
            
        self.lines = PlotGraphics(lines, title=self.GetTitle(), 
                                  xLabel="Frequency (Hz)", 
                                  yLabel="%s%s" % (self.yLabel, self.yUnits))

    
    @classmethod
    def from2diter(cls, data, rows=None, cols=1, abortEvent=None):
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
#         print "shape=",rows,cols
        points = np.zeros(shape=(rows,cols), dtype=float)
        points[0,:] = row1

        for i, row in enumerate(dataIter,1):
            if abortEvent is not None and abortEvent():
                break
            # XXX: HACK. Spectrogram generation fails here. Find real cause.
            try:
                points[i,:] = row
            except IndexError:
                break

        return points
    
    
    @classmethod
    def from2diterWithDiscontinuity(cls, data, rows=None, cols=1):
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


#     @classmethod
#     def generateData(cls, data, rows=None, cols=1, fs=5000, sliceSize=2**16):
#         """ Compute 1D FFT from one or more channels of data, using Welch's
#             method.
#         
#             @note: This is the implementation from the old viewer and does not
#                 scale well to massive datasets. This *will* run of of memory; 
#                 the exact number of samples/RAM has yet to be determined.
#                 
#             @param data: An iterable collection of event values (no times!). The
#                 data can have one or more channels (e.g. accelerometer X or XYZ
#                 together). This can be an iterator, generator, or array.
#             @keyword rows: The number of rows (samples) in the set, if known.
#             @keyword cols: The number of columns (channels) in the set; a 
#                 default if the dataset does not contain multiple columns.
#             @keyword fs: Frequency of sample, i.e. the sample rate (Hz)
#             @keyword sliceSize: The size of the 'window' used to compute the 
#                 FFTs via Welch's method. Should be a power of 2!
#             @return: A multidimensional array, with the first column the 
#                 frequency.
#         """
# #         print "rows=%r cols=%r fs=%r sliceSize=%r" % (rows, cols, fs, sliceSize)
#         points = cls.from2diter(data, rows, cols)
#         rows, cols = points.shape
#         shape = points.shape
#         points.resize((max(nextPow2(shape[0]),sliceSize), shape[1]))
#         
#         slicePad = sliceSize
#         sliceSize = max(sliceSize, rows)
#         
#         # NOTE: Copied verbatim from old viewer. Revisit whether or not all this
#         #     shaping and stacking is really necessary.
#         fftData = np.arange(0, slicePad/2.0 + 1) * (fs/float(slicePad))
#         fftData = fftData.reshape(-1,1)
#         
#         scalar = (sliceSize/2.0)
#         
#         for i in xrange(cols):
#             # Returns (FFT data, frequencies)
#             tmp_fft, _ = spec.welch(points[:,i], NFFT=sliceSize, Fs=fs, 
#                                     detrend=spec.detrend_mean, 
#                                     noverlap=sliceSize/2, sides='onesided', 
#                                     scale_by_freq=False, pad_to=slicePad, 
#                                     window=spec.window_hanning)
#             tmp_fft = tmp_fft / scalar
#             tmp_fft = tmp_fft.reshape(-1,1)
#             fftData = hstack((fftData, tmp_fft))
#             
#             # Remove huge DC component from displayed data; so data of interest 
#             # can be seen after auto axis fitting
#             thisCol = i+1
#             fftData[0,thisCol] = 0.0
#             fftData[1,thisCol] = 0.0
#             fftData[2,thisCol] = 0.0
#         
#         return fftData

    @classmethod
    def generateData(cls, data, rows=None, cols=1, fs=5000, sliceSize=2 ** 16,
                     abortEvent=None, forPsd=False, useWelch=False):
        """ Compute 1D FFT from one or more channels of data.

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
            @return: A multidimensional array, with the first column the
                frequency.
        """
        points = cls.from2diter(data, rows, cols, abortEvent=abortEvent)
        rows, cols = points.shape
        NFFT = nextPow2(rows)

        # Create frequency range (first column)
        fftData = np.arange(0, NFFT/2.0 + 1) * (fs/float(NFFT))
        fftData = fftData.reshape(-1,1)

#         print "rows: %s\tNFFT=%s" % (rows, NFFT)
        for i in xrange(cols):
            if abortEvent is not None and abortEvent():
                return

#            fft_obj = rfft(points[:,i], NFFT, planner_effort='FFTW_ESTIMATE')
#            if forPsd:
#                tmp_fft = abs(fft_obj()[:NFFT/2+1])
#            else:
#                tmp_fft = 2*abs(fft_obj()[:NFFT/2+1])/rows

            if forPsd:
                tmp_fft = abs(np.fft.fft(points[:,i], NFFT)[:NFFT/2+1])
            else:
                tmp_fft = 2*abs(np.fft.fft(points[:,i], NFFT)[:NFFT/2+1])/rows

            fftData = hstack((fftData, tmp_fft.reshape(-1,1)))

            # Remove huge DC component from displayed data; so data of interest
            # can be seen after auto axis fitting
            thisCol = i+1
            fftData[0,thisCol] = 0.0
            fftData[1,thisCol] = 0.0
            fftData[2,thisCol] = 0.0

        return fftData


    #===========================================================================
    # Event Handlers
    #===========================================================================

    def OnExportCsv(self, evt):
        ex = None if DEBUG else Exception
        filename = None
        
        dlg = wx.FileDialog(self, 
            message="Export CSV...", 
#             defaultDir=defaultDir,  defaultFile=defaultFile, 
            wildcard = "Comma Separated Values (*.csv)|*.csv",
            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
        
        if filename is None:
            return False
        
        try:
            np.savetxt(filename, self.data, fmt=self.formatter, delimiter=', ')
            return True
        except ex as err:
            what = "exporting %s as CSV" % self.NAME
            self.root.handleError(err, what=what)
            return False
        
    
    def OnExportImage(self, event):
        ex = None if DEBUG else Exception
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
        except ex as err:
            what = "exporting %s as an image" % self.NAME
            self.root.handleError(err, what=what)
            return False

    def zoomPlot(self, plot, amount):
        fullX = plot.GetXMaxRange()
        fullY = plot.GetYMaxRange()
        oldX = plot.GetXCurrentRange()
        oldY = plot.GetYCurrentRange()
        newX = (max(fullX[0], (1.0-amount) * oldX[0]), min(fullX[1], (1.0+amount) * oldX[1]))
        newY = (max(fullY[0], (1.0-amount) * oldY[0]), min(fullY[1], (1.0+amount) * oldY[1]))

        if newX[0] > newX[1]:
            newX = tuple(oldX)
        if newY[0] > newY[1]:
            newY = tuple(oldY)
        plot.Draw(plot.last_draw[0], xAxis=newX, yAxis=newY)

    def OnZoomOut(self, evt):
        self.zoomPlot(self.canvas, .1)
        
    def OnZoomIn(self, evt):
        self.zoomPlot(self.canvas, -.1)
    
    def OnMenuViewReset(self, evt):
        self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
        self.canvas.Reset()
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    def OnMenuDataLog(self, evt):
        """
        """
        self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
        self.logarithmic = (self.logFreq.IsChecked(), self.logAmp.IsChecked())
        self.canvas.setLogScale(self.logarithmic)
        self.canvas.Redraw()
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    def OnMenuViewLegend(self, evt):
        self.showLegend = evt.IsChecked()
        self.canvas.SetEnableLegend(self.showLegend)
        self.canvas.Redraw()
    
    def OnMenuViewTitle(self, evt):
        self.showTitle = evt.IsChecked()
        self.canvas.SetEnableTitle(self.showTitle)
        self.canvas.Redraw()

    def OnMenuViewGrid(self, evt):
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
        self.showGrid = evt.IsChecked()
        self.canvas.SetEnableGrid(self.showGrid)
        self.root.app.setPref('fft.showGrid', self.showGrid)
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
#         self.canvas.Redraw()

    def OnViewChangeTitle(self, evt):
        dlg = wx.TextEntryDialog(self, 'New Plot Title:', 'Change Title', 
                                 self.lines.getTitle())

        if dlg.ShowModal() == wx.ID_OK:
            self.lines.setTitle(dlg.GetValue())
            self.canvas.Redraw()

        dlg.Destroy()

    def OnMenuFileClose(self):
        self.Close()

    def OnClose(self, evt):
        self.abortEvent.set()
        evt.Skip()

    def OnFilePageSetup(self, event):
        self.canvas.PageSetup()
        
    def OnFilePrint(self, evt):
        self.canvas.Printout()
        
    def OnFilePrintPreview(self, evt):
        self.canvas.PrintPreview()


#===============================================================================
# 
#===============================================================================

class SpectrogramPlot(FFTPlotCanvas):
    """ A subclass of the standard `wx.lib.plot.PlotCanvas` that draws a bitmap
        instead of a vector graph. 
        
        @todo: Refactor this. Subclassing PlotCanvas was kind of a hack in
            order to get a quick graph similar to the standard FFT plot, and
            is much heavier than necessary.
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.image = kwargs.pop('image', None)
        self.outOfRangeColor = kwargs.pop('outOfRangeColor', (200,200,200))
        self.zoomedImage = None
        self.lastZoom = None
        super(SpectrogramPlot, self).__init__(*args, **kwargs)


    def _Draw(self, graphics, xAxis = None, yAxis = None, dc = None):
        """\
        Draw objects in graphics with specified x and y axis.
        graphics- instance of PlotGraphics with list of PolyXXX objects
        xAxis - tuple with (min, max) axis range to view
        yAxis - same as xAxis
        dc - drawing context - doesn't have to be specified.    
        If it's not, the offscreen buffer is used
        """

        # Modification: remember if xAxis or yAxis set (the variables change)
        zoomed = not (xAxis is None and yAxis is None)
        thisZoom = str((xAxis, yAxis))
        
        if dc is None:
            # sets new dc and clears it 
            dc = wx.BufferedDC(wx.ClientDC(self.canvas), self._Buffer)
            bbr = wx.Brush(self.GetBackgroundColour(), wx.SOLID)
            dc.SetBackground(bbr)
            dc.SetBackgroundMode(wx.SOLID)
            dc.Clear()
        if self._antiAliasingEnabled:
            if not isinstance(dc, wx.GCDC):
                try:
                    dc = wx.GCDC(dc)
                except Exception:
                    pass
                else:
                    if self._hiResEnabled:
                        dc.SetMapMode(wx.MM_TWIPS) # high precision - each logical unit is 1/20 of a point
                    self._pointSize = tuple(1.0 / lscale for lscale in dc.GetLogicalScale())
                    self._setSize()
        elif self._pointSize != (1.0, 1.0):
            self._pointSize = (1.0, 1.0)
            self._setSize()
        if sys.platform in ("darwin", "win32") or not isinstance(dc, wx.GCDC):
            self._fontScale = sum(self._pointSize) / 2.0
        else:
            # on Linux, we need to correct the font size by a certain factor if wx.GCDC is used,
            # to make text the same size as if wx.GCDC weren't used
            ppi = dc.GetPPI()
            self._fontScale = (96.0 / ppi[0] * self._pointSize[0] + 96.0 / ppi[1] * self._pointSize[1]) / 2.0
        graphics._pointSize = self._pointSize
            
        dc.SetTextForeground(self.GetForegroundColour())
        dc.SetTextBackground(self.GetBackgroundColour())

        dc.BeginDrawing()
        # dc.Clear()
        
        # set font size for every thing but title and legend
        dc.SetFont(self._getFont(self._fontSizeAxis))

        # MODIFICATION: Get ranges
        x_range = None
        y_range = None

        # BUG: Zoom limitations don't work!
#         print "==============================\nbefore:"
#         print xAxis, x_range
#         print yAxis, y_range

        # sizes axis to axis type, create lower left and upper right corners of plot
        if xAxis is None or yAxis is None:
            # One or both axis not specified in Draw
            p1, p2 = graphics.boundingBox()     # min, max points of graphics
            if xAxis is None:
                xAxis = self._axisInterval(self._xSpec, p1[0], p2[0]) # in user units
            else:
                # MODIFICATION: (this 'else' branch) limit zoom to data extents
                x_range = self.GetXMaxRange()
                xAxis = (max(x_range[0], xAxis[0]), min(x_range[1], xAxis[1]))
            if yAxis is None:
                yAxis = self._axisInterval(self._ySpec, p1[1], p2[1])
            else:
                # MODIFICATION: (this 'else' branch) limit zoom to data extents
                y_range = self.GetYMaxRange()
                yAxis = (max(y_range[0], yAxis[0]), min(y_range[1], yAxis[1]))
            # Adjust bounding box for axis spec
            p1[0],p1[1] = xAxis[0], yAxis[0]     # lower left corner user scale (xmin,ymin)
            p2[0],p2[1] = xAxis[1], yAxis[1]     # upper right corner user scale (xmax,ymax)
        else:
            # Both axis specified in Draw
            p1= np.array([xAxis[0], yAxis[0]])    # lower left corner user scale (xmin,ymin)
            p2= np.array([xAxis[1], yAxis[1]])     # upper right corner user scale (xmax,ymax)

        self.last_draw = (graphics, np.array(xAxis), np.array(yAxis))       # saves most recient values

#         print "==============================\nafter:"
#         print xAxis, x_range
#         print yAxis, y_range
#         
        # Get ticks and textExtents for axis if required
        if self._xSpec is not 'none':        
            xticks = self._xticks(xAxis[0], xAxis[1])
            xTextExtent = dc.GetTextExtent(xticks[-1][1])# w h of x axis text last number on axis
        else:
            xticks = None
            xTextExtent= (0,0) # No text for ticks
        if self._ySpec is not 'none':
            yticks = self._yticks(yAxis[0], yAxis[1])
            if self.getLogScale()[1]:
                yTextExtent = dc.GetTextExtent('-2e-2')
            else:
                yTextExtentBottom = dc.GetTextExtent(yticks[0][1])
                yTextExtentTop = dc.GetTextExtent(yticks[-1][1])
                yTextExtent= (max(yTextExtentBottom[0],yTextExtentTop[0]),
                              max(yTextExtentBottom[1],yTextExtentTop[1]))
        else:
            yticks = None
            yTextExtent= (0,0) # No text for ticks

        # TextExtents for Title and Axis Labels
        titleWH, xLabelWH, yLabelWH= self._titleLablesWH(dc, graphics)

        # TextExtents for Legend
        legendBoxWH, legendSymExt, legendTextExt = self._legendWH(dc, graphics)

        # room around graph area
        rhsW= max(xTextExtent[0], legendBoxWH[0])+5*self._pointSize[0] # use larger of number width or legend width
        lhsW= yTextExtent[0]+ yLabelWH[1] + 3*self._pointSize[0]
        bottomH= max(xTextExtent[1], yTextExtent[1]/2.)+ xLabelWH[1] + 2*self._pointSize[1]
        topH= yTextExtent[1]/2. + titleWH[1]
        textSize_scale= np.array([rhsW+lhsW,bottomH+topH]) # make plot area smaller by text size
        textSize_shift= np.array([lhsW, bottomH])          # shift plot area by this amount

        # draw title if requested
        if self._titleEnabled:
            dc.SetFont(self._getFont(self._fontSizeTitle))
            titlePos= (self.plotbox_origin[0]+ lhsW + (self.plotbox_size[0]-lhsW-rhsW)/2.- titleWH[0]/2.,
                       self.plotbox_origin[1]- self.plotbox_size[1])
            dc.DrawText(graphics.getTitle(),titlePos[0],titlePos[1])

        # draw label text
        dc.SetFont(self._getFont(self._fontSizeAxis))
        xLabelPos= (self.plotbox_origin[0]+ lhsW + (self.plotbox_size[0]-lhsW-rhsW)/2.- xLabelWH[0]/2.,
                 self.plotbox_origin[1]- xLabelWH[1])
        dc.DrawText(graphics.getXLabel(),xLabelPos[0],xLabelPos[1])
        yLabelPos= (self.plotbox_origin[0] - 3*self._pointSize[0],
                 self.plotbox_origin[1]- bottomH- (self.plotbox_size[1]-bottomH-topH)/2.+ yLabelWH[0]/2.)
        if graphics.getYLabel():  # bug fix for Linux
            dc.DrawRotatedText(graphics.getYLabel(),yLabelPos[0],yLabelPos[1],90)

        # drawing legend makers and text
        if self._legendEnabled:
            self._drawLegend(dc,graphics,rhsW,topH,legendBoxWH, legendSymExt, legendTextExt)

        # allow for scaling and shifting plotted points
        scale = (self.plotbox_size-textSize_scale) / (p2-p1)* np.array((1,-1))
        shift = -p1*scale + self.plotbox_origin + textSize_shift * np.array((1,-1))
        self._pointScale= scale / self._pointSize  # make available for mouse events
        self._pointShift= shift / self._pointSize
        
        ptx,pty,rectWidth,rectHeight= self._point2ClientCoord(p1, p2)
        
        # MODIFICATION: Draw the spectrogram bitmap
        if self.image is not None:
            if zoomed:
                if thisZoom == self.lastZoom and self.zoomedImage is not None:
                    img = self.zoomedImage
                else:
                    self.lastZoom = thisZoom
                    if x_range is None:
                        x_range = self.GetXMaxRange()
                    if y_range is None:
                        y_range = self.GetYMaxRange()
                    img_w, img_h = self.image.GetSize()
                    
                    x1 = mapRange(p1[0], x_range[0], x_range[1], 0, img_w)
                    x2 = mapRange(p2[0], x_range[0], x_range[1], 0, img_w)
                    y1 = mapRange(p1[1], y_range[0], y_range[1], 0, img_h)
                    y2 = mapRange(p2[1], y_range[0], y_range[1], 0, img_h)
                    
                    zoomSize = wx.Size(max(1, abs(x2-x1)), max(1, abs(y2-y1)))
                    zoomPos = wx.Point(-x1, -(img_h-y2))
                    self.zoomedImage = self.image.Size(zoomSize, zoomPos, 
                                                       *self.outOfRangeColor)
                img = self.zoomedImage
            else:
                img = self.image
                
            try:
                # Bad dimensions raise an exception; ignore it.
                img = img.Scale(rectWidth, rectHeight).ConvertToBitmap()
                dc.DrawBitmap(img, ptx, pty)
            except:
                pass
        
        self._drawAxes(dc, p1, p2, scale, shift, xticks, yticks)
        
        graphics.scaleAndShift(scale, shift)
        graphics.setPrinterScale(self.printerScale)  # thicken up lines and markers if printing
        
        # set clipping area so drawing does not occur outside axis box
        # allow graph to overlap axis lines by adding units to width and height
        dc.SetClippingRegion(ptx*self._pointSize[0],pty*self._pointSize[1],rectWidth*self._pointSize[0]+2,rectHeight*self._pointSize[1]+1)
        # Draw the lines and markers
        #start = _time.clock()
#         graphics.draw(dc)
        # print "entire graphics drawing took: %f second"%(_time.clock() - start)
        # remove the clipping region
        dc.DestroyClippingRegion()
        dc.EndDrawing()

        self._adjustScrollbars()
        

#===============================================================================
# 
#===============================================================================

class SpectrogramView(FFTView):
    """
    """
    NAME = TITLE_NAME = "Spectrogram"
    FULLNAME = "Spectrogram View"
    xLabel = "Time"
    yLabel = "Amplitude"
    
    ID_COLOR_SPECTRUM = wx.NewId()
    ID_COLOR_GRAY = wx.NewId()
    
    def __init__(self, *args, **kwargs):
        """
        """
        # Colorizers: The functions that render the spectrogram image.
        self.colorizers = {self.ID_COLOR_GRAY: self.plotGrayscale,
                           self.ID_COLOR_SPECTRUM: self.plotColorSpectrum}
        # 'Out of range' colors: The background color if the plot is scrolled
        # or zoomed out beyond the bounds of the image. The color is one that
        # is identifiable as not part of the spectrogram rendering.
        self.outOfRangeColors = {self.ID_COLOR_GRAY: (200,200,255),
                                 self.ID_COLOR_SPECTRUM: (200,200,200)}
        
        self.slicesPerSec = float(kwargs.pop('slicesPerSec', 4.0))
        self.images = None
        self.colorizerId = kwargs.pop('colorizer', self.ID_COLOR_SPECTRUM)
        self.colorizer = self.colorizers.get(self.colorizerId, self.plotColorSpectrum)
        self.outOfRangeColor = self.outOfRangeColors.get(self.colorizerId, (200,200,200))
        
        # The spectrogram is basically a 3D graph, time/frequency/amplitude
        kwargs.setdefault('logarithmic', (False, False, True))
        super(SpectrogramView, self).__init__(*args, **kwargs)


    def initPlot(self):
        ""
        self.canvas = aui.AuiNotebook(self, -1, style=aui.AUI_NB_TOP | 
                                   aui.AUI_NB_TAB_SPLIT |
                                   aui.AUI_NB_TAB_MOVE | 
                                   aui.AUI_NB_SCROLL_BUTTONS)


    def addPlot(self, channelIdx):
        """
        """
        p = SpectrogramPlot(self)
        p.SetFont(wx.Font(10,wx.SWISS,wx.NORMAL,wx.NORMAL))
        p.SetFontSizeAxis(10)
        p.SetFontSizeLegend(7)
        p.setLogScale((False,False))
        p.SetXSpec('min')
        p.SetYSpec('auto')
        self.canvas.AddPage(p, self.subchannels[channelIdx].displayName)
        p.SetEnableTitle(self.showTitle)

        p.image = self.images[channelIdx]
        p.outOfRangeColor = self.outOfRangeColor
        p.SetEnableZoom(True)
        p.SetShowScrollbars(True)
        p.Draw(self.lines[channelIdx])


    def makeLineList(self):
        """ Turn each column of data into its own line plot.
        """
        # The "line list" is really sort of a hack, just containing a single
        # line from min/min to max/max in order to make the plot's scale
        # draw correctly.
        if self.data is None:
            return
        
        start = self.source[self.indexRange[0]][-2] * self.timeScalar
        end = self.source[self.indexRange[1]][-2] * self.timeScalar
        self.lines = []
        self.ranges = []

        self_lines_append = self.lines.append
        for i in range(len(self.data)):
            d = self.data[i]
            points = ((start, d[1][0]), 
                      (end, d[1][-1]))
            name = self.subchannels[i-1].displayName
 
            self_lines_append(PlotGraphics([PolyLine(points, legend=name)],
                              title=self.subchannels[i].displayName, #title=self.GetTitle(),
                              xLabel="Time (s)", yLabel="Frequency (Hz)"))

    
    @classmethod
    def plotColorSpectrum(cls, n):
        """ Generate a 24-bit RGB color from a positive normalized float value 
            (0.0 to 1.0). 
        """
        # Because H=0 and H=1.0 have the same RGB value, reduce `n`.
        r,g,b = colorsys.hsv_to_rgb((1.0-n)*.6667,1.0,1.0)
        return int(r*255), int(g*255), int(b*255) 
#         return tuple(map(lambda x: int(x*255), 
#                          colorsys.hsv_to_rgb((1.0-n)*.6667,1.0,1.0)))

                     
    @classmethod
    def plotGrayscale(cls, n):
        """ Generate a grayscale level (as 24-bit RGB color where R==G==B) from
            a positive normalized float value (0.0 to 1.0). 
        """
        v = int(n*255)
        return v,v,v
 

    @classmethod
    def makePlots(cls, data, logarithmic=(False, False, True), 
                  colorizer=plotColorSpectrum):
        """ Create a set of spectrogram images from a set of computed data.
        
            @param data: A list of (spectrogram data, frequency, bins) for each
                channel.
            @return: A list of `wx.Image` images.
        """
        
        if logarithmic[2]:
            temp = [np.log(d[0]) if d != 0 else 0 for d in data]
        else:
            temp = [d[0] for d in data]
#         minAmp = np.amin(temp)
        minAmp = np.median(temp)
        maxAmp = np.amax(temp)

        # Create a mapped function to normalize a numpy.ndarray
        norm = np.vectorize(lambda x: max(0,((x-minAmp)/(maxAmp-minAmp))))
        imgsize = data[0][0].shape[1], data[0][0].shape[0]
        images = []
        for amps in temp:
            # TODO: This could use the progress bar (if there is one)
            buf = bytearray()
            for p in norm(amps).reshape((1,-1))[0,:]:
                buf.extend(colorizer(p))
            img = wx.EmptyImage(*imgsize)
            img.SetData(buf)
            images.append(img.Mirror(horizontally=False))
            
        return images


    def finishDraw(self, *args):
        """
        """
        try:
            super(SpectrogramView, self).finishDraw(*args)
            for i in range(len(self.subchannels)):#ch in subchIds:
                self.addPlot(i)
        except TypeError:
            # occurs if the view is dead
            pass


    def _draw(self, abortEvent=None):
        """
        """
        try:
            # self.canvas is the plot canvas
            if self.subchannels is not None:
                start, stop = self.indexRange #self.source.getRangeIndices(*self.range)
                recordingTime = self.source[-1][-2] - self.source[0][-2]
                recordingTime *= self.timeScalar
                fs = self.source.getSampleRate()
                subchIds = [c.id for c in self.subchannels]
                data = self.source.itervalues(start, stop, subchannels=subchIds, display=self.useConvertedUnits)
                self.data = self.generateData(data, rows=stop-start,
                                              cols=len(self.subchannels), fs=fs, 
                                              sliceSize=self.sliceSize,
                                              slicesPerSec=self.slicesPerSec, 
                                              recordingTime=recordingTime,
                                              abortEvent=abortEvent)

                self.images = self.makePlots(self.data, self.logarithmic, 
                                             self.colorizer)
                self.makeLineList()
            
        except wx.PyDeadObjectError:
            pass


    @classmethod
    def generateData(cls, data, rows=None, cols=1, fs=5000, sliceSize=2**16, 
                     slicesPerSec=4.0, recordingTime=None, abortEvent=None):
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
            @keyword slicesPerSec: 
            @return: A multidimensional array, with the first column the 
                frequency.
        """
        points = cls.from2diter(data, rows, cols, abortEvent=abortEvent)
        rows, cols = points.shape
#         points.resize((max(nextPow2(rows),sliceSize), cols))
         
        specgram_nfft = int(rows/(recordingTime*slicesPerSec))
         
#         print "recordingTime:",recordingTime
#         print "specgram_nfft:",specgram_nfft
        specData = []
                 
        for i in xrange(cols):
            pts = points[:,i]
            # This is basically what matplotlib.mlab.specgram does.
            # Parameters cribbed from matplotlib and the old viewer
            Pxx, freqs, bins = spec.x_spectral_helper(pts, pts, 
                NFFT=specgram_nfft, Fs=fs, detrend=spec.detrend_none, 
                window=spec.window_hanning, noverlap=specgram_nfft/2, 
                pad_to=None, sides='onesided', scale_by_freq=None,
#                 abortEvent=abortEvent
                )
            
            if Pxx is None:
                break
            
            Pxx = Pxx.real
     
            specData.append((Pxx[1:,:], freqs[1:], bins))
             
        return specData


#     @classmethod
#     def generateData(cls, data, start=0, stop=None, cols=1, timerange=None, 
#                      fs=5000, sliceSize=2**16, slicesPerSec=4.0, 
#                      recordingTime=None, **kwargs):
#         """ Compute 2D FFT from one or more channels of data.
#          
#             @note: This is the implementation from the old viewer and does not
#                 scale well to massive datasets. This *will* run of of memory; 
#                 the exact number of samples/RAM has yet to be determined.
#                  
#             @param data: An iterable collection of event values (no times!). The
#                 data can have one or more channels (e.g. accelerometer X or XYZ
#                 together). This can be an iterator, generator, or array.
#             @keyword rows: The number of rows (samples) in the set, if known.
#             @keyword cols: The number of columns (channels) in the set; a 
#                 default if the dataset does not contain multiple columns.
#             @keyword fs: Frequency of sample, i.e. the sample rate (Hz)
#             @keyword slicesPerSec: 
#             @return: A multidimensional array, with the first column the 
#                 frequency.
#         """
#         specData = [None] * cols
#         freqs = None
#         stop = len(data) if stop is None else stop
#         rows = stop - start
#         totalTime = timerange[1] - timerange[0]
#  
#         nfft = nextPow2(int((totalTime / 1000000) * slicesPerSec))
#          
#         bins = np.arange(timerange[0], timerange[1], float(totalTime)/nfft) / 1000000
#         nfft = int(rows/nfft)
#         print "start: %s \t stop: %s \t NFFT: %s len(bins): %s" % (start,stop,nfft,len(bins))
#  
#         for n,i in enumerate(xrange(start, stop, nfft)):
#             print n,i
#             if isinstance(data, np.ndarray):
#                 dataslice = data[:,i:i+nfft]
#             else:
#                 dataslice = data.itervalues(i,i+nfft)
#             fft = super(SpectrogramView, cls).generateData(dataslice, rows=rows, cols=cols, fs=fs)
#             if freqs is None:
#                 freqs = fft[:,0]
#             for c in xrange(cols):
#                 thisCol = fft[:,c+1].reshape((1,-1))
#                 if specData[c] is None:
#                     specData[c] = [thisCol, freqs, bins]
#                 else:
#                     specData[c][0] = vstack((specData[c][0], thisCol))
#  
# #         print specData
# #         print [[y.shape for y in x] for x in specData]
#         return specData
    

    #===========================================================================
    # 
    #===========================================================================

    def initMenus(self):
        super(SpectrogramView, self).initMenus()
#         self.MenuBar.FindItemById(self.ID_EXPORT_IMG).Enable(False)

        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_FREQ, checked=False, enabled=False)
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_AMP, checked=self.logarithmic[2])
        self.setMenuItem(self.viewMenu, self.ID_VIEW_SHOWLEGEND, checked=False, enabled=False)
        self.setMenuItem(self.viewMenu, self.ID_VIEW_SHOWGRID, checked=False, enabled=False)
        
        self.dataMenu.AppendSeparator()
        
        colorMenu = wx.Menu()
        self.addMenuItem(colorMenu, self.ID_COLOR_GRAY, "Grayscale", "", 
                         self.OnMenuColorize, kind=wx.ITEM_RADIO)
        self.addMenuItem(colorMenu, self.ID_COLOR_SPECTRUM, "Spectrum", "", 
                         self.OnMenuColorize, kind=wx.ITEM_RADIO)
        self.setMenuItem(colorMenu, self.colorizerId, checked=True)
        self.dataMenu.AppendMenu(-1, "Colorization", colorMenu)

    #===========================================================================
    # 
    #===========================================================================

    def redrawPlots(self):
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
        self.images = self.makePlots(self.data, self.logarithmic, self.colorizer)
        self.makeLineList()
        for i in range(self.canvas.GetPageCount()):
            p = self.canvas.GetPage(i)
            p.image = self.images[i]
            p.zoomedImage = None
            p.SetEnableTitle(self.showTitle)
            p.outOfRangeColor = self.outOfRangeColor
            p.Redraw()
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        

    #===========================================================================
    # 
    #===========================================================================

    def OnExportCsv(self, evt):
        ex = None if DEBUG else Exception
        exportChannels = []
        if len(self.subchannels) > 1:
            channelNames = [c.name for c in self.subchannels]
            dlg = wx.MultiChoiceDialog( self, 
                "Spectrogram CSV exports can contain only one channel per file."
                "\n\nThe exported filename(s) will include the channel name.",
                "Select Channels to Export", channelNames)
    
            exportChannels = None
            if (dlg.ShowModal() == wx.ID_OK):
                exportChannels = dlg.GetSelections()
            dlg.Destroy()
        else:
            exportChannels = range(len(self.subchannels))

        if not exportChannels:
            return            
            
        baseName = None
        while baseName is None:
            dlg = wx.FileDialog(self, 
                message="Export CSV(s)...", 
                wildcard="Comma Separated Values (*.csv)|*.csv", 
                style=wx.SAVE)
            
            if dlg.ShowModal() == wx.ID_OK:
                baseName = dlg.GetPath()
            dlg.Destroy()
            
            if baseName is None:
                return False
            
            filenames = []
    
            for idx in exportChannels:
                c = self.subchannels[idx]
                name, ext = os.path.splitext(baseName)
                filenames.append('%s_%s%s' % (name, sanitizeFilename(c.name), ext))
            
            existing = filter(os.path.exists, filenames)
            if existing:
                #warn
                names = '\n'.join(map(os.path.basename, existing))
                mb = wx.MessageBox('Exporting will overwrite the following '
                                   'files:\n\n%s\n\nContinue?' % names, 
                                   'Overwrite files?', parent=self,
                        style=wx.YES_NO|wx.NO_DEFAULT|wx.ICON_WARNING) 
                if mb != wx.YES:
                    baseName=None

        for num, filename in zip(exportChannels, filenames): 
            try:
                data, freqs, times  = self.data[num]
                freqs = np.reshape(hstack((np.array((-1,)),freqs)), (-1,1))
                data = hstack((freqs, vstack((np.reshape(times, (1,-1)), data))))
                np.savetxt(filename, data, fmt=self.formatter, delimiter=', ')

#                 out = open(filename, "wb")
#                 for d in data:
#                     out.write(', '.join(map(lambda x: dataFormat % x, d)))
#                     out.write('\n')
# #                 writer = csv.writer(out)
# #                 writer.writerows(data)
#                 out.close()
            except ex as err:
                what = "exporting %s as CSV %s" % (self.NAME, filename)
                self.root.handleError(err, what=what)
                return False

        return True

    def OnZoomOut(self, evt):
        self.zoomPlot(self.canvas.GetCurrentPage(), .1)

    def OnZoomIn(self, evt):
        self.zoomPlot(self.canvas.GetCurrentPage(), -.1)

    def OnMenuViewReset(self, evt):
        self.canvas.GetCurrentPage().Reset()

    def OnMenuDataLog(self, evt):
        """
        """
        self.logarithmic=(False, False, evt.IsChecked())
        self.redrawPlots()

    
    def OnMenuColorize(self, evt):
        evt_id = evt.GetId()
        self.colorizer = self.colorizers.get(evt_id, self.plotColorSpectrum)
        self.outOfRangeColor = self.outOfRangeColors.get(evt_id, (200,200,200))
        self.redrawPlots()


    def OnMenuViewTitle(self, evt):
        self.showTitle = evt.IsChecked()
        self.redrawPlots()

    def OnFilePageSetup(self, event):
        self.canvas.GetCurrentPage().PageSetup()
        
    def OnFilePrint(self, evt):
        self.canvas.GetCurrentPage().Printout()
        
    def OnFilePrintPreview(self, evt):
        self.canvas.GetCurrentPage().PrintPreview()


    def OnViewChangeTitle(self, evt):
        p = self.canvas.GetCurrentPage()
        idx = self.canvas.GetPageIndex(p)
        
        dlg = wx.TextEntryDialog(self, 'New Plot Title:', 'Change Title', 
                                 self.lines[idx].getTitle())
        
        if dlg.ShowModal() == wx.ID_OK:
            self.lines[idx].setTitle(dlg.GetValue())
            p.Redraw()

        dlg.Destroy()


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
            return self.canvas.GetCurrentPage().SaveFile(filename)
        except Exception as err:
            what = "exporting %s as an image" % self.NAME
            self.root.handleError(err, what=what)
            return False


#===============================================================================
# 
#===============================================================================

class PSDView(FFTView):
    """
    """
    NAME = TITLE_NAME = "PSD"
    FULLNAME = "PSD View"
    yLabel = "Power/Frequency"
    yUnits = "dB/Hz"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('logarithmic', (True, True))
        kwargs.setdefault('yUnits', self.yUnits)

        super(PSDView, self).__init__(*args, **kwargs)

#        if not self.useWelch:
        sourceUnits = self.subchannels[0].units[1]
        if sourceUnits:
            self.yUnits = u" (%s\u00b2/Hz)" % sourceUnits
            
        self.formatter = '%E'

    @classmethod
    def generateData(cls, data, rows=None, cols=1, fs=5000, sliceSize=2**16,
                     abortEvent=None, useWelch=False):
        """ Compute 1D FFT from one or more channels of data.
        
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
            @return: A multidimensional array, with the first column the 
                frequency.
        """
        if useWelch:
            logger.info("Calculating PSD using Welch's Method")
            points = cls.from2diter(data, rows, cols, abortEvent=abortEvent)
            rows, cols = points.shape
            NFFT = nextPow2(sliceSize)
            logger.info("PSD calculation: NFFT = %s" % NFFT)

            fftData = None
            for i in xrange(cols):
                if abortEvent is not None and abortEvent():
                    return 
                   
                tmp_fft, freqs = spec.welch(points[:,i], NFFT, fs, scale_by_freq=True)#, detrend=spec.demean)
                if fftData is None: 
                    fftData = freqs.reshape(-1,1)
                fftData = hstack((fftData, tmp_fft.reshape(-1,1)))
                   
                # Remove huge DC component from displayed data; so data of interest 
                # can be seen after auto axis fitting
                thisCol = i+1
                fftData[0,thisCol] = 0.0
                fftData[1,thisCol] = 0.0
                fftData[2,thisCol] = 0.0
              
            return fftData

        logger.info("Calculating PSD using regular FFT function")

        fftData = FFTView.generateData(data, rows=rows, cols=cols, fs=fs, sliceSize=sliceSize,
                     abortEvent=abortEvent, forPsd=True)
        if rows is None:
            if hasattr(fftData, '__len__'):
#                logger.info("PSD generateData: Using len of fftData")
                rows = len(fftData)
            else:
#                logger.info("PSD generateData: Problem! Setting sample length")
                rows = 1                        # PJS: Really this is an error...
#        else:
#            logger.info("PSD generateData: Row input for size")

        fftData[:,1:] = np.square(fftData[:,1:])*2/(fs*rows)
#        fftData[:,1:] = np.square(fftData[:,1:])/fftData[1,0]
        return fftData
        

#===============================================================================
# 
#===============================================================================

# XXX: REMOVE THIS LATER. Makes running this module run the 'main' viewer.
if __name__ == "__main__":
    import viewer
    app = viewer.ViewerApp(loadLastFile=True)
    app.MainLoop()