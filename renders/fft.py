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
import threading

import numpy as np
from numpy.core import hstack, vstack
#from pyfftw.builders import rfft


from wx import aui
import wx; wx = wx 
import wx.lib.delayedresult as delayedresult

import matplotlib as mpl
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavigationToolbar
from matplotlib.backends.backend_wx import _load_bitmap
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

import spectrum as spec

from base import MenuMixin
from common import mapRange, nextPow2, sanitizeFilename, greater, lesser
from widgets.shared import StatusBar

from build_info import DEBUG
from logger import logger

from ctypes import windll

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



class ZoomingPlot:

    DEBOUNCE_WAIT_TIME = windll.user32.GetDoubleClickTime() * 1e-3

    def initialize_stuff(self):
        # Initialise the rectangle
        self.rect = Rectangle((0, 0), 0, 0, facecolor='None', edgecolor='black', linewidth=0.5, zorder=3)
        self.xData0 = None
        self.yData0 = None
        self.xData1 = None
        self.yData1 = None
        self.x0 = None
        self.y0 = None
        self.x1 = None
        self.y1 = None
        self.axes.add_patch(self.rect)


        # Connect the mouse events to their relevant callbacks
        self.canvas.mpl_connect('button_press_event', self._onPress)
        self.canvas.mpl_connect('button_release_event', self._onRelease)
        self.canvas.mpl_connect('motion_notify_event', self._onMotion)

        self.click_thread_helper = None
        self.double_clicked = False

        # Lock to stop the motion event from behaving badly when the mouse isn't pressed
        self.pressed = False


    def _single_click_thread_fn_helper(self, event):
        self.click_thread_helper = None

    def _onPress(self, event):
        ''' Callback to handle the mouse being clicked and held over the canvas'''

        if self.click_thread_helper is None:
            self.click_thread_helper = threading.Timer(self.DEBOUNCE_WAIT_TIME, self._single_click_thread_fn_helper, [event])
            self.click_thread_helper.start()

        if event.dblclick:
            self.click_thread_helper.cancel()
            self.double_clicked = True
            self.click_thread_helper = None

        # Check the mouse press was actually on the canvas
        if event.xdata is not None and event.ydata is not None:

            # Upon initial press of the mouse record the origin and record the mouse as pressed
            self.pressed = True
            self.rect.set_alpha(1)
            self.rect.set_linestyle('solid')
            self.xData0 = event.xdata
            self.yData0 = event.ydata
            self.x0 = event.x
            self.y0 = event.y


    def _onRelease(self, event):
        ''' Callback to handle the mouse being released over the canvas '''

        # Check that the mouse was actually pressed on the canvas to begin with and this isn't a rouge mouse
        # release event that started somewhere else
        if self.pressed:

            # mark unpressed and set rectangle to transparent
            self.pressed = False
            self.rect.set_alpha(0)

            # update event data if available
            if event.xdata is not None and event.ydata is not None:
                self.xData1 = event.xdata
                self.yData1 = event.ydata
                self.x1 = event.x
                self.y1 = event.y
            else:
                return # If something is going wrong, this might be something to look at

            if self.x0 > self.x1:
                self.x0, self.x1 = self.x1, self.x0
                self.xData0, self.xData1 = self.xData1, self.xData0
            
            if self.y0 > self.y1:
                self.y0, self.y1 = self.y1, self.y0
                self.yData0, self.yData1 = self.yData1, self.yData0

            hasXMoved = abs(self.x1 - self.x0) > 3
            hasYMoved = abs(self.y1 - self.y0) > 3

            # release left click
            if event.button == wx.MOUSE_BTN_LEFT:
                # mouse did not move
                if not hasXMoved and not hasYMoved:
                    if not self.double_clicked: # zoom 20% onto where the mouse is at (x1, y1)
                        xl = self.axes.get_xlim()
                        leftMargin = self.xData1 - xl[0]
                        rightMargin = xl[1] - self.xData1
                        self.axes.set_xlim(self.xData1 - 0.8*leftMargin, self.xData1 + 0.8*rightMargin)

                        yl = self.axes.get_ylim()
                        bottomMargin = self.yData1 - yl[0]
                        topMargin = yl[1] - self.yData1
                        self.axes.set_ylim(self.yData1 - 0.8*bottomMargin, self.yData1 + 0.8*topMargin)
                    else:  # Zoom fit
                        self.OnMenuViewReset(event)

                # mouse moved only horizontally
                elif hasXMoved and not hasYMoved:
                    # keep vertical position, move horizontal
                    self.axes.set_xlim(self.xData0, self.xData1)

                # mouse moved only vertically
                elif not hasXMoved and hasYMoved:
                    # keep horizontal position, move vertical
                    self.axes.set_ylim(self.yData0, self.yData1)

                # mouse moved vertically and horizontally
                else:
                    # zoom both vertical and horizontal
                    self.axes.set_xlim(self.xData0, self.xData1)
                    self.axes.set_ylim(self.yData0, self.yData1)
            elif event.button == wx.MOUSE_BTN_RIGHT:

                # mouse did not move
                if not hasXMoved and not hasYMoved:
                    # zoom 20% away from where the mouse is at (x1, y1)
                    xl = self.axes.get_xlim()
                    leftMargin = self.xData1 - xl[0]
                    rightMargin = xl[1] - self.xData1

                    yl = self.axes.get_ylim()
                    bottomMargin = self.yData1 - yl[0]
                    topMargin = yl[1] - self.yData1

                    self.axes.set_xlim(self.xData1 - 1.2*leftMargin, self.xData1 + 1.2*rightMargin)
                    self.axes.set_ylim(self.yData1 - 1.2*bottomMargin, self.yData1 + 1.2*topMargin)

                # mouse moved only horizontally
                elif hasXMoved and not hasYMoved:
                    # keep vertical position, move horizontal
                    xl = self.axes.get_xlim()
                    leftMargin = min(self.xData0, self.xData1) - xl[0]
                    rightMargin = xl[1] - max(self.xData0, self.xData1)

                    self.axes.set_xlim(xl[0] - 1.2*leftMargin, xl[1] + 1.2*rightMargin)

                # mouse moved only vertically
                elif not hasXMoved and hasYMoved:
                    # keep horizontal position, move vertical
                    yl = self.axes.get_ylim()
                    bottomMargin = min(self.yData0, self.yData1) - yl[0]
                    topMargin = yl[1] - max(self.yData0, self.yData1)

                    self.axes.set_ylim(yl[0] - 1.2*bottomMargin, yl[1] + 1.2*topMargin)

                # mouse moved vertically and horizontally
                else:
                    # zoom both vertical and horizontal
                    xl = self.axes.get_xlim()
                    leftMargin = min(self.xData0, self.xData1) - xl[0]
                    rightMargin = xl[1] - max(self.xData0, self.xData1)

                    yl = self.axes.get_ylim()
                    bottomMargin = min(self.yData0, self.yData1) - yl[0]
                    topMargin = yl[1] - max(self.yData0, self.yData1)

                    self.axes.set_xlim(xl[0] - 1.2*leftMargin, xl[1] + 1.2*rightMargin)
                    self.axes.set_ylim(yl[0] - 1.2*bottomMargin, yl[1] + 1.2*topMargin)

            elif event.button == wx.MOUSE_BTN_MIDDLE:
                pass

            self.canvas.draw()
            self.double_clicked = False


    def _onMotion(self, event):
        '''Callback to handle the motion event created by the mouse moving over the canvas'''

        # If the mouse has been pressed draw an updated rectangle when the mouse is moved so
        # the user can see what the current selection is
        if self.pressed:

            # Check the mouse was released on the canvas, and if it wasn't then just leave the width and
            # height as the last values set by the motion event
            if event.xdata is not None and event.ydata is not None:
                self.xData1 = event.xdata
                self.yData1 = event.ydata

            # Set the width and height and draw the rectangle
            self.rect.set_width(self.xData1 - self.xData0)
            self.rect.set_height(self.yData1 - self.yData0)
            self.rect.set_xy((self.xData0, self.yData0))
            self.canvas.draw()

    def zoomPlot(self, plot, amount):
        if plot is None:
            plot = self

        if amount == 0:
            bbox = self.axes.dataLim
            plot.axes.set_xlim(bbox.xmin, bbox.xmax)
            plot.axes.set_ylim(bbox.ymin, bbox.ymax)
            return

        old_x = plot.axes.get_xbound()
        old_y = plot.axes.get_ybound()
        cur_xview_dist = old_x[1] - old_x[0]
        cur_yview_dist = old_y[1] - old_y[0]

        if amount > 0:
            dist_x_zoom = cur_xview_dist * (1 / (1 - amount) - 1)
            dist_y_zoom = cur_yview_dist * (1 / (1 - amount) - 1)
        else:
            dist_x_zoom = cur_xview_dist * amount
            dist_y_zoom = cur_yview_dist * amount

        new_x_lims = (old_x[0] - dist_x_zoom / 2, old_x[1] + dist_x_zoom / 2)
        new_y_lims = (old_y[0] - dist_y_zoom / 2, old_y[1] + dist_y_zoom / 2)
        plot.axes.set_xlim(*new_x_lims)
        plot.axes.set_ylim(*new_y_lims)

    def OnMenuViewReset(self, evt, add_border=True):
        bbox = self.axes.dataLim
        if add_border:
            x_shift = (bbox.xmax - bbox.xmin) / 100
            y_shift = (bbox.ymax - bbox.ymin) / 100
        else:
            x_shift, y_shift = 0, 0

        self.axes.set_xlim(bbox.xmin - x_shift, bbox.xmax + x_shift)
        self.axes.set_ylim(bbox.ymin - y_shift, bbox.ymax + y_shift)
        self.canvas.draw()

#===============================================================================
# 
#===============================================================================

class FFTView(wx.Frame, MenuMixin, ZoomingPlot):
    """
    """
    NAME = TITLE_NAME = "FFT"
    FULLNAME = "FFT View"
    xLabel = "Frequency"
    yLabel = "Amplitude"
    
    ID_EXPORT_CSV = wx.NewIdRef()
    ID_EXPORT_IMG = wx.NewIdRef()
    ID_DATA_LOG_AMP = wx.NewIdRef()
    ID_DATA_LOG_FREQ = wx.NewIdRef()
    ID_VIEW_SHOWTITLE = wx.NewIdRef()
    ID_VIEW_SHOWLEGEND = wx.NewIdRef()
    ID_VIEW_SHOWGRID = wx.NewIdRef()
    ID_VIEW_ANTIALIAS = wx.NewIdRef()
    ID_VIEW_CHANGETITLE = wx.NewIdRef()

    IMAGE_FORMATS = "Joint Photographic Experts Group (*.jpeg;*.jpg)|*.jpg;*.jpeg|" \
                    "Portable Network Graphics (*.png)|(*.png)|" \
                    "Encapsulated Postscript (*.eps)|*.eps|" \
                    "PGF code for LaTeX (*.pgf)|*.pgf|" \
                    "Portable Document Format (*.pdf)|*.pdf|" \
                    "Postscript (*.ps)|*.ps|" \
                    "Raw RGBA bitmap (*.raw;*.rgba)|*.raw;*.rgba|" \
                    "Scalable Vector Graphics (*.svg;*.svgz)|*.svg;*.svgz|" \
                    "Tagged Image File Format (*.tif;*.tiff)|*.tif;*.tiff"


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
        self.indexRange = kwargs.pop('start', 0), kwargs.pop('stop', len(self.source) if self.source else None)
        self.numRows = kwargs.pop('numRows')
        self.noBivariates = kwargs.pop('noBivariates', False)
        self.useWelch = kwargs.pop('useWelch', False)
        if self.useWelch:
            self.NAME = self.TITLE_NAME = "Windowed PSD"


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
        self.title = kwargs.get('title', '')
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

        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_autoscale_on(True)
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 1, wx.TOP | wx.LEFT | wx.EXPAND)

        self.axes.set_title(self.title)

        self.initialize_stuff()

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
            self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        except RuntimeError:
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
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROWWAIT))
        t = delayedresult.startWorker(self.finishDraw, self._draw, daemon=True)
        t.setName("%sThread" % self.NAME)
        

    def _draw(self):
        """
        """
        if FOREGROUND:
            logger.info("Starting %s._draw() in foreground process." % self.__class__.__name__)
        else:
            logger.info("Starting %s._draw() in new thread." % self.__class__.__name__)
        drawStart = time.time()

        self.lines = None
        if self.subchannels is not None:
            subchannelIds = [c.id for c in self.subchannels]
            start, stop = self.source.getRangeIndices(*self.range)
            data = self.source.arrayValues(start,stop,subchannels=subchannelIds,display=self.useConvertedUnits)
            # BUG: Calculation of actual sample rate is wrong. Investigate.
#             fs = (channel[stop][0]-channel[start][0]) / ((stop-start) + 0.0)
            fs = self.source.getSampleRate()
            self.data = self.generateData(data, rows=stop-start,
                                          cols=len(self.subchannels), fs=fs,
                                          sliceSize=self.sliceSize, useWelch=self.useWelch)

        if self.data is not None:
            # self.makeLineList()
            for i in range(1, self.data.shape[1]):
                self.axes.plot(self.data[:, 0], self.data[:, i], antialiased=True, linewidth=0.5,
                               label=self.subchannels[i-1].name, color=[float(x)/255. for x in self.root.getPlotColor(self.subchannels[i-1])])

            if self.logarithmic[0]:
                self.axes.set_xscale('log')
            if self.logarithmic[1]:
                self.axes.set_yscale('log')

            bbox = self.axes.dataLim
            x_shift = (bbox.xmax - bbox.xmin) / 100
            y_shift = (bbox.ymax - bbox.ymin) / 100
            self.axes.set_xlim(bbox.xmin - x_shift, bbox.xmax + x_shift)
            self.axes.set_ylim(bbox.ymin - y_shift, bbox.ymax + y_shift)

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
    
    def initMenus(self):
        """ Install and set up the main menu.
        """
        self.menubar = wx.MenuBar()
        
        fileMenu = self.fileMenu = wx.Menu()
        self.addMenuItem(fileMenu, self.ID_EXPORT_CSV, "&Export CSV...", "", 
                         self.OnExportCsv)
        self.addMenuItem(fileMenu, self.ID_EXPORT_IMG, "&Save Image...\tCtrl+S", "", 
                         self.OnExportImage, True)
        # fileMenu.AppendSeparator()
        # self.addMenuItem(fileMenu, wx.ID_PRINT, "&Print...\tCtrl+P", "",
        #                  self.OnFilePrint)
        # self.addMenuItem(fileMenu, wx.ID_PREVIEW, "Print Preview...", "",
        #                  self.OnFilePrintPreview)
        # self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, "Print Setup...", "",
        #                  self.OnFilePageSetup)
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
            @keyword forPsd: Return just PSD, without 2/rows gain
            @return: A multidimensional array, with the first column the
                frequency.
        """
        points = data.T
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
            # thisCol = i+1
            # fftData[0,thisCol] = 0.0
            # fftData[1,thisCol] = 0.0
            # fftData[2,thisCol] = 0.0

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
            wildcard="Comma Separated Values (*.csv)|*.csv",
            style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
        
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
        
    
    def OnExportImage(self, event, figure=None):
        if figure is None:
            figure = self.figure

        ex = None if DEBUG else Exception
        filename = None
        dlg = wx.FileDialog(self, 
            message="Export Image...", 
            wildcard=self.IMAGE_FORMATS, 
            style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
        
        if filename is None:
            return False
        
        try:
            file_extension = filename.split('.')[-1]

            return figure.savefig(filename, format=file_extension)
        except ex as err:
            what = "exporting %s as an image" % self.NAME
            self.root.handleError(err, what=what)
            return False

    # def zoomPlot(self, plot, amount):
    #     bbox = self.axes.dataLim
    #     fullX = (bbox.xmin, bbox.xmax)
    #     fullY = (bbox.ymin, bbox.ymax)
    #     oldX = self.axes.get_xbound()
    #     oldY = self.axes.get_ybound()
    #     newX = (greater(fullX[0], (1.0-amount) * oldX[0]), lesser(fullX[1], (1.0+amount) * oldX[1]))
    #     newY = (greater(fullY[0], (1.0-amount) * oldY[0]), lesser(fullY[1], (1.0+amount) * oldY[1]))
    #
    #     if newX[0] > newX[1]:
    #         newX = tuple(oldX)
    #     if newY[0] > newY[1]:
    #         newY = tuple(oldY)
    #     self.axes.set_xlim(newX[0], newX[1])
    #     self.axes.set_ylim(newY[0], newY[1])

    def OnZoomOut(self, evt):
        self.zoomPlot(None, .1)
        self.canvas.draw()
        
    def OnZoomIn(self, evt):
        self.zoomPlot(None, -.1)
        self.canvas.draw()

    def OnMenuDataLog(self, evt):
        """
        """
        if self.logFreq.IsChecked():
            self.axes.set_xscale('log')
        else:
            self.axes.set_xscale('linear')

        if self.logAmp.IsChecked():
            self.axes.set_yscale('log')
        else:
            self.axes.set_yscale('linear')
        # self.zoomPlot(self.canvas, 0.0)
        # self.canvas.draw()
        self.zoomPlot(None, 0.0)
        self.canvas.draw()
        # self.SetCursor(wx.Cursor(wx.CURSOR_WAIT))
        # self.logarithmic = (self.logFreq.IsChecked(), self.logAmp.IsChecked())
        # self.canvas.setLogScale(self.logarithmic)
        # self.canvas.Redraw()
        # self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))

    def OnMenuViewLegend(self, evt):
        if evt.IsChecked():
            self.axes.legend()
        else:
            self.axes.get_legend().remove()
        self.canvas.draw()
        # self.showLegend = evt.IsChecked()
        # self.canvas.SetEnableLegend(self.showLegend)
        # self.canvas.draw()
    
    def OnMenuViewTitle(self, evt):
        if evt.IsChecked():
            self.axes.set_title(self.title)
        else:
            self.axes.set_title('')
        self.canvas.draw()
        # self.showTitle = evt.IsChecked()
        # self.canvas.SetEnableTitle(self.showTitle)
        # self.canvas.Redraw()

    def OnMenuViewGrid(self, evt):
        self.axes.grid(evt.IsChecked())
        self.canvas.draw()
        # self.SetCursor(wx.Cursor(wx.CURSOR_ARROWWAIT))
        # self.showGrid = evt.IsChecked()
        # self.canvas.SetEnableGrid(self.showGrid)
        # self.root.app.setPref('fft.showGrid', self.showGrid)
        # self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
#         self.canvas.Redraw()

    def OnViewChangeTitle(self, evt):
        dlg = wx.TextEntryDialog(self, 'New Plot Title:', 'Change Title', self.axes.get_title())

        if dlg.ShowModal() == wx.ID_OK:
            self.axes.set_title(dlg.GetValue())
            self.canvas.draw()

        dlg.Destroy()

    def OnMenuFileClose(self, evt=None):
        self.Close()

    def OnClose(self, evt):
        self.abortEvent.set()
        evt.Skip()

#===============================================================================
# 
#===============================================================================

class SpectrogramPlot(wx.Panel, ZoomingPlot):
    def __init__(self, parent, name="", dpi=None, id=-1, **kwargs):
        wx.Panel.__init__(self, parent, id=id, **kwargs)

        self.parent = parent

        self.figure = mpl.figure.Figure(dpi=dpi, figsize=(2, 2))

        self.axes = self.figure.add_subplot(111)

        self.title = "%s Spectrogram"%name

        self.axes.set_title(self.title)
        self.axes.set_xlabel("Time (s)")
        self.axes.set_ylabel("Frequency (Hz)")

        self.figure.add_axes(self.axes)

        self.canvas = FigureCanvas(self, -1, self.figure)

        self.image = kwargs.pop('image', None)
        # self.outOfRangeColor = kwargs.pop('outOfRangeColor', (200, 200, 200))
        # self.zoomedImage = None
        # self.lastZoom = None

        self.enableTitle = True

        self.cmap = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, wx.EXPAND)

        self.SetSizer(sizer)

    def OnMenuViewReset(self, evt):
        super(SpectrogramPlot, self).OnMenuViewReset(evt, add_border=False)

    def Redraw(self):
        title_to_set = self.title if self.enableTitle else ""

        self.axes.set_title(title_to_set)

        if self.cmap is not None:
            self.image.set_cmap(self.cmap)

        self.canvas.draw()


class SpectrogramView(FFTView):
    """
    """
    NAME = TITLE_NAME = "Spectrogram"
    FULLNAME = "Spectrogram View"
    xLabel = "Time"
    yLabel = "Amplitude"
    
    ID_COLOR_SPECTRUM = wx.NewIdRef()
    ID_COLOR_GRAY = wx.NewIdRef()
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.cmaps = {self.ID_COLOR_GRAY: 'gray',
                      self.ID_COLOR_SPECTRUM: 'viridis'}

        # 'Out of range' colors: The background color if the plot is scrolled
        # or zoomed out beyond the bounds of the image. The color is one that
        # is identifiable as not part of the spectrogram rendering.
        # self.outOfRangeColors = {self.ID_COLOR_GRAY: (200, 200, 255),
        #                          self.ID_COLOR_SPECTRUM: (200, 200, 200)}
        
        self.slicesPerSec = float(kwargs.pop('slicesPerSec', 4.0))
        self.colorizerId = kwargs.pop('colorizer', self.ID_COLOR_SPECTRUM)
        self.cmap = self.cmaps.get(self.colorizerId, 'viridis') ########PRETTY SURE I CAN REMOVE THIS ENTIRELY##############
        # self.outOfRangeColor = self.outOfRangeColors.get(self.colorizerId, (200, 200, 200))
        
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
        name = self.subchannels[channelIdx].displayName

        p = SpectrogramPlot(self, name)

        p.SetFont(wx.Font(10, wx.SWISS, wx.NORMAL, wx.NORMAL))
        p.fontSizeAxis = 10
        p.fontSizeLegend = 7
        p.logScale = (False, False)
        p.xSpec = 'min'
        p.ySpec = 'min'
        self.canvas.AddPage(p, name)
        p.enableTitle = self.showTitle

        start, stop = self.indexRange
        fs = self.source.getSampleRate()
        subchIds = [c.id for j, c in enumerate(self.subchannels) if j == channelIdx][0] ########HAVE CONNOR DOUBLE CHECK THIS############

        data = self.source.itervalues(start, stop, subchannels=subchIds, display=self.useConvertedUnits)

        #######################THE CODE BETWEEN THESE HASHES WAS TAKEN FROM OTHER IMPLEMENTATIONS AND IS NOT ENTIRELY UNDERSTOOD######################

        slicesPerSec = 4.0 ##DOUBLE CHECK THIS IS OKAY

        recordingTime = self.source[-1][0] - self.source[0][0]
        recordingTime *= self.timeScalar

        rows = stop - start

        points = self.from2diter(data, rows, 1, abortEvent=None)

        rows, cols = points.shape

        specgram_nfft = int(rows / (recordingTime * slicesPerSec))

        #######################THE CODE BETWEEN THESE HASHES WAS TAKEN FROM OTHER IMPLEMENTATIONS AND IS NOT ENTIRELY UNDERSTOOD######################

        axes_image = p.axes.specgram(
            points[:, 0],
            Fs=fs,
            sides="onesided",
            pad_to=None,
            NFFT=specgram_nfft,
            noverlap=specgram_nfft / 2,
            scale_by_freq=None,
            cmap=self.cmap,
        )[-1]

        p.cmap = self.cmap

        p.canvas.draw()
        p.initialize_stuff()

        p.image = axes_image
        # p.outOfRangeColor = self.outOfRangeColor
        p.enableZoom = True
        p.showScrollbars = True
    
#     @classmethod
#     def plotColorSpectrum(cls, n):
#         """ Generate a 24-bit RGB color from a positive normalized float value
#             (0.0 to 1.0).
#         """
#         # Because H=0 and H=1.0 have the same RGB value, reduce `n`.
#         print("ALALKJFLSKDJFJSDLKFJLSDKFLSDJLKSJDLKFJSLDKFJLKSDJF")
#         r,g,b = colorsys.hsv_to_rgb((1.0-n)*.6667,1.0,1.0)
#         return int(r*255), int(g*255), int(b*255)
# #         return tuple(map(lambda x: int(x*255),
# #                          colorsys.hsv_to_rgb((1.0-n)*.6667,1.0,1.0)))
#
#     @classmethod
#     def plotGrayscale(cls, n):
#         """ Generate a grayscale level (as 24-bit RGB color where R==G==B) from
#             a positive normalized float value (0.0 to 1.0).
#         """
#         v = int(n*255)
#         print("ALALKJFLSKDJFJSDLKFJLSDKFLSDJLKSJDLKFJSLDKFJLKSDJF")
#         return v,v,v
 

#     @classmethod
#     def makePlots(cls, data, logarithmic=(False, False, True),
#                   colorizer=plotColorSpectrum):
#         """ Create a set of spectrogram images from a set of computed data.
#
#             @param data: A list of (spectrogram data, frequency, bins) for each
#                 channel.
#             @return: A list of `wx.Image` images.
#         """
#
#         if logarithmic[2]:
#             temp = [np.log(d[0]) if d != 0 else 0 for d in data]
#         else:
#             temp = [d[0] for d in data]
# #         minAmp = np.amin(temp)
#         minAmp = np.median(temp)
#         maxAmp = np.amax(temp)
#
#         # Create a mapped function to normalize a numpy.ndarray
#         norm = np.vectorize(lambda x: max(0,((x-minAmp)/(maxAmp-minAmp))))
#         imgsize = data[0][0].shape[1], data[0][0].shape[0]
#         images = []
#         for amps in temp:
#             # TODO: This could use the progress bar (if there is one)
#             buf = bytearray()
#             for p in norm(amps).reshape((1,-1))[0,:]:
#                 buf.extend(colorizer(p))
#             img = wx.Image(*imgsize)
#             img.SetData(buf)
#             images.append(img.Mirror(horizontally=False))
#
#         return images


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
                recordingTime = self.source[-1][0] - self.source[0][0]
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
            
        except RuntimeError:
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
        self.dataMenu.Append(-1, "Colorization", colorMenu)

    #===========================================================================
    # 
    #===========================================================================

    def redrawPlots(self):
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROWWAIT))
        for i in range(self.canvas.GetPageCount()):
            p = self.canvas.GetPage(i)
            p.cmap = self.cmap
            p.zoomedImage = None  # Not sure if this is being used anymore
            p.enableTitle = self.showTitle
            # p.outOfRangeColor = self.outOfRangeColor # Not sure if this is being used anymore
            p.Redraw()
        self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        

    #===========================================================================
    # 
    #===========================================================================

    def OnExportCsv(self, evt):
        ex = None if DEBUG else Exception

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
                style=wx.FD_SAVE)
            
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

    # def zoomPlot(self, plot, amount):
    #     old_x = plot.axes.get_xbound()
    #     old_y = plot.axes.get_ybound()
    #     cur_xview_dist = old_x[1] - old_x[0]
    #     cur_yview_dist = old_y[1] - old_y[0]
    #
    #     if amount > 0:
    #         dist_x_zoom = cur_xview_dist * (1 / (1 - amount) - 1)
    #         dist_y_zoom = cur_yview_dist * (1 / (1 - amount) - 1)
    #     else:
    #         dist_x_zoom = cur_xview_dist * amount
    #         dist_y_zoom = cur_yview_dist * amount
    #
    #     new_x_lims = (old_x[0] - dist_x_zoom / 2, old_x[1] + dist_x_zoom / 2)
    #     new_y_lims = (old_y[0] - dist_y_zoom / 2, old_y[1] + dist_y_zoom / 2)
    #     plot.axes.set_xlim(*new_x_lims)
    #     plot.axes.set_ylim(*new_y_lims)

    def OnZoomOut(self, evt):
        cur_page = self.canvas.GetCurrentPage()
        self.zoomPlot(cur_page, .1)
        cur_page.Redraw()

    def OnZoomIn(self, evt):
        cur_page = self.canvas.GetCurrentPage()
        self.zoomPlot(cur_page, -.1)
        cur_page.Redraw()

    def OnMenuViewReset(self, evt):
        self.canvas.GetCurrentPage().OnMenuViewReset(evt)

    def OnMenuDataLog(self, evt):
        """
        """
        self.logarithmic = (False, False, evt.IsChecked())
        self.redrawPlots()

    
    def OnMenuColorize(self, evt):
        evt_id = evt.GetId()

        # self.outOfRangeColor = self.outOfRangeColors.get(evt_id, (200, 200, 200))  # Pretty sure this can be removed

        self.cmap = self.cmaps.get(evt_id, 'viridis')

        self.redrawPlots()


    def OnMenuViewTitle(self, evt):
        self.showTitle = evt.IsChecked()
        self.redrawPlots()

    def OnViewChangeTitle(self, evt):
        p = self.canvas.GetCurrentPage()
        idx = self.canvas.GetPageIndex(p)
        
        dlg = wx.TextEntryDialog(self, 'New Plot Title:', 'Change Title', p.axes.get_title())

        if dlg.ShowModal() == wx.ID_OK:
            p.title = dlg.GetValue()
            p.Redraw()

        dlg.Destroy()

    def OnExportImage(self, event):
        super(SpectrogramView, self).OnExportImage(event, figure=self.canvas.GetCurrentPage().figure)

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



class MyNavigationToolbar(NavigationToolbar):
    """
    Extend the default wx toolbar with your own event handlers
    """
    ON_CUSTOM = wx.NewId()

    def __init__(self, canvas, cankill):
        NavigationToolbar.__init__(self, canvas)

        # for simplicity I'm going to reuse a bitmap from wx, you'll
        # probably want to add your own.
        

#===============================================================================
# 
#===============================================================================

# XXX: REMOVE THIS LATER. Makes running this module run the 'main' viewer.
if __name__ == "__main__":
    import viewer
    app = viewer.ViewerApp(loadLastFile=True)
    app.MainLoop()
