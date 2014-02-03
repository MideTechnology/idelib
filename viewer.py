'''
Slam Stick eXtreme Data Viewer

Description should go here. At the moment, this is also the text that appears
in the About Box.

### This line and below are not in the About Box. ###

@todo: See individual TODO tags in the body of code. The long-term items
    are also listed here.
@todo: Revamp the zooming and navigation to be event-driven, handled as far up
    the chain as possible. Consider using wx.lib.pubsub if it's thread-safe
    in conjunction with wxPython views.


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
from fft import FFTView, SpectrogramView
from loader import Loader
from plots import PlotSet

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
        self._nextColor = 0
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
        elif self.app.getPref('openOnStart', True):
            self.OnFileOpenMenu(None)


    def buildMenus(self):
        """ Construct and configure the view's menu bar. Called once by
            `buildUI()`.
        """        
        self.menubar = wx.MenuBar()
        
        fileMenu = wx.Menu()
        self.addMenuItem(fileMenu, wx.ID_NEW, "&New Viewer Window", "",
                         self.OnFileNewMenu)
#         self.addMenuItem(fileMenu, wx.ID_CLOSE, "Close Viewer Window", "",
#                          None)
        fileMenu.AppendSeparator()
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
        self.addMenuItem(fileMenu, self.ID_RENDER_SPEC, 
                         "Render Spectrogram (2D FFT)...", "", 
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
        self.addMenuItem(helpMenu, wx.ID_ABOUT, 
                         "About %s %s..." % (APPNAME, __version__), "", 
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
        menus = (wx.ID_CANCEL, wx.ID_REVERT, wx.ID_SAVEAS, self.ID_RECENTFILES, 
                 self.ID_EXPORT, self.ID_RENDER_FFT, wx.ID_PRINT, 
                 wx.ID_PRINT_SETUP, self.ID_VIEW_ANTIALIAS, self.ID_VIEW_JITTER,
#                  wx.ID_CUT, wx.ID_COPY, wx.ID_PASTE
                 )
        
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


    #===========================================================================
    # 
    #===========================================================================

    def ask(self, message, title="Confirm", 
              style=wx.YES_NO | wx.NO_DEFAULT, icon=wx.ICON_QUESTION,
              parent=None):
        """ Generate a simple modal dialog box and get the button clicked.
        """
        style |= icon
        parent = parent or self
        dlg = wx.MessageDialog(parent, message, title, style)
        result = dlg.ShowModal()
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
        if self.app.getPref('warnBeforeQuit', True):
            return self.ask("Really quit?") == wx.ID_YES
        return True

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
                             "Open File",style=wx.YES_NO|wx.CANCEL)
                if q == wx.ID_NO:
                    self.app.createNewView(filename=filename)
                    return
                elif q == wx.ID_CANCEL:
                    return
                
        self.closeFile()
        
        try:
            stream = ThreadAwareFile(filename, 'rb')
            newDoc = mide_ebml.dataset.Dataset(stream)
            self.app.addRecentFile(filename, 'import')
        # More specific exceptions should be caught here, before ultimately:
        except Exception as err:
            # Catch-all for unanticipated errors
            self.handleException(err, what="importing the file %s" % filename,
                                 closeFile=True)
            return
        
        self.dataset = newDoc
        loader = Loader(self, newDoc, **self.app.getPref('loader'))
        self.pushOperation(loader, modal=False)
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
        settings = xd.CSVExportDialog.getExport(root=self)
        
        if settings is None:
            return
        
        source = settings['source']
        subchannels = settings['channels']
        subchannelIds = [c.id for c in subchannels]
        start, stop = settings['indexRange']
        
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
        settings = xd.FFTExportDialog.getExport(root=self)
        if settings is None:
            return
        
        source = settings.get('source', None)
        subchannels = settings['channels']
        startTime, stopTime = settings['timeRange']
        sliceSize = settings['windowSize']
        
        places = self.app.getPref("precisionX", 4)
        timeFormat = "%%.%df" % places
        title = "FFT: %s (%ss to %ss)" % (
                                    ", ".join([c.name for c in subchannels]), 
                                    timeFormat % (startTime * self.timeScalar), 
                                    timeFormat % (stopTime * self.timeScalar))
        viewId = wx.NewId()

        try:
            view = FFTView(self, viewId, title=title, size=self.GetSize(), 
                           root=self, source=source, subchannels=subchannels, 
                           start=startTime, end=stopTime,
                           sliceSize=sliceSize)
            self.fftViews[viewId] = view
        except Exception as e:
            self.handleException(e, what="generating FFT")


    def renderSpectrogram(self, evt=None):
        """ Create a 2D FFT/Time plot.
            
            @keyword evt: An event (not actually used), making this method
                compatible with event handlers.
        """
        settings = xd.SpectrogramExportDialog.getExport(root=self)
        
        source = settings.get('source', None)
        subchannels = settings['channels']
        startTime, stopTime = settings['timeRange']
        sliceSize = settings['windowSize']
        slicesPerSec = settings['slices']
        
        places = self.app.getPref("precisionX", 4)
        timeFormat = "%%.%df" % places
        title = "Spectrogram: %s (%ss to %ss)" % (
                                    ", ".join([c.name for c in subchannels]), 
                                    timeFormat % (startTime * self.timeScalar), 
                                    timeFormat % (stopTime * self.timeScalar))
        viewId = wx.NewId()

#         try:
        view = SpectrogramView(self, viewId, title=title, size=self.GetSize(), 
                       root=self, source=source, subchannels=subchannels, 
                       start=startTime, end=stopTime,
                       sliceSize=sliceSize, slicesPerSec=slicesPerSec)
        self.fftViews[viewId] = view
#         except Exception as e:
#             self.handleException(e, what="generating Spectrogram")
        
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
        for _ in self.cancelQueue:
            self.cancelOperation()
        
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
        
        if not isinstance(msg, basestring):
            # Slightly more specific error messages go here.
            if isinstance(err, MemoryError):
                msg = "The system ran out of memory%s" % what
            else:
                msg = u"An unexpected %s occurred%s:\n\n%s" % \
                        (err.__class__.__name__, what, unicode(err))

        # If exceptions are explicitly raised, raise it.
        if raiseException and isinstance(err, Exception):
            raise err

        if fatal:
            msg += "\n\nThe application will now shut down."

        dlg = wx.MessageDialog(self, msg, APPNAME, wx.OK | icon)
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
        'defaultColors': [#"RED",
                          #"GREEN",
                          #"BLUE",
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

        'locale': 'LANGUAGE_ENGLISH_US', # wxPython constant name (wx.*)
#         'locale': 'English_United States.1252', # Python's locale name string
        'loader': dict(numUpdates=100, updateInterval=1.0),
        'warnBeforeQuit': False, #True,
        'openOnStart': True,
        'showDebugChannels': __DEBUG__,
        'showFullPath': False,

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
        """ Retrieve a value from the preferences.
        """
        return self.prefs.get(args[0], self.defaultPrefs.get(*args))


    def setPref(self, name, val):
        """ Set the value of a preference.
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
                        help="The name of the MIDE file to import")
    parser.add_argument("-p", "--prefsFile", 
                        help="An alternate preferences file")
    args = parser.parse_args()

    app = ViewerApp(**vars(args))
    app.MainLoop()