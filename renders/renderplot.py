'''
Created on Oct 14, 2014

@author: dstokes
'''

import time

import numpy as np; np=np

import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas

################### THE FOLLOWING CODE SHOULD BE LOOKED AT TO SEE IF WE WANT TO USE IT OR MAKE IT AN OPTION ####################
# import matplotlib.style as mplstyle
# mplstyle.use('fast')

from logger import logger
from renders.fft import FFTView, ZoomingPlot


class PlotView(FFTView, ZoomingPlot):
    """
    """
    
    NAME = "Plot"
    FULLNAME = "Rendered Plot"
    TITLE_NAME = None

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
        self.axes.set_xlabel('Time (s)')
        self.axes.set_ylabel("%s%s" % (self.yLabel, self.yUnits))

        # Sizer to contain the canvas
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 3, wx.EXPAND | wx.ALL)
        self.SetSizer(self.sizer)
        self.Fit() #########WHY IS THIS DONE TWICE#####

        self.initialize_zoom_rectangle()

        self.Fit() #########WHY IS THIS DONE TWICE#####


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
            for channel in set(c.parent for c in self.subchannels):
                subchannels = [s for s in self.subchannels if s in channel.children]
                source = channel.getSession()
                subchannelIds = [s.id for s in subchannels]
                start, stop = source.getRangeIndices(*self.range)
                data = source.arrayValues(start, stop, subchannels=subchannelIds, display=self.useConvertedUnits)
                fs = source.getSampleRate()
                data = self.generateData(data, rows=stop-start,
                                         cols=len(subchannels), fs=fs,
                                         sliceSize=self.sliceSize)

                if data is not None:
                    for i in range(data.shape[1] - 1):
                        self.axes.plot(data[:, 0], data[:, i + 1], antialiased=True, linewidth=0.5,
                                       label=subchannels[i - 1].name, color=[float(x)/255. for x in self.root.getPlotColor(subchannels[i-1])])

                if data is not None:
                    if self.data is None:
                        self.data = [data]
                    else:
                        self.data.append(data)

        if self.data is None:
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
        t = np.linspace(0, (rows - 1)/fs, rows)
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
    
    def SetGridColour(self, color):
        """
        """
        if not isinstance(color, wx.Colour):
            color = wx.Colour(color)
            
        pen = self.canvas.gridPen
        pen.SetColour(color)
        self.canvas.gridPen = pen
