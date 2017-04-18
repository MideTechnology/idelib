"""
Widgets for the main view plots.

@todo: Right-click of legend may need to be refactored for cross-platform use
    (use context menu functionality which should allow control-clicking on Mac)
"""

from collections import defaultdict
import colorsys
import sys
import time

from wx import aui
import wx

# Graphics (icons, etc.)
import images

# Custom controls
from base import ViewerPanel, MenuMixin
from common import expandRange, mapRange, inRect
from widgets.timeline import VerticalScaleCtrl

from logger import logger

from build_info import DEBUG

# ANTIALIASING_MULTIPLIER = 3.33
# RESAMPLING_JITTER = 0.125

#===============================================================================
# 
#===============================================================================

def constrainInt(val):
    """ Helper function to prevent an `OverflowError` when plotting at extreme
        magnification.
    """
    if val > 2147483647L:
        return 2147483647L
    if val < -2147483648L:
        return -2147483648L
    return val


#===============================================================================
# 
#===============================================================================

class VerticalScale(ViewerPanel):
    """ The vertical axis of the plot. Contains the scale and the vertical
        zoom buttons.
    """
    MIN_LABEL_PT_SIZE = 9
    
    zoomAmount = 0.25
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
        """
        kwargs.setdefault('style',wx.NO_BORDER)
        super(VerticalScale, self).__init__(*args, **kwargs)
        
        self.highlightColor = wx.Colour(255,255,255)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        subsizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(subsizer)
        
        # Zoom buttons
        self.defaultButtonStyle = wx.DEFAULT | wx.ALIGN_BOTTOM
        self.defaultSizerFlags = 0
        
        self.zoomInButton = self._addButton(subsizer, images.zoomInV, 
                                            self.OnZoomIn, 
                                            Id=wx.ID_ZOOM_IN,
                                            tooltip="Zoom In (Y axis)")
        self.zoomOutButton = self._addButton(subsizer, images.zoomOutV, 
                                             self.OnZoomOut, 
                                            Id=wx.ID_ZOOM_OUT,
                                             tooltip="Zoom Out (Y axis)")
        self.zoomFitButton = self._addButton(subsizer, images.zoomFitV, 
                                            self.OnZoomFit, 
                                            Id=wx.ID_ZOOM_FIT,
                                            tooltip="Zoom to fit min and max "
                                            "values in displayed interval")
        
        # Vertical axis label
        self.defaultFont = wx.Font(16, wx.SWISS, wx.NORMAL, wx.NORMAL)
        self.unitLabel = wx.StaticText(self, -1, self.Parent.yUnits[1], 
                                       style=wx.ALIGN_CENTER|wx.ST_NO_AUTORESIZE)
        self.unitLabel.SetFont(self.defaultFont)
        subsizer.Add(self.unitLabel, 1, wx.EXPAND)

        # Vertical scale 
        self.unitsPerPixel = 1.0
        self.scrollUnitsPerUnit = 1.0
        self.scale = VerticalScaleCtrl(self, -1, size=(1200,-1), 
                                       style=wx.NO_BORDER|wx.ALIGN_RIGHT)
        self.scale.SetRange(*self.visibleRange)
        self.scale.SetBackgroundColour(self.root.uiBgColor)
        self.scale.SetCursor(wx.StockCursor(wx.CURSOR_SIZENS))
        sizer.Add(self.scale, -1, wx.EXPAND)
        self.SetSizer(sizer)
        self.SetMinSize((self.root.corner.GetSize()[0],-1))
        self.SetBackgroundColour(self.root.uiBgColor)

        self.barClickPos = None
        self.originalRange = self.visibleRange[:]

        self.scale.Bind(wx.EVT_SIZE, self.OnResize)
        self.scale.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.scale.Bind(wx.EVT_LEFT_DOWN, self.OnScaleClick)
        self.scale.Bind(wx.EVT_LEFT_UP, self.OnScaleRelease)
        self.scale.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseExit)

        # Just in case the initial units are too long to fit
        self.setUnits(self.Parent.yUnits[1])

    #===========================================================================
    # 
    #===========================================================================
    
    def setValueRange(self, top=None, bottom=None, instigator=None,
                      tracking=False):
        """ Set the currently visible range of values (i.e. the vertical axis). 
            Propagates to its children.
            
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
        self.Parent.updateScrollbar()
        if not tracking:
            self.Parent.Refresh()
    
    
    def getValueRange(self):
        """ Get the currently displayed range of time (i.e. the vertical axis).
        """
        return self.visibleRange


    def getValueAt(self, vpos):
        """ Get the value corresponding to a given vertical pixel location.
        """
        return self.visibleRange[1] - (vpos * self.unitsPerPixel)

        
    def setUnits(self, units, setSize=True):
        """ Set the unit label display, adjusting the size if necessary.
        """
        if setSize:
            w = self.unitLabel.GetTextExtent(units)[0]
            bw = self.zoomInButton.GetSizeTuple()[0]
            if w > bw:
                scaledFont = self.defaultFont.Scaled(bw/(w+0.0))
                if scaledFont.GetPointSize() < self.MIN_LABEL_PT_SIZE:
                    scaledFont.SetPointSize(self.MIN_LABEL_PT_SIZE)
                self.unitLabel.SetFont(scaledFont)
            elif self.unitLabel.GetFont() != self.defaultFont:
                self.unitLabel.SetFont(self.defaultFont)
        else:
            self.unitLabel.SetFont(self.defaultFont)
        self.unitLabel.SetLabel(units)


    def zoom(self, percent=zoomAmount, tracking=True, useKeyboard=False):
        """ Increase or decrease the size of the visible range.
        
            @param percent: A zoom factor. Use a normalized value, positive
                to zoom in, negative to zoom out.
            @param tracking:
        """
        if useKeyboard:
            if wx.GetKeyState(wx.WXK_CONTROL):
                percent *= 2
            if wx.GetKeyState(wx.WXK_SHIFT):
                percent /= 2
            if wx.GetKeyState(wx.WXK_ALT):
                percent *= 10

        v1, v2 = self.visibleRange
        d = (v1 - v2) * percent / 2.0
        self.setValueRange(v1-d,v2+d,None,False)

    
    #===========================================================================
    # Event Handlers
    #===========================================================================
    
    def OnResize(self, evt):
        # evt.Size should never be 0, but it has occurred when splitting
        # windows. The max() in the denominator is a hack to prevent (n/0).
        self.unitsPerPixel = abs((self.visibleRange[0] - self.visibleRange[1]) \
                                 / max(1,evt.Size[1] + 0.0))
        bRect = self.zoomFitButton.GetRect()
        self.unitLabel.SetPosition((-1,max(evt.Size[1]/2,bRect[1]+bRect[3])))
        evt.Skip()


    def OnMouseMotion(self, evt):
        if self.barClickPos is not None and evt.LeftIsDown():
            # The scale bar is being dragged
            self.scale.SetBackgroundColour(self.highlightColor)
            newPos = evt.GetY()
            moved = self.barClickPos - newPos
            start = self.visibleRange[0] - moved * self.unitsPerPixel
            end = self.visibleRange[1] - moved * self.unitsPerPixel
            if start >= self.Parent.range[0] and end <= self.Parent.range[1]:
                self.Parent.setValueRange(start, end, None, tracking=True)
            self.barClickPos = newPos
        else:
            self.barClickPos = None
            self.root.showMouseVPos(self.getValueAt(evt.GetY()), 
                                    units=self.Parent.yUnits[1])
        evt.Skip()
    
    
    def OnZoomIn(self, evt):
        self.zoom(self.zoomAmount, useKeyboard=True)
    
    
    def OnZoomOut(self, evt):
        self.zoom(-self.zoomAmount, useKeyboard=True)


    def OnZoomFit(self, evt):
        self.Parent.zoomToFit()


    def OnScaleClick(self, evt):
        # Capture the click position for processing drags
        self.barClickPos = evt.GetY()
        self.originalRange = self.visibleRange[:]
        evt.Skip()


    def OnScaleRelease(self, evt):
        if self.barClickPos is not None:
            self.barClickPos = None
            self.scale.SetBackgroundColour(self.root.uiBgColor)
            self.Parent.setVisibleRange(instigator=self, tracking=False)
        evt.Skip()


    def OnMouseExit(self, evt):
        if self.barClickPos is not None:
            self.barClickPos = None
            self.scale.SetBackgroundColour(self.root.uiBgColor)
            self.setValueRange(*self.originalRange, instigator=None, tracking=False)
        evt.Skip()

#===============================================================================
# 
#===============================================================================

class PlotCanvas(wx.ScrolledWindow):
    """ The actual plot-drawing area.
    
        @todo: Make drawing asynchronous and interruptible.
    """
    # Drawing styles: (preference name, color, width, style, dash style) 
    GRID_ORIGIN_STYLE = ("originHLineColor", "GRAY", 1, wx.SOLID, None)
    GRID_MAJOR_STYLE = ("majorHLineColor", "LIGHT GRAY", 1, wx.SOLID, None)
    GRID_MINOR_STYLE = ("minorHLineColor", "LIGHT GRAY", 1, wx.USER_DASH, [2,2])
    RANGE_MIN_STYLE = ("minRangeColor", "LIGHT BLUE", 1, wx.USER_DASH, [8,4])
    RANGE_MAX_STYLE = ("maxRangeColor", "PINK", 1, wx.USER_DASH, [2,4])
    RANGE_MEAN_STYLE = ("meanRangeColor", "YELLOW", 1, wx.USER_DASH, [8,4,4,4])
    

    def loadPrefs(self):
        """
        """
        app = self.root.app
        self.condensedThreshold = app.getPref('condensedPlotThreshold', 2.0)
        self.showWarningRange = app.getPref('showWarningRange', True,
                                            section="wvr")
        self.SetBackgroundColour(app.getPref('plotBgColor', 'white'))
        self.drawPoints = app.getPref("drawPoints", True)
        self.pointSize = app.getPref('pointSize', 2)
        self.weight = app.getPref('plotLineWidth', 1)

        self.originHLinePen = self.loadPen(*self.GRID_ORIGIN_STYLE)
        self.majorHLinePen = self.loadPen(*self.GRID_MAJOR_STYLE)
        self.minorHLinePen = self.loadPen(*self.GRID_MINOR_STYLE)
        self.minRangePen = self.loadPen(*self.RANGE_MIN_STYLE)
        self.maxRangePen = self.loadPen(*self.RANGE_MAX_STYLE)
        self.meanRangePen = self.loadPen(*self.RANGE_MEAN_STYLE)
        
        outOfRangeColor = app.getPref('outOfRangeColor', wx.Colour(250,250,250))
        self.outOfRangeBrush = wx.Brush(outOfRangeColor)

        legendOpacity = int(255 * app.getPref('legendOpacity', .94))
        legendOpacity = max(0, min(255, legendOpacity))
        self.legendBrush = wx.Brush(wx.Colour(255,255,255,legendOpacity), 
                                    wx.SOLID)

        self.setPlotPens()
        self.setAntialias(self.antialias)


    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword color: The plot's pen color.
            @keyword weight: The weight (thickness) of the plot's pen. 
        """
        self.root = kwargs.pop('root',None)
        self.color = kwargs.pop('color', 'BLUE')
        
        kwargs.setdefault('style',wx.VSCROLL|wx.BORDER_SUNKEN|wx.WANTS_CHARS)
        super(PlotCanvas, self).__init__(*args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        
        # Source-specific stuff: dictionaries keyed on source object.
        # Maybe make a single dict for fewer lookups?
        self.lineList = defaultdict(list)
        self.pointList = defaultdict(list)
        self.minMeanMaxLineList = {}
        self.pens = {}
        self.legendRect = self.legendItem = None
        
        self.antialias = False
        self.loadPrefs()
        
        self.lastEvents = None
        self.lastRange = None
        self.minorHLines = None
        self.majorHLines = None
        self.zooming = False
        self.zoomCorners = None
        self.zoomCenter = None
        self.NO_PEN = wx.Pen("white", style=wx.TRANSPARENT)
        self.BLACK_PEN = wx.Pen("black", style=wx.SOLID)
        
        self._cursor_arrowwait = wx.StockCursor(wx.CURSOR_ARROWWAIT)
        self._cursor_default = wx.StockCursor(wx.CURSOR_DEFAULT)

        self.pauseTimer = wx.Timer()
        self.abortRendering = False

        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnMouseLeftDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnMouseLeftUp)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnMouseRightDown)
        self.Bind(wx.EVT_SIZE, self.OnResize)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnMouseDoubleClick)
        self.pauseTimer.Bind(wx.EVT_TIMER, self.OnTimerFinish)

        self._collectParents()


    def loadPen(self, name, defaultColor, width, style, dashes):
        """ Create a pen using a color in the preferences.
            @param name: The name of the parameter to read from the preferences.
            @param defaultColor: The color to use if the preference name is
                not found.
            @param width: The width of the pen's line.
            @param style: The pen's wxWidget line style.
            @param dashes: The dash pattern as an array of integers or `None`
        """
        p = wx.Pen(self.root.app.getPref(name, defaultColor), width, style)
        if style == wx.USER_DASH:
            p.SetDashes(dashes)
        return p


    def lightenColor(self, color, saturation=.125, value=.99):
        """ Helper method to create lightened, desaturated version of a color.
        """
        if isinstance(color, wx.Colour):
            color = color.Get()
        r,g,b = color[:3]
        h,s,v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
        s *= saturation
        v *= value
        return wx.Colour(*map(lambda x: int(x*255), colorsys.hsv_to_rgb(h,s,v)))
            

    def setPlotPens(self, color=None, weight=None, style=wx.SOLID, dashes=None):
        """ Set the color, weight, and/or style of the plotting pens. Uses the
            plot color preferences.
            @keyword color: The default color to use for unknown plots.
            @keyword width: The width of the pen's line.
            @keyword style: The pen's wxWidget line style.
        """
        self.color = color if color is not None else self.color
        self.weight = weight if weight is not None else self.weight
        self.style = style if style is not None else self.style
        
        for s in self.Parent.sources:
            color = self.root.getPlotColor(s)
            mmcolor = self.lightenColor(color)
            minPen = wx.Pen(mmcolor, self.RANGE_MIN_STYLE[2], wx.USER_DASH)
            minPen.SetDashes(self.RANGE_MIN_STYLE[-1])
            maxPen = wx.Pen(mmcolor, self.RANGE_MAX_STYLE[2], wx.USER_DASH)
            maxPen.SetDashes(self.RANGE_MAX_STYLE[-1])
            self.pens[s] = (wx.Pen(color, self.weight, self.style),
                            wx.Brush(color, wx.SOLID),
                            minPen, 
                            maxPen)
            
        self._pen = (wx.Pen(self.color, self.weight, self.style),
                     wx.Brush(self.color, wx.SOLID),
                     self.minRangePen,
                     self.maxRangePen)
        
        self._pointPen = wx.Pen(wx.Colour(255,255,255,.5), 1, self.style)
        self.legendRect = None
        
    
    def addSource(self, source):
        """ Add a data source (subchannel) to the plot.
        """
        self._collectParents()
        self.legendRect = None
        self.setPlotPens()
        
    
    def removeSource(self, source):
        """ Remove a data source (subchannel) from the plot.
        """
        self._collectParents()
        self.legendRect = None
        self.lineList.pop(source, None)
        self.pointList.pop(source, None)
        self.minMeanMaxLineList.pop(source, None)

    
    
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


    #===========================================================================
    # Drawing
    #===========================================================================
    
    def makeHGridlines(self, pts, width, scale):
        """ Create the coordinates for the horizontal grid lines from a list of
            ruler indicator marks (i.e. 1D coordinates to 2D). Used internally.
        """
        return [(0, p.pos * scale, width * scale, p.pos * scale) for p in pts]

    
    def getRelRange(self):
        """ Get the time range for the current window, based on the parent
            view's timeline. Used internally.
        """
        rect = self.GetScreenRect()
        trect = self.root.timeline.timebar.GetScreenRect()
        
        # TODO: Make sure the window border isn't causing issues.
        p1 = rect[0] - trect[0]# + 3
        p2 = p1 + self.GetSize()[0]# - 3

        result = (int(self.root.timeline.getValueAt(p1)),
                  int(self.root.timeline.getValueAt(p2)))
        return result


    def makeMinMeanMaxLines(self, source, hRange, vRange, hScale, vScale):
        """ Generate the points for the minimum and maximum envelopes.
            Used internally.
        """
        if not source.hasMinMeanMax:
            return (tuple(),tuple(),tuple())
        
        width = int((hRange[1] - hRange[0]) * hScale)
        
        def _startline(lines, pt):
            thisT = int(min(max(0, (pt[0] - hRange[0])) * hScale, width))
            thisV = constrainInt(int((pt[-1] - vRange[0]) * vScale)) 
            lines.append((0, thisV, thisT, thisV))
        
        def _makeline(lines, pt, fun):
            l = lines[-1]
            lastT = l[2]
            lastV = l[3]
            thisT = int(min(max(0, (pt[0] - hRange[0])) * hScale, width))
            thisV = constrainInt(int((pt[-1] - vRange[0]) * vScale))
#             if thisT == lastT:
#                 lines[-1] = l[0], l[1], l[2], fun(lastV, thisV)
#             else:
#                 lines.append((lastT, lastV, thisT, lastV))
#                 lines.append((thisT, lastV, thisT, thisV))
            lines.append((lastT, lastV, thisT, lastV))
            lines.append((thisT, lastV, thisT, thisV))
        
        def _finishline(lines):
            t = lines[-1][2]
            v = lines[-1][3]
            lines.append((t, v, width, v))

        vals = source.iterMinMeanMax(*hRange, padding=1, display=True)
        minPts = []
        meanPts = []
        maxPts = []
        i=0

        try:
            pMin, pMean, pMax = vals.next()
            _startline(minPts, pMin)
            _startline(meanPts, pMean)
            _startline(maxPts, pMax)
            for pMin, pMean, pMax in vals:
                _makeline(minPts, pMin, min)
                _makeline(meanPts, pMean, lambda x,y: (x+y)*0.5)
                _makeline(maxPts, pMax, max)
                i+=1
            _finishline(minPts)
            _finishline(meanPts)
            _finishline(maxPts)
        except StopIteration:
            # No min/mean/max in the given range. Generally shouldn't happen.
            pass
        
        return (minPts[1:], meanPts, maxPts[1:])
    
    
    def _drawGridlines(self, dc, size):
        """ Helper method for drawing grid lines. 
        """
        parent = self.Parent
        legend = parent.legend
        # Get the horizontal grid lines. 
        # NOTE: This might not work in the future. Consider modifying
        #    VerticalScaleCtrl to ensure we've got access to the labels!
        if self.root.drawMinorHLines:
            if self.minorHLines is None:
                self.minorHLines = self.makeHGridlines(
                    legend.scale._minorlabels, size[0], self.viewScale)
            
        if self.root.drawMajorHLines:
            if self.majorHLines is None:
                self.majorHLines = self.makeHGridlines(
                    legend.scale._majorlabels, size[0], self.viewScale)

        # If the plot source does not have min/max data, the first drawing only
        # sets up the scale; don't draw the horizontal graduation.
        if not parent.firstPlot:
            # Minor lines are automatically removed.
            if self.root.drawMinorHLines and len(self.minorHLines) < size[1]/24:
                dc.DrawLineList(self.minorHLines, self.minorHLinePen)
            if self.root.drawMajorHLines:
                dc.DrawLineList(self.majorHLines, self.majorHLinePen)


    def _drawOutOfRange(self, dc, x, w, h):
        """ Helper method for coloring time before and/or after the recording.
        """
        oldPen = dc.GetPen()
        oldBrush = dc.GetBrush()
        dc.SetPen(self.NO_PEN)
        dc.SetBrush(self.outOfRangeBrush)
        dc.DrawRectangle(x, 0, w, h)
        dc.SetPen(oldPen)
        dc.SetBrush(oldBrush)


    def OnPaint(self, evt):
        """ Event handler for redrawing the plot. Catches common exceptions.
            Wraps the 'real' painting event handler.
        """
        if self.root.drawingSuspended:
            return
        
#         return self._OnPaint(evt)

        # Debugging: don't handle unexpected exceptions gracefully
        ex = None if DEBUG else Exception
        
        if self.root.dataset.loading:
            # Pause the import during painting to make it faster.
            job, paused = self.root.pauseOperation()
        else:
            paused = False
            
        try:
            self._OnPaint(evt)
        except IndexError:
            # Note: These can occur on the first plot, but are non-fatal.
            if self.root.dataset.loading:
                logger.warning("IndexError in plot (race condition?); continuing.") 
                wx.MilliSleep(50)
                wx.PostEvent(self, evt)
            else:
                logger.warning("IndexError in plot: no data?")
        except TypeError as err:
            # Note: These can occur on the first plot, but are non-fatal.
            if self.root.dataset.loading:
                logger.warning("%s (race condition?); continuing." % err.message) 
                wx.MilliSleep(50)
                wx.PostEvent(self, evt)
            else:
                logger.warning("%s; no data?" % err.message) 
        except (IOError, wx.PyDeadObjectError) as err:
            msg = "An error occurred while trying to read the recording file."
            self.root.handleError(err, msg, closeFile=True)
        except ex as err:
            self.root.handleError(err, what="plotting data")
        finally:
            if paused:
                self.root.resumeOperation(job)
        
        try:
            self.SetCursor(self._cursor_default)
        except wx.PyDeadObjectError:
            pass
        

    def _OnPaint(self, evt):
        """ Redraws the plot. Called by `PlotCanvas.OnPaint()`.
        
            @todo: Apply offset and scaling transforms to the DC itself, 
                eliminating all the per-point math. May complicate rubber band
                zoom.
            @todo: Refactor and modularize this monster. Separate the line-list
                generation so multiple plots on the same canvas will be easy.
        """
        if not self.Parent.sources:
            return
        
        t0 = time.time()
        self.SetCursor(self._cursor_arrowwait)

        self.InvalidateBestSize()
        dc = wx.PaintDC(self)
        dc.SetAxisOrientation(True,False)
        dc.Clear()

        size = dc.GetSize()
        
        # Antialiasing
        if self.antialias:
            dc = wx.GCDC(dc)
            dc.SetUserScale(self.userScale, self.userScale)
        
        dc.BeginDrawing()
        
        parent = self.Parent
        legend = parent.legend
        
        # The size of a chunk of data to draw, so the rendering seems more
        # interactive. Not really a tenth anymore.
        chunkSize = int(size[0]/2 * self.oversampling)

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

        # Auto-zoom the first drawing of the plot, using the source's 
        # minimum and maximum data if available. 
        mmSources = [s for s in parent.sources if s.hasMinMeanMax]
        if len(mmSources) > 0:
            mmm = mmSources[0].getRangeMinMeanMax(*hRange, display=True)
            parent.visibleValueRange = [mmm[0], mmm[2]]
        for s in mmSources[1:]:
            mmm = s.getRangeMinMeanMax(*hRange, display=True)
            if mmm is not None:
                expandRange(parent.visibleValueRange, *mmm)
        if parent.firstPlot and len(mmSources) > 0:
            parent.firstPlot = False
            parent.zoomToFit(self)
            return

        hScale = (size.x + 0.0) / (hRange[1]-hRange[0]) * self.viewScale
        if vRange[0] != vRange[1]:
            vScale = (size.y + 0.0) / (vRange[1]-vRange[0]) * self.viewScale
        else:
            vScale = -(size.y + 0.0) * self.viewScale
            
        thisRange = (hScale, vScale, hRange, vRange)
        if self.lastRange != thisRange:
            self.lineList.clear()
            self.minMeanMaxLineList.clear()
            self.minorHLines = None
            self.majorHLines = None
            self.lastRange = thisRange

        # Draw gray over out-of-range times (if visible)
        sourceInterval = [sys.maxint, -sys.maxint]
        for s in parent.sources:
            expandRange(sourceInterval, *s.getInterval())
        sourceFirst, sourceLast = sourceInterval 
        
        # Time before recording
        if sourceFirst > hRange[0]:
            self._drawOutOfRange(dc, 0, 
                                 int((sourceFirst-hRange[0])*hScale), 
                                 abs(int(size[1]/self.userScale)))
        
        # Time after recording
        if sourceLast < hRange[1]:
            x = int((sourceLast-hRange[0])*hScale)
            self._drawOutOfRange(dc, x, 
                                 abs(int((size[0]/self.userScale)-x)), 
                                 abs(int(size[1]/self.userScale)))
        
        # Draw 'idiot light'
        if self.showWarningRange:
            for r in parent.warningRanges:
                r.draw(dc, hRange, hScale, self.viewScale, size)
        
        # Draw horizontal grid lines
        self._drawGridlines(dc, size)

        # The actual data plotting
        linesDrawn = 0
        for s in parent.sources:
            if self.abortRendering:
                break
            linesDrawn += self._drawPlot(dc, s, size, hRange, vRange, hScale, vScale, chunkSize)
            
        dc.EndDrawing()
        self.SetCursor(self._cursor_default)
        
        if DEBUG and linesDrawn > 0:# and len(parent.sources) > 1:
            dt = time.time() - t0
            logger.info("Plotted %d lines for %d sources in %.4fs" % 
                        (linesDrawn, len(parent.sources), dt))

        self._drawLegend()


    def _collectParents(self):
        """ Collect the parent channels' EventLists for the subchannels in this 
            plot.
        """
        # Keep a dict, keyed on parent Channel EventLists, that keeps a list
        # of 'sources,' which are used as keys in the cached line/point lists.
        # Sibling subchannels that aren't in the plot are `None`.
        # This is all overly complex; refactor later.
        self.sourceChannels = {}
        for s in self.Parent.sources:
            ch = s._parentList
            ch.removeMean = self.Parent.plotRemoveMean
            ch.rollingMeanSpan = self.Parent.plotMeanSpan
            self.sourceChannels.setdefault(ch, [None]*len(ch.parent.subchannels))[s.parent.id] = s
        self.root.dataset.updateTransforms()
        

    def _drawPlot(self, dc, source, size, hRange, vRange, hScale, vScale, 
                  chunkSize):
        """ Does the plotting of a single source.
        """
        if self.abortRendering is True or self.root.drawingSuspended:
            # Bail if user interrupted drawing (scrolling, etc.)
            # Doesn't actually work yet!
            return 0
        
        t0 = time.time()
        parent = self.Parent
        lines = self.lineList[source]
        
        mainPen, pointBrush, minRangePen, maxRangePen = self.pens.get(source, self._pen)
        if len(self.pens) == 1:
            minRangePen = self.minRangePen
            maxRangePen = self.maxRangePen
        
        if source.hasMinMeanMax:
            # TODO: Make this work like the subchannel plotting. Not a big deal
            # since min/mean/max is currently kept in RAM.
            mmmLines = self.minMeanMaxLineList.get(source, None)
            if mmmLines is None:
                mmmLines = self.makeMinMeanMaxLines(source, hRange, vRange, hScale, vScale)
                self.minMeanMaxLineList[source] = mmmLines
            minLines, meanLines, maxLines = mmmLines
            drawCondensed = len(minLines) >= size[0] * self.condensedThreshold
            if drawCondensed:
                if not lines:
                    # More buffers than (virtual) pixels; draw vertical lines
                    # from min to max instead of the literal plot.
                    if self.root.drawHollowPlot and len(minLines)>2:
                        # Hollow mode: just draw min/max without first/last
                        # (they just go to the edges of the screen)
                        lines = minLines[1:-1] + maxLines[1:-1]
                    else:
                        # Draw solid plots, actually a tight sawtooth.
                        lines = []
                        lastPt = maxLines[0][:2]
                        for i in range(0,len(minLines),2):
                            a = minLines[i]
                            b = maxLines[i]
                            lines.append((lastPt[0],lastPt[1],a[0],a[1]))
                            lines.append((a[0],a[1],b[0],b[1]))
                            lastPt = b[:2]
                    self.lineList[source] = lines
            else:
                if self.root.drawMinMax:
                    dc.DrawLineList(minLines, minRangePen)
                    dc.DrawLineList(maxLines, maxRangePen)
                if self.root.drawMean:
                    dc.DrawLineList(meanLines, self.meanRangePen)
        else:
            drawCondensed = False
        
        dc.SetPen(mainPen)
        if lines:
            # No change in displayed range; Use cached lines.
#             dc.DrawLineList(lines)
            for i in range(0, len(lines), chunkSize):
                dc.DrawLineList(lines[i:i+chunkSize])
                if self.abortRendering is True:
                    return i
        else:
            lines = self.lineList[source] = []
            
            # Lines are drawn in sets to provide more immediate results
            lineSubset = []
            
            # OPTIMIZATION: Local variables to reduce indirect referencing
            _parentList = source._parentList
            source_hasMinMeanMax = source.hasMinMeanMax
            siblings = self.sourceChannels[_parentList]
            
            # The previous point (left side of line), by subchannel ID.
            lastPt = [None] * len(siblings)
            
            # Iterate the source's parent Channel's EventList, in case this
            # plot also contains sibling subchannels
            events = _parentList.iterResampledRange(hRange[0], hRange[1],
                size[0]*self.oversampling, padding=1, 
                jitter=self.root.noisyResample, display=True)
            
            # If a subchannel has been added, keep the existing sibling's lines.
            cached = [bool(self.lineList[s]) for s in siblings]

            try:
                # Handle the first sample explicitly before iterating over rest
                event = events.next()
                eTime = event[-2]
                for chId, eVal in enumerate(event[-1]):
                    s = siblings[chId]
                    if s is None:
                        continue
                    if not source_hasMinMeanMax:
                        # Get data min/max for zoom-to-fit
                        parent.visibleValueRange = [sys.maxint, -sys.maxint]
                        expandRange(parent.visibleValueRange, eVal)
                    lastPt[chId] = ((eTime - hRange[0]) * hScale, 
                                    constrainInt((eVal - vRange[0]) * vScale))
                    self.pointList[s] = [lastPt[chId]]
                
                # And now the rest of the samples:
                for i, event in enumerate(events,1):
                    if self.abortRendering is True:
                        # Bail if user interrupted drawing (scrolling, etc.)
                        return
                    eTime = event[-2]
                    for chId, eVal in enumerate(event[-1]):
                        s = siblings[chId]
                        if s is None:
                            continue
                        if cached[chId]:
                            continue
                        sLines = self.lineList[s]
                        sPoints = self.pointList[s]
                        pt = ((eTime - hRange[0]) * hScale, 
                              constrainInt((eVal - vRange[0]) * vScale))
                        sPoints.append(pt)
                        
                        # A value of None is a discontinuity; don't draw a line.
                        # Not actually implemented in EventList at this point!
                        if eVal is not None:
                            line = lastPt[chId] + pt
                            sLines.append(line)
                            if not source_hasMinMeanMax:
                                expandRange(parent.visibleValueRange, eVal)
                            if s == source:
                                lineSubset.append(line)
                        
                        # Draw 'chunks' of the graph to make things seem faster.
                        if i % chunkSize == 0:
                            dc.DrawLineList(lineSubset)
                            lineSubset = []
                            
                        lastPt[chId] = pt
                    
            except StopIteration:
                # This will occur if there are 0-1 events, but that's okay.
                pass
            
            # Draw the remaining lines (if any)
            if not parent.firstPlot:
                dc.DrawLineList(lineSubset) 

        if DEBUG:# and lines:
            dt = time.time() - t0
            if drawCondensed:
                logger.info("Plotted %d lines (condensed) in %.4fs for %r" % 
                            (len(self.lineList[source]), dt, source.parent.displayName))
            else:
                logger.info("Plotted %d lines in %.4fs for %r" % 
                            (len(self.lineList[source]), dt, source.parent.displayName))
                
        if parent.firstPlot:
            # First time the plot was drawn. Don't draw; scale to fit.
            parent.zoomToFit(self)
            parent.firstPlot = False
            self.SetCursor(self._cursor_default)
            dc.EndDrawing()
            return 0
        
        if self.drawPoints and len(lines) < size[0] / 4:
            # More pixels than points: draw actual points as circles.
            dc.SetPen(self._pointPen)
            dc.SetBrush(pointBrush)
            for p in self.pointList[source]:
                dc.DrawCirclePoint(p,self.weight*self.viewScale*self.pointSize)
        
        return len(lines)


    def _drawLegend(self, padding=8, margin=10, minWidth=60):
        """ Draw a legend with the plot colors and source names.
        """
        # TODO: Maybe draw this to a cached bitmap, then just draw that?
        numSources = len(self.Parent.sources)
        if self.abortRendering is True or not self.root.showLegend:
            return
        
        # Legend is antialiased
        dc = wx.GCDC(wx.ClientDC(self))
        if self.legendRect is None:
            w = minWidth
            items = []
            size = dc.GetSize()

            # Reversing the list, so the topmost item is the 'top' plot
            for i,s in enumerate(reversed(self.Parent.sources)):
                n = s.parent.displayName
                if s.parent.units[0] != s.units[0]:
                    n = "%s as %s" % (n, s.units[0])
                nt = dc.GetTextExtent(n)
                w = max(nt[0], w)
                items.append((i, n, self.pens[s][1]))
            swatchSize = nt[1]
            w += swatchSize + (padding * 3) # padding
            h = (swatchSize * numSources) + (padding * 2) + (4 * (numSources-1))
    
            x,y = margin,margin
            lpos = self.root.legendPos
            if lpos & 1:
                x = size[0] - w - margin # Right side
            if lpos & 2:
                y = size[1] - h - margin # Bottom
                
            self.legendRect = x, y, w, h, swatchSize, items
        else:
            x, y, w, h, swatchSize, items = self.legendRect

        dc.BeginDrawing()
        dc.SetPen(self.BLACK_PEN)
        dc.SetBrush(self.legendBrush)
        dc.DrawRectangle(x, y, w, h)
        swatchPos = x + padding
        textPos = swatchPos + padding + swatchSize
        for i,n,b in items:
            vpos = y+(i*(swatchSize+4))+padding
            dc.SetBrush(b)
            dc.DrawText(n, textPos, vpos)
            dc.DrawRectangle(swatchPos, vpos, swatchSize, swatchSize)
        dc.EndDrawing()


    #===========================================================================
    # "Rubber Band" Zooming
    #===========================================================================
    
    def _drawRubberBand(self, corner1, corner2):
        """ Draw (or erase) the 'rubber band' zoom rectangle. 
        """
        ptx = min(corner1[0], corner2[0])
        pty = min(corner1[1], corner2[1])
        rectWidth = max(corner1[0], corner2[0]) - ptx
        rectHeight = max(corner1[1], corner2[1]) - pty
        
        # draw rectangle
        dc = wx.ClientDC( self )
        dc.BeginDrawing()
        dc.SetPen(wx.Pen(wx.BLACK))
        dc.SetBrush(wx.Brush( wx.WHITE, wx.TRANSPARENT ))
        dc.SetLogicalFunction(wx.INVERT)
        dc.DrawRectangle( ptx,pty, rectWidth,rectHeight)
        dc.SetLogicalFunction(wx.COPY)
        dc.EndDrawing()
 

    #===========================================================================
    # 
    #===========================================================================
    
    def setAntialias(self, aa=True):
        """ Turn antialiasing on or off.
        """
        self.antialias = aa
        if aa:
            self.viewScale = self.root.aaMultiplier
            self.oversampling = self.viewScale * 1.33
        else:
            self.viewScale = 1.0
            self.oversampling = wx.GetApp().getPref('oversampling',2.0) #3.33 
            
        gridScale = self.viewScale
        rangeScale = self.viewScale
            
        self.userScale = 1.0/self.viewScale
        self.minorHLinePen.SetWidth(self.GRID_MINOR_STYLE[2]*gridScale)
        self.majorHLinePen.SetWidth(self.GRID_MAJOR_STYLE[2]*gridScale)
        self.minRangePen.SetWidth(self.RANGE_MAX_STYLE[2]*rangeScale)
        self.maxRangePen.SetWidth(self.RANGE_MIN_STYLE[2]*rangeScale)
        self.meanRangePen.SetWidth(self.RANGE_MEAN_STYLE[2]*rangeScale)
        self._pointPen.SetWidth(rangeScale)
        self.legendRect = None


    #===========================================================================
    # Event handlers (except painting)
    #===========================================================================
    
    def OnMouseMotion(self, evt):
        """ Event handler for mouse movement events.
        """
        pos = (evt.GetX(), evt.GetY())
        self.root.showMouseHPos(pos[0])
        self.root.showMouseVPos(self.Parent.legend.getValueAt(pos[1]),
                                units=self.Parent.yUnits[1])
        
        if self.zooming:
            if not evt.LeftIsDown():
                # Mouse probably left window, left button released, moved back
                self._drawRubberBand(*self.zoomCorners)
                self.zooming = False
            else:
                if pos != self.zoomCorners[1]:
                    # Moved; erase old rectangle
                    self._drawRubberBand(*self.zoomCorners)
                # Draw new rectangle
                self.zoomCorners[1] = pos
                if wx.GetKeyState(wx.WXK_SHIFT):
                    dx = pos[0] - self.zoomCenter[0]
                    dy = pos[1] - self.zoomCenter[1]
                    self.zoomCorners[0] = (self.zoomCenter[0]-dx,
                                           self.zoomCenter[1]-dy)
                else:
                    self.zoomCorners[0] = self.zoomCenter
                self._drawRubberBand(*self.zoomCorners)
        
        evt.Skip()


    def OnMouseLeftDown(self, evt):
        """ Handle start of click-and-drag, displaying 'rubber band' zoom box.
        """
        evtX = evt.GetX()
        evtY = evt.GetY()
        if self.root.showLegend and inRect(evtX, evtY, self.legendRect):
            evt.Skip()
            return
        self.zooming = True
        self.zoomCenter = (evtX, evtY)
        self.zoomCorners = [self.zoomCenter]*2


    def OnMouseDoubleClick(self, evt):
        """ Handle double-click. Ignored unless it's on the legend.
        """
        if self.zooming:
            # Cancel zoom rectangle
            self._drawRubberBand(*self.zoomCorners)
            self.zooming = False
            
        evtX = evt.GetX()
        evtY = evt.GetY()
        
        if self.root.showLegend and inRect(evtX, evtY, self.legendRect):
            idx = max(0,(evtY - self.legendRect[1] - 10) / self.legendRect[4])
            idx = min(len(self.Parent.sources)-1, idx)
            self.legendItem = self.Parent.sources[-1-idx]
            self.Parent.OnMenuSetColor(evt)
        else:
            self.root.OnZoomFitAll(evt)
        
        evt.Skip()


    def OnMouseRightDown(self, evt):
        """ Handle right-click. Zoom out, or context menu if over legend.
        """
        if self.zooming:
            # Cancel zoom rectangle
            self._drawRubberBand(*self.zoomCorners)
            self.zooming = False
            evt.Skip(False)
            return
        
        evtX = evt.GetX()
        evtY = evt.GetY()
        
        if self.root.showLegend and inRect(evtX, evtY, self.legendRect):
            # Right-click on the legend
            idx = max(0,(evtY - self.legendRect[1] - 10) / self.legendRect[4])
            idx = min(len(self.Parent.sources)-1, idx)
            self.legendItem = self.Parent.sources[-1-idx]
            self.Parent.showLegendPopup(self.legendItem)
        else:
            if wx.GetKeyState(wx.WXK_ALT):
                # Zoom to fit both axes
                self.root.navigator.OnZoomFit(evt)
                return
            # Zoom out on both axes
            percent = 1.25
            x = self.root.timeline.getValueAt(evtX)
            y = self.Parent.legend.getValueAt(evtY)
            t1, t2 = self.root.getVisibleRange()
            dx = (t1 - t2) * percent
            v1, v2 = self.Parent.getValueRange()
            dy = (v1 - v2) * percent
#             self.legendRect = None
            self.root.setVisibleRange(*sorted((x-dx, x+dx)), tracking=False)
            self.Parent.setValueRange(*sorted((y-dy, y+dy)), tracking=True)

    
    def OnMouseLeftUp(self, evt):
        if self.zooming:
            self._drawRubberBand(*self.zoomCorners)
            c0, c1 = self.zoomCorners
            if min(abs(c1[0]-c0[0]), abs(c1[1]-c0[1])) > 5:
                xStart = self.root.timeline.getValueAt(c0[0])
                xEnd = self.root.timeline.getValueAt(c1[0])
                yStart = self.Parent.legend.getValueAt(c0[1])
                yEnd = self.Parent.legend.getValueAt(c1[1])
                
                # TODO: Don't call root directly, use events 
                #    (for future threading)!
                self.root.setVisibleRange(*sorted((xStart, xEnd)))
                self.Parent.setValueRange(*sorted((yStart, yEnd)), 
                                          tracking=True)
            
        self.zooming = False
        self.zoomCorners = None


    def OnResize(self, evt):
        """ Window resize event handler.
        """
        self.legendRect = None
        self.abortRendering = True
        
        # Start up (or reset) the timer delaying the redraw 
        self.pauseTimer.Start(25, wx.TIMER_ONE_SHOT)


    def OnTimerFinish(self, evt):
        """ Handle expiration of the timer that delays refresh during resize.
        """
        self.abortRendering = False
        self.Refresh()

#===============================================================================
# 
#===============================================================================

class Plot(ViewerPanel, MenuMixin):
    """ A display of one or more subchannels of data, consisting of the 
        vertical scale and actual plot-drawing canvas.
    """
    ID_MENU_SETCOLOR = wx.NewId()
    ID_MENU_SETPOS_UL = wx.NewId()
    ID_MENU_SETPOS_UR = wx.NewId()
    ID_MENU_SETPOS_LR = wx.NewId()
    ID_MENU_SETPOS_LL = wx.NewId()
    ID_MENU_MOVE_TOP = wx.NewId()
    ID_MENU_MOVE_BOTTOM = wx.NewId()
    ID_MENU_REMOVE = wx.NewId()
    ID_MENU_HIDE_LEGEND = wx.NewId()
    LEGEND_POS_IDS = [ID_MENU_SETPOS_UL, ID_MENU_SETPOS_UR,
                      ID_MENU_SETPOS_LL, ID_MENU_SETPOS_LR]
        
    _sbMax = 10000.0 #(2**32)/2-1 + 0.0
    _minThumbSize = 100
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword source: The initial source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot).
            @keyword units: A tuple with the measurement type and units (e.g.
                `('Acceleration','X')`).
            @keyword initialRange: An initial display range.
            @keyword warningRange: 
        """
        source = kwargs.pop('source', None)
        self.yUnits= kwargs.pop('units',None)
        color = kwargs.pop('color', 'BLACK')
        self.range = kwargs.pop('initialRange', None)
        super(Plot, self).__init__(*args, **kwargs)
        
        self.firstPlot = True
        self.visibleValueRange = None
        self.drawMajorHLines = True
        self.drawMinorHLines = False
        self.scrollUnitsPerUnit = 1.0
        self.unitsPerPixel = 1.0
        self.scrolling = False
        
        self.range = self.range if self.range is not None else (-100,100)
        
        if self.yUnits is None:
            self.yUnits = getattr(source, "units", ('',''))
        self.nativeUnits = self.yUnits
    
        self.warningRanges = set()
        self.colors = {}
        if source is not None:
            self.sources = [source]
            self.colors[source] = color
            self._getWarningRanges()
        else:
            self.sources = []
        
        self.plotRemoveMean = True
        self.plotMeanSpan = 5000000
        self.plotTransform = None
        
        dispRange = [sys.maxint, -sys.maxint]
        for s in self.sources:
            if getattr(s, 'hasDisplayRange', False):
                expandRange(dispRange, s.displayRange[0])
                expandRange(dispRange, s.displayRange[1])
        if dispRange != [sys.maxint, -sys.maxint]:
            self.range = dispRange
        
        self.legend = VerticalScale(self, -1, visibleRange=(max(self.range),
                                                            min(self.range)))
        self.plot = PlotCanvas(self, -1)
        self.scrollbar = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.legend, 0, wx.EXPAND)
        sizer.Add(self.plot, -1, wx.EXPAND)
        sizer.Add(self.scrollbar, 0, wx.EXPAND)
        self.SetSizer(sizer)
        self.legend.SetSize((self.Parent.Parent.corner.GetSize()[0],-1))
        
        self.plot.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseLeave)

        self._bindScrollEvents(self.scrollbar, self.OnScroll, 
                               self.OnScrollTrack, self.OnScrollEnd)
        
        self.buildLegendMenu()
        self.enableMenus()
#         self.setTabText()


    def buildLegendMenu(self):
        """ Create the legend contextual `wx.Menu`.
        """
        self.legendMenu = wx.Menu()
        self.addMenuItem(self.legendMenu, self.ID_MENU_SETCOLOR, 
                         "Set Color...", "", self.OnMenuSetColor)
        self.addMenuItem(self.legendMenu, self.ID_MENU_MOVE_TOP, 
                         "Move Plot to Top", "", self.OnMenuMoveTop)
        self.addMenuItem(self.legendMenu, self.ID_MENU_MOVE_BOTTOM, 
                         "Move Plot to Bottom", "", self.OnMenuMoveBottom)
        self.addMenuItem(self.legendMenu, self.ID_MENU_REMOVE,
                         "Remove Source", "", self.OnMenuRemoveSource)
        
        self.legendMenu.AppendSeparator()
        posMenu = self.addSubMenu(self.legendMenu, -1, "Legend Position")
        self.addMenuItem(posMenu, self.ID_MENU_SETPOS_UL, "Upper Left", "",
                         self.OnMenuLegendPos)
        self.addMenuItem(posMenu, self.ID_MENU_SETPOS_UR, "Upper Right", "",
                         self.OnMenuLegendPos)
        self.addMenuItem(posMenu, self.ID_MENU_SETPOS_LL, "Lower Left", "",
                         self.OnMenuLegendPos)
        self.addMenuItem(posMenu, self.ID_MENU_SETPOS_LR, "Lower Right", "",
                         self.OnMenuLegendPos)
        
        self.addMenuItem(self.legendMenu, self.ID_MENU_HIDE_LEGEND, 
                         "Hide Legend", "", self.OnMenuHideLegend)
       

    def showLegendPopup(self, item):
        """ Display the contextual menu for a legend item.
        """
        name = item.parent.displayName
        idx = self.sources.index(item)
        topEn = idx < len(self.sources)-1
        botEn = idx > 0
        removeEn = len(self.sources) > 0
        self.setMenuItem(self.legendMenu, self.ID_MENU_SETCOLOR,
                         label="Set Color of '%s'..." % name)
        self.setMenuItem(self.legendMenu, self.ID_MENU_MOVE_TOP, enabled=topEn,
                         label="Move '%s' to Top" % name)
        self.setMenuItem(self.legendMenu, self.ID_MENU_MOVE_BOTTOM, enabled=botEn,
                         label="Move '%s' to Bottom" % name)
        self.setMenuItem(self.legendMenu, self.ID_MENU_REMOVE, enabled=removeEn,
                         label="Remove '%s' from Plot" % name)
        self.PopupMenu(self.legendMenu)
       

    #===========================================================================
    # Source properties. 
    # TODO: Adding these was kind of a hack for multi-source plots; remove.
    #===========================================================================
        
    @property
    def rollingMeanSpan(self):
        return self.plotMeanSpan
#         if self.sources:
#             return self.sources[0].rollingMeanSpan
    
    @rollingMeanSpan.setter
    def rollingMeanSpan(self, v):
        self.plotMeanSpan = v
        for source in self.sources:
            source.rollingMeanSpan = v
        self.plot._collectParents()

    @property
    def units(self):
        return self.yUnits
    
    @units.setter
    def units(self, v):
        self.yUnits = v
        for source in self.sources:
            source.parent.units = v
        self.plot.legendRect = None

    @property
    def transform(self):
        if self.sources:
            return self.sources[0].transform
    
    @transform.setter
    def transform(self, t):
        for source in self.sources:
            source.transform = t
        self.plot.legendRect = None
        self.plot._collectParents()

    #===========================================================================
    # 
    #===========================================================================
    
    def loadPrefs(self):
        # The plot canvas does most of the work.
        self.plot.loadPrefs()


    def val2scrollbar(self, x):
        """ Convert a plot value to a scrollbar position. 
        """
        return int(mapRange(x, self.range[0], self.range[1], self._sbMax, 0))
        
    
    def scrollbar2val(self, x):
        """ Convert a scrollbar position to the plot value.
        """
        return mapRange(x, 0.0, self._sbMax, self.range[1], self.range[0])
    

    def updateScrollbar(self):
        """ Update the position and size of the vertical scrollbar to match
            the displayed value range.
        """
        start, end = self.legend.getValueRange()
        if start == end:
            return
        
        tpos = self.val2scrollbar(end)
        tsize = self.val2scrollbar(start) - tpos
        
        self.scrollbar.SetScrollbar(tpos, tsize, self._sbMax, int(tsize*.9))
        
        self.scrollUnitsPerUnit = self._sbMax / (start - end)


    def setTabText(self):
        """ Set the name displayed on the plot's tab.
        """
        if len(self.sources) == 0:
            ttip = s = self.yUnits[0]
        else:
            ttip = '\n'.join([s.parent.displayName for s in self.sources])
            if len(self.sources) == 1:
                if self.sources[0].parent.units[0] != self.yUnits[0]:
                    # Special case: show converted units
                    s = self.yUnits[0]
                else:
                    s = self.sources[0].parent.displayName
            else:
                s = "%s (%d sources)" % (self.yUnits[0], len(self.sources)) 
        try:
            i = self.Parent.GetPageIndex(self)
            self.Parent.SetPageText(i, s)
            self.Parent.SetPageToolTip(i, ttip)
        except AttributeError:
            # Can occur if the plot isn't in a tab; just in case.
            try:
                self.SetTitle(s)
            except AttributeError:
                pass
            

    def setUnitConverter(self, con):
        """ Apply (or remove) a unit conversion function.
        """
        self.plotTransform = con
        
        if not self.sources:
#             print "no sources"
            if self.plotTransform is not None:
                self.yUnits = self.plotTransform.units
            self.setTabText()
            return
            
#         oldUnits = self.sources[0].units[0]
        oldXform = self.sources[0].transform
        
        for source in self.sources:
            source.setTransform(con, update=False)
        self.root.dataset.updateTransforms()

        self.yUnits = self.sources[0].units
                
        self.legend.setUnits(self.yUnits[1])
        t,b = self.legend.getValueRange()
        
        if oldXform is not None:
            # Convert vertical range to original units
            nt = oldXform.revert(t)
            nb = oldXform.revert(b) 
            t = nt if nt is not None else t
            b = nb if nb is not None else b
        
        if con is not None:
            try:
                nt = con.convert(t)
                nb = con.convert(b)
                t = nt if nt is not None else t
                b = nb if nb is not None else b
            except ValueError:
                logger.debug("Value error adjusting vertical range %r" % con)
                pass
            
#             if oldUnits != con.units[0]:
#                 self.setTabText(con.units[0])
        
        self.plot.legendRect = None
        self.setTabText()
        self.legend.setValueRange(*sorted((t,b)))
        self.redraw()
        

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
        
        if start == end == 0:
            # shouldn't happen, but it could
            start, end = self.range
        elif start == end:
            # this can occur if there are no events in the current interval
            start *= .99
            end *= 1.01
            
        if not self.scrolling:
            self.updateScrollbar()
            
        if (start is None or end is None) and self.visibleValueRange is None:
            return
        instigator = self if instigator is None else instigator
        start = self.visibleValueRange[0] if start is None else start
        end = self.visibleValueRange[1] if end is None else end
        self.legend.setValueRange(start, end, instigator, tracking)
        
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


    def getValueRange(self):
        """ Get the vertical range of values.
        """
        return self.legend.getValueRange()


    def zoomOut(self, tracking=True):
        """ Zoom in or out on the Y axis. """
        self.legend.zoom(-self.legend.zoomAmount, tracking)


    def zoomIn(self, tracking=True):
        """ Zoom in or out on the Y axis. """
        self.legend.zoom(self.legend.zoomAmount, tracking)


    def zoomToFit(self, instigator=None, padding=0.05, tracking=False):
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
                           tracking)


    def redraw(self, force=False):
        """ Force the plot to redraw.
        """
        if force:
            self.plot.lineList.clear()
        self.Refresh()


    def removeMean(self, val=True, span=5000000):
        """ Turn 'remove mean' on or off.
        """
        self.plotRemoveMean = val
        self.plotMeanSpan = span
        
        changed = False
        for source in self.sources:
            val = val and source.hasMinMeanMax and source.allowMeanRemoval
            if source.removeMean != val or source.rollingMeanSpan != span:
                source.rollingMeanSpan = span
                source.removeMean = val
                changed = True
        
        if changed:
            self.plot._collectParents()
            self.plot.lineList.clear()
            self.plot.minMeanMaxLineList.clear()
            self.redraw()
            self.enableMenus()

        
    def showWarningRange(self, val=True):
        """ Display or hide all out-of-range warning indicators.
        """
        if not self.sources:
            return 
        self.plot.showWarningRange = val
        self.Refresh()
        self.enableMenus()


    def enableMenus(self):
        """ Update the plot-specific menus items in the main view's menu bar.
        """
        activePage = self.Parent.getActivePage()
        if self != activePage and activePage is not None:
            return

        enabled = any([s.allowMeanRemoval and s.hasMinMeanMax for s in self.sources])
        rt = self.root
        mb = rt.menubar
        
        if not enabled or self.plotRemoveMean is False:
            rt.setMenuItem(mb, rt.ID_DATA_NOMEAN, checked=True)
        elif self.plotMeanSpan == -1:
            rt.setMenuItem(mb, rt.ID_DATA_MEAN_TOTAL, checked=True)
        else:
            rt.setMenuItem(mb, rt.ID_DATA_MEAN, checked=True)
            
        for m in [rt.ID_DATA_NOMEAN, rt.ID_DATA_MEAN, rt.ID_DATA_MEAN_TOTAL]:
            rt.setMenuItem(mb, m, enabled=enabled)

        rt.setMenuItem(mb, rt.ID_VIEW_MINMAX, enabled=enabled, 
                       checked=rt.drawMinMax)
        rt.setMenuItem(mb, rt.ID_VIEW_LINES_MAJOR, enabled=True, 
                       checked=rt.drawMajorHLines)
        rt.setMenuItem(mb, rt.ID_VIEW_LINES_MINOR, enabled=True, 
                       checked=rt.drawMinorHLines)
        rt.setMenuItem(mb, rt.ID_VIEW_MEAN, enabled=enabled, 
                       checked=rt.drawMean)
        
        rt.setMenuItem(mb, rt.ID_VIEW_UTCTIME,
                       enabled=rt.session.utcStartTime is not None)
        
        rt.updateConversionMenu(self)
        rt.updateSourceMenu(self)      
        rt.updateWarningsMenu(self)       
            

    def _getWarningRanges(self):
        """ Collect all dataset.WarningRange objects for the plot's sources.
        """
        self.warningRanges.clear()
        for s in self.sources:
            if s.parent.warningId is not None:
                for i in s.parent.warningId:
                    w = self.Parent.warningRanges.get(i, None)
                    if w is not None:
                        self.warningRanges.add(w)


    def addSource(self, source, first=False):
        """ Add a data source (i.e. `Subchannel` or `Plot`) to the plot.
        """
        if source is None or source in self.sources:
            return
        
        if first:
            self.sources.insert(0, source)
        else:
            self.sources.append(source)
        source.setTransform(self.plotTransform)
        source.updateTransforms()
        self.plot.addSource(source)
        if source.hasMinMeanMax:
            source.removeMean = self.plotRemoveMean
            source.rollingMeanSpan = self.plotMeanSpan
        
        self._getWarningRanges()

        self.setTabText()


    def removeSource(self, source):
        """ Remove a `SubChannel` or `Plot` from the plot.
        """
        try:
            self.sources.remove(source)
            self.plot.removeSource(source)
            source.setTransform(None)
            self.setTabText()
            self._getWarningRanges()
            return True
        except ValueError:
            return False
            


    #===========================================================================
    # 
    #===========================================================================

    def OnMouseLeave(self, evt):
        self.root.showMouseHPos(None)
        self.root.showMouseVPos(None)
        evt.Skip()


    def OnScroll(self, evt):
        self.scrolling = True


    def OnScrollTrack(self, evt):
        self.visibleValueRange[1] - self.visibleValueRange[0]
        end = evt.GetPosition()
        start = evt.EventObject.GetThumbSize() + end
        self.setValueRange(self.scrollbar2val(start), self.scrollbar2val(end), 
                           None, tracking=True)


    def OnScrollEnd(self, evt):
        end = evt.GetPosition()
        start = evt.EventObject.GetThumbSize() + end
        self.setValueRange(self.scrollbar2val(start), self.scrollbar2val(end), 
                           None, tracking=False)
        self.scrolling = False


    def OnMenuSetColor(self, evt):
        """ Handle plot legend context menu selection event.
        """
        item = self.plot.legendItem
        data = wx.ColourData()
        data.SetChooseFull(True)
        data.SetColour(self.root.getPlotColor(item))
        dlg = wx.ColourDialog(self, data)
        dlg.SetTitle("%s Color" % item.parent.displayName)
        if dlg.ShowModal() == wx.ID_OK:
            color = dlg.GetColourData().GetColour().Get()
            self.root.setPlotColor(item, color)
            self.plot.setPlotPens()
            self.Refresh()

    
    def OnMenuMoveTop(self, evt):
        """ Handle plot legend context menu selection event.
        """
        item = self.plot.legendItem
        if item in self.sources:
            self.sources.remove(item)
            self.sources.append(item)
            self.plot.legendRect=None
            self.Refresh()
    
    
    def OnMenuMoveBottom(self, evt):
        """ Handle plot legend context menu selection event.
        """
        item = self.plot.legendItem
        if item in self.sources:
            self.sources.remove(item)
            self.sources.insert(0, item)
            self.plot.legendRect=None
            self.Refresh()
    
    
    def OnMenuLegendPos(self, evt):
        """ Handle plot legend context menu selection event.
        """
        mid = evt.GetId()
        try:
            posId = self.LEGEND_POS_IDS.index(mid)
            self.root.legendPos = self.root.app.setPref('legendPosition', posId)
            self.plot.legendRect = None
            self.Refresh()
        except ValueError:
            pass
            
            
    def OnMenuRemoveSource(self, evt):
        """ Handle plot legend context menu selection event.
        """
        self.removeSource(self.plot.legendItem)
        self.root.updateSourceMenu(self)
        self.legendRect = None
        self.Refresh()


    def OnMenuHideLegend(self, evt):
        self.root.showLegend = False
        self.root.app.setPref("showLegend", False)
        self.root.setMenuItem(self.root.menubar, self.root.ID_VIEW_LEGEND, checked=False)
        self.Parent.redraw()
        

#===============================================================================
# 
#===============================================================================

class WarningRangeIndicator(object):
    """ A visual indicator showing intervals in which a sensor's readings
        were outside a specific range.
    """
    PATTERNS = (wx.FDIAGONAL_HATCH, wx.BDIAGONAL_HATCH, 
                wx.HORIZONTAL_HATCH, wx.VERTICAL_HATCH)

    
    def __init__(self, parent, warning, color=None, style=None):
        """ Constructor.
            @param parent: The parent plot.
            @type warning: `mide_ebml.dataset.WarningRange`
            @keyword color: The warning area drawing color.
            @keyword style: The warning area fill style.
        """
        if style is None:
            style = self.PATTERNS[warning.id % len(self.PATTERNS)]
        if color is None:
            color = parent.root.app.getPref("warningColor", "PINK")
        self.source = warning
        self.sessionId = parent.root.session.sessionId
        self.brush = wx.Brush(color, style=style)
        self.pen = wx.Pen(color, style=wx.TRANSPARENT)
        self.oldDraw = None
        self.rects = None
        self.sourceList = warning.getSessionSource(self.sessionId)
        
    
    def draw(self, dc, hRange, hScale, scale=1.0, size=None):
        """ Draw a series of out-of-bounds rectangles in the given drawing
            context.
            
            @todo: Apply transforms to the DC itself before passing it, 
                eliminating all the scale and offset stuff.
            
            @param dc: TThe drawing context (a `wx.DC` subclass). 
        """
        if len(self.sourceList) < 2:
            return
        
        oldPen = dc.GetPen()
        oldBrush = dc.GetBrush()
        size = dc.GetSize() if size is None else size
        dc.SetPen(self.pen)
        dc.SetBrush(self.brush)

        thisDraw = (hRange, hScale, scale, size)
        if thisDraw != self.oldDraw or not self.rects:
            self.oldDraw = thisDraw
            self.rects = []
            for r in self.source.getRange(*hRange, sessionId=self.sessionId):
                # TODO: Apply transforms to DC in PlotCanvas.OnPaint() before
                # calling WarningRangeIndicator.draw(), eliminating these
                # offsets and scalars. May break rubber-band zooming, though.
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
        kwargs.setdefault('style',   aui.AUI_NB_TOP  
                                   | aui.AUI_NB_TAB_SPLIT 
                                   | aui.AUI_NB_TAB_MOVE  
                                   | aui.AUI_NB_SCROLL_BUTTONS 
                                   | aui.AUI_NB_WINDOWLIST_BUTTON
                                   | aui.AUI_NB_CLOSE_BUTTON
                                   | aui.AUI_NB_CLOSE_ON_ACTIVE_TAB
                                   )
        super(PlotSet, self).__init__(*args, **kwargs)

        if self.root is None:
            self.root = self.GetParent().root
        
        self.warningRanges = {}
        
        self.loadPrefs()
        
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CHANGED, self.OnPageChange)
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CLOSE, self.OnPageClose)
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CLOSED, self.OnPageClosed)
        

    def loadPrefs(self):
        """ (Re-)Load the app preferences.
        """
        for p in self:
            p.loadPrefs()


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
        
        
    def addPlot(self, source, title=None, name=None, color=None, 
                units=None, allowEmpty=False, initialRange=None):
        """ Add a new Plot to the display.
        
            @param source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
            @keyword title: The name displayed on the plot's tab
                (defaults to 'Plot #')
        """
        if source is not None:
            title = source.name or title
            
            if color is None:
                color = self.root.getPlotColor(source)
            
        title = "Plot %s" % len(self) if title is None else title
        name = name or title
        
        plot = Plot(self, source=source, root=self.root, name=name, units=units, 
                    initialRange=initialRange)
        plot.SetToolTipString(name)
        self.AddPage(plot, title)
        plot.setTabText()
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
        for _ in xrange(self.GetPageCount()):
            self.removePlot(0)
    
    
    def redraw(self, evt=None, force=False):
        """ Force a redraw.
        """
        # Clear the cached lines from all plots
        if force:
            for p in self:
                p.plot.lineList.clear()
                p.plot.minMeanMaxLineList.clear()
        self.Refresh()
        
    
    def OnPageChange(self, evt):
        """
        """
        self.getActivePage().enableMenus()


    def OnPageClose(self, evt):
        """
        """
        if len(self) == 1:
            pass
        evt.Skip()


    def OnPageClosed(self, evt):
        """
        """
        if self.GetPageCount() == 0:
            self.root.enableMenus(False)
        evt.Skip()


    def setAntialias(self, aa=True):
        """
        """
        for p in self:
            p.plot.setAntialias(aa)
        self.Refresh()

    
    def createWarningRanges(self):
        """
        """
        self.warningRanges.clear()
        for warn in self.root.dataset.warningRanges.values():
            self.warningRanges[warn.id] = WarningRangeIndicator(self, warn)


#===============================================================================
# 
#===============================================================================

# XXX: REMOVE THIS LATER. Makes running this module run the 'main' viewer.
if __name__ == "__main__":
    import viewer
    app = viewer.ViewerApp(loadLastFile=True)
    app.MainLoop()