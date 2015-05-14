# import colorsys
# from itertools import izip
# import math
import sys
import time

from wx import aui
import wx; wx = wx # Workaround for Eclipse code comprehension

# Graphics (icons, etc.)
import images

# Custom controls
from base import ViewerPanel
from common import expandRange, mapRange
from timeline import VerticalScaleCtrl

from logger import logger

# The actual data-related stuff
from mide_ebml.dataset import WarningRange 

from build_info import DEBUG

ANTIALIASING_MULTIPLIER = 3.33
RESAMPLING_JITTER = 0.125

#===============================================================================
# 
#===============================================================================

def constrainInt(val):
    """ Helper function to prevent an `OverflowError` when plotting at extreme
        magnification.
    """
    return max(-2147483648L, min(2147483647L, val))

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
    GRID_ORIGIN_STYLE = ("originHLineColor", "GRAY", 1, wx.SOLID, None)
    GRID_MAJOR_STYLE = ("majorHLineColor", "LIGHT GRAY", 1, wx.SOLID, None)
    GRID_MINOR_STYLE = ("minorHLineColor", "LIGHT GRAY", 1, wx.USER_DASH, [2,2])
    RANGE_MIN_STYLE = ("minRangeColor", "LIGHT BLUE", 1, wx.USER_DASH, [8,4,4,4])    
    RANGE_MAX_STYLE = ("maxRangeColor", "PINK", 1, wx.USER_DASH, [8,4,4,4])
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
        self.setPlotPen()

        self.originHLinePen = self.loadPen(*self.GRID_ORIGIN_STYLE)
        self.majorHLinePen = self.loadPen(*self.GRID_MAJOR_STYLE)
        self.minorHLinePen = self.loadPen(*self.GRID_MINOR_STYLE)
        self.minRangePen = self.loadPen(*self.RANGE_MIN_STYLE)
        self.maxRangePen = self.loadPen(*self.RANGE_MAX_STYLE)
        self.meanRangePen = self.loadPen(*self.RANGE_MEAN_STYLE)

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
        
        self.antialias = False
        self.loadPrefs()
        
        self.lines = None
        self.points = None
        self.lastEvents = None
        self.lastRange = None
        self.minorHLines = None
        self.majorHLines = None
        self.minMeanMaxLines = None
        self.zooming = False
        self.zoomCorners = None
        self.zoomCenter = None

        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnMouseLeftDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnMouseLeftUp)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnMouseRightDown)

       
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


    def setPlotPen(self, color=None, weight=None, style=wx.SOLID, dashes=None):
        """ Set the color, weight, and/or style of the plotting pens.
            @keyword color: The color to use.
            @keyword width: The width of the pen's line.
            @keyword style: The pen's wxWidget line style.
        """
        self.NO_PEN = wx.Pen("white", style=wx.TRANSPARENT)
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
        
        p1 = rect[0] - trect[0]
        p2 = p1 + self.GetSize()[0]

        # XXX:
#         p1 = 0
#         p2 = self.GetSize()[0]
#         print "XXX: getRelRange: size=%r, rect=%r, trect=%r, p1=%r, p2=%r" % (self.GetSize(),rect, trect, p1, p2)
        
        result = (int(self.root.timeline.getValueAt(p1)),
                  int(self.root.timeline.getValueAt(p2)))
        
        return result


    def makeMinMeanMaxLines(self, hRange, vRange, hScale, vScale):
        """ Generate the points for the minimum and maximum envelopes.
            Used internally.
        """
        if not self.Parent.source.hasMinMeanMax:
            self.minMeanMaxLines = (tuple(),tuple(),tuple())
        
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
            if False:#thisT == lastT:
                lines[-1] = l[0], l[1], l[2], fun(lastV, thisV)
            else:
                lines.append((lastT, lastV, thisT, lastV))
                lines.append((thisT, lastV, thisT, thisV))
        
        def _finishline(lines):
            t = lines[-1][2]
            v = lines[-1][3]
            lines.append((t, v, width, v))

        vals = self.Parent.source.iterMinMeanMax(*hRange, padding=1, display=True)
        minPts = []
        meanPts = []
        maxPts = []
        # XXX: Test
#         bufferMarks = []
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
                # XXX: TEST
#                 x = (int(min(max(0, (pMin[0] - hRange[0])) * hScale, width)))
#                 bufferMarks.append((x,vRange[1]*vScale,x,vRange[0]*vScale))
                i+=1
            _finishline(minPts)
            _finishline(meanPts)
            _finishline(maxPts)
        except StopIteration:
            # No min/mean/max in the given range. Generally shouldn't happen.
            pass
        
        self.minMeanMaxLines = (minPts[1:], meanPts, maxPts[1:])
        # XXX: TEST
#         self.bufferMarks = bufferMarks
    

    def OnPaint(self, evt):
        """ Event handler for redrawing the plot. Catches common exceptions.
            Wraps the 'real' painting event handler.
        """
#         self._OnPaint(evt)
#         return
        if len(self.Parent.source) == 0:
            return
        
        ex = None if DEBUG else Exception
        
        try:
            self._OnPaint(evt)
        except IndexError:
            # TODO: These can occur on the first plot, but are non-fatal. Fix.
            # TODO: Make sure this actually works!
            logger.warning("IndexError in plot (race condition?); continuing.") 
            wx.MilliSleep(50)
            wx.PostEvent(self, evt)
        except IOError as err:
            msg = "An error occurred while trying to read the recording file."
            self.root.handleError(err, msg, closeFile=True)
        except ex as err:
            self.root.handleError(err, what="plotting data")
        

    def _OnPaint(self, evt):
        """ Redraws the plot. Called by `PlotCanvas.OnPaint()`.
        
            @todo: Apply offset and scaling transforms to the DC itself, 
                eliminating all the per-point math. May complicate rubber band
                zoom.
            @todo: Refactor and modularize this monster. Separate the line-list
                generation so multiple plots on the same canvas will be easy.
        """
#         logger.info("XXX: %s hasMinMeanMax==%s" % (self.Parent.source.parent.displayName, self.Parent.source.hasMinMeanMax))
        t0 = time.time()
        if self.Parent.source is None:
            return
        if self.root.drawingSuspended:
            return
        
        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))

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

        legend = self.Parent.legend
        
        # The size of a chunk of data to draw, so the rendering seems more
        # interactive. Not really a tenth anymore.
        tenth = int(size[0]/2 * self.oversampling)

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
        if self.Parent.source.hasMinMeanMax:
            mmm = self.Parent.source.getRangeMinMeanMax(hRange[0], hRange[1], display=True)
            if mmm is not None:
                self.Parent.visibleValueRange = [mmm[0], mmm[2]]
                if self.Parent.firstPlot: 
                    self.Parent.firstPlot = False
                    self.Parent.zoomToFit(self)
                    return

        hScale = (size.x + 0.0) / (hRange[1]-hRange[0]) * self.viewScale
        if vRange[0] != vRange[1]:
            vScale = (size.y + 0.0) / (vRange[1]-vRange[0]) * self.viewScale
        else:
            vScale = -(size.y + 0.0) * self.viewScale
            
        thisRange = (hScale, vScale, hRange, vRange)
        newRange = self.lastRange != thisRange or self.lines is None
        if newRange:
            self.lines = None
            self.minMeanMaxLines = None
            self.minorHLines = None
            self.majorHLines = None
            self.lastRange = thisRange
        drawCondensed = False

        # Draw gray over out-of-range times (if visible)
        sourceFirst, sourceLast = self.Parent.source.getInterval()
        if sourceFirst > hRange[0]:
            oldPen = dc.GetPen()
            oldBrush = dc.GetBrush()
            dc.SetPen(wx.Pen("WHITE", style=wx.TRANSPARENT))
            dc.SetBrush(wx.Brush(wx.Colour(240,240,240)))
            w = int((sourceFirst-hRange[0])*hScale)
            dc.DrawRectangle(0, 0, w, int(size[1]))
            dc.SetPen(oldPen)
            dc.SetBrush(oldBrush)
        
        if sourceLast < hRange[1]:
            oldPen = dc.GetPen()
            oldBrush = dc.GetBrush()
            dc.SetPen(wx.Pen("WHITE", style=wx.TRANSPARENT))
            dc.SetBrush(wx.Brush(wx.Colour(240,240,240)))
            x = int((sourceLast-hRange[0])*hScale)
            dc.DrawRectangle(x, 0, int(size[0]-x), int(size[1]))
            dc.SetPen(oldPen)
            dc.SetBrush(oldBrush)       
        
        if self.showWarningRange:
            for r in self.Parent.warningRange:
                r.draw(dc, hRange, hScale, self.viewScale, size)
                
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
        # sets up the scale; don't draw.
        if not self.Parent.firstPlot:
            # Minor lines are automatically removed.
            if self.root.drawMinorHLines and len(self.minorHLines) < size[1]/24:
                dc.DrawLineList(self.minorHLines, self.minorHLinePen)
            if self.root.drawMajorHLines:
                dc.DrawLineList(self.majorHLines, self.majorHLinePen)
        
        if self.Parent.source.hasMinMeanMax:
            if self.minMeanMaxLines is None:
                self.makeMinMeanMaxLines(hRange, vRange, hScale, vScale)
            drawCondensed = len(self.minMeanMaxLines[0]) >= size[0] * self.condensedThreshold
            if drawCondensed:
                if self.lines is None:
                # More buffers than (virtual) pixels; draw vertical lines
                # from min to max instead of the literal plot.
                    self.lines = []
                    lastPt = self.minMeanMaxLines[2][0][:2]
                    for i in range(0,len(self.minMeanMaxLines[0]),2):
                        a = self.minMeanMaxLines[0][i]
                        b = self.minMeanMaxLines[2][i]
                        self.lines.append((lastPt[0],lastPt[1],a[0],a[1]))
                        self.lines.append((a[0],a[1],b[0],b[1]))
                        lastPt = b[:2]
            else:
                if self.root.drawMinMax:
                    dc.DrawLineList(self.minMeanMaxLines[0], self.minRangePen)
                    dc.DrawLineList(self.minMeanMaxLines[2], self.maxRangePen)
                if self.root.drawMean:
                    dc.DrawLineList(self.minMeanMaxLines[1], self.meanRangePen)
                # XXX: TEST
#                 dc.DrawLineList(self.bufferMarks, self.meanRangePen)
        
        dc.SetPen(self._pen)
        if self.lines is None:
            i=1
            self.lines=[]
            self.points=[]
            
            # Lines are drawn in sets to provide more immediate results
            lineSubset = []
            
            events = self.Parent.source.iterResampledRange(hRange[0], hRange[1],
                size[0]*self.oversampling, padding=1, 
                jitter=self.root.noisyResample, display=True)

            try:
                event = events.next()
                if not self.Parent.source.hasMinMeanMax:
                    self.Parent.visibleValueRange = [sys.maxint, -sys.maxint]
                    expandRange(self.Parent.visibleValueRange, event[-1])
                lastPt = ((event[-2] - hRange[0]) * hScale, 
                          constrainInt((event[-1] - vRange[0]) * vScale))
                
                for i, event in enumerate(events,1):
                    # Using negative indices here in case doc.useIndices is True
                    pt = ((event[-2] - hRange[0]) * hScale, 
                          constrainInt((event[-1] - vRange[0]) * vScale))
                    self.points.append(pt)
                    
                    # A value of None is a discontinuity; don't draw a line.
                    if event[-1] is not None:
                        line = lastPt + pt
                        lineSubset.append(line)
                        self.lines.append(line)
                        if not self.Parent.source.hasMinMeanMax:
                            expandRange(self.Parent.visibleValueRange, 
                                        event[-1])
                    
                    if i % tenth == 0:
                        dc.DrawLineList(lineSubset)
                        lineSubset = []
                        
                    lastPt = pt
                    
            except StopIteration:
                # This will occur if there are 0-1 events, but that's okay.
                pass

            # Draw the remaining lines (if any)
            if not self.Parent.firstPlot:
                dc.DrawLineList(lineSubset) 

        else:
            # No change in displayed range; Use cached lines.
            dc.DrawLineList(self.lines)
        
        if DEBUG and self.lines:
            dt = time.time() - t0
            if drawCondensed:
                logger.info("Plotted %d lines (condensed mode) in %.4fs for %r" % (len(self.lines), dt, self.Parent.source.parent.displayName))
            else:
                logger.info("Plotted %d lines in %.4fs for %r" % (len(self.lines), dt, self.Parent.source.parent.displayName))
        
        if self.Parent.firstPlot:
            # First time the plot was drawn. Don't draw; scale to fit.
            self.Parent.zoomToFit(self)
            self.Parent.firstPlot = False
            self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
            dc.EndDrawing()
            return
        
        if self.drawPoints and len(self.lines) < size[0] / 4:
            # More pixels than points: draw actual points as circles.
            dc.SetPen(self._pointPen)
            dc.SetBrush(self._pointBrush)
            for p in self.points:
                dc.DrawCirclePoint(p,self.weight*self.viewScale*self.pointSize)
        
        dc.EndDrawing()
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


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
        dc.SetBrush(wx.Brush( wx.WHITE, wx.TRANSPARENT ) )
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
        self.zooming = True
        self.zoomCenter = (evt.GetX(), evt.GetY())
        self.zoomCorners = [self.zoomCenter]*2


    def OnMouseRightDown(self, evt):
        if self.zooming:
            # Cancel zoom rectangle
            self._drawRubberBand(*self.zoomCorners)
            self.zooming = False
            evt.Skip(False)
        else:
            if wx.GetKeyState(wx.WXK_ALT):
                # Zoom to fit both axes
                self.root.navigator.OnZoomFit(evt)
                return
            # Zoom out on both axes
            percent = 1.25
            x = self.root.timeline.getValueAt(evt.GetX())
            y = self.Parent.legend.getValueAt(evt.GetY())
            t1, t2 = self.root.getVisibleRange()
            dx = (t1 - t2) * percent
            v1, v2 = self.Parent.getValueRange()
            dy = (v1 - v2) * percent
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


    def OnMenuColor(self, evt):
        data = wx.ColourData()
        data.SetChooseFull(True)
        data.SetColour(self.color)
        dlg = wx.ColourDialog(self, data)
        if self.Parent.Name:
            dlg.SetTitle("%s Color" % self.Parent.Name)
        else:
            dlg.SetTitle("Plot Color")

        if dlg.ShowModal() == wx.ID_OK:
            color = dlg.GetColourData().GetColour().Get()
            self.setPlotPen(color=color)
            self.Refresh()


#===============================================================================
# 
#===============================================================================

class Plot(ViewerPanel):
    """ A single plotted channel, consisting of the vertical scale and actual
        plot-drawing canvas.
    """
    _sbMax = 10000.0 #(2**32)/2-1 + 0.0
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
        self.range = kwargs.pop('range', (-(2**16), (2**16)-1))
        self.warningRange = kwargs.pop("warningRange", [])
        super(Plot, self).__init__(*args, **kwargs)
        
        self.firstPlot = True
        self.visibleValueRange = None
        self.drawMajorHLines = True
        self.drawMinorHLines = False
        self.scrollUnitsPerUnit = 1.0
        self.unitsPerPixel = 1.0
        self.scrolling = False
        
        if self.root is None:
            self.root = self.Parent.root
            
        if self.yUnits is None:
            self.yUnits = getattr(self.source, "units", ('',''))
        
        if hasattr(self.source, 'hasDisplayRange'):
            self.range = self.source.displayRange
        
        self.legend = VerticalScale(self, -1, 
                                 visibleRange=(max(*self.range),min(*self.range)))
        self.plot = PlotCanvas(self, -1, color=color)
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
        
        self.enableMenus()


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


    def setTabText(self, s):
        """ Set the name displayed on the plot's tab.
        """
        try:
            i = self.Parent.GetPageIndex(self)
            self.Parent.SetPageText(i, s)
        except AttributeError:
            # Can occur if the plot isn't in a tab; just in case.
            self.SetTitle(s)
            

    def setUnitConverter(self, con):
        """ Apply (or remove) a unit conversion function.
        """
        oldUnits = self.source.units[0]
        oldXform = self.source.transform
        
        self.source.setTransform(con) #, update=False)
#         self.source.dataset.updateTransforms()
        self.yUnits = self.source.units
        self.legend.setUnits(self.source.units[-1])
        t,b = self.legend.getValueRange()
        
        if oldXform is not None:
            # Convert vertical range to original units
            nt = oldXform.revert(t)
            nb = oldXform.revert(b) 
            t = nt if nt is not None else t
            b = nb if nb is not None else b
        
        if con is None:
            self.setTabText(self.source.parent.displayName)
        else:
            try:
                nt = con.convert(t)
                nb = con.convert(b)
                t = nt if nt is not None else t
                b = nb if nb is not None else b
            except ValueError:
                logger.debug("Value error adjusting vertical range %r" % con)
                pass
            
            if oldUnits != con.units[0]:
                self.setTabText(con.units[0])
        
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

    def setPlotColor(self, evt=None):
        self.plot.OnMenuColor(evt)

    def redraw(self):
        """ Force the plot to redraw.
        """
        self.plot.lines = None
        self.Refresh()


    def removeMean(self, val=True, span=5000000):
        """ Turn 'remove mean' on or off.
        """
        if not self.source:
            return
        val = val and self.source.hasMinMeanMax
        if self.source.removeMean != val or self.source.rollingMeanSpan != span:
            self.source.rollingMeanSpan = span
            self.source.removeMean = val
            self.redraw()
        self.enableMenus()

        
    def showWarningRange(self, val=True):
        if not self.source:
            return 
        self.plot.showWarningRange = val
        self.redraw()
        self.enableMenus()


    def enableMenus(self):
        """ Update the plot-specific menus items in the main view's menu bar.
        """
        if self.Parent.getActivePage() != self:
            return
         
        enabled = self.source.hasMinMeanMax
        rt = self.root
        
        if not enabled or self.source.removeMean is False:
            rt.setMenuItem(rt.menubar, rt.ID_DATA_NOMEAN, checked=True)
        elif self.source.rollingMeanSpan == -1:
            rt.setMenuItem(rt.menubar, rt.ID_DATA_MEAN_TOTAL, checked=True)
        else:
            rt.setMenuItem(rt.menubar, rt.ID_DATA_MEAN, checked=True)
            
        for m in [rt.ID_DATA_NOMEAN, rt.ID_DATA_MEAN, rt.ID_DATA_MEAN_TOTAL]:
            rt.setMenuItem(rt.menubar, m, enabled=enabled)

        rt.setMenuItem(rt.menubar, rt.ID_DATA_WARNINGS, 
                       checked=self.plot.showWarningRange,
                       enabled=(len(self.warningRange)>0))

        rt.setMenuItem(rt.menubar, self.root.ID_VIEW_MINMAX, enabled=enabled, 
                       checked=self.root.drawMinMax)
        rt.setMenuItem(rt.menubar, self.root.ID_VIEW_LINES_MAJOR, enabled=True, 
                       checked=self.root.drawMajorHLines)
        rt.setMenuItem(rt.menubar, self.root.ID_VIEW_LINES_MINOR, enabled=True, 
                       checked=self.root.drawMinorHLines)
        rt.setMenuItem(rt.menubar, self.root.ID_VIEW_MEAN, enabled=enabled, 
                       checked=self.root.drawMean)
        
        rt.setMenuItem(rt.menubar, rt.ID_VIEW_UTCTIME,
                       enabled=rt.session.utcStartTime is not None)
        
        rt.updateConversionMenu()                
            

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


#===============================================================================
# 
#===============================================================================

class WarningRangeIndicator(object):
    """ A visual indicator showing intervals in which a sensor's readings
        were outside a specific range.
    """
    
    def __init__(self, source, sessionId=None, color="PINK", style=wx.BDIAGONAL_HATCH):
        """ 
            @type source: `mide_ebml.dataset.WarningRange`
            @keyword color: The warning area drawing color.
            @keyword style: The warning area fill style.
        """
        self.source = source
        self.sessionId = sessionId
        self.brush = wx.Brush(color, style=style)
        self.pen = wx.Pen(color, style=wx.TRANSPARENT)
        self.oldDraw = None
        self.rects = None
        self.sourceList = source.getSessionSource(sessionId)
        
        
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
                                   )
        super(PlotSet, self).__init__(*args, **kwargs)

        if self.root is None:
            self.root = self.GetParent().root
        
        self.loadPrefs()
        
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CHANGED, self.OnPageChange)
        

    def loadPrefs(self):
        """
        """
        # TODO: Remove this when the full ChannelList is implemented.
        # The default RecorderInfo will contain these defaults.
        self.warnLow = self.root.app.getPref("tempMin", -20.0, section="wvr")
        self.warnHigh = self.root.app.getPref("tempMax", 60.0, section="wvr")
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
                units=None, allowEmpty=False):
        """ Add a new Plot to the display.
        
            @param source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
            @keyword title: The name displayed on the plot's tab
                (defaults to 'Plot #')
        """
        
#         if len(source) == 0:
#             return None
        
        # For debugging: catch no exceptions
        Ex = None if DEBUG else Exception
        
        # TODO: Use the warning referenced by the subchannel in the file's
        # ChannelList element.
        try:
            warningRange = WarningRange(source.dataset, warningId=0, 
              channelId=1, subchannelId=1, low=self.warnLow, high=self.warnHigh)
            warnings = [WarningRangeIndicator(warningRange, source.session.sessionId)]
        except (IndexError, KeyError):
            # Dataset had no data for channel and/or subchannel.
            # Should not normally occur, but not fatal.
            warnings = []
        except Ex as err:
            self.handleError(err, 
                             what="creating a plot view warning indicator")

        title = source.name or title
        title = "Plot %s" % len(self) if title is None else title
        name = name or title
        
        if color is None:
            color = self.root.getPlotColor(source)
        
        plot = Plot(self, source=source, root=self.root, name=name,
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
        for _ in xrange(self.GetPageCount()):
            self.removePlot(0)
    
    
    def redraw(self, evt=None):
        """ Force a redraw.
        """
        # Clear the cached lines from all plots
        for p in self:
            p.plot.lines = None
        self.Refresh()
        
    
    def OnPageChange(self, evt):
        ""
        self.getActivePage().enableMenus()


    def setAntialias(self, aa=True):
        for p in self:
            p.plot.setAntialias(aa)
        self.redraw()


#===============================================================================
# 
#===============================================================================

# XXX: REMOVE THIS LATER. Makes running this module run the 'main' viewer.
if __name__ == "__main__":
    import viewer
    app = viewer.ViewerApp(loadLastFile=True)
    app.MainLoop()