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
import csv
import os.path
import sys
import time

# import Image

import numpy as np
from numpy.core import hstack

import wx.lib.plot as P
from wx import aui
import wx; wx = wx 

import spectrum as spec

from base import MenuMixin
from common import mapRange, StatusBar, nextPow2, sanitizeFilename
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
    ID_DATA_LOG_AMP = wx.NewId()
    ID_DATA_LOG_FREQ = wx.NewId()
    ID_VIEW_SHOWTITLE = wx.NewId()
    ID_VIEW_SHOWLEGEND = wx.NewId()
    
    IMAGE_FORMATS = "Windows Bitmap (*.bmp)|*.bmp|" \
                     "JPEG (*.jpg)|*.jpg|" \
                     "Portable Network Graphics (*.png)|*.png" 
    
    def __init__(self, *args, **kwargs):
        """ FFT view main panel. Takes standard wx.Window arguments plus:
        
            @keyword root: The parent viewer window
            @keyword source: 
            @keyword subchannels: A list of subchannels
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
        self.logarithmic = kwargs.pop('logarithmic', (False, False))
        
        if self.source is None and self.subchannels is not None:
            self.source = self.subchannels[0].parent.getSession(
                                                    self.root.session.sessionId)
        
        super(FFTView, self).__init__(*args, **kwargs)
        
        self.showTitle = self.root.app.getPref('fft.showTitle', True)
        self.showLegend = self.root.app.getPref('fft.showLegend', True)
        self.timeScalar = getattr(self.root, "timeScalar", 1.0/(6**10))
        self.statusBar = StatusBar(self)
        self.statusBar.stopProgress()
        self.SetStatusBar(self.statusBar)
        
        self.initMenus()
        self.initPlot()
        
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
        self.Show(True)
        self.Update()

        # XXX: TESTING
#         drawStart = time.time()
#         self.source.parent.raw=True
#         self.source.removeMean = False
        
        self.draw()

        # XXX: TESTING
#         print "Elapsed time: %s" % (time.time() - drawStart)


    def initPlot(self):
        """
        """
        self.canvas = P.PlotCanvas(self)
        self.canvas.SetEnableAntiAliasing(True)
        self.canvas.SetFont(wx.Font(10,wx.SWISS,wx.NORMAL,wx.NORMAL))
        self.canvas.SetFontSizeAxis(10)
        self.canvas.SetFontSizeLegend(7)
        self.canvas.setLogScale(self.logarithmic)
        self.canvas.SetXSpec('min')
        self.canvas.SetYSpec('auto')
        self.canvas.SetEnableLegend(self.showLegend)
        self.canvas.SetEnableTitle(self.showTitle)


    def draw(self):
        """
        """
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
        """ Install and set up the main menu.
        """
#         helpText = "%s Help" % self.FULLNAME
        
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

        self.dataMenu = wx.Menu()
        self.logAmp = self.addMenuItem(self.dataMenu, self.ID_DATA_LOG_AMP, 
                         "Amplitude: Logarithmic Scale", "",
                         self.OnMenuDataLog, kind=wx.ITEM_CHECK)
        self.logFreq = self.addMenuItem(self.dataMenu, self.ID_DATA_LOG_FREQ, 
                         "Frequency: Logarithmic Scale", "",
                         self.OnMenuDataLog, kind=wx.ITEM_CHECK)
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_FREQ, checked=self.logarithmic[0])
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_AMP, checked=self.logarithmic[1])
        self.menubar.Append(self.dataMenu, "Data")

        self.addMenuItem(self.dataMenu, self.ID_VIEW_SHOWLEGEND, "Show Legend", "", self.OnMenuViewLegend, kind=wx.ITEM_CHECK)
        self.addMenuItem(self.dataMenu, self.ID_VIEW_SHOWTITLE, "Show Title", "", self.OnMenuViewTitle, kind=wx.ITEM_CHECK)
        self.setMenuItem(self.dataMenu, self.ID_VIEW_SHOWLEGEND, checked=self.showLegend)
        self.setMenuItem(self.dataMenu, self.ID_VIEW_SHOWTITLE, checked=self.showTitle)
        
        helpMenu = wx.Menu()
        self.addMenuItem(helpMenu, wx.ID_ABOUT, 
            "About %s %s..." % (self.root.app.GetAppDisplayName(), self.root.app.versionString), "", 
             self.root.OnHelpAboutMenu)
        self.menubar.Append(helpMenu, "Help")
        
        self.SetMenuBar(self.menubar)
    
    
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

            lines.append(P.PolyLine(points, legend=name, 
                        colour=self.root.getPlotColor(self.subchannels[i-1])))
            
        self.lines = P.PlotGraphics(lines, title=self.GetTitle(), 
                                    xLabel="Frequency", yLabel="Amplitude")
        
    
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


    #===========================================================================
    # Event Handlers
    #===========================================================================

    def OnExportCsv(self, evt):
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
            out = open(filename, "wb")
            writer = csv.writer(out)
            writer.writerows(self.data)
            out.close()
            return True
        except Exception as err:
            what = "exporting %s as CSV" % self.NAME
            self.root.handleError(err, what=what)
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
            self.root.handleError(err, what=what)
            return False
    

    def OnMenuDataLog(self, evt):
        """
        """
        self.logarithmic = (self.logFreq.IsChecked(), self.logAmp.IsChecked())
#         self.canvas.setLogScale((False, evt.IsChecked()))
        self.canvas.setLogScale(self.logarithmic)
        self.canvas.Redraw()
        
    def OnMenuViewLegend(self, evt):
        self.showLegend = evt.IsChecked()
        self.canvas.SetEnableLegend(self.showLegend)
        self.canvas.Redraw()
    
    def OnMenuViewTitle(self, evt):
        self.showTitle = evt.IsChecked()
        self.canvas.SetEnableTitle(self.showTitle)
        self.canvas.Redraw()

    def OnClose(self, evt):
        self.Close()
    

#===============================================================================
# 
#===============================================================================

class SpectrogramPlot(P.PlotCanvas):
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
        
        if dc == None:
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

        # sizes axis to axis type, create lower left and upper right corners of plot
        if xAxis == None or yAxis == None:
            # One or both axis not specified in Draw
            p1, p2 = graphics.boundingBox()     # min, max points of graphics
            if xAxis == None:
                xAxis = self._axisInterval(self._xSpec, p1[0], p2[0]) # in user units
            if yAxis == None:
                yAxis = self._axisInterval(self._ySpec, p1[1], p2[1])
            # Adjust bounding box for axis spec
            p1[0],p1[1] = xAxis[0], yAxis[0]     # lower left corner user scale (xmin,ymin)
            p2[0],p2[1] = xAxis[1], yAxis[1]     # upper right corner user scale (xmax,ymax)
        else:
            # Both axis specified in Draw
            p1= np.array([xAxis[0], yAxis[0]])    # lower left corner user scale (xmin,ymin)
            p2= np.array([xAxis[1], yAxis[1]])     # upper right corner user scale (xmax,ymax)

        self.last_draw = (graphics, np.array(xAxis), np.array(yAxis))       # saves most recient values

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
                x_range = self.GetXMaxRange()
                y_range = self.GetYMaxRange()
                img_w, img_h = self.image.GetSize()
                
                
                x1 = mapRange(p1[0], x_range[0], x_range[1], 0, img_w)
                x2 = mapRange(p2[0], x_range[0], x_range[1], 0, img_w)
                
                y1 = mapRange(p1[1], y_range[0], y_range[1], 0, img_h)
                y2 = mapRange(p2[1], y_range[0], y_range[1], 0, img_h)
                
                print "xAxis:", xAxis
                print "yAxis:", yAxis
                print "p1:",p1
                print "p2:",p2
                print "x_range:", x_range
                print "y_range:", y_range
                print "img size:", self.image.GetSize()
                print "rect:", x1, y1, x2, y2
                print "*"*30
#                 print "rect:", x1, y1, crop_w, crop_h
#                 img = self.image.GetSubImage(wx.Rect(x1, img_h-y2, abs(x2-x1), abs(y2-y1)))
                img = self.image.Size(wx.Size(abs(x2-x1), abs(y2-y1)), wx.Point(-x1, -(img_h-y2)), 255, 255, 255)
#                 img = self.image.GetSubImage(wx.Rect(x1, y1, crop_w, crop_h))
            else:
                img = self.image
            img = img.Scale(rectWidth, rectHeight).ConvertToBitmap()
            dc.DrawBitmap(img, ptx, pty)
        
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
        


class SpectrogramView(FFTView):
    """
    """
    NAME = "Spectrogram"
    FULLNAME = "Spectrogram View"
    
    ID_COLOR_SPECTRUM = wx.NewId()
    ID_COLOR_GRAY = wx.NewId()
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.slicesPerSec = float(kwargs.pop('slicesPerSec', 4.0))
        self.images = None
        self.colorizers = {self.ID_COLOR_GRAY: self.plotGrayscale,
                           self.ID_COLOR_SPECTRUM: self.plotColorSpectrum}
        self.colorizerId = kwargs.pop('colorizer', self.ID_COLOR_SPECTRUM)
        self.colorizer = self.colorizers.get(self.colorizerId, self.plotColorSpectrum)
        
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
        p.SetEnableAntiAliasing(True)
        p.SetFont(wx.Font(10,wx.SWISS,wx.NORMAL,wx.NORMAL))
        p.SetFontSizeAxis(10)
        p.SetFontSizeLegend(7)
        p.setLogScale((False,False))
        p.SetXSpec('min')
        p.SetYSpec('auto')
        self.canvas.AddPage(p, self.subchannels[channelIdx].name)
        p.SetEnableTitle(self.showTitle)

        p.image = self.images[channelIdx]
        # XXX: REMOVE xAxis AND yAxis
#         p.Draw(self.lines[channelIdx], yAxis=(0,2000))
        p.Draw(self.lines[channelIdx], xAxis=(0,6), yAxis=(400,2000))
#         p.Draw(self.lines[channelIdx])


    def makeLineList(self):
        """ Turn each column of data into its own line plot.
        """
        # The "line list" is really sort of a hack, just containing a single
        # line from min/min to max/max in order to make the plot's scale
        # draw correctly.
        start = self.source[0][-2] * self.timeScalar
        end = self.source[-1][-2] * self.timeScalar
        self.lines = []
        self.ranges = []

        for i in range(len(self.data)):
            d = self.data[i]
            points = ((start, d[1][0]), 
                      (end, d[1][-1]))
            name = self.subchannels[i-1].name
 
            self.lines.append(P.PlotGraphics([P.PolyLine(points, legend=name)],
                              title=self.subchannels[i].name, #title=self.GetTitle(),
                              xLabel="Time", yLabel="Frequency"))
             

    
    @classmethod
    def plotColorSpectrum(cls, n):
        """ Generate a 24-bit RGB color from a positive normalized float value 
            (0.0 to 1.0). 
             
            @note: Not currently used.
        """
        # Because H=0 and H=1.0 have the same RGB value, reduce `n`.
        return tuple(map(lambda x: int(x*255), 
                         colorsys.hsv_to_rgb((1.0-n)*.6667,1.0,1.0)))

                     
    @classmethod
    def plotGrayscale(cls, n):
        """ Generate a 24-bit RGB color from a positive normalized float value 
            (0.0 to 1.0). 
             
            @note: Not currently used.
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
            temp = [np.log(d[0]) for d in data]
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


    def draw(self):
        """
        """
        # self.canvas is the plot canvas
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))

        if self.subchannels is not None:
            subchIds = [c.id for c in self.subchannels]
            start, stop = self.source.getRangeIndices(*self.range)
            recordingTime = self.source[-1][-2] - self.source[0][-2]
            recordingTime *= self.timeScalar
            data = self.source.itervalues(start, stop, subchannels=subchIds)
            fs = self.source.getSampleRate()
            
            self.data = self.generateData(data, rows=stop-start, 
                                          cols=len(self.subchannels), fs=fs, 
                                          sliceSize=self.sliceSize,
                                          slicesPerSec=self.slicesPerSec, 
                                          recordingTime=recordingTime)

            self.images = self.makePlots(self.data, self.logarithmic, self.colorizer)
            self.makeLineList()
            for i in range(len(self.subchannels)):#ch in subchIds:
                self.addPlot(i)

        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


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
            @keyword slicesPerSec: 
            @return: A multidimensional array, with the first column the 
                frequency.
        """
        points = cls.from2diter(data, rows, cols)
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
            Pxx, freqs, bins = spec._spectral_helper(pts, pts, 
                NFFT=specgram_nfft, Fs=fs, detrend=spec.detrend_none, 
                window=spec.window_hanning, noverlap=specgram_nfft/2, 
                pad_to=None, sides='onesided', scale_by_freq=None)
            Pxx = Pxx.real
    
            specData.append((Pxx[1:,:], freqs[1:], bins))
            
        return specData
        
    #===========================================================================
    # 
    #===========================================================================

    def initMenus(self):
        super(SpectrogramView, self).initMenus()
        self.MenuBar.FindItemById(self.ID_EXPORT_IMG).Enable(False)

        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_FREQ, checked=False, enabled=False)
        self.setMenuItem(self.dataMenu, self.ID_DATA_LOG_AMP, checked=self.logarithmic[2])
        self.setMenuItem(self.dataMenu, self.ID_VIEW_SHOWLEGEND, checked=False, enabled=False)
        
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
            p.SetEnableTitle(self.showTitle)
            p.Redraw()
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        

    #===========================================================================
    # 
    #===========================================================================

    def OnExportCsv(self, evt):
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
                out = open(filename, "wb")
                writer = csv.writer(out)
                writer.writerows(self.data[num][0])
                out.close()
            except Exception as err:
                what = "exporting %s as CSV %s" % (self.NAME, filename)
                self.root.handleError(err, what=what)
                return False

        return True


    def OnMenuDataLog(self, evt):
        """
        """
        self.logarithmic=(False, False, evt.IsChecked())
        self.redrawPlots()

    
    def OnMenuColorize(self, evt):
        self.colorizer = self.colorizers.get(evt.GetId(), self.plotColorSpectrum)
        self.redrawPlots()

    def OnMenuViewTitle(self, evt):
        self.showTitle = evt.IsChecked()
        self.redrawPlots()

