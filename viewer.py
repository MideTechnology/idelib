'''
Slam Stick eXtreme Data Viewer

Description should go here. At the moment, this is also the text that appears
in the About Box.

### This line and below are not in the About Box. ###

@todo: See individual TODO tags in the body of code. The long-term items
    are also listed here.
@todo: Multi-threaded plot drawing, so the app won't appear to hang and drawing
    can be interrupted.
@todo: Revamp the zooming and navigation to be event-driven, handled as far up
    the chain as possible. Consider using wx.lib.pubsub if it's thread-safe
    in conjunction with wxPython views.
@todo: Refactor the user preferences, maybe using `wx.Config` so the wxWidgets
    file history system can be used.

'''

APPNAME = u"Slam Stick X Data Viewer"
__version__="0.1"
__copyright__=u"Copyright (c) 2014 Mid\xe9 Technology"
__url__ = ("http://mide.com", "")
__credits__=["David R. Stokes", "Tim Gipson"]

# XXX: REMOVE THIS BEFORE RELEASE!
from dev_build_number import BUILD_NUMBER, BUILD_TIME
__version__ = '%s.%04d' % (__version__, BUILD_NUMBER)

from datetime import datetime
import fnmatch
import json
import os
import sys
from textwrap import dedent

from wx.lib.rcsizer import RowColSizer
from wx.lib.wordwrap import wordwrap
import wx; wx = wx # Workaround for Eclipse code comprehension

# Graphics (icons, etc.)
import images

# Custom controls, events and base classes
from base import ViewerPanel, MenuMixin
from common import StatusBar
from events import *
from timeline import TimelineCtrl, TimeNavigatorCtrl

# Views, dialogs and such
import config_dialog
from device_dialog import selectDevice
import export_dialog as xd
from fileinfo import RecorderInfoDialog
from fft import FFTView, SpectrogramView
from loader import Loader
from plots import PlotSet
from preference_dialog import PrefsDialog
from range_dialog import RangeDialog

# XXX: EXPERIMENTAL
from memorydialog import MemoryDialog

# Special helper objects and functions
import devices
from threaded_file import ThreadAwareFile

# The actual data-related stuff
import mide_ebml

ANTIALIASING_MULTIPLIER = 3.33
RESAMPLING_JITTER = 0.125

# XXX: Debugging. Remove later!
from mide_ebml.dataset import __DEBUG__

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
        """ Retrieve the value at a given horizontal pixel position.
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
        # Capture the click position for processing drags in OnMouseMotion
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
            # The timeline is being dragged
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
        
        self._addButton(sizer, images.zoomOutH, self.OnZoomOut, 
                        tooltip="Zoom Out (X axis)")
        self._addButton(sizer, images.zoomInH, self.OnZoomIn, 
                        tooltip="Zoom In (X axis)")
        self._addButton(sizer, images.zoomFitH, self.OnZoomFit, 
                        tooltip="Zoom to fit entire loaded time range (X axis)")
        
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


    def zoom(self, percent, tracking=True, useKeyboard=False):
        """ Increase or decrease the size of the visible range.
        
            @param percent: A zoom factor. Use a normalized value, positive
                to zoom in, negative to zoom out.
            @keyword tracking: `True` if the widget doing the update is 
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond if 
                `tracking` is `True`.
            @keyword useKeyboard: If `True`, the state of the modifier keys
                is checked, multiplying the amount of zoom.
        """
        if useKeyboard:
            if wx.GetKeyState(wx.WXK_CONTROL):
                percent *= 2
            if wx.GetKeyState(wx.WXK_SHIFT):
                percent /= 2
            if wx.GetKeyState(wx.WXK_ALT):
                percent *= 10

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
        self.zoom(.25, False, useKeyboard=True)

    
    def OnZoomOut(self, evt):
        """ Handle 'zoom out' events, i.e. the zoom in button was pressed. 
        """
        self.zoom(-.25, False, useKeyboard=True)


    def OnZoomFit(self, evt):
        """
        """
        self.setVisibleRange(*self.timerange)
        self.postSetVisibleRangeEvent(*self.timerange, tracking=False)

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
        startLabel.SetSizerProps(valign="center")
        endLabel.SetSizerProps(valign="center")
        self.startUnits.SetSizerProps(valign="center")
        self.endUnits.SetSizerProps(valign="center")

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
    ID_FILE_PROPERTIES = wx.NewId()
    ID_EDIT_CLEARPREFS = wx.NewId()
    ID_EDIT_RANGES = wx.NewId()
    ID_DEVICE_CONFIG = wx.NewId()
    ID_DEVICE_SET_CLOCK = wx.NewId()
    ID_VIEW_ZOOM_OUT_Y = wx.NewId()
    ID_VIEW_ZOOM_IN_Y = wx.NewId()
    ID_VIEW_ZOOM_FIT_Y = wx.NewId()
    ID_VIEW_ANTIALIAS = wx.NewId()
    ID_VIEW_JITTER = wx.NewId()
    ID_VIEW_UTCTIME = wx.NewId()
    ID_VIEW_MINMAX = wx.NewId()
    ID_VIEW_MEAN = wx.NewId()
    ID_VIEW_LINES_MAJOR = wx.NewId()
    ID_VIEW_LINES_MINOR = wx.NewId()
    ID_DATA_MEAN_SUBMENU = wx.NewId()
    ID_DATA_NOMEAN = wx.NewId()
    ID_DATA_MEAN = wx.NewId()
    ID_DATA_MEAN_TOTAL = wx.NewId()
    ID_DATA_NOMEAN_ALL = wx.NewId()
    ID_DATA_NOMEAN_NONE = wx.NewId()

    ID_DEBUG_SUBMENU = wx.NewId()
    ID_DEBUG_SAVEPREFS = wx.NewId()
    ID_DEBUG0 = wx.NewId()
    ID_DEBUG1 = wx.NewId()
    ID_DEBUG2 = wx.NewId()
    ID_DEBUG3 = wx.NewId()
    ID_DEBUG4 = wx.NewId()


    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Frame/MenuMixin arguments plus:
        
            @keyword app: The viewer's parent application.
        """
        self.app = kwargs.pop('app', None)
        self.units = kwargs.pop('units',('seconds','s'))
        self.drawingSuspended = False
        
        filename = kwargs.pop('filename', None)
        
        displaySize = wx.DisplaySize()
        windowSize = int(displaySize[0]*.66), int(displaySize[1]*.66)
        kwargs['size'] = kwargs.get('size', windowSize)
        
        super(Viewer, self).__init__(*args, **kwargs)
        
        self.loadPrefs()
        
        self.showUtcTime = False
        
        self.dataset = None
        self.session = None
        self.cancelQueue = []
        
        self.buildUI()
        self.Centre()
        self.Show()
        
        self.plots = []
        self._nextColor = 0
        self.setVisibleRange(self.timerange[0], self.timerange[1])
        
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
        elif self.app.getPref('openOnStart', True):
            self.OnFileOpenMenu(None)


    def loadPrefs(self):
        """ Get all the attributes that are read from the preferences.
            Separated from `__init__` to allow reloading after editing in the
            preferences dialog.
        """
        self.uiBgColor = wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE)
        self.xFormatter = "X: %%.%df %%s" % self.app.getPref('precisionX', 4)
        self.yFormatter = "Y: %%.%df %%s" % self.app.getPref('precisionY', 4)
        self.antialias = self.app.getPref('antialiasing', False)
        self.aaMultiplier = self.app.getPref('antialiasingMultiplier', 
                                             ANTIALIASING_MULTIPLIER)
        self.noisyResample = self.app.getPref('resamplingJitter', False)
        self.showUtcTime = self.app.getPref('showUtcTime', False)
        self.drawMinMax = self.app.getPref('drawMinMax', False)
        self.drawMean = self.app.getPref('drawMean', False)
        self.drawMajorHLines = self.app.getPref('drawMajorHLines', True)
        self.drawMinorHLines = self.app.getPref('drawMinorHLines', False)
        
        self.showDebugChannels = self.app.getPref('showDebugChannels', True)


    def buildMenus(self):
        """ Construct and configure the view's menu bar. Called once by
            `buildUI()`. Used internally.
        """        
        self.menubar = wx.MenuBar()
        
        # "File" menu
        #=======================================================================
        fileMenu = wx.Menu()
        self.addMenuItem(fileMenu, wx.ID_NEW, "&New Viewer Window\tCtrl+N", "",
                         self.OnFileNewMenu)
        self.addMenuItem(fileMenu, wx.ID_CLOSE, 
                         "Close Viewer Window\tCtrl+W", "", self.OnClose)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_OPEN, "&Open...\tCtrl+O", "", 
                         self.OnFileOpenMenu)
        self.addMenuItem(fileMenu, wx.ID_CANCEL, "Stop Importing\tCrtl-.", "", 
                         self.cancelOperation, enabled=False)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, self.ID_EXPORT, 
                         "&Export Data (CSV)...\tCtrl+S", "", self.exportCsv)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, self.ID_RENDER_FFT, 
                         "Render &FFT...\tCtrl+F", "", 
                         self.renderFFT)
        self.addMenuItem(fileMenu, self.ID_RENDER_SPEC, 
                         "Render Spectro&gram (2D FFT)...\tCtrl+G", "", 
                         self.renderSpectrogram)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, self.ID_FILE_PROPERTIES, 
                         "Recording Properties...\tCtrl+I", "", 
                         self.OnFileProperties)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_PRINT, "&Print...\tCtrl+P", "", 
                         enabled=False)
        self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, "Print Setup...", "", 
                         enabled=False)
        fileMenu.AppendSeparator()
#         self.recentFilesMenu = wx.Menu()
#         fileMenu.AppendMenu(self.ID_RECENTFILES, "Recent Files", 
#                             self.recentFilesMenu)
#         fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_EXIT, 'E&xit\tCtrl+Q', '', 
                self.OnFileExitMenu)
        wx.App.SetMacExitMenuItemId(wx.ID_EXIT)
        self.menubar.Append(fileMenu, '&File')
        
        # "Edit" menu
        #=======================================================================
        editMenu = wx.Menu()
        self.addMenuItem(editMenu, wx.ID_CUT, "Cut", "", enabled=False)
        self.addMenuItem(editMenu, wx.ID_COPY, "Copy", "", enabled=False)
        self.addMenuItem(editMenu, wx.ID_PASTE, "Paste", "", enabled=False)
        editMenu.AppendSeparator()
#         self.addMenuItem(editMenu, self.ID_EDIT_CLEARPREFS, 
#                          "Reset Hidden Dialogs and Warnings", "", 
#                          self.OnClearPrefs)
        self.addMenuItem(editMenu, wx.ID_PREFERENCES, "Preferences...", "",
                         self.app.editPrefs)
        self.menubar.Append(editMenu, '&Edit')

        # "View" menu
        #=======================================================================
        viewMenu = wx.Menu()
        self.addMenuItem(viewMenu, wx.ID_REFRESH, "&Redraw Plots\tCtrl+R", "",
                         self.plotarea.redraw)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_EDIT_RANGES, 
                         "Edit Visible Ranges...\tCtrl+E", "", 
                         self.OnEditRanges)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, wx.ID_ZOOM_OUT, "Zoom Out X\tCtrl+-", "",
                         self.navigator.OnZoomOut)
        self.addMenuItem(viewMenu, wx.ID_ZOOM_IN, "Zoom In X\tCtrl+=", "",
                         self.navigator.OnZoomIn)
        self.addMenuItem(viewMenu, wx.ID_ZOOM_FIT, "Zoom to Fit X\tCtrl+0", "",
                         self.navigator.OnZoomFit)
        self.addMenuItem(viewMenu, self.ID_VIEW_ZOOM_OUT_Y, 
                         "Zoom Out Y\tAlt+-", '', self.OnZoomOutY)
        self.addMenuItem(viewMenu, self.ID_VIEW_ZOOM_IN_Y, 
                         "Zoom In Y\tAlt+=", '', self.OnZoomInY)
        self.addMenuItem(viewMenu, self.ID_VIEW_ZOOM_FIT_Y, 
                        "Zoom to Fit Y\tAlt+0", '', self.OnZoomFitY)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_ANTIALIAS, 
                         "Antialiased Drawing", "", 
                         self.OnToggleAA, kind=wx.ITEM_CHECK)
        self.addMenuItem(viewMenu, self.ID_VIEW_JITTER,
                        "Noisy Resampling", "", 
                        self.OnToggleNoise, kind=wx.ITEM_CHECK)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_MINMAX,
                         "Show Buffer Minimum/Maximum", "",
                         self.OnToggleMinMax, kind=wx.ITEM_CHECK)
        self.addMenuItem(viewMenu, self.ID_VIEW_MEAN,
                         "Show Buffer Mean", "",
                         self.OnToggleViewMean, kind=wx.ITEM_CHECK)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_LINES_MAJOR,
                         "Show Major Horizontal Gridlines\tCtrl+'", "",
                         self.OnToggleLinesMajor, kind=wx.ITEM_CHECK)
        self.addMenuItem(viewMenu, self.ID_VIEW_LINES_MINOR,
                         "Show Minor Horizontal Gridlines\tCtrl+SHIFT+'", "",
                         self.OnToggleLinesMinor, kind=wx.ITEM_CHECK)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_UTCTIME, 
                         "Show Absolute UTC Time", "",
                         self.OnToggleUtcTime, kind=wx.ITEM_CHECK)
        self.menubar.Append(viewMenu, 'V&iew')

        deviceMenu = wx.Menu()
        self.addMenuItem(deviceMenu, self.ID_DEVICE_CONFIG, 
                        "Configure &Device...\tCtrl+D", "", 
                         self.OnDeviceConfigMenu)
        self.menubar.Append(deviceMenu, 'De&vice')
        
        # "Data" menu
        #=======================================================================
        dataMenu = wx.Menu()
        meanMenu = wx.Menu()
        self.addMenuItem(meanMenu, self.ID_DATA_NOMEAN, 
                         "Do Not Remove Mean", "",
                         self.OnDontRemoveMeanCheck, kind=wx.ITEM_RADIO)
        self.addMenuItem(meanMenu, self.ID_DATA_MEAN, 
                         "Remove Rolling Mean from Data", "",
                         self.OnRemoveRollingMeanCheck, kind=wx.ITEM_RADIO)
        self.addMenuItem(meanMenu, self.ID_DATA_MEAN_TOTAL, 
                         "Remove Total Mean from Data", "",
                         self.OnRemoveTotalMeanCheck, kind=wx.ITEM_RADIO)
        dataMenu.AppendMenu(self.ID_DATA_MEAN_SUBMENU, "Remove Mean", meanMenu)
        self.menubar.Append(dataMenu, "&Data")
        
        # "Help" menu
        #=======================================================================
        helpMenu = wx.Menu()
        self.addMenuItem(helpMenu, wx.ID_ABOUT, 
                         "About %s %s..." % (APPNAME, __version__), "", 
                         self.OnHelpAboutMenu)
        debugMenu = wx.Menu()
        helpMenu.AppendSeparator()
        self.addMenuItem(debugMenu, self.ID_DEBUG_SAVEPREFS, 
                         "Save All Preferences", "",
                         lambda(evt): self.app.saveAllPrefs())
#         self.addMenuItem(debugMenu, self.ID_DEBUG0, "Ask test","",
#                          self.DEBUG_OnTestAsk)
        
        self.menubar.Append(helpMenu, '&Help')
        helpMenu.AppendMenu(self.ID_DEBUG_SUBMENU, "Debugging", debugMenu)

        # Finishing touches.
        #=======================================================================
        self.SetMenuBar(self.menubar)
        self.enableMenus(False)


    
    def buildUI(self):
        """ Construct and configure all the viewer window's panels. Called once
            by the constructor. Used internally.
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
        # These are the menus that are enabled even when there's no file open.
        # There are fewer of them than menus that are disabled.
        menus = (wx.ID_NEW, wx.ID_OPEN, wx.ID_EXIT, self.ID_DEVICE_CONFIG,
                 wx.ID_ABOUT, self.ID_DEBUG_SUBMENU, self.ID_DEBUG_SAVEPREFS,
                 self.ID_DEBUG0, self.ID_DEBUG1, self.ID_DEBUG2, self.ID_DEBUG3,
                 self.ID_DEBUG4)
        
        if not enabled:
            self.enableMenuItems(self.menubar, menus, True, False)
        else:
            self.enableMenuItems(self.menubar, enable=True)
    
        # the 'show properties' menu is only enabled if there is recorder info
        m = self.menubar.FindItemById(self.ID_FILE_PROPERTIES)
        m.Enable(enabled and self.dataset.recorderInfo is not None)

        # Some items should always be disabled unless explicitly enabled
        alwaysDisabled = (wx.ID_CUT, wx.ID_COPY, wx.ID_PASTE, 
                          wx.ID_PRINT, wx.ID_PRINT_SETUP)

        self.enableMenuItems(self.menubar, alwaysDisabled, False)

    
    def enableChildren(self, enabled=True):
        """ Enable (or disable) all child UI items.
            
            @keyword enabled: `True` (default) to enable the children, 
                `False` to disable.
        """
        for c in self.Children:
            c.Enable(enabled)


    #===========================================================================
    # 
    #===========================================================================

    def ask(self, message, title="Confirm", style=wx.YES_NO | wx.NO_DEFAULT, 
            icon=wx.ICON_QUESTION, parent=None, pref=None, saveNo=True,
            extendedMessage=None, rememberMsg=None, persistent=True):
        """ Generate a message box to notify or prompt the user, allowing for
            a simple means of turning off such warnings and prompts. If a
            preference name is supplied and that preference exists, the user
            will not be prompted and the remembered value will be returned.If 
            the preference doesn't exist, the dialog will contain a 'remember' 
            checkbox that, if checked, will save the user's response as the 
            preference. "Cancel" (if the dialog has the button) will never be 
            saved.
            
            @param message: The main message/prompt to display
            @keyword title: The dialog's title
            @keyword style: Standard wxWindows style flags
            @keyword icon: The wxWindows style flag for the icon to display.
                Separated from `style` because `MemoryDialog` always needs an 
                icon, making it behave differently than normal dialogs.
            @keyword parent: The dialog's parent; defaults to `self`.
            @keyword pref: The name of the preference to load and/or save
            @keyword extendedMessage: A longer, more detailed message.
            @keyword rememberMessage: The prompt next to the 'remember'
                checkbox (if shown).
            @keyword persistent: If `False` and 'remember' is checked, the
                result is saved in memory but not written to disk.
        """
        style |= icon
        parent = self or parent
        if pref is not None and self.app.hasPref(pref, section="ask"):
            return self.app.getPref(pref, section="ask")
        remember = pref is not None
        dlg = MemoryDialog(parent, message, title, style, remember=remember)
        if extendedMessage:
            dlg.SetExtendedMessage(extendedMessage)
        result = dlg.ShowModal()
        savePref = result != wx.ID_CANCEL or (result == wx.ID_NO and saveNo)
        if pref is not None and savePref:
            if dlg.getRememberCheck():
                self.app.setPref(pref, result, "ask", persistent)
        dlg.Destroy()
        return result


    def getSaveFile(self, message, defaults=None, types=None, 
                    style=wx.SAVE|wx.OVERWRITE_PROMPT):
        """ Wrapper for showing getting the name of an output file.
        """
        defaults = self.getDefaultExport() if defaults is None else defaults
        types = self.app.getPref('exportTypes') if types is None else types
        
        defaultDir, defaultFile = defaults
        filename = None
        
        dlg = wx.FileDialog(self, message=message, 
                            defaultDir=defaultDir,  defaultFile=defaultFile, 
                            wildcard='|'.join(types), 
                            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
        
        return filename

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
        
        for d in self.dataset.getPlots(debug=self.showDebugChannels):
            self.plotarea.addPlot(d.getSession(self.session.sessionId), 
                                  title=d.name)
        
        self.enableChildren(True)
        # enabling plot-specific menu items happens on page select; do manually
#         if len(self.plotarea):
        self.plotarea.getActivePage().enableMenus()

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
        """ Get the path and name of the default data file. If the app is
            running directly off a recorder, the recorder's data directory
            is returned.
        """
        curdir = os.path.realpath(os.path.curdir)
        recorder = devices.onRecorder(curdir)
        if recorder:
            datadir = os.path.join(recorder, "DATA")
            if os.path.exists(datadir):
                return (datadir, '')
            return (recorder, '')
        # TODO: Use a path from the file history, maybe?
        return (curdir, '')


    def getDefaultExport(self):
        """ Get the path and name of the default export file.
        """
        # TODO: This should be based on the current path.
        if not self.dataset or not self.dataset.filename:
            return (os.path.realpath(os.path.curdir), "export.csv")
        filename = os.path.splitext(os.path.basename(self.dataset.filename))[0]
        return (os.path.realpath(os.path.curdir), filename + ".csv")


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
        q = self.ask("Really quit?", "Quit", wx.OK|wx.CANCEL,
                     pref="promptBeforeQuit")
        return q == wx.ID_OK

    #===========================================================================
    # 
    #===========================================================================
    
    def openFile(self, filename, prompt=True):
        """ Open a recording file. This also handles prompting the user when
            a file is loading or has already been loaded.
            
            @param filename: The full path and name of the file to open. 
            @keyword prompt: If `True`, the user will be warned before loading
                a new file over the old one. If `False`, the old file will
                get clobbered automatically.
        """
        if prompt and self.dataset is not None:
            if self.dataset.loading is True:
                if self.ask("Abort loading the current file?") != wx.ID_YES:
                    return
            else:
                q = self.ask("Do you want to close the current file?\n"
                             "'No' will open the file in another window.",
                             "Open File",style=wx.YES_NO|wx.CANCEL,
                             pref="openInSameWindow")
                if q == wx.ID_NO:
                    self.app.createNewView(filename=filename)
                    return
                elif q == wx.ID_CANCEL:
                    return
                
        self.closeFile()
        
        try:
            stream = ThreadAwareFile(filename, 'rb')
            newDoc = mide_ebml.dataset.Dataset(stream, quiet=True)
            self.app.addRecentFile(filename, 'import')
            if newDoc.schemaVersion < newDoc.ebmldoc.version:
                q = self.root.ask("The data file was created using a newer "
                  "version of the MIDE EBML schema (viewer version is %s, "
                  "file version is %s); this could potentially cause problems. "
                  "\n\nOpen anyway?" % (newDoc.schemaVersion, 
                                        newDoc.ebmldoc.version), 
                  "Schema Version Mismatch", wx.YES|wx.CANCEL, wx.ICON_WARNING,
                  pref="schemaVersionMismatch")
                if q == wx.ID_NO:
                    stream.closeAll()
                    return
        # More specific exceptions should be caught here, before ultimately:
        except Exception as err:
            # Catch-all for unanticipated errors
            stream.closeAll()
            self.handleException(err, what="importing the file %s" % filename,
                                 closeFile=True)
            return
        
        self.dataset = newDoc
        loader = Loader(self, newDoc, **self.app.getPref('loader'))
        self.pushOperation(loader)
        self.SetTitle(self.app.getWindowTitle(filename))
        loader.start()
        self.enableMenus(True)
    
    
    def closeFile(self):
        """ Close a file. Does not close the viewer window itself.
        """
        self.cancelOperation()
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
        removeMean = 0
        if self.plotarea[0].source.removeMean:
            removeMean = 2 if self.plotarea[0].source.rollingMeanSpan == -1 else 1
        settings = xd.CSVExportDialog.getExport(root=self, 
                                                removeMean=removeMean)
        
        if settings is None:
            return
        
        source = settings['source']
        subchannels = settings['channels']
        subchannelIds = [c.id for c in subchannels]
        start, stop = settings['indexRange']
        addHeaders = settings['addHeaders']
        removeMeanType = settings.get('removeMean', 0)
        
        removeMean = removeMeanType > 0
        if removeMeanType == 1:
            meanSpan = self.app.getPref('rollingMeanSpan', 5) / self.timeScalar
        else:
            meanSpan = -1
        
        filename = self.getSaveFile("Export CSV...")
        if filename is None:
            return

        try:
            stream = open(filename, 'w')
        except Exception as err:
            self.handleException(err, what="exporting CSV")
            return
        
        self.drawingSuspended = True
        numRows = stop-start
        msg = "Exporting %d rows" % numRows
        dlg = xd.ModalExportProgress("Exporting CSV", msg, maximum=numRows, 
                                     parent=self)
        
        source.exportCsv(stream, start=start, stop=stop, 
                         subchannels=subchannelIds, timeScalar=self.timeScalar, 
                         callback=dlg, callbackInterval=0.0005, 
                         raiseExceptions=True,
                         useIsoFormat=settings['useIsoFormat'],
                         useUtcTime=settings['useUtcTime'],
                         headers=addHeaders,
                         removeMean=removeMean,
                         meanSpan=meanSpan)
        
        dlg.Destroy()
        stream.close()
        self.drawingSuspended = False


    def _formatTime(self, t):
        places = self.app.getPref("precisionX", 4)
        return ("%%.%df" % places) % (t * self.timeScalar)


    def renderFFT(self, evt=None):
        """ Create a 1D FFT plot after getting input from the user (range,
            window size, etc.).
            
            @keyword evt: An event (not actually used), making this method
                compatible with event handlers.
        """
        settings = xd.FFTExportDialog.getExport(root=self)
        if settings is None:
            return
        
        source = settings.get('source', None)
        subchannels = settings['channels']
        startTime, stopTime = settings['timeRange']
        sliceSize = settings['windowSize']
        
        title = "FFT: %s (%ss to %ss)" % (
                      ", ".join([c.name for c in subchannels]), 
                      self._formatTime(startTime), self._formatTime(stopTime)) 
        viewId = wx.NewId()
        size = self.GetSize()
        
        try:
            view = FFTView(self, viewId, title=title, size=size, root=self, 
                   source=source, subchannels=subchannels, start=startTime, 
                   end=stopTime, sliceSize=sliceSize)
            self.fftViews[viewId] = view
        except Exception as e:
            self.handleException(e, what="generating FFT")


    def renderSpectrogram(self, evt=None):
        """ Create a 2D FFT/Time plot.
            
            @keyword evt: An event (not actually used), making this method
                compatible with event handlers.
        """
        # TODO: Much of this is identical to FFT rendering; refactor to share.
        settings = xd.SpectrogramExportDialog.getExport(root=self)
        if settings is None:
            return
        
        source = settings.get('source', None)
        subchannels = settings['channels']
        startTime, stopTime = settings['timeRange']
#         sliceSize = settings['windowSize']
        slicesPerSec = settings['slices']
        
        title = "Spectrogram: %s (%ss to %ss)" % (
                      ", ".join([c.name for c in subchannels]), 
                      self._formatTime(startTime), self._formatTime(stopTime)) 
        viewId = wx.NewId()
        size = self.GetSize()

        try:
            view = SpectrogramView(self, viewId, title=title, size=size, 
                   root=self, source=source, subchannels=subchannels, 
                   start=startTime, end=stopTime, slicesPerSec=slicesPerSec,)
                    #sliceSize=sliceSize)
            self.fftViews[viewId] = view
        except Exception as e:
            self.handleException(e, what="generating Spectrogram")
        
    #===========================================================================
    # 
    #===========================================================================

    def getPlotColor(self, source):
        """ Get the plotting color for a data source. The color is retrieved
            from the preferences. Channel/subchannel combinations not known are
            assigned one of the standard default colors.
        
            @param source: The source, either `mide_ebml.dataset.Channel`,
                `mide_ebml.dataset.SubChannel`, or `mide_ebml.dataset.EventList`
        """
        if isinstance(source, mide_ebml.dataset.EventList):
            source = source.parent
            
        try:
            sourceId = "%02x.%d" % (source.parent.id, 
                                    source.id)
            color = self.root.app.getPref('plotColors')[sourceId]
        except (KeyError, AttributeError):
            defaults = self.app.getPref('defaultColors')
            color = defaults[self._nextColor % len(defaults)]
            self._nextColor += 1
        
        return color
            
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
        self.cancelAllOperations()
        
        # Close related windows
        for fft in self.fftViews.itervalues():
            try:
                fft.Destroy()
            except (AttributeError, wx.PyDeadObjectError):
                # FFT view may already have been destroyed; that's okay.
                pass
            
        self.Destroy()
        evt.Skip()
    
    
    #===========================================================================
    # Menu Events
    #===========================================================================

    def OnFileNewMenu(self, evt):
        """
        """
        self.app.createNewView()


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
            self.openFile(dlg.GetPath())
            
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


    def OnFileProperties(self, evt):
        """
        """
        if self.dataset:
            RecorderInfoDialog.showRecorderInfo(self.dataset)
        

    def OnClearPrefs(self, evt):
        """
        """
        self.app.deletePref(section="ask")

    def OnEditRanges(self, evt):
        """
        """
        newRanges = RangeDialog.display(self)
        if newRanges is not None:
            self.setVisibleRange(*newRanges[0])
            p = self.plotarea.getActivePage()
            if p is not None:
                p.setValueRange(*newRanges[1])
                

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
        desc = wordwrap(desc, 350, wx.ClientDC(self))
        vers = "Version %s (build %d), %s" % (__version__, BUILD_NUMBER, 
                                    datetime.fromtimestamp(BUILD_TIME).date())
        
        info = wx.AboutDialogInfo()
        info.Name = APPNAME
        info.Version = __version__
        info.Copyright = __copyright__
        info.Description = "%s\n%s" % (desc, vers)
        info.WebSite = __url__
#         info.Developers = __credits__
#         info.License = wordwrap(__license__, 500, wx.ClientDC(self))
        wx.AboutBox(info)
    

    def OnDontRemoveMeanCheck(self, evt):
        """
        """ 
        if isinstance(evt, bool):
            self.setMenuItem(self.menubar, self.ID_DATA_NOMEAN, checked=evt)
            
        for p in self.plotarea:
            p.removeMean(False)
        

    def OnRemoveRollingMeanCheck(self, evt):
        """ Handler for ID_DATA_MEAN menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.
            
            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """ 
        if isinstance(evt, bool):
            self.setMenuItem(self.menubar, self.ID_DATA_MEAN, checked=evt)
            checked = evt
        else:
            checked = evt.IsChecked() 
            
        span = self.app.getPref('rollingMeanSpan', 5) / self.timeScalar
        for p in self.plotarea:
            p.removeMean(checked, span=span)


    def OnRemoveTotalMeanCheck(self, evt):
        """ Handler for ID_DATA_MEAN menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.
            
            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """ 
        if isinstance(evt, bool):
            self.setMenuItem(self.menubar, self.ID_DATA_MEAN_TOTAL, 
                             checked=evt)
            checked = evt
        else:
            checked = evt.IsChecked() 
            
        for p in self.plotarea:
            p.removeMean(checked, span=-1)


    def OnZoomInY(self, evt):
        p = self.plotarea.getActivePage()
        if p is not None:
            p.zoomIn()


    def OnZoomOutY(self, evt):
        p = self.plotarea.getActivePage()
        if p is not None:
            p.zoomOut()

    def OnZoomFitY(self, evt):
        p = self.plotarea.getActivePage()
        if p is not None:
            p.zoomToFit()

    def OnToggleAA(self, evt):
        """ Handler for ID_VIEW_ANTIALIAS menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.
            
            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """ 
        if isinstance(evt, bool):
            checked = evt
            self.setMenuItem(self.ID_VIEW_ANTIALIAS, checked=evt)
        else:
            checked = evt.IsChecked()
             
        self.antialias = self.app.setPref('antialiasing', checked)
        self.plotarea.setAntialias(checked)
        

    def OnToggleNoise(self, evt):
        """ Handler for ID_VIEW_JITTER menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.
            
            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """ 
        if isinstance(evt, bool):
            checked = evt
            self.setMenuItem(self.ID_VIEW_JITTER, checked=evt)
        else:
            checked = evt.IsChecked()
            
        # 'noisy resampling' is turned on or off by changing its amount.
        if checked:
            self.noisyResample = self.app.getPref('resamplingJitterAmount', 
                                                  RESAMPLING_JITTER)
        else:
            self.noisyResample = 0
        
        self.app.setPref('resamplingJitter', checked)
        self.plotarea.redraw()


    def OnToggleUtcTime(self, evt):
        """ Handler for ID_VIEW_UTCTIME menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.
            
            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """ 
        if isinstance(evt, bool):
            checked = evt
            self.menubar.FindItemById(self.ID_VIEW_UTCTIME).Check(evt)
        else:
            checked = evt.IsChecked()
        self.showUtcTime = self.app.setPref('showUtcTime', checked)


    def OnToggleMinMax(self, evt):
        """ Handler for ID_VIEW_MINMAX menu item selection.
        """
        self.drawMinMax = self.app.setPref('drawMinMax', evt.IsChecked())
        self.plotarea.redraw()
    
    def OnToggleViewMean(self, evt):
        """
        """
        self.drawMean = self.app.setPref('drawMean', evt.IsChecked())
        self.plotarea.redraw()
    
    def OnToggleLinesMajor(self, evt):
        """ Handler for ID_VIEW_LINES_MAJOR menu item selection.
        """
        checked = evt.IsChecked()
        self.drawMajorHLines = self.app.setPref('drawMajorHLines', checked)
        self.plotarea.redraw()
    
    
    def OnToggleLinesMinor(self, evt):
        """ Handler for ID_VIEW_LINES_MAJOR menu item selection.
        """
        checked = evt.IsChecked()
        self.drawMinorHLines = self.app.setPref('drawMinorHLines', checked)
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
        self.removeOperation(evt.job)
        self.menubar.FindItemById(wx.ID_CANCEL).Enable(False)


    #===========================================================================
    # Background operation stuff
    #===========================================================================

    def pushOperation(self, job):
        """ Adds a task thread to the stack of operations. All keyword arguments
            override attributes of the job object itself if not `None`.
            
            @param job: A `Job` process.
            @keyword modal: Can this operation not run in the background?
                Not currently implemented.
            @keyword prompt: Should the user be prompted prior to canceling?
            @keyword title: The title of the cancel dialog (if applicable).
            @keyword pref: The name of the preference to be used to suppress
                the cancel dialog, or `None` if the dialog isn't 'memorable.'
        """
        # The initial implementation is simply a list, wrapped for future dev.
        self.cancelQueue.append(job)
    
    
    def removeOperation(self, job):
        """ Given an instance of `Job`, remove its corresponding entry in the
            queue. Note that this does not cancel a job, only removes it from
            the queue. 
            
            @param job: A `Job` object.
            @return: `True` if the operation was removed, `False` if not.
        """
        # The initial implementation is simply a list, wrapped for future dev.
        if job is None:
            return False
        try:
            self.cancelQueue.remove(job)
            return True
        except ValueError:
            return False

    def getCurrentOperation(self):
        """ Retrieve the currently-running background task.
        """
        # The initial implementation is simply a list, wrapped for future dev.
        if len(self.cancelQueue) == 0:
            return None
        return self.cancelQueue[-1]
        

    def cancelOperation(self, evt=None, job=None, prompt=True):
        """ Cancel the current background operation. 
            
            @keyword evt: The event that initiated the cancel, if any.
            @keyword job: A specific `Job` to cancel. Defaults to the last
                job started.
            @keyword prompt: `True` to prompt the user before canceling (job
                must also have its `cancelPrompt` attribute `True`), `False`
                to suppress the prompt.
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
        
        if job is None:
            job = self.getCurrentOperation()
        
        if job.cancelPrompt and prompt:
            if self.ask(job.cancelMessage, job.cancelTitle, 
                        pref=job.cancelPromptPref) != wx.ID_YES:
                return False
        
        cancelled = job.cancel()
        if cancelled:
            msg = job.cancelResponse
            self.removeOperation(job)
            if len(self.cancelQueue) == 0:
                self.stopBusy()
            return msg

    
    def cancelAllOperations(self, evt=None, prompt=False):
        """
        """
        while len(self.cancelQueue) > 0:
            self.cancelOperation(prompt=prompt)

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
            self.statusBar.SetStatusText("", self.statusBar.xFieldNum)
            self.statusBar.SetStatusText("", self.statusBar.utcFieldNum)
            return
        
        units = self.units[1] if units is None else units
        t = self.timeline.getValueAt(pos) * self.timeScalar
        msg = self.xFormatter % (t, units)
        self.statusBar.SetStatusText(msg, self.statusBar.xFieldNum)
        
        if self.showUtcTime:# and t != 0:
            utc = str(datetime.utcfromtimestamp(self.session.utcStartTime+t))
            msg = "X (UTC): %s" % utc[:-2]
        else:
            msg = ""
        self.statusBar.SetStatusText(msg, self.statusBar.utcFieldNum)
        
    
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
                        raiseException=False, what='', where=None,
                        fatal=False, closeFile=False):
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
        
        if what:
            what = " while %s" % what
        
        xmsg = None
        
        if not isinstance(msg, basestring):
            # Slightly more specific error messages go here.
            if isinstance(err, MemoryError):
                msg = "The system ran out of memory%s" % what
            else:
                msg = u"An unexpected %s occurred%s" % \
                        (err.__class__.__name__, what)
                xmsg = unicode(err)

        # If exceptions are explicitly raised, raise it.
        if raiseException and isinstance(err, Exception):
            raise err

        if fatal:
            xmsg += "\n\nThe application will now shut down."

        self.ask(msg, APPNAME, wx.OK, icon=icon, extendedMessage=xmsg)
        ctrlPressed = wx.GetKeyState(wx.WXK_CONTROL)
        
        # Holding control when okaying alert shows more more info. 
        if ctrlPressed and isinstance(err, Exception):
            # TODO: Use a better error log display than stderr
            import pdb; pdb.set_trace()
#             raise err
        
        # The error occurred someplace critical; self-destruct!
        if fatal:
            self.Destroy()
        
        if closeFile:
            self.closeFile()
 

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
    
    # Default settings. Any user-changed preferences override these.
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
        
        # Data modifications
        'removeMean': False,
        'rollingMeanSpan': 5.0, # In seconds
        
        # Rendering
        'antialiasing': False,
        'antialiasingMultiplier': ANTIALIASING_MULTIPLIER,
        'resamplingJitter': False,
        'resamplingJitterAmount': RESAMPLING_JITTER,
        'drawMajorHLines': True,
        'drawMinorHLines': True, #False,
        'drawMinMax': False,
        'drawMean': True,
        'originHLineColor': wx.Colour(200,200,200),
        'majorHLineColor': wx.Colour(240,240,240),
        'minorHLineColor': wx.Colour(240,240,240),
        'minRangeColor': wx.Colour(190,190,255),
        'maxRangeColor': wx.Colour(255,190,190),
        'meanRangeColor': wx.Colour(255,255,150),
        'plotColors': {"00.0": "BLUE",
                       "00.1": "GREEN",
                       "00.2": "RED",
                       "01.0": "DARK GREEN",
                       "01.1": "VIOLET"
        },
        # default colors: used for subchannel plots not in plotColors
        'defaultColors': ["DARK GREEN",
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

        'locale': 'LANGUAGE_ENGLISH_US', # wxPython constant name (wx.*)
#         'locale': 'English_United States.1252', # Python's locale name string
        'loader': dict(numUpdates=100, updateInterval=1.0),
        'warnBeforeQuit': False, #True,
        'openOnStart': True,
        'showDebugChannels': __DEBUG__,
        'showFullPath': False,
        'showUtcTime': False,

        # WVR/SSX-specific parameters: the hard-coded warning range.        
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
        
        def _fix(d):
            if isinstance(d, (list,tuple)):
                d = [_fix(x) for x in d]
            elif isinstance(d, dict):
                for k,v in d.iteritems():
                    d[k] = _fix(v)
            elif isinstance(d, wx.Colour):
                d = tuple(d)
            return d
        
        prefs = _fix(prefs)
        
        # Convert wx.Colour objects and RGB sequences to tuples:
#         for k in fnmatch.filter(prefs.keys(), "*Color"):
#             if not isinstance(prefs[k], basestring):
#                 prefs[k] = tuple(prefs[k])
#         for k in fnmatch.filter(prefs.keys(), "*Colors"):
#             for i in xrange(len(prefs[k])):
#                 if not isinstance(prefs[k][i], basestring):
#                     prefs[k][i] = tuple(prefs[k][i])
        try:
            with open(filename, 'w') as f:
                json.dump(prefs, f, indent=2, sort_keys=True)
            if hideFile and "win" in sys.platform:
                os.system('attrib +h "%s"' % filename)
        except IOError:# as err:
            # TODO: Report a problem, or just ignore?
            pass
        
    
    def saveAllPrefs(self, filename=None, hideFile=None):
        """ Save all preferences, including defaults, to the config file.
            Primarily for debugging.
        """
        prefs = self.defaultPrefs.copy()
        prefs.update(self.prefs)
        self.prefs = prefs
        self.savePrefs(filename, hideFile)
    
    
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


    def getPref(self, name, default=None, section=None):
        """ Retrieve a value from the preferences.
            @param prefName: The name of the preference to retrieve.
            @keyword default: An optional default value to return if the
                preference is not found.
            @keyword section: An optional "section" name from which to
                delete. Currently a prefix in this implementation.
        """
        if section is not None:
            name = "%s.%s" % (section, name)
        return self.prefs.get(name, self.defaultPrefs.get(name, default))


    def setPref(self, name, val, section=None, persistent=True):
        """ Set the value of a preference. Returns the value set as a
            convenience.
        """
        if section is not None:
            name = "%s.%s" % (section, name)
        prefs = self.prefs if persistent else self.defaultPrefs
        prefs[name] = val
        return val


    def hasPref(self, name, section=None, defaults=False):
        """ Check to see if a preference exists, in either the user-defined
            preferences or the defaults.
        """
        if section is not None:
            name = "%s.%s" % (section, name)
        if defaults:
            return (name in self.prefs) or (name in self.defaultPrefs)
        return name in self.prefs
    
    
    def deletePref(self, name=None, section=None):
        """ Delete one or more preferences. Glob-style wildcards are allowed.
        
            @keyword name: The name of the preference to delete. Optional if
                `section` is supplied
            @keyword section: An optional section name, limiting the scope.
            @return: The number of deleted preferences.
        """
        if section is not None:
            name = name if name is not None else "*"
            name = "%s.%s" % (section, name)
        if name is None:
            return
        keys = fnmatch.filter(self.prefs.keys(), name)
        for k in keys:
            self.prefs.pop(k, None)
        return len(keys)
    
    def editPrefs(self, evt=None):
        """
        """
        newPrefs = PrefsDialog.editPrefs(None, self.prefs, self.defaultPrefs)
        if newPrefs is not None:
            self.prefs = newPrefs
            self.savePrefs()
            
            for v in self.viewers:
                v.loadPrefs()
    
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
    
    
    def getWindowTitle(self, filename=None):
        """ Generate a unique viewer window title.
        """
        basetitle = u'%s v%s' % (APPNAME, __version__)
        if filename:
            if self.getPref('showFullPath', False):
                # TODO: Abbreviate path if it's really long (ellipsis in center)
                basetitle = u'%s - %s' % (basetitle, filename)
            else:
                basetitle = u'%s - %s' % (basetitle, os.path.basename(filename))
            
        title = basetitle
        existingTitles = [v.GetTitle() for v in self.viewers]
        i = 0
        while title in existingTitles:
            i += 1
            title = u"%s (%d)" % (basetitle, i)
        return title 
            

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
if __name__ == '__main__':# or True:
    import argparse
    desc = "%s v%s \n%s" % (APPNAME, __version__, __copyright__)
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-f', '--filename',  
                        help="The name of the MIDE (*.IDE) file to import")
    parser.add_argument("-p", "--prefsFile", 
                        help="An alternate preferences file")
    args = parser.parse_args()

    app = ViewerApp(**vars(args))
    app.MainLoop()