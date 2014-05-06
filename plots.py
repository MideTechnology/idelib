# import colorsys
from itertools import izip
import sys

from wx import aui
import wx; wx = wx # Workaround for Eclipse code comprehension

# Graphics (icons, etc.)
import images

# Custom controls
from base import ViewerPanel, MenuMixin
from common import expandRange, mapRange
from timeline import VerticalScaleCtrl

# The actual data-related stuff
import mide_ebml

ANTIALIASING_MULTIPLIER = 3.33
RESAMPLING_JITTER = 0.125

#===============================================================================
# 
#===============================================================================

class LegendArea(ViewerPanel):
    """ The vertical axis of the plot. Contains the scale and the vertical
        zoom buttons.
    """
    zoomAmount = 0.25
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
        """
        kwargs.setdefault('style',wx.NO_BORDER)
        super(LegendArea, self).__init__(*args, **kwargs)
        
        self.highlightColor = wx.Colour(255,255,255)

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
        

    def zoom(self, percent, tracking=True, useKeyboard=False):
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
        self.unitsPerPixel = abs((self.visibleRange[0] - self.visibleRange[1]) \
                                 / (evt.Size[1] + 0.0))
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

class PlotCanvas(wx.ScrolledWindow, MenuMixin):
    """ The actual plot-drawing area.
    
        @todo: Make drawing asynchronous and interruptible.
    """
    GRID_ORIGIN_STYLE = ("originHLineColor", "GRAY", 1, wx.SOLID, None)
    GRID_MAJOR_STYLE = ("majorHLineColor", "LIGHT GRAY", 1, wx.SOLID, None)
    GRID_MINOR_STYLE = ("minorHLineColor", "LIGHT GRAY", 1, wx.USER_DASH, [2,2])
    RANGE_MIN_STYLE = ("minRangeColor", "LIGHT BLUE", 1, wx.USER_DASH, [8,4,4,4])    
    RANGE_MAX_STYLE = ("maxRangeColor", "PINK", 1, wx.USER_DASH, [8,4,4,4])
    RANGE_MEAN_STYLE = ("meanRangeColor", "YELLOW", 1, wx.USER_DASH, [8,4,4,4])
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel/ViewerPanel arguments plus:
        
            @keyword root: The viewer's 'root' window.
            @keyword color: The plot's pen color.
            @keyword weight: The weight (thickness) of the plot's pen. 
        """
        self.root = kwargs.pop('root',None)
        self.color = kwargs.pop('color', "BLUE")
        self.weight = kwargs.pop('weight',1)
        self.pointSize = kwargs.pop('pointSize', 2)
        kwargs.setdefault('style',wx.VSCROLL|wx.BORDER_SUNKEN)
        
        super(PlotCanvas, self).__init__(*args, **kwargs)
        self.SetBackgroundColour("white")
        
        if self.root is None:
            self.root = self.GetParent().root
        
        self.originHLinePen = self.loadPen(*self.GRID_ORIGIN_STYLE)
        self.majorHLinePen = self.loadPen(*self.GRID_MAJOR_STYLE)
        self.minorHLinePen = self.loadPen(*self.GRID_MINOR_STYLE)
        self.minRangePen = self.loadPen(*self.RANGE_MIN_STYLE)
        self.maxRangePen = self.loadPen(*self.RANGE_MAX_STYLE)
        self.meanRangePen = self.loadPen(*self.RANGE_MEAN_STYLE)
        
        self.lines = None
        self.points = None
        self.lastEvents = None
        self.lastRange = None
        self.minorHLines = None
        self.majorHLines = None
        self.minMeanMaxLines = None

        self.setPlotPen()
        self.setAntialias(False)
        
        self.setContextMenu(wx.Menu())
        self.addMenuItem(self.contextMenu, wx.ID_SELECT_COLOR, 
                         "Select Color...", "", 
                         self.OnMenuColor)
        self.contextMenu.AppendSeparator()
        self.addMenuItem(self.contextMenu, self.root.ID_DATA_NOMEAN, 
                         "Do Not Remove Mean", "",
                         self.root.OnDontRemoveMeanCheck, kind=wx.ITEM_RADIO)
        self.addMenuItem(self.contextMenu, self.root.ID_DATA_MEAN, 
                         "Remove Rolling Mean from Data", "",
                         self.root.OnRemoveRollingMeanCheck, kind=wx.ITEM_RADIO)
        self.addMenuItem(self.contextMenu, self.root.ID_DATA_MEAN_TOTAL, 
                         "Remove Total Mean from Data", "",
                         self.root.OnRemoveTotalMeanCheck, kind=wx.ITEM_RADIO)
#         self.contextMenu.AppendSeparator()
#         self.addMenuItem(self.contextMenu, self.root.ID_VIEW_ANTIALIAS, 
#                          "Antialiased Drawing", "", 
#                          self.root.OnToggleAA, kind=wx.ITEM_CHECK)
#         self.addMenuItem(self.contextMenu, self.root.ID_VIEW_JITTER,
#                         "Noisy Resampling", "", 
#                         self.root.OnToggleNoise, kind=wx.ITEM_CHECK)
#         self.addMenuItem(self.contextMenu, self.root.ID_VIEW_UTCTIME, 
#                          "Show Absolute UTC Time", "",
#                          self.root.OnToggleUtcTime, kind=wx.ITEM_CHECK)
        
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)

        self.normalBg = wx.Colour(255,255,255)
        self.minMaxBg = wx.Colour(240,240,240)
        
       
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
        trect = self.root.timeline.GetScreenRect()
        
        p1 = rect[0] - trect[0]
        p2 = p1 + self.GetSize()[0]

        result = (int(self.root.timeline.getValueAt(p1)),
                  int(self.root.timeline.getValueAt(p2)))
        
        return result


    def makeMinMeanMaxLines(self, hRange, vRange, hScale, vScale):
        """ Generate the points for the minimum and maximum envelopes.
            Used internally.
        """
        if not self.Parent.source.hasMinMeanMax:
            return (tuple(),tuple(),tuple())
        
        width = int((hRange[1] - hRange[0]) * hScale)
        
        def _startline(lines, pt):
            thisT = int(min(max(0, (pt[0] - hRange[0])) * hScale, width))
            thisV = int((pt[-1] - vRange[0]) * vScale) 
            lines.append((0, thisV, thisT, thisV))
        
        def _makeline(lines, pt):
            lastT = lines[-1][2]
            lastV = lines[-1][3]
            thisT = int(min(max(0, (pt[0] - hRange[0])) * hScale, width))
            thisV = int((pt[-1] - vRange[0]) * vScale)
            if thisT != lastT:
                lines.append((lastT, lastV, thisT, lastV))
                lines.append((thisT, lastV, thisT, thisV))
        
        def _finishline(lines):
            t = lines[-1][2]
            v = lines[-1][3]
            lines.append((t, v, width, v))

        vals = self.Parent.source.iterMinMeanMax(*hRange, padding=1)
        minPts = []
        meanPts = []
        maxPts = []

        pMin, pMean, pMax = vals.next()
        _startline(minPts, pMin)
        _startline(meanPts, pMean)
        _startline(maxPts, pMax)
        for pMin, pMean, pMax in vals:
            _makeline(minPts, pMin)
            _makeline(meanPts, pMean)
            _makeline(maxPts, pMax)
        _finishline(minPts)
        _finishline(meanPts)
        _finishline(maxPts)
        
        return (minPts[1:], meanPts, maxPts[1:])
    

    def makeMinMaxBoxes(self, hRange, vRange, hScale, vScale):
        """ Generate the rectangles forming the minimum and maximum range
            envelope. Used internally.
            DOES NOT WORK WITH ANTIALIASING; CURRENTLY UNUSED.
        """
        # TODO: Make this work or remove it.
        buff = hScale #0.1 * hScale
        boxes = []
        vals = self.Parent.source.iterMinMeanMax(*hRange, padding=1)
        lastMin, _, lastMax = vals.next()
        lastT = (lastMin[-2] - hRange[0]) * hScale
        lastMin = (lastMin[-1] - vRange[0]) * vScale
        lastMax = (lastMax[-1] - vRange[0]) * vScale
        
        for pMin, _, pMax in vals:
            t = (pMin[0] - hRange[0]) * hScale
            boxes.append((lastT, lastMin-buff, (t-lastT)*1.005, 
                          lastMax-lastMin+buff)) 
            lastT = t
            lastMin = (pMin[-1] - vRange[0]) * vScale
            lastMax = (pMax[-1] - vRange[0]) * vScale
        
        boxes.append((lastT, lastMin-buff, hRange[1]*hScale-lastT, 
                      lastMax-lastMin+buff))
#         return [map(lambda x: int(x+0.5), v) for v in boxes]
        return boxes


    def OnPaint(self, evt):
        """ Event handler for redrawing the plot. Catches common exceptions.
            Wraps the 'real' painting event handler.
        """
        self._OnPaint(evt)
        return
    
        try:
            self._OnPaint(evt)
        except IndexError:
            print "index error"
            return
        except IOError as err:
            msg = "An error occurred while trying to read the recording file."
            self.root.handleException(err, msg, closeFile=True)
        except Exception as err:
            self.root.handleException(err, what="plotting data")
        

    def _OnPaint(self, evt):
        """ Redraws the plot. Called by `PlotCanvas.OnPaint()`.
        
            @todo: Apply offset and scaling transforms to the DC itself, 
                eliminating all the per-point math.
            @todo: Refactor and modularize this monster. Separate the line-list
                generation so multiple plots on the same canvas will be easy.
            @todo: Remove the vertical scaling pass at first and use min/max
                from the data. 
        """
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
            mmm = self.Parent.source.getRangeMinMeanMax(hRange[0], hRange[1])
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
        newRange = self.lastRange != thisRange
        if newRange:
            self.lines = None
            self.minMeanMaxLines = None
            self.minorHLines = None
            self.majorHLines = None
            self.lastRange = thisRange
        drawCondensed = False
                
        for r in self.Parent.warningRange:
            r.draw(dc, hRange, hScale, self.viewScale, size)
                
        # Get the horizontal grid lines. 
        # NOTE: This might not work in the future. Consider modifying
        #    VerticalScaleCtrl to ensure we've got access to the labels!
        if self.root.drawMinorHLines:
            if self.minorHLines is None:
#             self.minorHLinePen.SetWidth(self.viewScale)
                self.minorHLines = self.makeHGridlines(legend.scale._minorlabels, 
                                                       size[0], self.viewScale)
            
        if self.root.drawMajorHLines:
            if self.majorHLines is None:
#             self.majorHLinePen.SetWidth(self.viewScale)
                self.majorHLines = self.makeHGridlines(legend.scale._majorlabels, 
                                                       size[0], self.viewScale)

        # If the plot source does not have min/max data, the first drawing only
        # sets up the scale; don't draw.
        if not self.Parent.firstPlot:
            # Minor lines are automatically removed.
            if self.root.drawMinorHLines and len(self.minorHLines) < size[1] / 24:
                dc.DrawLineList(self.minorHLines, self.minorHLinePen)
            if self.root.drawMajorHLines:
                dc.DrawLineList(self.majorHLines, self.majorHLinePen)
        
        if self.Parent.source.hasMinMeanMax:
            if self.minMeanMaxLines is None:
                self.minMeanMaxLines = self.makeMinMeanMaxLines(hRange, vRange, hScale, vScale)
            drawCondensed = len(self.minMeanMaxLines[0]) >= size[0] * 1.75
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

        
        dc.SetPen(self._pen)
        if self.lines is None:
            i=1
            self.lines=[]
            self.points=[]
            
            # Lines are drawn in sets to provide more immediate results
            lineSubset = []
            
            events = self.Parent.source.iterResampledRange(hRange[0], hRange[1],
                size[0]*self.oversampling, padding=1, jitter=self.root.noisyResample)

            try:
                event = events.next()
                if not self.Parent.source.hasMinMeanMax:
                    self.Parent.visibleValueRange = [sys.maxint, -sys.maxint]
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
                        if not self.Parent.source.hasMinMeanMax:
                            expandRange(self.Parent.visibleValueRange, event[-1])
                    
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
        
        if self.Parent.firstPlot:
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
                dc.DrawCirclePoint(p,self.weight*self.viewScale*self.pointSize)
        
        dc.EndDrawing()
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


    #===========================================================================
    # 
    #===========================================================================
    
    def setAntialias(self, aa=True):
        """
        """
        self.antialias = aa
        if aa:
            self.viewScale = self.root.aaMultiplier
            self.oversampling = self.viewScale * 1.33
            gridScale = self.viewScale
            rangeScale = self.viewScale
        else:
            self.viewScale = 1.0
            self.oversampling = 2.0 #3.33 # XXX: Clean this up!
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
        self.root.showMouseHPos(evt.GetX())
        self.root.showMouseVPos(self.Parent.legend.getValueAt(evt.GetY()),
                                units=self.Parent.yUnits[1])
        evt.Skip()


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
        """ Handle the antialiasing toggle on the context menu. """
        evt.IsChecked()
        pass
    
    
    def OnMenuJitter(self, evt):
        pass


    def OnMenuNoMean(self, evt):
        self.Parent.removeMean(evt.IsChecked())


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
        
        self.legend = LegendArea(self, -1, 
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
        
#         self.plot.Bind(wx.EVT_KEY_UP, self.OnKeypress)
        
        self.enableMenus()
        

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
        

    def enableMenus(self):
        """ Update the plot-specific menus, both on the main menu and the plot's
            contextual menu.
        """
        enabled = self.source.hasMinMeanMax
        rt = self.root
        pt = self.plot
        
        if not enabled or self.source.removeMean is False:
            rt.setMenuItem(rt.menubar, rt.ID_DATA_NOMEAN, checked=True)
            pt.setMenuItem(pt.contextMenu, rt.ID_DATA_NOMEAN, checked=True)
        elif self.source.rollingMeanSpan == -1:
            rt.setMenuItem(rt.menubar, rt.ID_DATA_MEAN_TOTAL, checked=True)
            pt.setMenuItem(pt.contextMenu, rt.ID_DATA_MEAN_TOTAL, checked=True)
        else:
            rt.setMenuItem(rt.menubar, rt.ID_DATA_MEAN, checked=True)
            pt.setMenuItem(pt.contextMenu, rt.ID_DATA_MEAN, checked=True)
            
        for m in [rt.ID_DATA_NOMEAN, rt.ID_DATA_MEAN, rt.ID_DATA_MEAN_TOTAL]:
            rt.setMenuItem(rt.menubar, m, enabled=enabled)
            pt.setMenuItem(pt.contextMenu, m, enabled=enabled)
        

        self.root.setMenuItem(self.root.menubar, 
                              self.root.ID_VIEW_MINMAX,
                              enabled=enabled, checked=self.root.drawMinMax)
        self.root.setMenuItem(self.root.menubar,
                              self.root.ID_VIEW_LINES_MAJOR, 
                              enabled=True, checked=self.root.drawMajorHLines)
        self.root.setMenuItem(self.root.menubar,
                              self.root.ID_VIEW_LINES_MINOR,
                              enabled=True, checked=self.root.drawMinorHLines)
        self.root.setMenuItem(self.root.menubar,
                              self.root.ID_VIEW_MEAN,
                              enabled=True, checked=self.root.drawMean)
                              
#         # Non-plot-specific menu items
#         self.plot.setMenuItem(self.plot.contextMenu, 
#                               self.root.ID_VIEW_ANTIALIAS,
#                               checked=self.root.antialias)
#         self.plot.setMenuItem(self.plot.contextMenu, self.root.ID_VIEW_JITTER,
#                               checked=self.root.noisyResample != 0)
#         self.plot.setMenuItem(self.plot.contextMenu, self.root.ID_VIEW_UTCTIME,
#                               checked=self.root.showUtcTime)
            

    #===========================================================================
    # 
    #===========================================================================

#     def OnKeypress(self, evt):
#         """ Handle a keypress event in a plot. """
#         keycode = evt.GetUnicodeKey()
#         keychar = unichr(keycode)
#         
#         if keychar == u'R':
#             self.plot.Refresh()
#         elif evt.CmdDown() and not evt.ShiftDown():
#             # TODO: These won't necessarily work on international keyboards
#             # (e.g. '=' is a shift combination on German keyboards)
#             if keychar == u'-':
#                 self.legend.OnZoomOut(None)
#             elif keychar == u'=':
#                 self.legend.OnZoomIn(None)
#             elif keychar == u'0':
#                 self.zoomToFit()
#             else:
#                 evt.Skip()
#         else:
#             evt.Skip()
#         
    
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
    
    def __init__(self, source, color="PINK", style=wx.BDIAGONAL_HATCH):
        """ 
            @type source: `mide_ebml.dataset.WarningRange`
            @keyword color: The warning area drawing color.
            @keyword style: The warning area fill style.
        """
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
        kwargs.setdefault('style', aui.AUI_NB_TOP | 
                                   aui.AUI_NB_TAB_SPLIT |
                                   aui.AUI_NB_TAB_MOVE | 
                                   aui.AUI_NB_SCROLL_BUTTONS)
        super(PlotSet, self).__init__(*args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
            
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CHANGED, self.OnPageChange)
        

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
                units=None):
        """ Add a new Plot to the display.
        
            @param source: The source of data for the plot (i.e. a
                sensor channel's dataset.EventList or dataset.Plot)
            @keyword title: The name displayed on the plot's tab
                (defaults to 'Plot #')
        """
        
        # NOTE: Hard-coded warning range is for WVR hardware! Modify later.
        try:
            warnLow = self.root.app.getPref("wvr_tempMin", -20.0)
            warnHigh = self.root.app.getPref("wvr_tempMax", 60.0)
            warningRange = mide_ebml.dataset.WarningRange(
                source.dataset.channels[1][1].getSession(), warnLow, warnHigh)
            warnings = [WarningRangeIndicator(warningRange)]
        except (IndexError, KeyError):
            # Dataset had no data for channel and/or subchannel.
            # Should not normally occur, but not fatal.
            warnings = []
        except Exception as err:
            self.handleException(err, 
                                 what="creating a plot view warning indicator")

        title = source.name or title
        title = "Plot %s" % len(self) if title is None else title
        name = name or title
        
        if color is None:
            color = self.root.getPlotColor(source)
        
        plot = Plot(self, source=source, root=self.root, 
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