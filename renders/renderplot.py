'''
Created on Oct 14, 2014

@author: dstokes
'''

import time
import threading

import numpy as np; np=np

import wx
from wx.lib.plot import PolyLine, PlotGraphics
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.patches import Rectangle

################### THE FOLLOWING CODE SHOULD BE LOOKED AT TO SEE IF WE WANT TO USE IT OR MAKE IT AN OPTION ####################
# import matplotlib.style as mplstyle
# mplstyle.use('fast')

from common import lesser
from logger import logger
from renders.fft import FFTPlotCanvas, FFTView

from ctypes import windll


class PlotView(FFTView):
    """
    """
    
    NAME = "Plot"
    FULLNAME = "Rendered Plot"
    TITLE_NAME = None
    DEBOUNCE_WAIT_TIME = windll.user32.GetDoubleClickTime() * 1e-3


    def makeTitle(self):
        """ Helper method to generate a nice-looking title.
        """

        # Smart plot naming: use parent channel name if all children plotted.
        events = [c.getSession(self.root.session.sessionId) for c in self.subchannels]
        units = [el.units[0] for el in events if el.units[0] != events[0].units[0]]
        if len(units) == 0:
            title = "%s %s" % (events[0].units[0], ', '.join([c.name for c in self.subchannels]))
        else:
            title = ", ".join([c.displayName for c in self.subchannels])

        if self.TITLE_NAME:
            return "%s: %s" % (self.NAME, title)
        else:
            return title


    def initPlot(self):
        """
        """
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_autoscale_on(True)
        self.canvas = FigureCanvas(self, -1, self.figure)

        self.axes.set_title(self.title)
        self.timer = None
        self._delay = windll.user32.GetDoubleClickTime()

        # Initialise the rectangle
        self.rect = Rectangle((0,0), 1, 1, facecolor='None', edgecolor='black', linewidth=0.5, zorder=3)
        self.xData0 = None
        self.yData0 = None
        self.xData1 = None
        self.yData1 = None
        self.x0 = None
        self.y0 = None
        self.x1 = None
        self.y1 = None
        self.axes.add_patch(self.rect)

        # Sizer to contain the canvas
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 3, wx.EXPAND | wx.ALL)
        self.SetSizer(self.sizer)
        self.Fit()

        # Connect the mouse events to their relevant callbacks
        self.canvas.mpl_connect('button_press_event', self._onPress)
        self.canvas.mpl_connect('button_release_event', self._onRelease)
        self.canvas.mpl_connect('motion_notify_event', self._onMotion)

        self.click_thread_helper = None
        self.double_clicked = False

        # Lock to stop the motion event from behaving badly when the mouse isn't pressed
        self.pressed = False

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

        logger.info("Starting %s._draw() in new thread." % self.__class__.__name__ )
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


    def _getXY(self, event):
        """Takes a mouse event and returns the XY user axis values."""
        x, y = self.PositionScreenToUser(event.GetPosition())
        return x, y

    def PositionScreenToUser(self, pntXY):
        """Converts Screen position to User Coordinates"""
        screenPos = np.array(pntXY)
        x, y = (screenPos - self._pointShift) / self._pointScale
        return x, y


    #===========================================================================
    #
    #===========================================================================

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
                    else: # Zoom fit
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
            
