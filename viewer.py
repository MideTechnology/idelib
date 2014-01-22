'''
Created on Oct 21, 2013

@author: dstokes
'''

APPNAME = u"Slam Stick X Data Viewer"
__version__="0.0.1"
__copyright__=u"Copyright (c) 2013 MID\xc9 Technology"
__credits__=["David R. Stokes", "Tim Gipson"]

from datetime import datetime
import json
import os
from threading import Thread

import wx.aui
import  wx.lib.newevent

import wx; wx = wx # Workaround for Eclipse code comprehension
# from wx.aui import AuiNotebook
from wx.lib.rcsizer import RowColSizer
from wx.lib.wordwrap import wordwrap

# This pattern was lifted from examples. Is it deprecated?
try:
    from agw import rulerctrl
except ImportError:
    import wx.lib.agw.rulerctrl as rulerctrl

from timeline import TimelineCtrl, TimeNavigatorCtrl, VerticalScaleCtrl
from timeline import EVT_INDICATOR_CHANGING, EVT_INDICATOR_CHANGED

from icons import MideLogo_77px as MideLogo
from icons import SlamStickX_Logo_Black_Alpha_116px as SSXLogo

from dataset import Dataset
import importer

# XXX: FOR TESTING PURPOSES ONLY:
# from fakedata import makeFakeData

# XXX: EXPERIMENTAL!
from threaded_file import ThreadAwareFile
#===============================================================================
# 
#===============================================================================

(Evt_Set_Visible_Range, EVT_SET_VISIBLE_RANGE) = wx.lib.newevent.NewEvent()
(Evt_Set_Time_Range, EVT_SET_TIME_RANGE) = wx.lib.newevent.NewEvent()
(Evt_Progress_Start, EVT_PROGRESS_START) = wx.lib.newevent.NewEvent()
(Evt_Progress_Update, EVT_PROGRESS_UPDATE) = wx.lib.newevent.NewEvent()
(Evt_Progress_End, EVT_PROGRESS_END) = wx.lib.newevent.NewEvent()
(Evt_Init_Plots, EVT_INIT_PLOTS) = wx.lib.newevent.NewEvent()

#===============================================================================
# 
#===============================================================================

class Loader(Thread):
    """ The object that does the work of spawning an asynchronous file-loading
        thread and updating the viewer as data is loaded.
    """

    cancelMsg = "Import cancelled"
    
    def __init__(self, root, dataset, numTics=100, updateInterval=1.0,
                 autoStart=True):
        """ Create the Loader and start the loading process.
            
            @param root: The Viewer.
            @param dataset: The Dataset being loaded. It should be fresh,
                referencing a file stream but not yet loaded.
            @keyword numTics: The minimum number of calls to the updater to
                be made. There will be more than this number of updates if
                any takes longer than the specified `updateInterval` (below).
            @keyword updateInterval: The maximum number of seconds between
                calls to the updater
        """
        self.root = root
        self.dataset = dataset
        self.numTics = numTics
        self.updateInterval = updateInterval
        self.cancelled = False
        self.startTime = self.lastTime = None
        self.readingData = False

        super(Loader, self).__init__()

        if autoStart:
            self.start()


    def run(self):
        wx.PostEvent(self.root, 
                     Evt_Progress_Start(label="Importing...", initialVal=-1, 
                                        cancellable=True, cancelEnabled=None))
        importer.readData(self.dataset, self, 
                          numTics=self.numTics, 
                          updateInterval=self.updateInterval)

        wx.PostEvent(self.root, Evt_Progress_End(label=None))


    def formatEstimate(self, est):
        """ Format the `datetime.timedelta` of estimated time remaining as a
            pretty string.
        """
        if est is None or est.seconds < 1:
            return ""
        if est.seconds < 60:
            s = "%d sec." % est.seconds
        else:
            s = str(est)[:-7].lstrip("0:")
        return "- Est. finish in %s" % s 


    def __call__(self, count=0, percent=None, total=None, error=None, done=False):
        """ Update the Viewer's display.
        
            @param count: the current line number.
            @param percent: The estimated percentage of the file read, as a
                normalized float (0.0 to 1.0). 
            @param total: the total number of samples (if known).
            @param error: Any unexpected exception, if raised during the import.
            @param done: `True` when the export is complete.
        """
        if error is not None:
            if isinstance(error, IOError):
                # A file IO error of some sort, other than premature EOF
                # TODO: Implement this
                pass
            elif isinstance(error, MemoryError):
                # Typically out-of-memory error
                # TODO: Implement this
                pass
            elif isinstance(error, EnvironmentError):
                # A broad, operating-system-level error
                # TODO: Implement this
                pass
            else:
                # TODO: Implement this
                pass
            return
        
        if done:
            # TODO: Implement this
            return
        
        if not self.readingData:
            if count > 0:
                # The start of data.
                self.root.currentSession = self.dataset.lastSession
                wx.PostEvent(self.root, Evt_Init_Plots())
                endTime = self.root.currentSession.endTime
                if endTime is None:
                    endTime = self.root.currentSession.lastTime
                if endTime is not None:
                    evt = Evt_Set_Visible_Range(
                        start=self.root.currentSession.startTime, end=endTime, 
                        instigator=None, tracking=True)
                    wx.PostEvent(self.root, evt)
                # TODO: Finish this
                self.readingData = True
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
        
        msg = "%d samples imported %s" % (count, self.formatEstimate(est))
        
        wx.PostEvent(self.root, Evt_Progress_Update(val=percent, 
                                                    label=msg, 
                                                    cancellable=True))

        if self.dataset.lastSession == self.root.currentSession:
            evt = Evt_Set_Time_Range(start=self.root.currentSession.firstTime, 
                                     end=self.root.currentSession.lastTime, 
                                     instigator=None, 
                                     tracking=True)
            wx.PostEvent(self.root, evt)
        
        self.lastTime = thisTime


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
        
        logo = MideLogo.GetBitmap()
        self.logo = wx.StaticBitmap(self, -1, logo)

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
        fieldWidths[self.messageFieldNum] = -3
        fieldWidths[self.progressFieldNum] = -1
        fieldWidths[self.buttonFieldNum] = bwidth

        self.SetFieldsCount(self.numFields)
        self.SetStatusWidths(fieldWidths)

        self.SetStatusText("Welcome to %s v%s" % (APPNAME, __version__), 
                           self.messageFieldNum)

        self.progressBar = wx.Gauge(self, -1, 1000)

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
        
class Timeline(wx.Panel):
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
        self.timerange = kwargs.pop('timerange',(0,10**6))
        self.root = kwargs.pop('root',None)
        kwargs.setdefault('style',wx.NO_BORDER)
        super(Timeline, self).__init__(*args, **kwargs)

        self.barClickPos = None
        self.scrolling = False
                
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.timebar = TimelineCtrl(self, -1, orient=wx.HORIZONTAL, style=wx.NO_BORDER)
        sizer.Add(self.timebar, 0, wx.EXPAND)
        self.timebar.SetBackgroundColour(self.root.uiBgColor)
        self.timebar.SetRange(self.timerange[0] * self.root.timeScalar,
                             self.timerange[1] * self.root.timeScalar)
        
        self.scrollbar = wx.ScrollBar(self, -1, style=wx.SB_HORIZONTAL)
        sizer.Add(self.scrollbar, 0, wx.EXPAND|wx.ALIGN_BOTTOM)
        self.SetSizer(sizer)

        # TODO: Finish scrolling implementation
        # http://www.wxpython.org/docs/api/wx.ScrollEvent-class.html
        self.scrollbar.Bind(wx.EVT_SCROLL, self.OnScroll) # Used to bind all scroll events
        self.scrollbar.Bind(wx.EVT_SCROLL_TOP, self.OnScroll) # scroll-to-top events (minimum position)
        self.scrollbar.Bind(wx.EVT_SCROLL_BOTTOM, self.OnScroll) # scroll-to-bottom events (maximum position)
        self.scrollbar.Bind(wx.EVT_SCROLL_LINEUP, self.OnScroll) # line up events
        self.scrollbar.Bind(wx.EVT_SCROLL_LINEDOWN, self.OnScroll) # line down events
        self.scrollbar.Bind(wx.EVT_SCROLL_PAGEUP, self.OnScroll) # page up events
        self.scrollbar.Bind(wx.EVT_SCROLL_PAGEDOWN, self.OnScroll) # page down events
        self.scrollbar.Bind(wx.EVT_SCROLL_THUMBTRACK, self.OnScrollTrack) # thumbtrack events (frequent events sent as the user drags the 'thumb')
#         self.scrollbar.Bind(wx.EVT_SCROLL_THUMBRELEASE, self.OnScroll) # thumb release events
        self.scrollbar.Bind(wx.EVT_SCROLL_CHANGED, self.OnScrollEnd) # End of scrolling
        
        self.timebar.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.timebar.Bind(wx.EVT_LEFT_DOWN, self.OnTimebarClick)
        
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
        self.scrollbar.SetScrollbar(self.scrollUnitsPerUSec * (self.currentTime - self.timerange[0]), 
                                    self.scrollUnitsPerUSec * self.displayLength, 
                                    self._sbMax,
                                    self.scrollUnitsPerUSec * self.displayLength)
        self.unitsPerPixel = (self.displayLength / self.timebar.GetSize()[0] + 0.0)
        
        if broadcast:
            instigator = self if instigator is None else instigator
            self.root.setVisibleRange(self.currentTime, end, instigator, tracking)


    def getFullRange(self):
        # Test: get real thing from parent
        return self.timerange


    def getVisibleRange(self):
        # Test: get real thing from parent
        return self.currentTime, self.currentTime + self.displayLength


    #===========================================================================
    # Event Handlers
    #===========================================================================
    
    def OnTimebarClick(self, evt):
        self.barClickPos = evt.GetX()


    def OnMouseMotion(self, evt):
        if self.scrolling:
            return
        if self.barClickPos is not None and evt.LeftIsDown():
            newPos = evt.GetX()
            moved = self.barClickPos - newPos
            start = self.currentTime + moved * self.unitsPerPixel
            end = start + self.displayLength
            if start >= self.timerange[0] and end <= self.timerange[1]:
                self.setVisibleRange(start, end, None, tracking=False, 
                                     broadcast=True)
            self.barClickPos = newPos
        else:
            self.barClickPos = None
            self.root.showMouseHPos(evt.GetX())

    
    def OnScroll(self, evt):
        self.scrolling = True


    def OnScrollTrack(self, evt):
        start = (evt.GetPosition() / self.scrollUnitsPerUSec) + self.timerange[0]
        end = start + self.displayLength
        self.setVisibleRange(start, end, None, tracking=True, broadcast=True)


    def OnScrollEnd(self, evt):
        self.scrolling = False
        start = (evt.GetPosition() / self.scrollUnitsPerUSec) + self.timerange[0]
        end = start + self.displayLength
        self.setVisibleRange(start, end, None, tracking=False, broadcast=True)


#===============================================================================
# 
#===============================================================================

class TimeNavigator(wx.Panel):
    """ The full timeline view shown above the graph.
        
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword timerange: The default time range, in microseconds. 
        """
        self.timeRange = kwargs.pop('timerange',(0,1000))
        self.root = kwargs.pop('root',None)
        kwargs.setdefault('style', wx.NO_BORDER)
        super(TimeNavigator, self).__init__(*args, **kwargs)

        if self.root is None:
            self.root = self.GetParent()
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        logo = wx.StaticBitmap(self, -1, SSXLogo.GetBitmap())
        sizer.Add(logo, 0, wx.ALIGN_CENTER)
        
        self.timeline = TimeNavigatorCtrl(self,-1)
        sizer.Add(self.timeline, -1, wx.EXPAND)
        
        self.zoomOutButton = wx.BitmapButton(self, -1, wx.Bitmap('images/ZoomOut_H_22px.png'))
        self.zoomOutButton.SetBitmapDisabled(wx.Bitmap('images/ZoomOut_Disabled_22px.png'))
        sizer.Add(self.zoomOutButton, 0, wx.EXPAND)
        self.zoomInButton = wx.BitmapButton(self, -1, wx.Bitmap('images/ZoomIn_H_22px.png'))
        self.zoomInButton.SetBitmapDisabled(wx.Bitmap('images/ZoomIn_Disabled_22px.png'))
        sizer.Add(self.zoomInButton, 0, wx.EXPAND)
        self.zoomFitButton = wx.BitmapButton(self, -1, wx.Bitmap('images/ZoomFit_H_22px.png'))
        self.zoomFitButton.SetBitmapDisabled(wx.Bitmap('images/ZoomFit_Disabled_22px.png'))
        sizer.Add(self.zoomFitButton, 0, wx.EXPAND)
        self.zoomFitButton.Enable(False)
        
        self.SetSizer(sizer)
        
        self.Bind(EVT_INDICATOR_CHANGING, self.OnMarkChanging)#, id=103)
        self.Bind(EVT_INDICATOR_CHANGED, self.OnMarkChanged)#, id=101, id2=104)
        self.Bind(wx.EVT_BUTTON, self.OnZoomIn, self.zoomInButton)
        self.Bind(wx.EVT_BUTTON, self.OnZoomOut, self.zoomOutButton)
        self.Bind(wx.EVT_BUTTON, self.OnZoomToFit, self.zoomFitButton)
        

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
        if instigator != self:
            self.timeline.setVisibleRange(start * self.root.timeScalar, 
                                          end * self.root.timeScalar)

    def zoom(self, percent, liveUpdate=True):
        """ Increase or decrease the size of the visible range.
        
            @param percent: A zoom factor. Use a normalized value, positive
                to zoom in, negative to zoom out.
            @param liveUpdate:
        """
        v1, v2 = self.timeline.getVisibleRange()
        d = (v2 - v1) * percent / 2
        v1 = max(self.timerange[0], (v1 + d)/ self.root.timeScalar) 
        v2 = min(self.timerange[1], (v2 - d)/ self.root.timeScalar)
        self.setVisibleRange(v1,v2)
        self.root.setVisibleRange(v1, v2, self, not liveUpdate)


#     def getVisibleRange(self):
#         r = self.timeline.getVisibleRange

    #===========================================================================
    # 
    #===========================================================================
    
    def OnMarkChanging(self, evt):
        """ Dynamically handle one of the visible range markers as it is being 
            moved.
        """
        evt.Skip()
        v1, v2 = self.timeline.getVisibleRange()
        v1 /= self.root.timeScalar
        v2 /= self.root.timeScalar
#         self.GetParent().setVisibleRange(v1, v2, self, True)
        pass
    
    def OnMarkChanged(self, evt):
        """ Handle the final adjustment of a visible range marker.
        """
        print "OnMarkChanged"
        evt.Skip()
        v1, v2 = self.timeline.getVisibleRange()
        self.root.setVisibleRange(v1/self.root.timeScalar, v2/self.root.timeScalar, self, True)
        pass

    def OnZoomIn(self, evt):
        """ Handle 'zoom in' events, i.e. the zoom in button was pressed. 
        """
        self.zoom(.25)

    
    def OnZoomOut(self, evt):
        """ Handle 'zoom out' events, i.e. the zoom in button was pressed. 
        """
        self.zoom(-.25)


    def OnZoomToFit(self, evt):
        """ Handle 'zoom to fit' events, i.e. the zoom-to-fit button press.
        """
        # XXX: Implement ZoomToFit!
        pass

#===============================================================================
# 
#===============================================================================

class LegendArea(wx.Panel):
    """
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
            @keyword root: The viewer's 'root' window.
        """
        self.root = kwargs.pop('root',None)
        self.visibleRange = kwargs.pop('visibleRange',(1.0,-1.0))
        kwargs.setdefault('style',wx.NO_BORDER)
        super(LegendArea, self).__init__(*args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        subsizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(subsizer)
        
        # Zoom buttons
        self.zoomInButton = wx.BitmapButton(self, -1, wx.Bitmap('images/ZoomIn_V_22px.png'), style=wx.DEFAULT|wx.ALIGN_BOTTOM)
        self.zoomInButton.SetBitmapDisabled(wx.Bitmap('images/ZoomIn_Disabled_22px.png'))
        subsizer.Add(self.zoomInButton, -1, wx.EXPAND)
        self.zoomOutButton = wx.BitmapButton(self, -1, wx.Bitmap('images/ZoomOut_V_22px.png'), style=wx.DEFAULT|wx.ALIGN_BOTTOM)
        self.zoomOutButton.SetBitmapDisabled(wx.Bitmap('images/ZoomOut_Disabled_22px.png'))
        subsizer.Add(self.zoomOutButton, -1, wx.EXPAND)
        self.zoomFitButton = wx.BitmapButton(self, -1, wx.Bitmap('images/ZoomFit_V_22px.png'), style=wx.DEFAULT|wx.ALIGN_BOTTOM)
        self.zoomFitButton.SetBitmapDisabled(wx.Bitmap('images/ZoomFit_Disabled_22px.png'))
        subsizer.Add(self.zoomFitButton, -1, wx.EXPAND)
        self.zoomFitButton.Enable(False)
        
        self.unitsPerPixel = 1.0
        self.scale = VerticalScaleCtrl(self, -1, size=(1200,-1), style=wx.NO_BORDER|wx.ALIGN_RIGHT)
        self.scale.SetFormat(rulerctrl.RealFormat)
#         self.scale.SetRange(max(self.visibleRange),min(self.visibleRange))
        self.scale.SetRange(*self.visibleRange)
        self.scale.SetBackgroundColour(self.root.uiBgColor)
        sizer.Add(self.scale, -1, wx.EXPAND)
        self.SetSizer(sizer)
        self.SetMinSize((self.root.corner.GetSize()[0],-1))
        self.SetBackgroundColour(self.root.uiBgColor)

        self.Bind(wx.EVT_BUTTON, self.OnZoomIn, self.zoomInButton)
        self.Bind(wx.EVT_BUTTON, self.OnZoomOut, self.zoomOutButton)
        self.Bind(wx.EVT_BUTTON, self.OnZoomToFit, self.zoomFitButton)

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
            @keyword instigator: The object that initiated the change, in order
                to avoid an infinite loop of child calling parent calling child.
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
        self.scale.SetRange(top,bottom)
        self.unitsPerPixel = abs((top - bottom) / (vSize + 0.0))
        if not tracking:
            self.Parent.Refresh()
    
    
    def getValueRange(self):
        return self.visibleRange


    def getValueAt(self, vpos):
        """
        """
        return self.visibleRange[0] - (vpos * self.unitsPerPixel)
        

    def zoom(self, percent, liveUpdate=True):
        """ Increase or decrease the size of the visible range.
        
            @param percent: A zoom factor. Use a normalized value, positive
                to zoom in, negative to zoom out.
            @param liveUpdate:
        """
        v1, v2 = self.visibleRange
        d = (v1 - v2) * percent / 2.0
        self.setValueRange(v1-d,v2+d,None,False)


    
    #===========================================================================
    # Event Handlers
    #===========================================================================
    
    def OnResize(self, evt):
        self.unitsPerPixel = abs((self.visibleRange[0] - self.visibleRange[1]) / (evt.Size[1] + 0.0))
#         print evt.Size, self.visibleRange, self.unitsPerPixel
        evt.Skip()
    
    def OnMouseMotion(self, evt):
        self.root.showMouseVPos(self.getValueAt(evt.GetY()), 
                                units=self.Parent.yUnits[1])
    
    def OnZoomIn(self, evt):
        self.zoom(.25)
    
    def OnZoomOut(self, evt):
        self.zoom(-.25)

    def OnZoomToFit(self, evt):
        # XXX: Implement LegendArea.OnZoomToFit!
        pass

#===============================================================================
# 
#===============================================================================

class PlotCanvas(wx.ScrolledWindow):
    """ The actual plot-drawing area.
    """
    
    def __init__(self, *args, **kwargs):#parent, id_=-1):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
            @keyword root: The viewer's 'root' window.
        """
        self.root = kwargs.pop('root',None)
        self.color = kwargs.pop('color', "BLUE")
        self.weight = kwargs.pop('weight',1)
        kwargs.setdefault('style',wx.VSCROLL|wx.BORDER_SUNKEN)
        super(PlotCanvas, self).__init__(*args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        
        self.SetBackgroundColour("white")
        self.setPen()
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        
        self.visibleValueRange = None


    def setPen(self, color=None, weight=None, style=wx.SOLID):
        """
        """
        self.color = color if color is not None else self.color
        self.weight = weight if weight is not None else self.weight
        self.style = style if style is not None else self.style
        self._pen = wx.Pen(self.color, self.weight, self.style)
        
    
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
        print "PlotCanvas.setVisibleRange"
        if instigator != self and tracking:
            self.Refresh()
    
    
    def OnMouseMotion(self, evt):
        """
        """
        self.root.showMouseHPos(evt.GetX())
        self.root.showMouseVPos(self.Parent.legend.getValueAt(evt.GetY()),
                                units=self.Parent.yUnits[1])
        evt.Skip()


    def OnPaint(self, evt):
        if self.Parent.source is None:
            return
        self.InvalidateBestSize()
        dc = wx.PaintDC(self) # wx.BufferedPaintDC(self)
#         gc = wx.GraphicsContext.Create(dc)
#         if self.root.app._antiAliasingEnabled:
#             if not isinstance(dc, wx.GCDC):
#                 try:
#                     dc = wx.GCDC(dc)
#                 except:
#                     pass
#         print dc.GetLogicalScale()
        size = dc.GetSize()

        hRange = self.root.getVisibleRange()
        vRange = self.Parent.legend.scale.GetRange()

        hscale = (size.x + 0.0) / (hRange[1]-hRange[0])
        vscale = (size.y + 0.0) / (vRange[1]-vRange[0])
        
        lines = []
        lastPt = None
#         events = self.Parent.source.iterResampledRange(hRange[0], hRange[1], size[0])
#         print list(events)
        events = self.Parent.source.iterResampledRange(hRange[0], hRange[1], size[0])
        try:
            lastPt = events.next()
            lastPt = (lastPt[-2] - hRange[0]) * hscale, (lastPt[-1] - vRange[0]) * vscale
            self.visibleValueRange = [lastPt[-2], lastPt[-2]]
            for event in events:
                # Using negative indices here in case doc.useIndices is True
                if event[-1] is not None:
                    event = (event[-2] - hRange[0]) * hscale, (event[-1] - vRange[0]) * vscale
                    lines.append((lastPt[-2], lastPt[-1], event[-2], event[-1]))
                    self.visibleValueRange[0] = min(self.visibleValueRange[0], event[-2])
                    self.visibleValueRange[1] = max(self.visibleValueRange[1], event[-2])
                    # TODO: Also build a list of point markers? Other plots?
                lastPt = event
        except StopIteration:
            pass

        dc.Clear()
        dc.BeginDrawing()
        dc.SetPen(self._pen)
        dc.DrawLineList(lines)
        dc.EndDrawing()

#===============================================================================
# 
#===============================================================================

class Plot(wx.Panel):
    """ A single plotted channel, consisting of the vertical scale and actual
        plot-drawing canvas.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
        """
        self.source = kwargs.pop('source', None)
        self.root = kwargs.pop('root',None)
        self.yUnits= kwargs.pop('units',None)
        color = kwargs.pop('color', 'BLACK')
        scale = kwargs.pop('scale', (-1,1))
        super(Plot, self).__init__(*args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        if self.yUnits is None:
            self.yUnits = getattr(self.source, "units", ('',''))
        
        self.legend = LegendArea(self, -1, visibleRange=scale)
        self.plot = PlotCanvas(self, -1, style=wx.FULL_REPAINT_ON_RESIZE, color=color)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.legend, 0, wx.EXPAND)
        sizer.Add(self.plot, -1, wx.EXPAND)
        self.SetSizer(sizer)
        self.legend.SetSize((self.Parent.Parent.corner.GetSize()[0],-1))
        
        self.plot.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseLeave)
        

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
        pass
    
    
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

class PlotSet(wx.aui.AuiNotebook):
    """ A tabbed window containing multiple Plots.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
            @keyword root: The viewer's 'root' window.
        """
        self.root = kwargs.pop('root', None)
        kwargs.setdefault('style', wx.aui.AUI_NB_TOP | 
                                   wx.aui.AUI_NB_TAB_SPLIT | 
                                   wx.aui.AUI_NB_TAB_MOVE | 
                                   wx.aui.AUI_NB_SCROLL_BUTTONS)
        super(PlotSet, self).__init__(*args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        

    def __len__(self):
        return self.GetPageCount()
    
    
    def __iter__(self):
        for i in xrange(len(self)):
            yield(self.GetPage(i))
    
        
    def addPlot(self, source, title=None, name=None, scale=None, color="BLACK", units=None):
        """ Add a new Plot to the display.
        
            @param source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
            @keyword title: The name displayed on the plot's tab
                (defaults to 'Plot #')
        """

        title = source.name if title is None else title
        title = "Plot %s" % len(self) if title is None else title
        
        print "adding:",title
        
        if scale is None:
            scale = getattr(source, "possibleRange", (-1.0,1.0))
            
        name = name if name is not None else title
        plot = Plot(self, source=source, root=self.root, scale=scale, color=color, units=units)
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
        """
        """
        pagecount = len(self)
        idx = pagecount + idx if idx < 0 else idx
        if idx < pagecount:
            pIdx = self.GetPageIndex(self.GetPage(idx))
            if pIdx != wx.NOT_FOUND:
                self.DeletePage(pIdx)

    
    
    def clearAllPlots(self):
        """
        """
        for i in xrange(self.GetPageCount):
            self.removePlot(0)
        
#===============================================================================
# 
#===============================================================================

class Corner(wx.Panel):
    """ A 'bug' to fit into the empty space in the lower left corner.
    """
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root',None)
        super(Corner, self).__init__(*args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
            
        sizer = wx.FlexGridSizer(2,3, hgap=4, vgap=4)
        sizer.AddGrowableCol(0,-2)
        sizer.AddGrowableCol(1,-4)
        sizer.AddGrowableCol(2,-1)
        
        self.startField = wx.TextCtrl(self, -1, "start", size=(56, -1), 
                                      style=wx.TE_PROCESS_ENTER | wx.TE_PROCESS_TAB)
        startLabel = wx.StaticText(self,-1,"Start:",size=(30,-1),
                                   style=wx.ALIGN_RIGHT)
        self.startUnits = wx.StaticText(self, -1, self.root.units[1], 
                                        style=wx.ALIGN_LEFT)
        sizer.Add(startLabel,0,0)
        sizer.Add(self.startField,1,0)
        sizer.Add(self.startUnits, 2,0)
        
        self.endField = wx.TextCtrl(self, -1, "end", size=(56, -1), 
                                    style=wx.TE_PROCESS_ENTER | wx.TE_PROCESS_TAB)
        endLabel = wx.StaticText(self,-1,"End:",size=(30,-1),
                                 style=wx.ALIGN_RIGHT)
        self.endUnits = wx.StaticText(self, -1, self.root.units[1], 
                                      style=wx.ALIGN_LEFT)
        sizer.Add(endLabel,1,0)
        sizer.Add(self.endField,1,1)
        sizer.Add(self.endUnits, 2,1)

        self.SetSizer(sizer)
        self.SetBackgroundColour(self.root.uiBgColor)
        
        self.startField.Bind(wx.EVT_TEXT_ENTER, self.OnRangeChanged)
        self.endField.Bind(wx.EVT_TEXT_ENTER, self.OnRangeChanged)


    def setXUnits(self, symbol=None):
        """
        """
        symbol = self.root.units[1] if symbol is None else symbol
        self.startUnits.SetLabel(symbol)
        self.startUnits.Refresh()
        self.endUnits.SetLabel(symbol)
        

    def setVisibleRange(self, start=None, end=None, instigator=None, 
                        tracking=None):
        """
        """
        if start is not None:
            self.startField.SetValue("%.6f" % (self.root.timeScalar * start))
        if end is not None:
            self.endField.SetValue("%.6f" % (self.root.timeScalar * end))


    def setTimeRange(self, start=None, end=None, instigator=None, 
                     tracking=None):
        """
        """
        pass
    
    
    def OnRangeChanged(self, evt):
        """
        """
        print "change"
        pass
    
#===============================================================================
# 
#===============================================================================

class Viewer(wx.Frame):
    timeScalar = 1.0/(10**6)
    timerange = (1043273L * timeScalar*2,7672221086L * timeScalar)

    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments plus:
        
            @keyword app: The viewer's parent application.
        """
        self.app = kwargs.pop('app', None)
        self.units = kwargs.pop('units',('seconds','s'))
        
        displaySize = wx.DisplaySize()
        windowSize = int(displaySize[0]*.66), int(displaySize[1]*.66)
        kwargs['size'] = kwargs.get('size', windowSize)
        
        super(Viewer, self).__init__(*args, **kwargs)
        
        self.uiBgColor = wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE)
        
        self.InitUI()
        self.Centre()
        self.Show()
        
        self.dataset = None
        self.currentSession = None
        self.cancelQueue = []
        
        self.plots = []
        self.setVisibleRange(self.timerange[0], self.timerange[1])
        
        self.Bind(EVT_SET_VISIBLE_RANGE, self.OnSetVisibleRange)
        self.Bind(EVT_SET_TIME_RANGE, self.OnSetTimeRange)
        self.Bind(EVT_PROGRESS_START, self.OnProgressStart)
        self.Bind(EVT_PROGRESS_UPDATE, self.OnProgressUpdate)
        self.Bind(EVT_PROGRESS_END, self.OnProgressEnd)
        self.Bind(EVT_INIT_PLOTS, self.initPlots)

        # XXX: TEST CODE BELOW. REMOVE LATER.
        
        self.openFile(r"C:\Users\dstokes\workspace\wvr\test_full_cdb_huge.dat")



    def InitMenus(self):
        """
        """
        
        self.menuItems = {}
        
        # Just to make the menu adding less tedious
        def addItem(menu, id_, text, helpString, handler, enabled=True):
            item = menu.Append(id_, text, helpString)
            item.Enable(enabled)
            if handler is not None:
                self.Bind(wx.EVT_MENU, handler, item)
            self.menuItems[id] = item
            return item
        
        self.menubar = wx.MenuBar()
        self.ID_EXPORT_VISIBLE = wx.NewId()
        
        fileMenu = wx.Menu()
        addItem(fileMenu, wx.ID_OPEN, "&Open...", "", self.OnFileOpenMenu)
        self.fileMenu_Cancel = addItem(fileMenu, wx.ID_CANCEL, "Stop Loading File\tCrtl-.", "", None, False)
        addItem(fileMenu, wx.ID_REVERT, "&Reload Current File", "", self.OnFileReloadMenu, False)
        fileMenu.AppendSeparator()
        addItem(fileMenu, wx.ID_SAVEAS, "Export Data...", "Export all data for this channel", self.OnFileExportMenu, False)
        addItem(fileMenu, self.ID_EXPORT_VISIBLE, "Export Visible Range...", "Export the currently visible range as CSV", self.OnFileExportViewMenu, False)
        fileMenu.AppendSeparator()
        addItem(fileMenu, wx.ID_PRINT, "&Print...", "", None, False)
        addItem(fileMenu, wx.ID_PRINT_SETUP, "Print Setup...", "", None, False)
        fileMenu.AppendSeparator()
        self.fileMenu_Exit = addItem(fileMenu, wx.ID_EXIT, 'E&xit', '', self.OnFileExitMenu)
        wx.App.SetMacExitMenuItemId(self.fileMenu_Exit.GetId())
        self.menubar.Append(fileMenu, '&File')
        
        editMenu = wx.Menu()
        addItem(editMenu, wx.ID_CUT, "Cut", "", None, False)
        addItem(editMenu, wx.ID_COPY, "Copy", "", None, False)
        addItem(editMenu, wx.ID_PASTE, "Paste", "", None, False)
        self.menubar.Append(editMenu, '&Edit')

        dataMenu = wx.Menu()
        dataSessionsMenu = wx.Menu()
        # XXX: THIS IS TEST CODE. REPLACE WITH DYNAMIC MENU GENERATION
        # v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v.v
        dataSessionsMenu.Append(30001, "Session 0", "", wx.ITEM_RADIO)
        dataSessionsMenu.Append(30002, "Session 1", "", wx.ITEM_RADIO)
        dataSessionsMenu.Append(30003, "Session 2", "", wx.ITEM_RADIO)
        dataSessionsMenu.Append(30004, "Session 3", "", wx.ITEM_RADIO)
        dataMenu.AppendMenu(300, "Sessions", dataSessionsMenu)
        # ^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^'^
        self.menubar.Append(dataMenu, '&Data')
        
        helpMenu = wx.Menu()
        addItem(helpMenu, wx.ID_ABOUT, "About %s..." % APPNAME, "", self.OnHelpAboutMenu)
        self.menubar.Append(helpMenu, '&Help')

        self.SetMenuBar(self.menubar)
        
    
    def InitUI(self):
        """
        """
        self.root = self
        self.timeDisplays = []
        
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

        icon = wx.Icon("images/ssx_icon_white.png", wx.BITMAP_TYPE_PNG)
        self.SetIcon(icon)
        
        self.InitMenus()

        # XXX: TEST CODE BELOW. REMOVE LATER.
#         fakedata = makeFakeData()
#         self.setTimeRange(fakedata[0][0][0], fakedata[0][100][0], None, True)
#         self.setVisibleRange(fakedata[0][0][0], fakedata[0][100][0], None, True)
#         for d,c in zip(fakedata, self.app.prefs['defaultColors']):
#             self.plotarea.addPlot(d, scale=(65407,128), color=c)
#         self.runTestTimer()
#         self.startBusy()
        # XXX: TEST CODE ABOVE. REMOVE LATER.


    def enableMenus(self, enabled=True):
        """
        """
        menus = [wx.ID_OPEN, wx.ID_CANCEL, wx.ID_REVERT, wx.ID_SAVEAS, 
                 self.ID_EXPORT_VISIBLE, wx.ID_PRINT, wx.ID_PRINT_SETUP,
                 wx.ID_CUT, wx.ID_COPY, wx.ID_PASTE]
        
        for m in menus:
            self.menuItems[m].Enable(enabled)
    

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
        """
        """
        if self.dataset is None:
            return
        
        if self.currentSession is None:
            self.currentSession = self.dataset.sessions[0]
        
        for d,c in zip(self.dataset.getPlots(), self.app.prefs['defaultColors']):
            name = d.name
            self.plotarea.addPlot(d.getSession(self.currentSession.sessionId), 
                                  title=name,
                                  scale=(65407,128), 
                                  color=c)

        

    #===========================================================================
    # 
    #===========================================================================

    def setXUnits(self, name=None, symbol=None, displayScale=timeScalar):
        """ Set the horizontal units.
        """
        if name == symbol == None:
            name = symbol = ''
        elif name is None:
            name = symbol
        else:
            symbol = name
        self.units = (name, symbol)
        self.timeScalar = displayScale if displayScale is not None else self.timeScalar
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
                calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
#         print "setVisibleRange", start, end
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
                calling child.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
#         print "setTimeRange", start, end
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
        return self.timeline.getVisibleRange()

    #===========================================================================
    # 
    #===========================================================================

    def getDefaultImport(self):
        """ Get the path and name of the default data file. """
        # TODO: Better way of determining this
        return (os.getcwd(), 'test.dat')


    def getDefaultExport(self):
        """ Get the path and name of the default export file.
        """
        # TODO: This should be based on the current filename.
        return (os.getcwd(), "export.csv")


    def getCurrentFile(self):
        """ Returns the path and name of the currently open file.
        """
        # XXX: IMPLEMENT ME
        return None

    
    def okayToExit(self):
        """ Returns `True` if the app is in a state to immediately quit.
        """
        # XXX: IMPLEMENT ME
        return True

    #===========================================================================
    # 
    #===========================================================================
    
    def openFile(self, filename):
        """
        """
        try:
#             stream = open(filename, 'rb')
            stream = ThreadAwareFile(filename, 'rb')
            newDoc = Dataset(stream)
#         except IOError as err:
#             pass
        except Exception as err:
            raise err
            pass
        
        self.dataset = newDoc
        loader = Loader(self, newDoc, autoStart=False)
        self.pushOperation(loader, modal=False)
        loader.start()
    
    
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
                            wildcard="|".join(self.app.prefs['importTypes']),
                            style=wx.OPEN | wx.CHANGE_DIR)
        dlg.SetFilterIndex(0)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            if self.dataset is None or self.dataset.filename == filename:
                self.openFile(filename)
            else:
                openNew = self.ask("Are you sure you want to close the current file and open another?", "Open File")
                if openNew == wx.ID_YES:
                    self.openFile(filename)
            
        # Note to self: do this last!
        dlg.Destroy()


    def OnFileExportMenu(self, evt):
        """ Handle File->Export menu events.
        """
        defaultDir, defaultFile = self.getDefaultExport()
        dlg = wx.FileDialog(self, 
                            message="Export as ...", 
                            defaultDir=defaultDir, 
                            defaultFile=defaultFile, 
                            wildcard='|'.join(self.app.prefs['exportTypes']), 
                            style=wx.SAVE)

        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            # XXX: IMPLEMENT ME
            print "You opened %s" % repr(filename)

        dlg.Destroy()


    def OnFileExportViewMenu(self, evt):
        """ Handle File->Export View menu events.
        """
        defaultDir, defaultFile = self.getDefaultExport()
        dlg = wx.FileDialog(self, 
                            message="Export visible interval as ...", 
                            defaultDir=defaultDir, 
                            defaultFile=defaultFile, 
                            wildcard='|'.join(self.app.exportTypes), 
                            style=wx.SAVE)

        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            # XXX: IMPLEMENT ME
            print "You opened %s" % repr(filename)

        dlg.Destroy()

    
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
        # TODO: Get real copy, possibly replace with nicer dialog.
        info = wx.AboutDialogInfo()
        info.Name = APPNAME
        info.Version = __version__
        info.Copyright = __copyright__
        info.Description = wordwrap("This would be the about text.", 
                                    350, wx.ClientDC(self))
        info.WebSite = ("http://mide.com", "")
#         info.Developers = __credits__
#         info.License = wordwrap(__license__, 500, wx.ClientDC(self))
        wx.AboutBox(info)


    #===========================================================================
    # Custom Events
    #===========================================================================
    
    def OnSetVisibleRange(self, evt):
        """
        """
        self.setVisibleRange(evt.start, evt.end, instigator=evt.instigator, 
                             tracking=evt.tracking)
        
        
    def OnSetTimeRange(self, evt):
        """
        """
        self.setTimeRange(evt.start, evt.end, instigator=evt.instigator, 
                             tracking=evt.tracking)
        
        
    def OnProgressStart(self, evt):
        """
        """
        self.statusBar.startProgress(evt.label, evt.initialVal, 
                                     evt.cancellable, evt.cancelEnabled)


    def OnProgressUpdate(self, evt):
        """
        """
        self.statusBar.updateProgress(val=evt.val, label=evt.label, 
                                      cancellable=evt.cancellable)
    
    
    def OnProgressEnd(self, evt):
        """
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
    # XXX: TEMPORARY STUFF BELOW
    #===========================================================================
    
    def runTestTimer(self):
        # XXX: THIS IS TEMPORARY
        self._prog = 0.0
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.TestTimerHandler)
        self.timer.Start(1000)

    def __del__(self):
        self.timer.Stop()
        
    def TestTimerHandler(self, evt):
        v1, v2 = self.timerange
        self.timerange = v1, v2+100
        self.setTimeRange(*self.timerange)
        self._prog += 0.01
        self.statusBar.updateProgress(self._prog)

    #===========================================================================
    # XXX: TEMPORARY STUFF ABOVE
    #===========================================================================

#===============================================================================
# 
#===============================================================================

class ViewerApp(wx.App):
    """
    """
    
    prefsFile = os.path.join(os.path.dirname(__file__), 'ssx_viewer.cfg')
    
    defaultPrefs = {
        'importTypes': ["Slam Stick X Data File (*.dat)|*.dat",
                        "MIDE Data File (*.mide)|*.mide", 
                        "All files (*.*)|*.*"],
        'exportTypes': ["Comma Separated Values (*.csv)|*.csv"],
        'defaultColors': ["RED",
                          "GREEN",
                          "BLUE",
                          "YELLOW",
                          "VIOLET",
                          "GREY",
                          "MAGENTA",
                          "NAVY",
                          "PINK",
                          "SKY BLUE",
                          "BROWN",
                          "CYAN",
                          "DARK GREY",
                          "DARK GREEN",
                          "GOLD",
                          "BLACK",
                          "BLUE VIOLET"]
    }


    def loadPrefs(self, filename=prefsFile):
        """
        """
        if not filename:
            return {}
        try:
            with open(filename) as f:
                prefs = json.load(f)
                if isinstance(prefs, dict):
                    return prefs
        except IOError:
            # TODO: Report a problem, or just ignore?
            pass
        return {}


    def savePrefs(self, filename=prefsFile):
        """
        """
        try:
            with open(filename, 'w') as f:
                json.dump(self.prefs, f, indent="  ", sort_keys=True)
        except IOError:
            # TODO: Report a problem, or just ignore?
            pass
    
    
    
    def __init__(self, *args, **kwargs):
        prefsFile = kwargs.pop('prefsFile', self.prefsFile)
        self.prefs = self.defaultPrefs.copy()
        self.prefs.update(self.loadPrefs(prefsFile))
        
        super(ViewerApp, self).__init__(*args, **kwargs)
                

    def OnInit(self):
        self._antiAliasingEnabled = True
        viewTitle = u'%s v%s' % (APPNAME, __version__)
        self.viewers = [Viewer(None, title=viewTitle, app=self)]
        
        for v in self.viewers:
            v.Show() 
            
        return True


#===============================================================================
# 
#===============================================================================

# XXX: Change this back for 'real' version
if True:#__name__ == '__main__':
    app = ViewerApp()
    app.MainLoop()