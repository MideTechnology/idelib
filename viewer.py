'''
Slam Stick eXtreme Data Viewer

Description should go here. At the moment, this is also the text that appears
in the About Box.

'''

APPNAME = u"Slam Stick X Data Viewer"
__version__="0.0.1"
__created__="Oct 21, 2013"
__date__="Oct 21, 2013"
__copyright__=u"Copyright (c) 2013 MID\xc9 Technology"
__url__ = ("http://mide.com", "")
__credits__=["David R. Stokes", "Tim Gipson"]

from datetime import datetime
# import errno
import fnmatch
import json
import locale
import os
import sys
from threading import Thread

from wx import aui
from wx.lib.rcsizer import RowColSizer
from wx.lib.wordwrap import wordwrap
import wx; wx = wx # Workaround for Eclipse code comprehension

from base import *

# Custom controls
from timeline import TimelineCtrl, TimeNavigatorCtrl, VerticalScaleCtrl
from timeline import EVT_INDICATOR_CHANGED
from export_dialog import ModalExportProgress, ExportDialog

# Graphics (icons, etc.)
import images

# Special helper objects and functions
from threaded_file import ThreadAwareFile

# The actual data-related stuff
import mide_ebml

ANTIALIASING_MULTIPLIER = 6.66
RESAMPLING_JITTER = 0.125

#===============================================================================
# 
#===============================================================================

def expandRange(l, v):
    """ Given a two element list containing a minimum and maximum value, 
        expand it if the given value is outside that range. 
    """
    l[0] = min(l[0],v)
    l[1] = max(l[1],v)


#===============================================================================
# 
#===============================================================================




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

class StatusBar(wx.StatusBar):
    """
    The viewer status bar.  It mainly provides a progress bar and status text
    when the Viewer is doing something in the background (i.e. file import or
    export). The progress bar can show an actual value, or it can just run 
    continuously.
    """
    frameDelay = 30
    numFields = 6
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments, plus:
        
            @keyword root: The viewer's 'root' window.
        """
        self.root = kwargs.pop('root', None)
        wx.StatusBar.__init__(self, *args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        
        logo = images.MideLogo.GetBitmap()
        self.logo = wx.StaticBitmap(self, -1, logo)

        self.progressBar = wx.Gauge(self, -1, 1000)
        self.cancelButton = wx.Button(self, wx.ID_CANCEL, style=wx.BU_EXACTFIT)
        bwidth, bheight = self.cancelButton.GetBestSize()
        self.buttonWidth = bwidth + 2
        self.cancelButton.SetSize((bwidth, bheight-2))

        fieldWidths = [-1] * self.numFields

        self.buttonFieldNum = self.numFields-1
        self.progressFieldNum = self.numFields-2
        self.messageFieldNum = self.numFields-3
        self.yFieldNum = self.numFields-4
        self.xFieldNum = self.numFields-5
        self.logoFieldNum = 0

        fieldWidths[self.logoFieldNum] = logo.GetSize()[0]
        fieldWidths[self.messageFieldNum] = -4
        fieldWidths[self.progressFieldNum] = -2
        fieldWidths[self.buttonFieldNum] = bwidth

        self.SetFieldsCount(self.numFields)
        self.SetStatusWidths(fieldWidths)

        self.SetStatusText("Welcome to %s v%s" % (APPNAME, __version__), 
                           self.messageFieldNum)

        self.Bind(wx.EVT_SIZE, self.repositionProgressBar)
        self.Bind(wx.EVT_BUTTON, self.OnCancelClicked, self.cancelButton)
        
        self.repositionProgressBar()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.TimerHandler)


    def __del__(self):
        self.timer.Stop()


    def OnCancelClicked(self, evt):
        """ Process a click to the 'Cancel' button, checking with the parent
            to make sure it's okay.
        """
        cancelled = self.GetParent().cancelOperation(evt, prompt=True)
        if cancelled is not False:
            if isinstance(cancelled, basestring):
                self.stopProgress(cancelled)
            else:
                self.stopProgress()


    def TimerHandler(self, event):
        """ Update the indefinite progress bar (if active). 
        """
        self.progressBar.Pulse()
   
        
    def repositionProgressBar(self, evt=None):
        """ The positions of the progress bar and cancel button need to be 
            manually set after resize.
            
            @keyword evt: The event that triggered the repositioning.
        """
        rect = self.GetFieldRect(self.numFields-2)
        self.progressBar.SetSize((rect.width-8, rect.height-8))
        self.progressBar.SetPosition((rect.x+4, rect.y+4))
        
        buttonRect = self.GetFieldRect(self.numFields-1)
        self.cancelButton.SetPosition(buttonRect[:2])

        
    def startProgress(self, label="Working...", initialVal=0, cancellable=True,
                      cancelEnabled=None, delay=frameDelay):
        """ Start the progress bar, showing a specific value.
        
            @keyword label: Text to display in the status bar.
            @keyword initialVal: The starting value displayed. -1 will start
                the progress bar in indefinite mode.
            @keyword cancellable: If `True`, the Cancel button will be visible.
            @keyword cancelEnabled: If `False` and `cancellable` is `True`,
                the Cancel button will be visible but disabled (grayed out).
                For use in cases where a process can only be cancelled after
                a certain point.
        """
        self.SetStatusText(label, 0)
        self.progressBar.Show(True)
        if initialVal < 0 or initialVal > 1.0:
            self.timer.Start(delay)
        else:
            self.timer.Stop()
            self.progressBar.SetValue(initialVal*1000.0)
            
        cancelEnabled = cancellable if cancelEnabled is None else cancelEnabled
        self.cancelButton.Show(cancellable)
        self.cancelButton.Enable(cancelEnabled)


    def updateProgress(self, val=None, label=None, cancellable=None):
        """ Change the progress bar's value and/or label. If the value is
            greater than 1.0, the bar automatically changes to its
            'throbber' mode (indefinite cycling bar).
        
            @param val: The value to display on the progress bar, as a
                normalized float.
            @keyword label: Text to display in the status bar.
            @keyword cancelEnabled: If the Cancel button is visible,
                `True` will enable it, `False` will disable it.
                `None` (default) will leave it as-is.
        """
        self.progressBar.Show(True)

        if label is not None:
            self.SetStatusText(label, self.messageFieldNum)
        if cancellable is not None:
            self.cancelButton.Enable(cancellable)
            if cancellable is True:
                self.progressBar.Show(True)
            
        if val is None:
            return
        
        if val > 1.0 or val < 0:
            if not self.timer.IsRunning():
                self.timer.Start(self.frameDelay)
        else:
            if self.timer.IsRunning():
                self.timer.Stop()
            self.progressBar.SetValue(val*1000.0)

        
    def stopProgress(self, label=""):
        """ Hide the progress bar and Cancel button (if visible).
            
            @keyword label: Text to display in the status bar.
        """
        self.timer.Stop()
        if label is not None:
            self.SetStatusText(label, self.messageFieldNum)
        self.progressBar.Show(False)
        self.cancelButton.Show(False)


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
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
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
        self.currentTime = 1000 # the start of the displayed interval, in microseconds
        self.displayLength = 5000 # The length of the displayed interval, in microseconds
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
                self.scrollUnitsPerUSec * (self.currentTime - self.timerange[0]), 
                self.scrollUnitsPerUSec * self.displayLength, 
                self._sbMax,
                self.scrollUnitsPerUSec * self.displayLength)
        
        self.unitsPerPixel = (self.displayLength/self.timebar.GetSize()[0] + 0.0)
        
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
    """ The full timeline view shown above the graph. Includes moveable markers 
        showing the currently visible interval.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
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
                                             self.OnZoomOut)
        self.zoomInButton = self._addButton(sizer, images.zoomInH,
                                            self.OnZoomIn)
        self.zoomFitButton = self._addButton(sizer, images.zoomFitH,
                                             self.OnZoomFit)
        
        self.SetSizer(sizer)
        
        self.movingMarks = False
        
        self.Bind(EVT_INDICATOR_CHANGED, self.OnMarkChanged)
        self.timeline.Bind(wx.EVT_LEFT_UP, self.OnMouseLeftUp)
        

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
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
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
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
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
                                            self.OnZoomIn)
        self.zoomOutButton = self._addButton(subsizer, images.zoomOutV, 
                                             self.OnZoomOut)
        self.zoomFitButton = self._addButton(subsizer, images.zoomFitV, 
                                             self.OnZoomFit)
        
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

class PlotCanvas(wx.ScrolledWindow):
    """ The actual plot-drawing area.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
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
        
        self.originHLinePen = wx.Pen(
            self.root.app.getPref("originHLineColor", "GRAY"), 1, wx.SOLID)
        self.majorHLinePen = wx.Pen(
            self.root.app.getPref("majorHLineColor", "GRAY"), 1, wx.DOT)
        self.minorHLinePen = wx.Pen(
            self.root.app.getPref("minorHLineColor", "GRAY"), 1, wx.DOT)
        
        self.lines = None
        self.points = None
        self.lastEvents = None
        self.lastRange = None

        self.setPen()
        
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
                
    
    def setPen(self, color=None, weight=None, style=wx.SOLID):
        """
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
        print "PlotCanvas.setTimeRange"
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


    def makeHGridlines(self, points, width, scale):
        return [(0, p.pos * scale, width * scale, p.pos * scale) for p in points]


    def OnPaint(self, evt):
        """ Event handler to redraw the plot.
        """
        if self.Parent.source is None:
            return
        
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))

        self.InvalidateBestSize()
        dc = wx.PaintDC(self)
        dc.SetAxisOrientation(True,False)
        dc.Clear()

        size = dc.GetSize()
        
        # XXX: EXPERIMENTAL ANTIALIASING
        viewScale = 1.0
        oversampling = 3.33
        if self.root.antialias:
            dc = wx.GCDC(dc)
            viewScale = self.root.aaMultiplier
            oversampling = viewScale * 1.33
            dc.SetUserScale(1/viewScale,1/viewScale)
        
        dc.BeginDrawing()

        legend = self.Parent.legend
        
        tenth = size[0]/10 * viewScale
        
        hRange = map(int,self.root.getVisibleRange())
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
        
        # Get the horizontal grid lines. 
        # NOTE: This might not work in the future. Consider modifying
        #    VerticalScaleCtrl to ensure we've got access to the labels!
        majorHLines = []
        minorHLines = []
        if self.Parent.drawMajorHLines:
            self.majorHLinePen.SetWidth(viewScale)
            majorHLines = self.makeHGridlines(legend.scale._majorlabels, size[0], viewScale)
        if self.Parent.drawMinorHLines:
            minorHLines = self.makeHGridlines(legend.scale._miorlabels, size[0], viewScale)

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
            
#             print "iterResampledRange(%s, %s, %s)" % (hRange[0], hRange[1], size[0]*3.33),
#             print "timespan:", hRange[1]-hRange[0]
#             print "no. events:", i, "source len:", len(self.Parent.source)

            try:
                self.Parent.visibleValueRange = [sys.maxint, -sys.maxint]
                event = events.next()
                expandRange(self.Parent.visibleValueRange, event[-1])
                lastPt = ((event[-2] - hRange[0]) * hScale, 
                          (event[-1] - vRange[0]) * vScale)
                
                for i, event in enumerate(events):
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
                # This will occur if there are no events, but that's okay.
                pass

            # Draw the remaining lines (if any)
            dc.DrawLineList(lineSubset)

        else:
            # No change in displayed range; Use cached lines.
            dc.DrawLineList(self.lines)
#         print "len lines:", len(self.lines), size, self.lines[-1]
        
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
        
#         for l in self.lines[-10:]: print l
        
        dc.EndDrawing()
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


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
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
        """
        self.source = kwargs.pop('source', None)
        self.yUnits= kwargs.pop('units',None)
        color = kwargs.pop('color', 'BLACK')
        scale = kwargs.pop('scale', (-1,1))
        self.range = kwargs.pop('range', (-(2**16), (2**16)-1))
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
        
        scale = self.source.displayRange if getattr(self.source, 
                                                    'hasDisplayRange', False) \
                                                    else scale
        
        self.legend = LegendArea(self, -1, visibleRange=(max(*scale),min(*scale)))
        self.plot = PlotCanvas(self, -1, color=color)#, style=wx.FULL_REPAINT_ON_RESIZE)
        self.scrollbar = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.legend, 0, wx.EXPAND)
        sizer.Add(self.plot, -1, wx.EXPAND)
        sizer.Add(self.scrollbar, 0, wx.EXPAND)
        self.SetSizer(sizer)
        self.legend.SetSize((self.Parent.Parent.corner.GetSize()[0],-1))
        
        self.plot.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseLeave)

        # TODO: Finish scrolling implementation
        self.scrollbar.Enable(False)
        self._bindScrollEvents(self.scrollbar, self.OnScroll, 
                              self.OnScrollTrack, self.OnScrollEnd)
        

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
        
#         self.scrollUnitsPerUnit = self._sbMax / (start-end)
#         self.scrollbar.SetScrollbar(self.scrollUnitsPerUnit * (self.currentTime - self.timerange[0]), 
#                                     self.scrollUnitsPerUSec * self.displayLength, 
#                                     self._sbMax,
#                                     self.scrollUnitsPerUSec * self.displayLength)
                                    
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
    
    def OnMouseLeave(self, evt):
        self.root.showMouseHPos(None)
        self.root.showMouseVPos(None)
        evt.Skip()

#===============================================================================
# 
#===============================================================================

class PlotSet(aui.AuiNotebook):
    """ A tabbed window containing multiple Plots. The individual plots (pages)
        can be accessed by index like a tuple or list.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
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
        """
        """
        p = self.GetSelection()
        if p == -1:
            return None
        return self.GetPage(p)
        
        
    def addPlot(self, source, title=None, name=None, scale=None, color="BLACK", units=None):
        """ Add a new Plot to the display.
        
            @param source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
            @keyword title: The name displayed on the plot's tab
                (defaults to 'Plot #')
        """

        title = source.name or title
        title = "Plot %s" % len(self) if title is None else title
        name = name or title
        
        if scale is None:
            scale = getattr(source, "displayRange", (-1.0,1.0))
            
        plot = Plot(self, source=source, root=self.root, scale=scale, 
                    color=color, units=units)
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

class Viewer(wx.Frame):
    """ The main data viewer frame, wrapping all major functionality.
    """
    
    timeScalar = 1.0/(10**6)
    timerange = (1043273L * timeScalar*2,7672221086L * timeScalar)

    ID_RECENTFILES = wx.NewId()
    ID_EXPORT = wx.NewId()
    ID_EXPORT_VISIBLE = wx.NewId()
    ID_DEVICE_TIME = wx.NewId()
    ID_DEVICE_CONFIG = wx.NewId()
    ID_DEVICE_SET_CLOCK = wx.NewId()


    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
            @keyword app: The viewer's parent application.
        """
        self.app = kwargs.pop('app', None)
        self.units = kwargs.pop('units',('seconds','s'))
        self.drawingSuspended = False
        
        self.showDebugChannels = self.getPref('showDebugChannels', True)
        
        displaySize = wx.DisplaySize()
        windowSize = int(displaySize[0]*.66), int(displaySize[1]*.66)
        kwargs['size'] = kwargs.get('size', windowSize)
        
        super(Viewer, self).__init__(*args, **kwargs)
        
        self.uiBgColor = wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE)
        
        self.InitUI()
        self.Centre()
        self.Show()
        
        self.dataset = None
        self.session = None
        self.cancelQueue = []
        
        self.plots = []
        self.setVisibleRange(self.timerange[0], self.timerange[1])
        self.antialias = False
        self.aaMultiplier = ANTIALIASING_MULTIPLIER
        self.noisyResample = False
        
        self.Bind(EVT_SET_VISIBLE_RANGE, self.OnSetVisibleRange)
        self.Bind(EVT_SET_TIME_RANGE, self.OnSetTimeRange)
        self.Bind(EVT_PROGRESS_START, self.OnProgressStart)
        self.Bind(EVT_PROGRESS_UPDATE, self.OnProgressUpdate)
        self.Bind(EVT_PROGRESS_END, self.OnProgressEnd)
        self.Bind(EVT_INIT_PLOTS, self.initPlots)
        self.Bind(EVT_IMPORT_ERROR, self.handleException)
        
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # TODO: Remove this later? 
        self.OnFileOpenMenu(None)


    def InitMenus(self):
        """ Construct and configure the view's menu bar. Called one by
            `InitUI()`.
        """        
        self.menuItems = {}
        
        # Just to make the menu adding less tedious
        def addItem(menu, id_, text, helpString, handler, enabled=True, 
                    kind=wx.ITEM_NORMAL):
            item = menu.Append(id_, text, helpString, kind)
            item.Enable(enabled)
            if handler is not None:
                self.Bind(wx.EVT_MENU, handler, item)
            self.menuItems[id] = item
            return item
        
        self.menubar = wx.MenuBar()
        
        fileMenu = wx.Menu()
        addItem(fileMenu, wx.ID_OPEN, "&Open...", "", 
                self.OnFileOpenMenu, True)
        addItem(fileMenu, wx.ID_CANCEL, "Stop Loading File\tCrtl-.", "", 
                self.cancelOperation, False)
        addItem(fileMenu, wx.ID_REVERT, "&Reload Current File", "", 
                self.OnFileReloadMenu, False)
        fileMenu.AppendSeparator()
        addItem(fileMenu, self.ID_EXPORT, "Export Data...", "", 
                self.OnFileExportMenu, True)
        fileMenu.AppendSeparator()
        addItem(fileMenu, wx.ID_PRINT, "&Print...", "", 
                None, False)
        addItem(fileMenu, wx.ID_PRINT_SETUP, "Print Setup...", "", 
                None, False)
        fileMenu.AppendSeparator()
#         self.recentFilesMenu = wx.Menu()
#         fileMenu.AppendMenu(self.ID_RECENTFILES, "Recent Files", self.recentFilesMenu)
#         fileMenu.AppendSeparator()
        addItem(fileMenu, wx.ID_EXIT, 'E&xit', '', 
                self.OnFileExitMenu, True)
        wx.App.SetMacExitMenuItemId(wx.ID_EXIT)
        self.menubar.Append(fileMenu, '&File')
        
        editMenu = wx.Menu()
        addItem(editMenu, wx.ID_CUT, "Cut", "", None, False)
        addItem(editMenu, wx.ID_COPY, "Copy", "", None, False)
        addItem(editMenu, wx.ID_PASTE, "Paste", "", None, False)
        self.menubar.Append(editMenu, '&Edit')

        deviceMenu = wx.Menu()
        addItem(deviceMenu, self.ID_DEVICE_CONFIG, "Configure Device...", "",
                None, False)
        addItem(deviceMenu, self.ID_DEVICE_SET_CLOCK, "Set Device Clock", "",
                None, False)
        self.menubar.Append(deviceMenu, 'De&vice')
        
        
        debugMenu = wx.Menu()
        addItem(debugMenu, wx.NewId(), "Toggle Antialiasing Drawing", 
                "Primarily a visual effect, although it does do more resampling", 
                self.DEBUG_OnToggleAA, kind=wx.ITEM_CHECK)
        addItem(debugMenu, wx.NewId(), "Toggle Noisy Resampling", "", 
                self.DEBUG_OnToggleNoise, kind=wx.ITEM_CHECK)
        self.menubar.Append(debugMenu, 'DEBUG')
        
        helpMenu = wx.Menu()
        addItem(helpMenu, wx.ID_ABOUT, "About %s..." % APPNAME, "", 
                self.OnHelpAboutMenu)
        self.menubar.Append(helpMenu, '&Help')

        self.SetMenuBar(self.menubar)
        
    
    def InitUI(self):
        """
        """
        self.root = self
        self.timeDisplays = []
        
        self.SetIcon(images.icon.GetIcon())
#         self.SetIcon(wx.Icon("images/ssx_icon_white.png", 
#                              wx.BITMAP_TYPE_PNG))
        
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

        self.InitMenus()


    def enableMenus(self, enabled=True):
        """ Enable (or disable) all menus applicable only when a file has
            been imported.
            
            @keyword enabled: `True` (default) to enable the menus, `False`
                to disable.
        """
        menus = [wx.ID_OPEN, wx.ID_CANCEL, wx.ID_REVERT, wx.ID_SAVEAS, 
                 self.ID_EXPORT_VISIBLE, wx.ID_PRINT, wx.ID_PRINT_SETUP,
                 wx.ID_CUT, wx.ID_COPY, wx.ID_PASTE]
        
        for m in menus:
            self.menuItems[m].Enable(enabled)
    
    
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
        return self.ask("Really quit?") == wx.ID_YES

    #===========================================================================
    # 
    #===========================================================================
    
    def openFile(self, filename):
        """
        """
        if self.dataset is not None and self.dataset.loading is True:
            if self.ask("Abort loading the current?") != wx.ID_YES:
                return
            else:
                self.cancelOperation()
        try:
            stream = ThreadAwareFile(filename, 'rb')
            newDoc = mide_ebml.dataset.Dataset(stream)
            self.app.addRecentFile(filename, 'import')
        except Exception as err:
            self.handleException(err)
            return
        
        self.dataset = newDoc
        loader = Loader(self, newDoc, **self.app.getPref('loader'))
        self.pushOperation(loader, modal=False)
        loader.start()
    
    
    def closeFile(self):
        """ Close a file. Does not close the viewer window itself.
        """
        self.plotarea.clearAllPlots()
        self.dataset = None
        self.enableChildren(False)
        
    
    def exportCsv(self, evt=None):
        """ Export the active plot view's data as CSV.
        """
        dlg = ExportDialog(self, -1, "Export CSV", root=self)
        result = dlg.ShowModal()
        subchannels = dlg.getSelectedChannels()
        startTime, stopTime = dlg.getExportRange()
        dlg.Destroy()
        if result == wx.ID_CANCEL or len(subchannels) == 0:
            return

        if self.dataset.loading:
            x = self.ask("A dataset is currently being loaded. "
                         "This will make exporting slow. "
                         "Export anyway?")
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
                                   "Open File")
                if openNew == wx.ID_YES:
                    self.openFile(filename)
            
        # Note to self: do this last!
        dlg.Destroy()


    def OnFileExportMenu(self, evt):
        """ Handle File->Export menu events.
        """
        self.exportCsv()


    def OnFileExitMenu(self, evt):
        """ Handle File->Exit menu events. 
        """
        if self.okayToExit():
            self.Close()


    def OnFileReloadMenu(self, evt):
        """ Handle File->Reload menu events.
        """
        # XXX: IMPLEMENT ME
        print "File:Reload"
        pass

    
    def OnHelpAboutMenu(self, evt):
        """ Handle Help->About menu events.
        """
        info = wx.AboutDialogInfo()
        info.Name = APPNAME
        info.Version = __version__
        info.Copyright = __copyright__
        info.Description = wordwrap(__doc__, 350, wx.ClientDC(self))
        info.WebSite = __url__
#         info.Developers = __credits__
#         info.License = wordwrap(__license__, 500, wx.ClientDC(self))
        wx.AboutBox(info)
    

    def DEBUG_OnToggleAA(self, evt):
        self.antialias = evt.IsChecked()
        self.plotarea.redraw()
        
    def DEBUG_OnToggleNoise(self, evt):
        if evt.IsChecked():
            self.noisyResample = RESAMPLING_JITTER
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
    
    def startBusy(self):
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
        self.busy = True

    def stopBusy(self):
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
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
            msg = u"X: %.6f %s" % (self.timeline.getValueAt(pos) * self.timeScalar,
                                   units)
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
            msg = u"Y: %.6f %s" % (pos, units)
        self.statusBar.SetStatusText(msg, self.statusBar.yFieldNum)
        


    #===========================================================================
    # 
    #===========================================================================
    
    def getPref(self, *args, **kwargs):
        return self.app.getPref(*args, **kwargs)
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    def handleException(self, err, msg=None, icon=wx.ICON_ERROR, 
                        raiseException=False, fatal=False):
        """ General-purpose exception handler that attempts to provide a 
            meaningful error message. Also works as an event handler for
            custom error events (e.g. `EvtImportError`).
            
            @param err: The raised exception, an event object (e.g.
                `EvtImportError`), or `None`.
            @keyword msg: An alternative error message, to be shown verbatim.
            @keyword icon: The icon to show in the dialog box.
            @keyword raiseException: If `True`, the exception will be raised
                before the dialog is displayed.
            @keyword fatal: If `True`, the app Viewer will shut down. 
                
        """
        if isinstance(err, wx.Event):
            err = err.err
            msg = getattr(err, 'msg', None)
            
        if not isinstance(msg, basestring):
            if isinstance(err, EnvironmentError):
                # IOError or OSError; use the the error code.
                # TODO: Improve this
                msg = unicode(err)
            elif isinstance(err, MemoryError):
                msg = "Out of memory!"
            else:
                msg = u"An unexpected error occurred:\n\n%s: %s" % \
                        (err.__class__.__name__, unicode(err))

        # If exceptions are explicitly raised, raise it.
        if raiseException and isinstance(err, Exception):
            raise err

        dlg = wx.MessageDialog(self, msg, APPNAME, wx.OK | icon)
        dlg.ShowModal()
        ctrlPressed = wx.GetKeyState(wx.WXK_CONTROL)
        dlg.Destroy()
        
        # Holding control when okaying alert shows more more info. 
        if ctrlPressed and isinstance(err, Exception):
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
    prefsFile = os.path.realpath(os.path.join(os.path.dirname(__file__), 'ssx_viewer.cfg'))
    
    defaultPrefs = {
        'importTypes': ["MIDE Data File (*.ide)|*.ide", 
                        "Slam Stick X Data File (*.dat)|*.dat",
                        "All files (*.*)|*.*"],
        'exportTypes': ["Comma Separated Values (*.csv)|*.csv"],
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
        'locale': 'English_United States.1252',
        'loader': dict(numUpdates=100, updateInterval=1.0),
        'fileHistory': {},
        'fileHistorySize': 10,
        'originHLineColor': wx.Color(220,220,220),
        'majorHLineColor': wx.Color(220,220,220),
        'minorHLineColor': wx.Color(240,240,240),
        'warnBeforeQuit': True,
        'antialiasing': True,
        'showDebugChannels': False,
    }


    def loadPrefs(self, filename=prefsFile):
        """ Load saved preferences from file.
        """
        def tuple2color(c):
            if isinstance(c, list):
                return wx.Color(*c)
            return c
        
        if not filename:
            return {}
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
        except Exception:#IOError:
            # TODO: Report a problem, or just ignore?
            pass
        return {}


    def savePrefs(self, filename=prefsFile, hideFile=None):
        """ Write custom preferences to a file.
        """
        if hideFile is None:
            hideFile = os.path.basename(filename).startswith(".")
            
        prefs = self.prefs.copy()
        # Convert wx.Color objects and RGB sequences to tuples:
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
                os.system("attrib +h %s" % filename)
        except IOError as err:
            # TODO: Report a problem, or just ignore?
            err
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
        self.prefs = self.loadPrefs(prefsFile)
        locale.setlocale(locale.LC_ALL, str(self.getPref('locale')))
        
        self.viewers = []
        
        super(ViewerApp, self).__init__(*args, **kwargs)
                

    def createNewView(self, title=None):
        """ Create a new viewer window.
        """
        if title is None:
            title = u'%s v%s' % (APPNAME, __version__)
        viewer = Viewer(None, title=title, app=self)
        self.viewers.append(viewer)
        viewer.Show()
        

    def OnInit(self):
        self._antiAliasingEnabled = True
        self.createNewView()
        
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
if True:#__name__ == '__main__':
    app = ViewerApp()
    app.MainLoop()