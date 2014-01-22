'''
Slam Stick eXtreme Data Viewer

Description should go here. At the moment, this is also the text that appears
in the About Box.

### This line and below are not in the About Box. ###

@todo: See individual TODO tags in the body of code. The long-term items
    are also listed here.
@todo: Revamp the zooming and navigation to be event-driven, handled as far up
    the chain as possible. Consider using wx.lib.pubsub if it's thread-safe.


'''

APPNAME = u"Slam Stick X Data Viewer"
__version__="0.0.1"
__date__="Oct 21, 2013"
__copyright__=u"Copyright (c) 2014 Mid\xe9 Technology"
__url__ = ("http://mide.com", "")
__credits__=["David R. Stokes", "Tim Gipson"]


from datetime import datetime
# import errno
import fnmatch
import json
import locale
import os
import sys
from textwrap import dedent
from threading import Thread

from wx import aui
from wx.lib.rcsizer import RowColSizer
from wx.lib.wordwrap import wordwrap
import wx; wx = wx # Workaround for Eclipse code comprehension

# Graphics (icons, etc.)
import images

# Custom controls
from base import ViewerPanel, MenuMixin
from common import StatusBar, expandRange
import config_dialog
from events import *
from export_dialog import ModalExportProgress, CSVExportDialog, FFTExportDialog
from device_dialog import selectDevice
from timeline import TimelineCtrl, TimeNavigatorCtrl, VerticalScaleCtrl

import fft

# Special helper objects and functions
from threaded_file import ThreadAwareFile

# The actual data-related stuff
import mide_ebml

ANTIALIASING_MULTIPLIER = 3.33
RESAMPLING_JITTER = 0.125


#===============================================================================
# 
#===============================================================================

class Loader(Thread):
    """ The object that does the work of spawning an asynchronous file-loading
        thread and updating the viewer as data is loaded.
    """

    cancelMsg = "Import cancelled"
    
    def __init__(self, root, dataset, numUpdates=100, updateInterval=1.0):
        """ Create the Loader and start the loading process.
            
            @param root: The Viewer.
            @param dataset: The Dataset being loaded. It should be fresh,
                referencing a file stream but not yet loaded.
            @keyword numUpdates: The minimum number of calls to the updater to
                be made. There will be more than this number of updates if
                any takes longer than the specified `updateInterval` (below).
            @keyword updateInterval: The maximum number of seconds between
                calls to the updater
        """
        self.root = root
        self.dataset = dataset
        self.numUpdates = numUpdates
        self.updateInterval = updateInterval
        self.cancelled = False
        self.startTime = self.lastTime = None
        self.readingData = False
        self.lastCount = 0

        super(Loader, self).__init__()


    def run(self):
        evt = EvtProgressStart(label="Importing...", initialVal=-1, 
                               cancellable=True, cancelEnabled=None)
        wx.PostEvent(self.root, evt)
        
        self.totalUpdates = 0
        mide_ebml.importer.readData(self.dataset, self, 
                                    numUpdates=self.numUpdates,
                                    updateInterval=self.updateInterval)

        evt = EvtProgressEnd(label=self.formatMessage(self.lastCount))
        wx.PostEvent(self.root, evt)


    def formatMessage(self, count, est=None):
        """ Create a nice message string containing the total import count
            and (optionally) the estimated time remaining.
        """
        # BUG: wxPython is forcing the use of their own wx.Locale, but it 
        # doesn't format numbers correctly. Figure out why.
        countStr = locale.format("%d", count, grouping=True)

        if est is None or est.seconds < 2:
            estStr = ""
        elif est.seconds < 60:
            estStr = "- Est. finish in %d sec." % est.seconds
        else:
            estStr = "- Est. finish in %s" % str(est)[:-7].lstrip("0:")
            
        return "%s samples imported %s" % (countStr, estStr)
        

    def __call__(self, count=0, percent=None, total=None, error=None, 
                 done=False):
        """ Update the Viewer's display.
        
            @param count: the current line number.
            @param percent: The estimated percentage of the file read, as a
                normalized float (0.0 to 1.0). 
            @param total: the total number of samples (if known).
            @param error: Any unexpected exception, if raised during the import.
            @param done: `True` when the export is complete.
        """
        self.totalUpdates += 1
        
        if error is not None:
            self.cancel()
            wx.PostEvent(self.root, EvtImportError(err=error))
            return
        
        if done:
            # Nothing else needs to be done. Put cleanup here if need be.
            return
        
        if not self.readingData:
            if count > 0:
                # The start of data.
                self.readingData = True
                self.root.session = self.dataset.lastSession
                wx.PostEvent(self.root, EvtInitPlots())
                endTime = self.root.session.endTime
                if endTime is None:
                    endTime = self.root.session.lastTime
                if endTime is not None:
                    kwargs = {'start': self.root.session.firstTime, 
                              'end': endTime, 
                              'instigator': None, 
                              'tracking': False}
                    wx.PostEvent(self.root, EvtSetTimeRange(**kwargs))
                    wx.PostEvent(self.root, EvtSetVisibleRange(**kwargs))
            else:
                # Still in header; don't update.
                return
        
        est = None
        thisTime = datetime.now()
        if self.startTime is None:
            self.startTime = thisTime
        elif percent is not None:
            p = int(percent * 100)
            if p > 0 and p < 100:
                est = ((thisTime - self.startTime) / p) * (100-p)
        
        msg = self.formatMessage(count, est)
        
        wx.PostEvent(self.root, 
            EvtProgressUpdate(val=percent, label=msg, cancellable=True))

        if self.dataset.lastSession == self.root.session:
            evt = EvtSetTimeRange(start=self.root.session.firstTime, 
                                  end=self.root.session.lastTime, 
                                  instigator=None, 
                                  tracking=True)
            wx.PostEvent(self.root, evt)
        
        self.lastTime = thisTime
        self.lastCount = count


    def cancel(self, blocking=True):
        """
        """
        self.cancelled = True
        if not blocking:
            return
        while self.isAlive():
            pass


#===============================================================================
# 
#===============================================================================
        
class Timeline(ViewerPanel):
    """ The key below the graph. The Timeline itself actually determines the
        range and zoom shown.
        
        @ivar timeScalar: A scaling factor for the time displayed (maps
            microseconds to float seconds)
        @ivar timerange: 
        @ivar currentTime: 
        @ivar displayLength: 
    """
    
    _sbMax = 10000.0
    _minThumbSize = 100
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword timerange: The default time range, in microseconds. 
        """
        kwargs.setdefault('style',wx.NO_BORDER)
        super(Timeline, self).__init__(*args, **kwargs)

        self.barClickPos = None
        self.scrolling = False
        self.highlightColor = wx.Colour(255,255,255)
                
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.timebar = TimelineCtrl(self, -1, orient=wx.HORIZONTAL, 
                                    style=wx.NO_BORDER)
        sizer.Add(self.timebar, 0, wx.EXPAND)
        self.timebar.SetBackgroundColour(self.root.uiBgColor)
        self.timebar.SetCursor(wx.StockCursor(wx.CURSOR_SIZEWE))
        self.timebar.SetRange(self.timerange[0] * self.root.timeScalar,
                             self.timerange[1] * self.root.timeScalar)
        
        self.scrollbar = wx.ScrollBar(self, -1, style=wx.SB_HORIZONTAL)
        sizer.Add(self.scrollbar, 0, wx.EXPAND|wx.ALIGN_BOTTOM)
        self.SetSizer(sizer)

        self._bindScrollEvents(self.scrollbar, self.OnScroll, 
                               self.OnScrollTrack, self.OnScrollEnd)
        
        self.timebar.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.timebar.Bind(wx.EVT_LEFT_DOWN, self.OnTimebarClick)
        self.timebar.Bind(wx.EVT_LEFT_UP, self.OnTimebarRelease)
        self.timebar.Bind(wx.EVT_LEAVE_WINDOW, self.OnTimebarRelease)
        
        # Initial value: probably not true, but is changed almost immediately.
        self.scrollUnitsPerUSec = 1.0
        self.unitsPerPixel = 1.0
        self.currentTime = 1000 # start of displayed interval, in microseconds
        self.displayLength = 5000 # The length of displayed interval, in us.
        self.setTimeRange(*self.timerange)
        

    #===========================================================================
    # 
    #===========================================================================
    
    def getValueAt(self, hpos):
        """
        """
        return (hpos * self.unitsPerPixel) + self.currentTime
        

    #===========================================================================
    # 
    #===========================================================================

    def setTimeRange(self, start=None, end=None, instigator=None,
                    tracking=False):
        """ Set the current time range. Propagates to its children.
            
            @keyword start: The first time in the range. Defaults to
                the current start.
            @keyword end: The last time in the range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if self.scrolling:
            return
        start = self.timerange[0] if start is None else start
        end = self.timerange[1] if end is None else end
        self.timerange = (start, end)
        if end != start:
            self.scrollUnitsPerUSec = self._sbMax / (end-start)
        else:
            # This is probably not the best solution
            self.scrollUnitsPerUSec = 1
        self.setVisibleRange()


    def setVisibleRange(self, start=None, end=None, instigator=None,
                        tracking=False, broadcast=False):
        """ Set the currently visible time range.
            
            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return
        
        if start is not None:
            self.currentTime = start
        
        if end is None:
            end = self.currentTime + self.displayLength
        else:
            if end - self.currentTime < self._minThumbSize:
                self.currentTime = end - self._minThumbSize 
            self.displayLength = end - self.currentTime
        
        self.timebar.SetRange(self.root.timeScalar * self.currentTime, 
                              self.root.timeScalar * end)
        
        self.scrollbar.SetScrollbar(
                self.scrollUnitsPerUSec * (self.currentTime-self.timerange[0]), 
                self.scrollUnitsPerUSec * self.displayLength, 
                self._sbMax,
                self.scrollUnitsPerUSec * self.displayLength)
        
        self.unitsPerPixel = (self.displayLength/self.timebar.GetSize()[0]+0.0)
        
        if broadcast:
            instigator = self if instigator is None else instigator
            wx.PostEvent(self.root, EvtSetVisibleRange(start=self.currentTime, 
                                                       end=end, 
                                                       instigator=self, 
                                                       tracking=tracking))


    def getVisibleRange(self):
        # Test: get real thing from parent
        return self.currentTime, self.currentTime + self.displayLength


    #===========================================================================
    # Event Handlers
    #===========================================================================
    
    def OnTimebarClick(self, evt):
        self.barClickPos = evt.GetX()
        evt.Skip()


    def OnTimebarRelease(self, evt):
        if self.barClickPos is not None:
            self.postSetVisibleRangeEvent(self.currentTime, 
                                          self.currentTime + self.displayLength)
            self.barClickPos = None
            self.timebar.SetBackgroundColour(self.root.uiBgColor)
        evt.Skip()


    def OnMouseMotion(self, evt):
        evt.Skip()
        if self.scrolling:
            return
        if self.barClickPos is not None and evt.LeftIsDown():
            self.timebar.SetBackgroundColour(self.highlightColor)
            newPos = evt.GetX()
            moved = self.barClickPos - newPos
            start = self.currentTime + moved * self.unitsPerPixel
            end = start + self.displayLength
            if start >= self.timerange[0] and end <= self.timerange[1]:
                self.setVisibleRange(start, end, None, tracking=True, 
                                     broadcast=True)
            self.barClickPos = newPos
        else:
            self.barClickPos = None
            self.root.showMouseHPos(evt.GetX())

    
    def OnScroll(self, evt):
        self.scrolling = True


    def OnScrollTrack(self, evt):
        start = (evt.GetPosition()/self.scrollUnitsPerUSec) + self.timerange[0]
        end = start + self.displayLength
        self.setVisibleRange(start, end, None, tracking=True, broadcast=True)


    def OnScrollEnd(self, evt):
        self.scrolling = False
        start = (evt.GetPosition()/self.scrollUnitsPerUSec) + self.timerange[0]
        end = start + self.displayLength
        self.setVisibleRange(start, end, None, tracking=False, broadcast=True)


#===============================================================================
# 
#===============================================================================

class TimeNavigator(ViewerPanel):
    """ The full timeline view shown above the graph. Includes movable markers 
        showing the currently visible interval.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword timerange: The default time range, in microseconds. 
        """
        kwargs.setdefault('style', wx.NO_BORDER)
        super(TimeNavigator, self).__init__(*args, **kwargs)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        logo = wx.StaticBitmap(self, -1, images.SSXLogo.GetBitmap())
        sizer.Add(logo, 0, wx.ALIGN_CENTER)
        
        self.timeline = TimeNavigatorCtrl(self,-1)
        sizer.Add(self.timeline, -1, wx.EXPAND)
        
        self.zoomOutButton = self._addButton(sizer, images.zoomOutH,
                                             self.OnZoomOut, 
                                             tooltip="Zoom Out (X axis)")
        self.zoomInButton = self._addButton(sizer, images.zoomInH,
                                            self.OnZoomIn, 
                                            tooltip="Zoom In (X axis)")
        self.zoomFitButton = self._addButton(sizer, images.zoomFitH,
                                             self.OnZoomFit, 
                                             tooltip="Zoom to fit entire "
                                             "loaded time range (X axis)")
        
        self.SetSizer(sizer)
        
        self.movingMarks = False
        
        self.Bind(TimeNavigatorCtrl.EVT_INDICATOR_CHANGED, self.OnMarkChanged)
        self.timeline.Bind(wx.EVT_LEFT_UP, self.OnMouseLeftUp)
        

    #===========================================================================
    # 
    #===========================================================================
    
    def setTimeRange(self, start=None, end=None, instigator=None,
                     tracking=False):
        """ Set the current time range. Propagates to its children.
            
            @keyword start: The first time in the range. Defaults to the 
                current start.
            @keyword end: The last time in the range. Defaults to the current 
                end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond if 
                `tracking` is `True`.
        """
        if instigator != self:
            self.timerange = start, end
            self.timeline.SetRange(start * self.root.timeScalar, 
                                   end * self.root.timeScalar)

        
    def setVisibleRange(self, start=None, end=None, instigator=None,
                        tracking=False):
        """ Set the currently visible time range.
            
            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is 
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond if 
                `tracking` is `True`.
        """
        if instigator != self:
            self.timeline.setVisibleRange(start * self.root.timeScalar, 
                                          end * self.root.timeScalar)


    def zoom(self, percent, tracking=True):
        """ Increase or decrease the size of the visible range.
        
            @param percent: A zoom factor. Use a normalized value, positive
                to zoom in, negative to zoom out.
            @param tracking:
        """
        v1, v2 = self.timeline.getVisibleRange()
        d = min(5000, (v2 - v1) * percent / 2)
        newStart = (v1 + d)/ self.root.timeScalar
        newEnd = (v2 - d)/ self.root.timeScalar
        
        # If one end butts the limit, more the other one more.
        if newStart < self.timerange[0]:
            newEnd += self.timerange[0] - newStart
        elif newEnd > self.timerange[1]:
            newStart -= self.timerange[1] - newEnd
            
        v1 = max(self.timerange[0], newStart) 
        v2 = min(self.timerange[1], newEnd)#max(v1+10000, newEnd)) # Buffer
        self.setVisibleRange(v1,v2)
        self.postSetVisibleRangeEvent(v1, v2, tracking)
#         self.root.setVisibleRange(v1, v2, self)#, not tracking)


    #===========================================================================
    # 
    #===========================================================================
    
    def OnMouseLeftUp(self, evt):
        """ Handle the release of the left mouse button. If previously dragging
            a range marker, do the non-tracking update.
        """
        evt.Skip()
        if not self.movingMarks:
            return
        
        self.movingMarks = False
        v1, v2 = self.timeline.getVisibleRange()
        self.postSetVisibleRangeEvent(v1/self.root.timeScalar, 
                                      v2/self.root.timeScalar, 
                                      False)    
    

    def OnMarkChanged(self, evt):
        """ Handle the final adjustment of a visible range marker.
        """
        evt.Skip()
        self.movingMarks = True
        v1, v2 = self.timeline.getVisibleRange()
        self.postSetVisibleRangeEvent(v1/self.root.timeScalar, 
                                      v2/self.root.timeScalar, 
                                      True)    

    def OnZoomIn(self, evt):
        """ Handle 'zoom in' events, i.e. the zoom in button was pressed. 
        """
        self.zoom(.25, False)

    
    def OnZoomOut(self, evt):
        """ Handle 'zoom out' events, i.e. the zoom in button was pressed. 
        """
        self.zoom(-.25, False)


    def OnZoomFit(self, evt):
        """
        """
        self.setVisibleRange(*self.timerange)
        self.postSetVisibleRangeEvent(*self.timerange, tracking=False)

#===============================================================================
# 
#===============================================================================

class LegendArea(ViewerPanel):
    """ The vertical axis of the plot. Contains the scale and the vertical
        zoom buttons.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
        """
        kwargs.setdefault('style',wx.NO_BORDER)
        super(LegendArea, self).__init__(*args, **kwargs)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        subsizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(subsizer)
        
        # Zoom buttons
        self.defaultButtonStyle = wx.DEFAULT | wx.ALIGN_BOTTOM
        self.defaultSizerFlags = 0
        
        self.zoomInButton = self._addButton(subsizer, images.zoomInV, 
                                            self.OnZoomIn, 
                                            tooltip="Zoom In (Y axis)")
        self.zoomOutButton = self._addButton(subsizer, images.zoomOutV, 
                                             self.OnZoomOut, 
                                             tooltip="Zoom Out (Y axis)")
        self.zoomFitButton = self._addButton(subsizer, images.zoomFitV, 
                                            self.OnZoomFit, 
                                            tooltip="Zoom to fit min and max "
                                            "values in displayed interval")
        
        # Vertical axis label
        self.unitLabel = wx.StaticText(self, -1, self.Parent.yUnits[0], 
                                       style=wx.ALIGN_CENTER)
        self.unitLabel.SetFont(wx.Font(16, wx.SWISS, wx.NORMAL, wx.NORMAL))
        subsizer.Add(self.unitLabel, 1, wx.EXPAND)

        # Vertical scale 
        self.unitsPerPixel = 1.0
        self.scrollUnitsPerUnit = 1.0
        self.scale = VerticalScaleCtrl(self, -1, size=(1200,-1), 
                                       style=wx.NO_BORDER|wx.ALIGN_RIGHT)
        self.scale.SetRange(*self.visibleRange)
        self.scale.SetBackgroundColour(self.root.uiBgColor)
        sizer.Add(self.scale, -1, wx.EXPAND)
        self.SetSizer(sizer)
        self.SetMinSize((self.root.corner.GetSize()[0],-1))
        self.SetBackgroundColour(self.root.uiBgColor)

        self.scale.Bind(wx.EVT_SIZE, self.OnResize)
        self.scale.Bind(wx.EVT_MOTION, self.OnMouseMotion)

    #===========================================================================
    # 
    #===========================================================================
    
    def setValueRange(self, top=None, bottom=None, instigator=None,
                      tracking=False):
        """ Set the currently visible time range. Propagates to its children.
            
            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in 
                order to avoid an infinite loop of child calling parent 
                calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return
        vSize = self.GetSize()[1]
        if vSize == 0:
            return
        top = self.visibleRange[0] if top is None else top
        bottom = self.visibleRange[1] if bottom is None else bottom
        self.visibleRange = top, bottom
        self.scale.SetRange(bottom,top)
        self.unitsPerPixel = abs((top - bottom) / (vSize + 0.0))
        if not tracking:
            self.Parent.Refresh()
    
    
    def getValueRange(self):
        """ Get the currently displayed range of time.
        """
        return self.visibleRange


    def getValueAt(self, vpos):
        """ Get the value corresponding to a given pixel location.
        """
        return self.visibleRange[1] - (vpos * self.unitsPerPixel)
        

    def zoom(self, percent, tracking=True):
        """ Increase or decrease the size of the visible range.
        
            @param percent: A zoom factor. Use a normalized value, positive
                to zoom in, negative to zoom out.
            @param tracking:
        """
        v1, v2 = self.visibleRange
        d = (v1 - v2) * percent / 2.0
        self.setValueRange(v1-d,v2+d,None,False)


    #===========================================================================
    # Event Handlers
    #===========================================================================
    
    def OnResize(self, evt):
        self.unitsPerPixel = abs((self.visibleRange[0] - self.visibleRange[1]) \
                                 / (evt.Size[1] + 0.0))
        bRect = self.zoomFitButton.GetRect()
        self.unitLabel.SetPosition((-1,max(evt.Size[1]/2,bRect[1]+bRect[3])))
        evt.Skip()
    
    def OnMouseMotion(self, evt):
        self.root.showMouseVPos(self.getValueAt(evt.GetY()), 
                                units=self.Parent.yUnits[1])
        evt.Skip()
    
    def OnZoomIn(self, evt):
        self.zoom(.25)
    
    def OnZoomOut(self, evt):
        self.zoom(-.25)

    def OnZoomFit(self, evt):
        self.Parent.zoomToFit()

#===============================================================================
# 
#===============================================================================

class PlotCanvas(wx.ScrolledWindow, MenuMixin):
    """ The actual plot-drawing area.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
        """
        self.root = kwargs.pop('root',None)
        self.color = kwargs.pop('color', "BLUE")
        self.weight = kwargs.pop('weight',1)
        kwargs.setdefault('style',wx.VSCROLL|wx.BORDER_SUNKEN)
        
        super(PlotCanvas, self).__init__(*args, **kwargs)
        self.SetBackgroundColour("white")
        
        if self.root is None:
            self.root = self.GetParent().root
        
        self.originHLinePen = self.loadPen("originHLineColor", "GRAY")
        self.majorHLinePen = self.loadPen("majorHLineColor", style=wx.DOT)
        self.minorHLinePen = self.loadPen("minorHLineColor", style=wx.DOT)
        
        self.lines = None
        self.points = None
        self.lastEvents = None
        self.lastRange = None

        self.setPlotPen()
        
        self.setContextMenu(wx.Menu())
        self.addMenuItem(self.contextMenu, -1, "Select Color...", "", 
                         self.OnMenuColor)
        
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)

       
    def loadPen(self, name, defaultColor="GRAY", width=1, style=wx.SOLID):
        """ Create a pen using a color in the preferences.
        """
        return wx.Pen(self.root.app.getPref(name, defaultColor), width, style)


    def setPlotPen(self, color=None, weight=None, style=wx.SOLID):
        """ Set the color, weight, and/or style of the plotting pens.
        """
        self.color = color if color is not None else self.color
        self.weight = weight if weight is not None else self.weight
        self.style = style if style is not None else self.style
        self._pen = wx.Pen(self.color, self.weight, self.style)
        self._pointPen = wx.Pen(wx.Colour(255,255,255,.5), 1, self.style)
        self._pointBrush = wx.Brush(self.color, wx.SOLID)
        
    
    def setTimeRange(self, start=None, end=None, instigator=None,
                     tracking=False):
        """ Set the current time range. Propagates to its children.
            
            @keyword start: The first time in the range. No change if `None`.
            @keyword end: The last time in the range. No change if `None`.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond if
                `tracking` is `True`.
        """
#         print "PlotCanvas.setTimeRange"
        if instigator == self:
            return
        pass
        
    
    def setVisibleRange(self, start=None, end=None, instigator=None,
                        tracking=False):
        """ Set the currently visible time range.
            
            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in 
                order to avoid an infinite loop of child calling parent 
                calling child. The call is aborted if the instigator is the
                object itself.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator != self and not tracking:
            self.Refresh()
    
    
    def OnMouseMotion(self, evt):
        """ Event handler for mouse movement events.
        """
        self.root.showMouseHPos(evt.GetX())
        self.root.showMouseVPos(self.Parent.legend.getValueAt(evt.GetY()),
                                units=self.Parent.yUnits[1])
        evt.Skip()


    def makeHGridlines(self, pts, width, scale):
        """ Create the coordinates for the horizontal grid lines from a list of
            ruler indicator marks. Used internally.
        """
        return [(0, p.pos * scale, width * scale, p.pos * scale) for p in pts]

    
    def getRelRange(self):
        """ Get the time range for the current window, based on the parent
            view's timeline. Used internally.
        """
        rect = self.GetScreenRect()
        trect = self.root.timeline.GetScreenRect()
        
        p1 = rect[0] - trect[0]
        p2 = p1 + self.GetSize()[0]

        result = (int(self.root.timeline.getValueAt(p1)),
                int(self.root.timeline.getValueAt(p2)))
        
        return result


    def OnPaint(self, evt):
        """ Event handler to redraw the plot.
        
            @todo: Apply offset and scaling transforms to the DC itself, 
                eliminating all the per-point math.
        """
        if self.Parent.source is None:
            return
        
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))

        self.InvalidateBestSize()
        dc = wx.PaintDC(self)
        dc.SetAxisOrientation(True,False)
        dc.Clear()

        size = dc.GetSize()
        
        # Antialiasing
        viewScale = 1.0
        oversampling = 2.0 #3.33 # XXX: Clean this up!
        if self.root.antialias:
            dc = wx.GCDC(dc)
            viewScale = self.root.aaMultiplier
            oversampling = viewScale * 1.33
            dc.SetUserScale(1.0/viewScale, 1.0/viewScale)
        
        dc.BeginDrawing()

        legend = self.Parent.legend
        
        tenth = int(size[0]/2 * oversampling)

        # BUG: This does not work for vertically split plots; they all start
        # at the start of the visible range instead of relative position on
        # the timeline. Investigate.
#         hRange = map(int,self.root.getVisibleRange())
        hRange = self.getRelRange()
        vRange = legend.scale.GetRange()
        
        # TODO: Implement regional redrawing.
#         updateBox = self.GetUpdateRegion().GetBox()
#         updateHRange = (self.root.timeline.getValueAt(updateBox[0]),
#                   self.root.timeline.getValueAt(updateBox[2]))
#         updateVRange = (legend.getValueAt(updateBox[1]),
#                   legend.getValueAt(updateBox[3]))        

        hScale = (size.x + 0.0) / (hRange[1]-hRange[0]) * viewScale
        if vRange[0] != vRange[1]:
            vScale = (size.y + 0.0) / (vRange[1]-vRange[0]) * viewScale
        else:
            vScale = -(size.y + 0.0) * viewScale
        thisRange = (hScale, vScale, hRange, vRange)
        
        for r in self.Parent.warningRange:
            r.draw(dc, hRange, hScale, viewScale, size)
                
        # Get the horizontal grid lines. 
        # NOTE: This might not work in the future. Consider modifying
        #    VerticalScaleCtrl to ensure we've got access to the labels!
        majorHLines = []
        minorHLines = []
        if self.Parent.drawMinorHLines:
            self.minorHLinePen.SetWidth(viewScale)
            minorHLines = self.makeHGridlines(legend.scale._minorlabels, 
                                              size[0], viewScale)
        if self.Parent.drawMajorHLines:
            self.majorHLinePen.SetWidth(viewScale)
            majorHLines = self.makeHGridlines(legend.scale._majorlabels, 
                                              size[0], viewScale)

        # The first drawing only sets up the scale; don't draw.
        if not self.Parent.firstPlot:
            dc.DrawLineList(majorHLines, self.majorHLinePen)
            dc.DrawLineList(minorHLines, self.minorHLinePen)
        
        dc.SetPen(self._pen)
        if self.lastRange != thisRange or self.lines is None and not self.root.drawingSuspended:
            i=1
            self.lines=[]
            self.points=[]
            self.lastRange = thisRange
            
            # Lines are drawn in sets to provide more immediate results
            lineSubset = []
            
            events = self.Parent.source.iterResampledRange(hRange[0], hRange[1],
                size[0]*oversampling, padding=1, jitter=self.root.noisyResample)

            try:
                self.Parent.visibleValueRange = [sys.maxint, -sys.maxint]
                event = events.next()
                expandRange(self.Parent.visibleValueRange, event[-1])
                lastPt = ((event[-2] - hRange[0]) * hScale, 
                          (event[-1] - vRange[0]) * vScale)
                
                for i, event in enumerate(events,1):
                    # Using negative indices here in case doc.useIndices is True
                    pt = ((event[-2] - hRange[0]) * hScale, 
                          (event[-1] - vRange[0]) * vScale)
                    self.points.append(pt)
                    
                    # A value of None is a discontinuity; don't draw a line.
                    if event[-1] is not None:
                        line = lastPt + pt
                        lineSubset.append(line)
                        self.lines.append(line)
                        expandRange(self.Parent.visibleValueRange, event[-1])
                    
                    if i % tenth == 0:
                        dc.DrawLineList(lineSubset)
                        lineSubset = []
                        
                    lastPt = pt
                    
            except StopIteration:
                # This will occur if there are 0-1 events, but that's okay.
                pass

            # Draw the remaining lines (if any)
            dc.DrawLineList(lineSubset)

        else:
            # No change in displayed range; Use cached lines.
            dc.DrawLineList(self.lines)
        
        if self.Parent.firstPlot and not self.Parent.source.hasDisplayRange:
            # First time the plot was drawn. Don't draw; scale to fit.
            self.Parent.zoomToFit(self)
            self.Parent.firstPlot = False
            self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
            dc.EndDrawing()
            return
        
        if len(self.lines) < size[0] / 4:
            # More pixels than points: draw actual points as circles.
            dc.SetPen(self._pointPen)
            dc.SetBrush(self._pointBrush)
            for p in self.points:
                dc.DrawCirclePoint(p,self.weight*3)
        
        dc.EndDrawing()
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


    def OnMenuColor(self, evt):
        data = wx.ColourData()
        data.SetChooseFull(True)
        data.SetColour(self.color)
        dlg = wx.ColourDialog(self, data)
        
        if dlg.ShowModal() == wx.ID_OK:
            color = dlg.GetColourData().GetColour().Get()
            self.setPlotPen(color=color)
            self.Refresh()
    
    
    def OnMenuAntialiasing(self, evt):
        evt.IsChecked()
        pass
    
    def OnMenuJitter(self, evt):
        pass

#===============================================================================
# 
#===============================================================================

class Plot(ViewerPanel):
    """ A single plotted channel, consisting of the vertical scale and actual
        plot-drawing canvas.
    """
    _sbMax = 10000.0
    _minThumbSize = 100
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
            @keyword units: 
            @keyword scale: 
            @keyword range: 
            @keyword warningRange: 
        """
        self.source = kwargs.pop('source', None)
        self.yUnits= kwargs.pop('units',None)
        color = kwargs.pop('color', 'BLACK')
        scale = kwargs.pop('scale', (-1,1))
        self.range = kwargs.pop('range', (-(2**16), (2**16)-1))
        self.warningRange = kwargs.pop("warningRange", [])
        super(Plot, self).__init__(*args, **kwargs)
        
        self.firstPlot = True
        self.visibleValueRange = None
        self.drawMajorHLines = True
        self.drawMinorHLines = False
        self.scrollUnitsPerUnit = 1.0
        self.unitsPerPixel = 1.0
        
        if self.root is None:
            self.root = self.Parent.root
            
        if self.yUnits is None:
            self.yUnits = getattr(self.source, "units", ('',''))
        
        if hasattr(self.source, 'hasDisplayRange'):
            scale = self.source.displayRange
        
        self.legend = LegendArea(self, -1, 
                                 visibleRange=(max(*scale),min(*scale)))
        self.plot = PlotCanvas(self, -1, color=color)#, 
#                                style=wx.FULL_REPAINT_ON_RESIZE)
        self.scrollbar = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.legend, 0, wx.EXPAND)
        sizer.Add(self.plot, -1, wx.EXPAND)
        sizer.Add(self.scrollbar, 0, wx.EXPAND)
        self.SetSizer(sizer)
        self.legend.SetSize((self.Parent.Parent.corner.GetSize()[0],-1))
        
        self.plot.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseLeave)

        # TODO: Finish scrolling implementation!
        self.scrollbar.Enable(False)
        self._bindScrollEvents(self.scrollbar, self.OnScroll, 
                              self.OnScrollTrack, self.OnScrollEnd)
        
#         self.Bind(wx.EVT_CHAR_HOOK, self.OnKeypress)
        self.plot.Bind(wx.EVT_KEY_UP, self.OnKeypress)
        

    def setValueRange(self, start=None, end=None, instigator=None, 
                      tracking=False):
        """ Set the currently visible range of values (the vertical axis). 
            Propagates to its children.
            
            @keyword start: The first value in the visible range. Defaults to
                the current start.
            @keyword end: The last value in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator is self:
            return
        if (start is None or end is None) and self.visibleValueRange is None:
            return
        instigator = self if instigator is None else instigator
        start = self.visibleValueRange[0] if start is None else start
        end = self.visibleValueRange[1] if end is None else end
        self.legend.setValueRange(start, end, instigator, tracking)
        
        # TODO: Implement/Enable vertical scrolling
#         self.scrollUnitsPerUnit = self._sbMax / (start-end)
#         self.scrollbar.SetScrollbar(
#             self.scrollUnitsPerUnit * (self.currentTime - self.timerange[0]), 
#             self.scrollUnitsPerUSec * self.displayLength, 
#             self._sbMax,
#             self.scrollUnitsPerUSec * self.displayLength)
                                    
        if not tracking:
            self.plot.Refresh()
    
    
    def setVisibleRange(self, start=None, end=None, instigator=None,
                        tracking=False):
        """ Set the currently visible time range.
            
            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator != self and tracking is False:
            self.plot.Refresh()


    def setTimeRange(self, start=None, end=None, instigator=None,
                        tracking=False):
        """ Set the current time range. Propagates to its children.
            
            @keyword start: The first time in the range. Defaults to
                the current start.
            @keyword end: The last time in the range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator != self and tracking is False:
            self.plot.Refresh()


    def zoomToFit(self, instigator=None, padding=0.05):
        """ Adjust the visible vertical range to fit the values in the
            currently displayed interval.
            
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword padding: The extra space to add to the top and bottom,
                as a normalized percent.
        """
        # TODO: Make all zooming event-based and handled by plot parents
        if self.visibleValueRange is None:
            return
        d = (self.visibleValueRange[1] - self.visibleValueRange[0]) * padding
        self.setValueRange(self.visibleValueRange[0] - d,
                           self.visibleValueRange[1] + d, 
                           instigator, 
                           False)


    #===========================================================================
    # 
    #===========================================================================


    def OnKeypress(self, evt):
        keycode = evt.GetUnicodeKey()
        keychar = unichr(keycode)
        
        if keychar == u'R':
            self.plot.Refresh()
        elif evt.CmdDown():
            # TODO: These won't necessarily work on international keyboards
            # (e.g. '=' is a shift combination on German keyboards)
            if keychar == u'-':
                self.legend.OnZoomOut(None)
            elif keychar == u'=':
                self.legend.OnZoomIn(None)
            elif keychar == u'0':
                self.zoomToFit()
            else:
                evt.Skip()
        else:
            evt.Skip()
        
    
    def OnMouseLeave(self, evt):
        self.root.showMouseHPos(None)
        self.root.showMouseVPos(None)
        evt.Skip()

#===============================================================================
# 
#===============================================================================

class WarningRangeIndicator(object):
    """ A visual indicator showing intervals in which a sensor's readings
        were outside a specific range.
    """
    
    def __init__(self, source, color="PINK", style=wx.BDIAGONAL_HATCH):
        self.source = source
        self.brush = wx.Brush(color, style=style)
        self.pen = wx.Pen(color, style=wx.TRANSPARENT)
        self.oldDraw = None
        self.rects = None
        
        
    def draw(self, dc, hRange, hScale, scale=1.0, size=None):
        """ Draw a series of out-of-bounds rectangles in the given drawing
            context.
            
            @todo: Apply transforms to the DC itself before passing it, 
                eliminating all the scale and offset stuff.
            
            @param dc: TThe drawing context (a `wx.DC` subclass). 
        """
        oldPen = dc.GetPen()
        oldBrush = dc.GetBrush()
        size = dc.GetSize() if size is None else size
        dc.SetPen(self.pen)
        dc.SetBrush(self.brush)

        thisDraw = (hRange, hScale, scale, size)
        if thisDraw != self.oldDraw or not self.rects:
            self.oldDraw = thisDraw
            self.rects = []
            for r in self.source.getRange(*hRange):
                # TODO: Apply transforms to DC in PlotCanvas.OnPaint() before
                # calling WarningRangeIndicator.draw(), eliminating these
                # offsets and scalars.
                x = (r[0]-hRange[0])*hScale
                y = 0
                w = ((r[1]-hRange[0])*hScale)-x if r[1] != -1 else size[0]*scale
                h = size[1] * scale
                rect = int(x),int(y),int(w),int(h)
                self.rects.append(rect)
            
        dc.DrawRectangleList(self.rects)
        
        dc.SetPen(oldPen)
        dc.SetBrush(oldBrush)

#===============================================================================
# 
#===============================================================================

class PlotSet(aui.AuiNotebook):
    """ A tabbed window containing multiple Plots. The individual plots (pages)
        can be accessed by index like a tuple or list.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
        """
        self.root = kwargs.pop('root', None)
        kwargs.setdefault('style', aui.AUI_NB_TOP|aui.AUI_NB_TAB_SPLIT |
                          aui.AUI_NB_TAB_MOVE | aui.AUI_NB_SCROLL_BUTTONS)
        super(PlotSet, self).__init__(*args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        

    def __len__(self):
        return self.GetPageCount()
    
    
    def __iter__(self):
        for i in xrange(len(self)):
            yield(self.GetPage(i))
    
    
    def __getitem__(self, idx):
        return self.GetPage(idx)
    
    
    def getActivePage(self):
        """ Retrieve the current plot (i.e. the one in focus).
        """
        p = self.GetSelection()
        if p == -1:
            return None
        return self.GetPage(p)
        
        
    def addPlot(self, source, title=None, name=None, scale=None, color="BLACK", 
                units=None):
        """ Add a new Plot to the display.
        
            @param source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
            @keyword title: The name displayed on the plot's tab
                (defaults to 'Plot #')
        """
        
        # NOTE: Hardcoded warning range is for WVR hardware; modify later.
        try:
            warnLow = self.root.app.getPref("wvr_tempMin", -20.0)
            warnHigh = self.root.app.getPref("wvr_tempMax", 60.0)
            warningRange = mide_ebml.dataset.WarningRange(
                source.dataset.channels[1][1].getSession(), warnLow, warnHigh)
            warnings = [WarningRangeIndicator(warningRange)]
        except (IndexError, KeyError):
            # Dataset had no data for channel and/or subchannel.
            # Should not occur, but not fatal.
            warnings = []

        title = source.name or title
        title = "Plot %s" % len(self) if title is None else title
        name = name or title
        
        if scale is None:
            scale = getattr(source, "displayRange", (-1.0,1.0))
            
        plot = Plot(self, source=source, root=self.root, scale=scale, 
                    color=color, units=units, warningRange=warnings)
        plot.SetToolTipString(name)
        self.AddPage(plot, title)
        self.Refresh()
        
        return plot


    def setVisibleRange(self, start=None, end=None, instigator=None, 
                        tracking=False):
        """ Set the currently visible time range. Propagates to its children.
            
            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return
        for p in self:
            if p.IsShownOnScreen():
                p.setVisibleRange(start, end, instigator, tracking)


    def setTimeRange(self, start=None, end=None, instigator=None,
                     tracking=False):
        """ Set the data set time range. Propagates to its children.
            
            @keyword start: The first time in the range. Defaults to
                the current start.
            @keyword end: The last time in the range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return
        for p in self:
            if p.IsShownOnScreen():
                p.setTimeRange(start, end, instigator, tracking)


    def removePlot(self, idx):
        """ Delete a plot page by index.
        """
        pagecount = len(self)
        idx = pagecount + idx if idx < 0 else idx
        if idx < pagecount:
            pIdx = self.GetPageIndex(self.GetPage(idx))
            if pIdx != wx.NOT_FOUND:
                self.DeletePage(pIdx)

    
    def clearAllPlots(self):
        """ Delete all plots.
        """
        for _ in xrange(self.GetPageCount):
            self.removePlot(0)
    
    
    def redraw(self):
        """ Force a redraw.
        """
        for p in self:
            p.plot.lines = None
        self.Refresh()
        
        
#===============================================================================
# 
#===============================================================================

class Corner(ViewerPanel):
    """ A 'bug' to fit into the empty space in the lower left corner.
        Provides a space for 'manually' entering an interval of time to
        display.
    """
    
    def __init__(self, *args, **kwargs):
        super(Corner, self).__init__(*args, **kwargs)
        
        self.updating = False
        self.formatting = "%.4f"
        
        fieldAtts = {'size': (56,-1),
                     'style': wx.TE_PROCESS_ENTER | wx.TE_PROCESS_TAB}
        labelAtts = {'size': (30,-1),
                     'style': wx.ALIGN_RIGHT | wx.ALIGN_BOTTOM}
        unitAtts = {'style': wx.ALIGN_LEFT}
        
        self.startField = wx.TextCtrl(self, -1, "start", **fieldAtts)
        startLabel = wx.StaticText(self,-1,"Start:", **labelAtts)
        self.startUnits = wx.StaticText(self, -1, " ", **unitAtts)

        self.endField = wx.TextCtrl(self, -1, "end", **fieldAtts)
        endLabel = wx.StaticText(self,-1,"End:", **labelAtts)
        self.endUnits = wx.StaticText(self, -1, " ", **unitAtts)

        sizer = wx.FlexGridSizer(2,3, hgap=4, vgap=4)
        sizer.AddGrowableCol(0,-2)
        sizer.AddGrowableCol(1,-4)
        sizer.AddGrowableCol(2,-1)
        
        sizer.Add(startLabel,0,0,wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL)
        sizer.Add(self.startField,1,0)
        sizer.Add(self.startUnits, 2,0)
        
        sizer.Add(endLabel,1,0)
        sizer.Add(self.endField,1,1)
        sizer.Add(self.endUnits, 2,1)
        
        self.SetSizer(sizer)

        self.SetBackgroundColour(self.root.uiBgColor)
        self.setXUnits()
        
        self.startField.Bind(wx.EVT_TEXT_ENTER, self.OnRangeChanged)
        self.endField.Bind(wx.EVT_TEXT_ENTER, self.OnRangeChanged)


    def _setValue(self, field, val):
        """ Sets displayed value of a field. Used internally.
        """
        if val is not None:
            field.SetValue(self.formatting % (self.root.timeScalar * val))
    
    
    def _getValue(self, field, default=None):
        """ Get the value (in dataset time units) of a field.
        """
        try:
            return float(field.GetValue()) / self.root.timeScalar
        except ValueError:
            return default
        
    
    def setXUnits(self, symbol=None):
        """ Set the displayed symbol for the horizontal units (e.g. time).
        """
        symbol = self.root.units[1] if symbol is None else symbol
        self.startUnits.SetLabel(symbol)
        self.endUnits.SetLabel(symbol)
        

    def setVisibleRange(self, start=None, end=None, instigator=None, 
                        tracking=None):
        """ Set the currently visible time range.
            
            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in 
                order to avoid an infinite loop of child calling parent 
                calling child. The call is aborted if the instigator is the
                object itself.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return

        self.updating = True
        self._setValue(self.startField, start)
        self._setValue(self.endField, end)
        self.updating = False
        

    def OnRangeChanged(self, evt):
        """
        """
        start = self._getValue(self.startField)
        end = self._getValue(self.endField)
        
        if not self.updating:
            self.Parent.setVisibleRange(start, end, None, False)
            
    
#===============================================================================
# 
#===============================================================================

class Viewer(wx.Frame, MenuMixin):
    """ The main data viewer frame, wrapping all major functionality.
    """
    
    timeScalar = 1.0/(10**6)
    timerange = (1043273L * timeScalar*2,7672221086L * timeScalar)

    # Custom menu IDs
    ID_RECENTFILES = wx.NewId()
    ID_EXPORT = wx.NewId()
    ID_EXPORT_VISIBLE = wx.NewId()
    ID_RENDER_FFT = wx.NewId()
    ID_RENDER_SPEC = wx.NewId()
    ID_DEVICE_TIME = wx.NewId()
    ID_DEVICE_CONFIG = wx.NewId()
    ID_DEVICE_SET_CLOCK = wx.NewId()
    ID_VIEW_ANTIALIAS = wx.NewId()
    ID_VIEW_JITTER = wx.NewId()


    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Frame/MenuMixin arguments plus:
        
            @keyword app: The viewer's parent application.
        """
        self.app = kwargs.pop('app', None)
        self.units = kwargs.pop('units',('seconds','s'))
        self.drawingSuspended = False
        
        filename = kwargs.pop('filename', None)
        self.showDebugChannels = self.app.getPref('showDebugChannels', True)
        
        displaySize = wx.DisplaySize()
        windowSize = int(displaySize[0]*.66), int(displaySize[1]*.66)
        kwargs['size'] = kwargs.get('size', windowSize)
        
        super(Viewer, self).__init__(*args, **kwargs)
        
        self.uiBgColor = wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE)
        
        self.xFormatter = "X: %%.%df %%s" % self.app.getPref('precisionX', 4)
        self.yFormatter = "Y: %%.%df %%s" % self.app.getPref('precisionY', 4)
        
        self.buildUI()
        self.Centre()
        self.Show()
        
        self.dataset = None
        self.session = None
        self.cancelQueue = []
        
        self.plots = []
        self.setVisibleRange(self.timerange[0], self.timerange[1])
        self.antialias = False
        self.aaMultiplier = self.app.getPref('antialiasingMultiplier', 
                                             ANTIALIASING_MULTIPLIER)
        self.noisyResample = False
        
        # TODO: FFT views as separate windows will eventually be refactored.
        self.fftViews = {}
        
        self.Bind(EVT_SET_VISIBLE_RANGE, self.OnSetVisibleRange)
        self.Bind(EVT_SET_TIME_RANGE, self.OnSetTimeRange)
        self.Bind(EVT_PROGRESS_START, self.OnProgressStart)
        self.Bind(EVT_PROGRESS_UPDATE, self.OnProgressUpdate)
        self.Bind(EVT_PROGRESS_END, self.OnProgressEnd)
        self.Bind(EVT_INIT_PLOTS, self.initPlots)
        self.Bind(EVT_IMPORT_ERROR, self.handleException)
        
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        if filename:
            self.openFile(filename)
        else:
            # TODO: Remove this later? Viewer is also used to configure devices.
            self.OnFileOpenMenu(None)


    def buildMenus(self):
        """ Construct and configure the view's menu bar. Called once by
            `buildUI()`.
        """        
        self.menubar = wx.MenuBar()
        
        fileMenu = wx.Menu()
        self.addMenuItem(fileMenu, wx.ID_OPEN, "&Open...", "", 
                         self.OnFileOpenMenu)
        self.addMenuItem(fileMenu, wx.ID_CANCEL, "Stop Importing\tCrtl-.", "", 
                         self.cancelOperation, enabled=False)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, self.ID_EXPORT, "Export Data (CSV)...", "", 
                         self.exportCsv)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, self.ID_RENDER_FFT, "Render FFT...", "", 
                         self.renderFFT)
        self.addMenuItem(fileMenu, self.ID_RENDER_SPEC, "Render Spectrogram (2D FFT)...", "", 
                         self.renderSpectrogram)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_PRINT, "&Print...", "", enabled=False)
        self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, "Print Setup...", "", 
                         enabled=False)
        fileMenu.AppendSeparator()
#         self.recentFilesMenu = wx.Menu()
#         fileMenu.AppendMenu(self.ID_RECENTFILES, "Recent Files", 
#                             self.recentFilesMenu)
#         fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_EXIT, 'E&xit', '', 
                self.OnFileExitMenu, True)
        wx.App.SetMacExitMenuItemId(wx.ID_EXIT)
        self.menubar.Append(fileMenu, '&File')
        
        editMenu = wx.Menu()
        self.addMenuItem(editMenu, wx.ID_CUT, "Cut", "", enabled=False)
        self.addMenuItem(editMenu, wx.ID_COPY, "Copy", "", enabled=False)
        self.addMenuItem(editMenu, wx.ID_PASTE, "Paste", "", enabled=False)
        self.menubar.Append(editMenu, '&Edit')

        deviceMenu = wx.Menu()
        self.addMenuItem(deviceMenu, self.ID_DEVICE_CONFIG, 
                         "Configure Device...", "", self.OnDeviceConfigMenu)
#         self.addMenuItem(deviceMenu, self.ID_DEVICE_SET_CLOCK, 
#                          "Set Device Clock", "", None, enabled=False)
        self.menubar.Append(deviceMenu, 'De&vice')
        
        viewMenu = wx.Menu()
        self.addMenuItem(viewMenu, self.ID_VIEW_ANTIALIAS, 
                         "Toggle Antialiasing Drawing", "", 
                         self.OnToggleAA, kind=wx.ITEM_CHECK)
        self.addMenuItem(viewMenu, self.ID_VIEW_JITTER,
                        "Toggle Noisy Resampling", "", 
                        self.OnToggleNoise, kind=wx.ITEM_CHECK)
        self.menubar.Append(viewMenu, 'View')
        
        helpMenu = wx.Menu()
        self.addMenuItem(helpMenu, wx.ID_ABOUT, "About %s..." % APPNAME, "", 
                self.OnHelpAboutMenu)
        self.menubar.Append(helpMenu, '&Help')

        self.SetMenuBar(self.menubar)
        self.enableMenus(False)

    
    def buildUI(self):
        """
        """
        self.root = self
        self.timeDisplays = []
        
        self.SetIcon(images.icon.GetIcon())
        
        self.SetMinSize((320,240))
        
        self.navigator = TimeNavigator(self, root=self)
        self.corner = Corner(self, root=self)
        self.plotarea = PlotSet(self, -1, root=self)
        self.timeline = Timeline(self, root=self)
        
        # List of components that display time-related data.
        # The second element is whether or no they do live updates.
        self.timeDisplays = [[self.navigator, True],
                             [self.plotarea, False],
                             [self.corner, True],
                             [self.timeline, True]]
        
        sizer = RowColSizer()
        sizer.Add(self.navigator, flag=wx.EXPAND, row=0, col=0, colspan=2)
        sizer.Add(self.plotarea, flag=wx.EXPAND, row=1, col=0, colspan=2)
        sizer.Add(self.corner, flag=wx.EXPAND, row=2, col=0)
        sizer.Add(self.timeline, flag=wx.EXPAND, row=2, col=1)
        
        sizer.AddGrowableCol(1)
        sizer.AddGrowableRow(1)
        
        self.SetSizer(sizer)
        self.statusBar = StatusBar(self)
        self.SetStatusBar(self.statusBar)
        
        self.enableChildren(False)

        self.buildMenus()


    def enableMenus(self, enabled=True):
        """ Enable (or disable) all menus applicable only when a file has
            been imported.
            
            @keyword enabled: `True` (default) to enable the menus, `False`
                to disable.
        """
        # These are the menus enabled only when a file is open.
        menus = [wx.ID_CANCEL, wx.ID_REVERT, wx.ID_SAVEAS, self.ID_RECENTFILES, 
                 self.ID_EXPORT, self.ID_RENDER_FFT, wx.ID_PRINT, 
                 wx.ID_PRINT_SETUP, self.ID_VIEW_ANTIALIAS, self.ID_VIEW_JITTER,
#                  wx.ID_CUT, wx.ID_COPY, wx.ID_PASTE
                 ]
        
        for menuId in menus:
            m = self.menubar.FindItemById(menuId)
            if m is not None:
                m.Enable(enabled)
    
    
    def enableChildren(self, enabled=True):
        """ Enable (or disable) all child UI items.
            
            @keyword enabled: `True` (default) to enable the children, 
                `False` to disable.
        """
        for c in self.Children:
            c.Enable(enabled)


    def ask(self, message, title="Confirm", 
              style=wx.YES_NO | wx.NO_DEFAULT, icon=wx.ICON_QUESTION):
        """ Generate a simple modal dialog box and get the button clicked.
        """
        style |= icon
        dlg = wx.MessageDialog(self, message, title, style)
        result = dlg.ShowModal()
        dlg.Destroy()
        return result


    #===========================================================================
    # 
    #===========================================================================
    
    def initPlots(self, evt=None):
        """ Set up the plot views specified in the dataset. Should only be
            called after the file's RecordingProperties and first data block
            have been read.
            
            @param evt: The event that initiated the initialization, if any.
                Not actually used; just there for compatibility with event
                handlers.
        """
        if self.dataset is None:
            return
        
        if self.session is None:
            self.session = self.dataset.lastSession
        
        for d,c in zip(self.dataset.getPlots(debug=self.showDebugChannels), 
                       self.app.getPref('defaultColors')):
            self.plotarea.addPlot(d.getSession(self.session.sessionId), 
                                  title=d.name,
                                  scale=(65407,128), 
                                  color=c)
        
        self.enableChildren(True)

    #===========================================================================
    # 
    #===========================================================================

    def setXUnits(self, name=None, symbol=None, displayScale=timeScalar):
        """ Set the horizontal units.
        
            @keyword name: The full name of the units used.
            @keyword symbol: The symbol or abbreviation of the unit.
            @keyword displayScale: A scaling factor for displaying the data. 
        """
        if name == symbol == None:
            name = symbol = ''
        elif name is None:
            name = symbol
        else:
            symbol = name
        self.units = (name, symbol)
        
        if displayScale is not None:
            self.timeScalar = displayScale

        try:
            self.corner.setXUnits(symbol)
        except AttributeError:
            # Probably called before corner bit initialization; that's okay.
            pass
        

    #===========================================================================
    # 
    #===========================================================================
    
    def setVisibleRange(self, start=None, end=None, instigator=None, 
                        tracking=False):
        """ Set the currently visible time range. Propagates to its children.
            
            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in 
                order to avoid an infinite loop of child calling parent 
                calling child. The call is aborted if the instigator is the
                object itself.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return
        instigator = self if instigator is None else instigator
        for display, liveUpdate in self.timeDisplays:
            if liveUpdate or not tracking and display != instigator:
                display.setVisibleRange(start, end, instigator, tracking)


    def setTimeRange(self, start=None, end=None, instigator=None,
                     tracking=False):
        """ Set the time range for the entire session. Propagates to its 
            children.
            
            @keyword start: The first time in the range. Defaults to
                the current start.
            @keyword end: The last time in the range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in 
                order to avoid an infinite loop of child calling parent 
                calling child. The call is aborted if the instigator is the
                object itself.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return
        start = start if start is not None else self.timerange[0]
        end = end if end is not None else self.timerange[1]
        self.timerange = start, end 
        instigator = self if instigator is None else instigator
        for display, liveUpdate in self.timeDisplays:
            if liveUpdate or not tracking and display != instigator:
                display.setTimeRange(start, end, instigator)


    def getVisibleRange(self):
        """ Retrieve the beginning and end of the currently displayed interval
            of time.
        """
        return self.timeline.getVisibleRange()


    def getTimeRange(self):
        """ Retrieve the start and end of the current session.
        """
        return self.timerange


    #===========================================================================
    # 
    #===========================================================================

    def getDefaultImport(self):
        """ Get the path and name of the default data file. """
        # TODO: Better way of determining this
        # Maybe app-level?
        return (os.getcwd(), 'test.dat')


    def getDefaultExport(self):
        """ Get the path and name of the default export file.
        """
        # TODO: This should be based on the current filename.
        return (os.getcwd(), "export.csv")


    def getCurrentFilename(self):
        """ Returns the path and name of the currently open file.
        """
        if self.dataset is None:
            return None
        return self.dataset.filename

    
    def okayToExit(self):
        """ Returns `True` if the app is in a state to immediately quit.
        """
        # TODO: Prompt to veto quitting only if an export is underway.
        if self.app.getPref('warnBeforeQuit', True):
            return self.ask("Really quit?") == wx.ID_YES
        return True

    #===========================================================================
    # 
    #===========================================================================
    
    def openFile(self, filename):
        """
        """
        if self.dataset is not None and self.dataset.loading is True:
            if self.ask("Abort loading the current file?") != wx.ID_YES:
                return
            else:
                self.cancelOperation()
                self.closeFile()
        try:
            stream = ThreadAwareFile(filename, 'rb')
            newDoc = mide_ebml.dataset.Dataset(stream)
            self.app.addRecentFile(filename, 'import')
        # More specific exceptions should be caught here, before ultimately:
        except Exception as err:
            # Catch-all for unanticipated errors
            self.handleException(err)
            return
        
        self.dataset = newDoc
        loader = Loader(self, newDoc, **self.app.getPref('loader'))
        self.pushOperation(loader, modal=False)
        loader.start()
        self.enableMenus(True)
    
    
    def closeFile(self):
        """ Close a file. Does not close the viewer window itself.
        """
        self.plotarea.clearAllPlots()
        self.dataset = None
        self.enableChildren(False)
        self.enableMenus(False)
        
    
    def exportCsv(self, evt=None):
        """ Export the active plot view's data as CSV. after getting input from
            the user (range, window size, etc.).
            
            @keyword evt: An event (not actually used), making this method
                compatible with event handlers.
        """
        dlg = CSVExportDialog(self, -1, "Export CSV", root=self)
        result = dlg.ShowModal()
        subchannels = dlg.getSelectedChannels()
        startTime, stopTime = dlg.getExportRange()
        dlg.Destroy()
        if result == wx.ID_CANCEL or len(subchannels) == 0:
            return

        if self.dataset.loading:
            x = self.ask("A dataset is currently being loaded. This will make "
                         "exporting slow. Export anyway?")
            if x != wx.ID_OK:
                return
        
        subchannelIds = [c.id for c in subchannels]
        source = subchannels[0].parent.getSession(self.session.sessionId)
        start, stop = source.getRangeIndices(startTime, stopTime)
        
        defaultDir, defaultFile = self.getDefaultExport()
        filename = None
        dlg = wx.FileDialog(self, 
            message="Export CSV...", 
            defaultDir=defaultDir,  defaultFile=defaultFile, 
            wildcard='|'.join(self.app.getPref('exportTypes')), 
            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
        
        if filename is None:
            return

        try:
            stream = open(filename, 'w')
        except Exception as err:
            self.handleException(err)
            return
        
        self.drawingSuspended = True
        numRows = stop-start
        msg = "Exporting %d rows" % numRows
        dlg = ModalExportProgress("Exporting CSV", msg, maximum=numRows, 
                                  parent=self)
        source.exportCsv(stream, start=start, stop=stop, 
                         subchannels=subchannelIds,
                         timeScalar=self.timeScalar,
                         callback=dlg, callbackInterval=0.0005, 
                         raiseExceptions=True)
        dlg.Destroy()
        stream.close()
        self.drawingSuspended = False


    def renderFFT(self, evt=None):
        """ Create a 1D FFT plot after getting input from the user (range,
            window size, etc.).
            
            @keyword evt: An event (not actually used), making this method
                compatible with event handlers.
        """
        dlg = FFTExportDialog(self, -1, "Render FFT", root=self)
        result = dlg.ShowModal()
        subchannels = dlg.getSelectedChannels()
        startTime, stopTime = dlg.getExportRange()
        sliceSize = dlg.windowSize
        dlg.Destroy()
        
        if result == wx.ID_CANCEL:
            return
        elif len(subchannels) == 0 or (startTime >= stopTime):
            return
        
        subchannels.sort(key=lambda x: x.name)
#         subchannelIds = [c.id for c in subchannels]
        source = subchannels[0].parent.getSession(self.session.sessionId)
        start, stop = source.getRangeIndices(startTime, stopTime)
        numRows = stop-start
        if numRows < 1:
            self.ask("Selected range contained no data!", "Render FFT",
                     style=wx.OK, icon=wx.ICON_ERROR)
            return
            
        if self.dataset.loading:
            x = self.ask("A dataset is currently being loaded. This will make "
                         "FFT generation slow. Proceed anyway?")
            if x != wx.ID_OK:
                return
        
        title = "FFT: %s (%ss to %ss)" % (
                                      ", ".join([c.name for c in subchannels]), 
                                      startTime * self.timeScalar, 
                                      stopTime * self.timeScalar)
        viewId = wx.NewId()
        
        try:
            view = fft.FFTView(self, viewId, title=title, size=self.GetSize(), 
                               root=self, sources=subchannels, 
                               start=startTime, end=stopTime,
                               sliceSize=sliceSize)
            self.fftViews[viewId] = view
        except Exception as e:
            self.handleException(e, what="generating FFT")
        


    def renderSpectrogram(self, evt=None):
        """
        """
        # XXX: IMPLEMENT renderSpectrogram!
        self.ask("Render Spectrogram not yet implemented!", "Not Implemented", wx.OK, wx.ICON_INFORMATION)
        
    #===========================================================================
    # 
    #===========================================================================
    
    def OnClose(self, evt):
        """ Close the viewer.
        """
        if evt.CanVeto():
            if not self.okayToExit():
                evt.Veto()
                return False
            
        self.app.savePrefs()

        # Kill all background processes
        for _ in self.cancelQueue:
            self.cancelOperation()
        self.Destroy()
        evt.Skip()
    
    
    #===========================================================================
    # Menu Events
    #===========================================================================

    def OnFileOpenMenu(self, evt):
        """ Handle File->Open menu events.
        """
        defaultDir, defaultFile = self.getDefaultImport()
        dlg = wx.FileDialog(self, 
                            message="Choose a file",
                            defaultDir=defaultDir, 
                            defaultFile=defaultFile,
                            wildcard="|".join(self.app.getPref('importTypes')),
                            style=wx.OPEN|wx.CHANGE_DIR|wx.FILE_MUST_EXIST)
        dlg.SetFilterIndex(0)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            if self.dataset is None or self.dataset.filename == filename:
                self.openFile(filename)
            else:
                openNew = self.ask("Are you sure you want to close the "
                                   "current file and open another?", 
                                   "Open File", style=wx.YES_NO|wx.CANCEL)
                if openNew == wx.ID_YES:
                    self.openFile(filename)
            
        # Note to self: do this last!
        dlg.Destroy()


    def OnFileExitMenu(self, evt):
        """ Handle File->Exit menu events. 
        """
        if self.okayToExit():
            self.Close()


    def OnFileReloadMenu(self, evt):
        """ Handle File->Reload menu events.
        """
        # XXX: IMPLEMENT OnFileReload!
        self.ask("File:Reload not yet implemented!", "Not Implemented", wx.OK, wx.ICON_INFORMATION)


    def OnDeviceConfigMenu(self, evt):
        """ Handle Device->Configure Device menu events.
        """
        dev = selectDevice()
        if dev is not None:
            config_dialog.configureRecorder(dev)
    
    
    def OnHelpAboutMenu(self, evt):
        """ Handle Help->About menu events.
        """
        # Goofy trick to reformat the __doc__ for the dialog:
        desc = dedent(__doc__[:__doc__.index("###")])
        desc = desc.replace('\n\n','\0').replace('\n',' ').replace('\0','\n\n')
        
        info = wx.AboutDialogInfo()
        info.Name = APPNAME
        info.Version = __version__
        info.Copyright = __copyright__
        info.Description = wordwrap(desc, 350, wx.ClientDC(self))
        info.WebSite = __url__
#         info.Developers = __credits__
#         info.License = wordwrap(__license__, 500, wx.ClientDC(self))
        wx.AboutBox(info)
    

    def OnToggleAA(self, evt):
        self.antialias = evt.IsChecked()
        self.plotarea.redraw()
        

    def OnToggleNoise(self, evt):
        if evt.IsChecked():
            self.noisyResample = self.app.getPref('resamplingJitter', 
                                                  RESAMPLING_JITTER)
        else:
            self.noisyResample = 0
        self.plotarea.redraw()

    #===========================================================================
    # Custom Events
    #===========================================================================
    
    def OnSetVisibleRange(self, evt):
        """ Handle the event signifying a change in visual range. Used
            primarily by the import thread.
        """
        self.setVisibleRange(evt.start, evt.end, instigator=evt.instigator, 
                             tracking=evt.tracking)
        
        
    def OnSetTimeRange(self, evt):
        """ Handle the event signifying a change in the dataset's total
            time range. Used primarily by the import thread.
        """
        self.setTimeRange(evt.start, evt.end, instigator=evt.instigator, 
                          tracking=evt.tracking)
        
        
    def OnProgressStart(self, evt):
        """ Handle the event signifying the start of the progress bar. Used
            primarily by the import thread.
        """
        self.statusBar.startProgress(evt.label, evt.initialVal, 
                                     evt.cancellable, evt.cancelEnabled)
        if evt.cancellable:
            self.menubar.FindItemById(wx.ID_CANCEL).Enable(True)



    def OnProgressUpdate(self, evt):
        """ Handle the event signifying an update of the progress bar. Used
            primarily by the import thread.
        """
        self.statusBar.updateProgress(val=evt.val, label=evt.label, 
                                      cancellable=evt.cancellable)
    
    
    def OnProgressEnd(self, evt):
        """ Handle the event signifying a the completion of the progress bar. 
            Used primarily by the import thread.
        """
        self.statusBar.stopProgress(evt.label)
        self.menubar.FindItemById(wx.ID_CANCEL).Enable(False)


    #===========================================================================
    # 
    #===========================================================================

    def pushOperation(self, job, modal=False):
        """ 
        """
        self.cancelQueue.append(job)
        

    def cancelOperation(self, evt=None, prompt=None, title="Cancel"):
        """ Cancel the current background operation. 
            
            @keyword evt: The event that initiated the cancel.
            @keyword prompt: A message to display before actually committing
                to the cancel. If `None` (default), the cancel is immediately
                processed.
            @return: `False` if the operation could not be cancelled,
                or a message string to display upon cancellation.
                Anything but `False` is considered a successful shutdown.
        """
        # if the cancel takes some time to take effect, the thing that
        # caused it could be disabled like this (to prevent extra clicks):
        # evt.EventObject.Enable(False)
        
        if len(self.cancelQueue) == 0:
            # Nothing to cancel. Shouldn't happen.
            self.stopBusy()
            return ""
        
        if prompt is not None:
            if prompt is True:
                prompt = "Are you sure you want to cancel?"
            if self.ask(unicode(prompt), title) != wx.ID_YES:
                return False
        
        job = self.cancelQueue[-1]
        cancelled = job.cancel()
        if cancelled:
            msg = job.cancelledMsg
            self.cancelQueue.remove(job)
            self.stopBusy()
            return msg


    #===========================================================================
    # 
    #===========================================================================
    
    def startBusy(self, cancellable=False):
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
        if cancellable:
            self.menubar.FindItemById(wx.ID_CANCEL).Enable(True)
        self.busy = True

    def stopBusy(self):
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        self.menubar.FindItemById(wx.ID_CANCEL).Enable(False)
        self.busy = False

    
    #===========================================================================
    # 
    #===========================================================================
    
    def showMouseHPos(self, pos, units=None):
        """ Display the X axis value for a given mouse position. All Plots
            within the same PlotArea use the same horizontal axis scale/units.
        """
        if pos is None:
            msg = ""
        else:
            units = self.units[1] if units is None else units
            msg = self.xFormatter % (
                        self.timeline.getValueAt(pos) * self.timeScalar, units)
        self.statusBar.SetStatusText(msg, self.statusBar.xFieldNum)
        
    
    def showMouseVPos(self, pos, units=""):
        """ Show a Y axis value, presumably calculated from the current
            Plot's vertical axis. This will vary between Plots, so unlike
            `showMouseHPos()`, this will show a literal value.
            
            @param h: 
        """
        if pos is None:
            msg = ""
        else:
            msg = self.yFormatter % (pos, units)
        self.statusBar.SetStatusText(msg, self.statusBar.yFieldNum)


    #===========================================================================
    # 
    #===========================================================================
    
    def handleException(self, err, msg=None, icon=wx.ICON_ERROR, 
                        raiseException=False, what=None, where=None,
                        fatal=False):
        """ General-purpose exception handler that attempts to provide a 
            meaningful error message. Also works as an event handler for
            custom error events (e.g. `EvtImportError`). Exception handling
            elsewhere in the program should attempt to catch expected
            exceptions first, then call this for the naked `Exception`.
            
            @param err: The raised exception, an event object (e.g.
                `EvtImportError`), or `None`.
            @keyword msg: An alternative error message, to be shown verbatim.
            @keyword icon: The icon to show in the dialog box.
            @keyword raiseException: If `True`, the exception will be raised
                before the dialog is displayed.
            @keyword what: A description of the operation being performed that
                raised the exception.
            @keyword where: The method in which the exception was raised; a
                lightweight sort of traceback.
            @keyword fatal: If `True`, the app Viewer will shut down. 
                
        """
        if isinstance(err, wx.Event):
            err = err.err
            msg = getattr(err, 'msg', None)
        
        if what is not None:
            what = " while %s" % what
        
        if not isinstance(msg, basestring):
            # Slightly more specific error messages go here.
            if isinstance(err, MemoryError):
                msg = "The system ran out of memory%s"
            else:
                msg = u"An unexpected %s occurred%%s:\n\n%s" % \
                        (err.__class__.__name__, unicode(err))

        # If exceptions are explicitly raised, raise it.
        if raiseException and isinstance(err, Exception):
            raise err

        if fatal:
            msg += "\n\nThe application will now shut down."

        dlg = wx.MessageDialog(self, msg % what, APPNAME, wx.OK | icon)
        dlg.ShowModal()
        ctrlPressed = wx.GetKeyState(wx.WXK_CONTROL)
        dlg.Destroy()
        
        # Holding control when okaying alert shows more more info. 
        if ctrlPressed and isinstance(err, Exception):
            # TODO: Use a better error log display than stderr
            raise err
        
        # The error occurred someplace critical; self-destruct!
        if fatal:
            self.Destroy()
 

#===============================================================================
# 
#===============================================================================

class ViewerApp(wx.App):
    """ The main class of the SSX Data Viewer. Most of the work is done by the
        Viewer; the app mainly handles global settings like preferences 
        (and the primary functionality inherited from `wx.App`, of course).
    """
    
#     prefsFile = os.path.realpath(os.path.expanduser("~/.ssx_viewer.cfg"))
    prefsFile = os.path.realpath(os.path.join(os.path.dirname(__file__), 
                                              'ssx_viewer.cfg'))
    
    defaultPrefs = {
        'importTypes': ["MIDE Data File (*.ide)|*.ide", 
                        "Slam Stick X Data File (*.dat)|*.dat",
                        "All files (*.*)|*.*"],
        'exportTypes': ["Comma Separated Values (*.csv)|*.csv"],
        'fileHistory': {},
        'fileHistorySize': 10,
        
        # Precision display of numbers
        'precisionX': 4,
        'precisionY': 4,
        
        # Rendering
        'antialiasing': False,
        'antialiasingMultiplier': ANTIALIASING_MULTIPLIER,
        'resamplingJitter': False,
        'resamplingJitterAmount': RESAMPLING_JITTER,
        'originHLineColor': wx.Colour(200,200,200),
        'majorHLineColor': wx.Colour(220,220,220),
        'minorHLineColor': wx.Colour(240,240,240),
        'defaultColors': ["RED",
                          "GREEN",
                          "BLUE",
                          "DARK GREEN",
                          "VIOLET",
                          "GREY",
                          "YELLOW",
                          "MAGENTA",
                          "NAVY",
                          "PINK",
                          "SKY BLUE",
                          "BROWN",
                          "CYAN",
                          "DARK GREY",
                          "GOLD",
                          "BLACK",
                          "BLUE VIOLET"],
        # TODO: Stop using defaultColors, use plotColors instead (with default
        #    as a set of colors for unknown devices/channels (there shouldn't be
        #    any for this release of the software).
        'plotColors': {"00.0": "BLUE",
                       "00.1": "GREEN",
                       "00.2": "RED",
                       "01.0": "DARK GREEN",
                       "01.1": "VIOLET"
        },

        'locale': 'LANGUAGE_ENGLISH_US', # wxPython constant name
#         'locale': 'English_United States.1252', # Python's locale name string
        'loader': dict(numUpdates=100, updateInterval=1.0),
        'warnBeforeQuit': False, #True,
        'showDebugChannels': False,

        # WVR/SSX-specific parameters: the hardcoded warning range.        
        'wvr_tempMin': -20.0,
        'wvr_tempMax': 60.0,
    }


    def loadPrefs(self, filename=None):
        """ Load saved preferences from file.
        """
        def tuple2color(c):
            if isinstance(c, list):
                return wx.Colour(*c)
            return c
        
        filename = filename or self.prefsFile
        if not filename:
            return {}
        
        filename = os.path.realpath(os.path.expanduser(filename))

        try:
            with open(filename) as f:
                prefs = json.load(f)
                if isinstance(prefs, dict):
                    # De-serialize *Color attributes (single colors)
                    for k in fnmatch.filter(prefs.keys(), "*Color"):
                        prefs[k] = tuple2color(prefs[k])
                    # De-serialize *Colors attributes (lists of colors)
                    for k in fnmatch.filter(prefs.keys(), "*Colors"):
                        if isinstance(prefs[k], list):
                            for i in xrange(len(prefs[k])):
                                prefs[k][i] = tuple2color(prefs[k][i])
                    return prefs
        except Exception:#IOError as err:
            # TODO: Report a problem, or just ignore?
            pass
        return {}


    def savePrefs(self, filename=None, hideFile=None):
        """ Write custom preferences to a file.
        """
        filename = filename or self.prefsFile
        
        if hideFile is None:
            hideFile = os.path.basename(filename).startswith(".")
        
        filename = os.path.realpath(os.path.expanduser(filename))
            
        prefs = self.prefs.copy()
        # Convert wx.Colour objects and RGB sequences to tuples:
        for k in fnmatch.filter(prefs.keys(), "*Color"):
            if not isinstance(prefs[k], basestring):
                prefs[k] = tuple(prefs[k])
        for k in fnmatch.filter(prefs.keys(), "*Colors"):
            for i in xrange(len(prefs[k])):
                if not isinstance(prefs[k][i], basestring):
                    prefs[k][i] = tuple(prefs[k][i])
        try:
            with open(filename, 'w') as f:
                json.dump(prefs, f, indent=2, sort_keys=True)
            if hideFile and "win" in sys.platform:
                os.system('attrib +h "%s"' % filename)
        except IOError:# as err:
            # TODO: Report a problem, or just ignore?
            pass
    
    
    def addRecentFile(self, filename, category="import"):
        """ Add a file to a history list. If the list is at capacity, the
            oldest file is removed.
        """
        allFiles = self.prefs.setdefault('fileHistory', {})
        files = allFiles.setdefault(category, [])
        if filename:
            if filename in files:
                files.remove(filename)
            files.insert(0,filename)
        allFiles[category] = files[:(self.getPref('fileHistorySize'))]


    def getPref(self, *args):
        """
        """
        return self.prefs.get(args[0], self.defaultPrefs.get(*args))


    def setPref(self, name, val):
        """
        """
        self.prefs[name] = val

    #===========================================================================
    # 
    #===========================================================================

    def __init__(self, *args, **kwargs):
        prefsFile = kwargs.pop('prefsFile', self.prefsFile)
        if prefsFile is not None:
            self.prefsFile = prefsFile
        self.initialFilename = kwargs.pop('filename')
        
        self.prefs = self.loadPrefs(self.prefsFile)
#         locale.setlocale(locale.LC_ALL, str(self.getPref('locale')))
        
        self.viewers = []
        
        super(ViewerApp, self).__init__(*args, **kwargs)
        localeName = self.getPref('locale', 'LANGUAGE_ENGLISH_US')
        self.locale = wx.Locale(getattr(wx, localeName, wx.LANGUAGE_ENGLISH_US))

        
    def createNewView(self, title=None, filename=None):
        """ Create a new viewer window.
        """
        if title is None:
            title = u'%s v%s' % (APPNAME, __version__)
        viewer = Viewer(None, title=title, app=self, filename=filename)
        self.viewers.append(viewer)
        viewer.Show()
        

    def OnInit(self):
        self._antiAliasingEnabled = True
        self.createNewView(filename=self.initialFilename)
        
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        return True


    def OnClose(self, evt):
        evt.Skip()
        if len(self.viewers) > 0:
            evt.Veto()
            return
        self.savePrefs(self.prefsFile)
        
#===============================================================================
# 
#===============================================================================

# XXX: Change this back for 'real' version
if __name__ == '__main__' or True:
    import argparse
    parser = argparse.ArgumentParser(description=APPNAME)
    parser.add_argument('--filename', '-f', 
                        help="The name of the MIDE file to import")
    parser.add_argument("--prefsFile", '-p', 
                        help="An alternate preferences file")
    args = parser.parse_args()

    app = ViewerApp(**vars(args))
    app.MainLoop()