"""

@todo: Completely replace RulerCtrl with a lighter-weight base class.
"""


import wx; wx=wx
import wx.lib.agw.rulerctrl as RC

# from wx.lib.embeddedimage import PyEmbeddedImage

import events
from base import ViewerPanel
import images
from timeutil import TimeValidator

# ---------------------------------------------------------------------------- #
# Class RulerCtrl
# ---------------------------------------------------------------------------- #

class TimelineCtrl(RC.RulerCtrl):
    """
    A subclass of RulerCtrl customized for displaying time ranges. It does not
    have indicators, is always horizontal, and it supports click-and-drag 
    adjustment.
    
    @todo: Replace more of the methods inherited from RulerCtrl (or entirely
        re-implement), removing all the conditional bits that aren't 
        applicable to a Timeline.
    """

    def __init__(self, *args, **kwargs):
        
        super(TimelineCtrl, self).__init__(*args, **kwargs)
        self._format = RC.RealFormat
        self._flip = True


    def OnMouseEvents(self, event):
        """ Handles the wx.EVT_MOUSE_EVENTS event for TimelineCtrl. """

        mousePos = event.GetPosition()

        if event.LeftDown():
            self.CaptureMouse()
            self._mousePosition = mousePos
        elif event.Dragging():
            self._mousePosition = mousePos
        elif event.LeftUp():
            if self.HasCapture():
                self.ReleaseMouse()
            if self._drawingparent:
                self._drawingparent.Refresh()

        event.Skip()
        
        
    def Draw(self, dc):
        """ Actually draws the whole TimelineCtrl. """
 
        if not self._valid:
            self.Update(dc)
 
        dc.SetBrush(wx.Brush(self._background))
        dc.SetPen(self._tickpen)
        dc.SetTextForeground(self._textcolour)
 
#         dc.DrawRectangleRect(self.GetClientRect())        
 
        if self._flip:
            dc.DrawLine(self._left, self._top, self._right+1, self._top)
        else:
            dc.DrawLine(self._left, self._bottom-1, self._right+1, self._bottom-1)
         
        dc.SetFont(self._majorfont)
 
        for label in self._majorlabels:
            pos = label.pos
             
            if self._flip:
                dc.DrawLine(self._left + pos, self._top,
                            self._left + pos, self._top + 5)
            else:
                dc.DrawLine(self._left + pos, self._bottom - 5,
                            self._left + pos, self._bottom)
             
            if label.text != "":
                dc.DrawText(label.text, label.lx, label.ly)
         
        dc.SetFont(self._minorfont)
 
        for label in self._minorlabels:
            pos = label.pos
 
            if self._flip:
                dc.DrawLine(self._left + pos, self._top,
                            self._left + pos, self._top + 3)
            else:
                dc.DrawLine(self._left + pos, self._bottom - 3,
                            self._left + pos, self._bottom)
             
            if label.text != "":
                dc.DrawText(label.text, label.lx, label.ly)


 
 
#===============================================================================
# 
#===============================================================================

# class IntervalIndicator(RC.Indicator):
#     IntervalMin = PyEmbeddedImage(
#         "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAMCAYAAABbayygAAAABHNCSVQICAgIfAhkiAAAAAlw"
#         "SFlzAAAFDQAABQ0Bt6aWewAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoA"
#         "AADqSURBVBiVdc8xSgMBEIXhbze7ahADMUmRytgIElJ4AfUC3kIvZGtraaGdB5BYGBCbINZW"
#         "ohAhBjUxYxEF3eiDgWH4572ZZJXbNq0ECQI9jl8i9v1Qtkn9tNFYXGk2qVbdj8d2ut26grKF"
#         "PJfv7so7HVotC4OBUrc7nQeRlstUKtRqpKl8dkEBnEykvR4PD1xdSYdDJeYdSxGe+n2Vft/i"
#         "1zN/Or4yvcESMkxQ+gs852CDkzWyMSqzhY8imEbE2SHbt4wyvM/AOccUIuLyiK1rHtf/i/5u"
#         "IuIuSZL2iItn3oqgiPhVWMZecf4JRKNfQuBAgZ0AAAAASUVORK5CYII=")
#     
#     IntervalMax = PyEmbeddedImage(
#         "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAMCAYAAABbayygAAAABHNCSVQICAgIfAhkiAAAAAlw"
#         "SFlzAAAFDQAABQ0Bt6aWewAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoA"
#         "AADcSURBVBiVbc8/S0IBFIbxn3+uIYqISlNLe0vQ5Nxa0ObQ2qeyoN1Ft76BY4NE4WQuDiZC"
#         "QWSYp6E7mNcD7/Ke5zxwchFheyq53O0Z1zlEmicmRTvTpHXfbh8cJQnLpY/ZzOV83sqABTal"
#         "TkdSrzOZSEYjpX5ffhdMCI0GzSa1mny5rIS9xnyvR7XKYiE/nSqt11kwIWIwsMIK73/He43x"
#         "nC7W+PrLJgMW+RmnpgSvrB+42QfGd2p84bPLeUQMM18XiGM88tblNCKGICL+5YS7K8Y43O4z"
#         "IC5Q2e1/AYOicX8ony1ZAAAAAElFTkSuQmCC")
#      
#     def __init__(self, *args, **kwargs):
#         super(IntervalIndicator, self).__init__(*args, **kwargs)
#         self.minMarker = self.IntervalMin.GetImage()
#         self.maxMarker = self.IntervalMax.GetImage()
#         self._other = None
#         self.getImage()
#          
#     def getOtherMark(self):
#         if self._other is None and self._parent.marks is not None and len(self._parent.marks) == 2:
#             if self.GetId() == TimeNavigatorCtrl.ID_MIN:
#                 self._other = self._parent.marks[1]
#             else:
#                 self._other = self._parent.marks[0]
#         return self._other
#      
#     def getImage(self):
#         other = self.getOtherMark()
#         if other is not None:
#             if self._value > other.GetValue():
#                 self._img = self.maxMarker
#             else:
#                 self._img = self.minMarker
#         else:
#             self._img = self.minMarker
#          
#      
#     def Draw(self, dc):
#         """
#         """
#         self.getImage()
#         super(IntervalIndicator, self).Draw(dc)
                

class TimeNavigatorCtrl(RC.RulerCtrl):
    """ Base class for time navigation controls.
    """
    ID_MIN = 100
    ID_MAX = 101
    
    EVT_INDICATOR_CHANGED = RC.EVT_INDICATOR_CHANGED
    EVT_INDICATOR_CHANGING = RC.EVT_INDICATOR_CHANGING
    
    def __init__(self, *args, **kwargs):
        super(TimeNavigatorCtrl, self).__init__(*args, **kwargs)
        self._format = RC.RealFormat
        self._labeledges = True
        
        self.root = self.GetParent().root
        
        self.marks = None
        self.AddIndicator(self.ID_MIN,0)
        self.AddIndicator(self.ID_MAX,0)
        
        self.marks = (self._indicators[0], self._indicators[1])
    
    def setVisibleRange(self, start, end):
        self.marks[0].SetValue(start)
        self.marks[1].SetValue(end)

    def getVisibleRange(self):
        return sorted((self.marks[0].GetValue(), self.marks[1].GetValue()))

#     def AddIndicator(self, Id, value):
#         self._indicators.append(IntervalIndicator(self, Id, value))
#         self.Refresh()

#===============================================================================
# 
#===============================================================================

class VerticalScaleCtrl(RC.RulerCtrl):
    def __init__(self, *args, **kwargs):
        kwargs['style'] = kwargs.get('style', 0) | wx.VERTICAL
        kwargs['orient'] = wx.VERTICAL
        self._borderSize = 1
        super(VerticalScaleCtrl, self).__init__(*args, **kwargs)
        self._format = RC.RealFormat

        if self._style & wx.NO_BORDER:
            self._borderSize = 1
        elif self._style & wx.SIMPLE_BORDER:
            self._borderSize = 1
        elif self._style & wx.STATIC_BORDER:
            self._borderSize = 3
        elif self._style & wx.SUNKEN_BORDER:
            self._borderSize = 5
        elif self._style & wx.RAISED_BORDER:
            self._borderSize = 7
        elif self._style & wx.DOUBLE_BORDER:
            self._borderSize = 7
        
        
    def Draw(self, dc):
        """
        Actually draws the whole L{RulerCtrl}.

        :param `dc`: an instance of `wx.DC`.
        """

        if not self._valid:
            self.Update(dc)

        dc.SetBrush(wx.Brush(self._background))
        dc.SetPen(self._tickpen)
        dc.SetTextForeground(self._textcolour)

#         dc.DrawRectangleRect(self.GetClientRect())        

        if self._flip:
            dc.DrawLine(self._left, self._top, self._left, self._bottom+1)
        else:
            dc.DrawLine(self._right-1, self._top, self._right-1, self._bottom+1)

        dc.SetFont(self._majorfont)

        for label in self._majorlabels:
            pos = label.pos
            
#             if self._flip:
#                 dc.DrawLine(self._left, self._top + pos,
#                             self._left + 5, self._top + pos)
#             else:
#                 dc.DrawLine(self._right - 5, self._top + pos,
#                             self._right, self._top + pos)
            
            if label.text != "":
                dc.DrawText(label.text, label.lx, label.ly)
        
        dc.SetFont(self._minorfont)

        for label in self._minorlabels:
            pos = label.pos

            if self._flip:
                dc.DrawLine(self._left, self._top + pos,
                            self._left + 3, self._top + pos)
            else:
                dc.DrawLine(self._right - 3, self._top + pos,
                            self._right, self._top + pos)
            
            if label.text != "":
                dc.DrawText(label.text, label.lx, label.ly)

        for indicator in self._indicators:
            indicator.Draw(dc)


    def CheckStyle(self):
        """ Adjust the L{RulerCtrl} style accordingly to borders, units, etc..."""

        width, height = self.GetSize()
        wbound = width - self._borderSize
        hbound = height - self._borderSize

        minText = self.LabelString(self._min, major=True)
        maxText = self.LabelString(self._max, major=True)

        dc = wx.ClientDC(self)
        minWidth, minHeight = dc.GetTextExtent(minText)
        maxWidth, maxHeight = dc.GetTextExtent(maxText)

        maxWidth = max(maxWidth, minWidth)
        maxHeight = max(maxHeight, minHeight)
        
        if maxWidth + 4 > wbound:
            wbound = maxWidth
            self.SetBestSize((maxWidth + 4, -1))
            if self.GetContainingSizer():
                self.GetContainingSizer().Layout()
                
        return wbound, hbound

    def GetRange(self):
        return self._min, self._max
    
#===============================================================================
# 
#===============================================================================

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
    
    BORDER_WIDTH = 4
    
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

        outerSizer = wx.BoxSizer(wx.HORIZONTAL)                
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
        
        outerSizer.Add(sizer, 1, wx.EXPAND)
        outerSizer.Add(wx.Panel(self, -1, size=(self.scrollbar.GetSize().y,16)),0)
        self.SetSizer(outerSizer)
#         self.SetSizer(sizer)

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
        return ((hpos+self.BORDER_WIDTH) * self.unitsPerPixel) + self.currentTime
        

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
            self.currentTime = start #max(self.timerange[0], start)
        
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
            evt = events.EvtSetVisibleRange(start=self.currentTime, end=end, 
                                            instigator=self, tracking=tracking)
            wx.PostEvent(self.root, evt)


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
                        Id=wx.ID_ZOOM_OUT, tooltip="Zoom Out (X axis)")
        self._addButton(sizer, images.zoomInH, self.OnZoomIn, 
                        Id=wx.ID_ZOOM_IN, tooltip="Zoom In (X axis)")
        self._addButton(sizer, images.zoomFitH, self.OnZoomFit, 
                        Id=wx.ID_ZOOM_FIT, tooltip="Zoom to fit entire "
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
            start = None if start is None else start * self.root.timeScalar
            end = None if end is None else end * self.root.timeScalar
            self.timeline.setVisibleRange(start, end)


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
        
        # If one end butts the limit, move the other one more.
        if newStart < self.timerange[0]:
            newEnd += self.timerange[0] - newStart
        elif newEnd > self.timerange[1]:
            newStart -= newEnd - self.timerange[1]
            
        v1 = max(self.timerange[0], newStart) 
        v2 = min(self.timerange[1], newEnd)#max(v1+10000, newEnd)) # Buffer
        self.setVisibleRange(v1,v2)
        self.postSetVisibleRangeEvent(v1, v2, tracking)


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
        self.zoom(.25, False, useKeyboard=evt.EventObject!=self.root)
        evt.Skip(False)

    
    def OnZoomOut(self, evt):
        """ Handle 'zoom out' events, i.e. the zoom in button was pressed. 
        """
        self.zoom(-.25, False, useKeyboard=evt.EventObject!=self.root)
        evt.Skip(False)


    def OnZoomFit(self, evt):
        """
        """
        self.setVisibleRange(*self.timerange)
        self.postSetVisibleRangeEvent(*self.timerange, tracking=False)
        evt.Skip(False)

#===============================================================================
# 
#===============================================================================

class Corner(ViewerPanel):
    """ A set of widgets to fit into the empty space in the lower left corner.
        Provides a space for 'manually' entering an interval of time to
        display.
    """
    
    def __init__(self, *args, **kwargs):
        super(Corner, self).__init__(*args, **kwargs)
        
        self.oldStart = self.oldEnd = None
        self.updating = False
        self.formatting = "%.4f"
        labelSize = self.GetTextExtent(" Start:")
        
        fieldAtts = {'size': (56,-1),
                     'style': wx.TE_PROCESS_ENTER}# | wx.TE_PROCESS_TAB}
        labelAtts = {'size': labelSize,#(30,-1),
                     'style': wx.ALIGN_RIGHT | wx.ALIGN_BOTTOM}
        unitAtts = {'style': wx.ALIGN_LEFT}
        
        self.startField = wx.TextCtrl(self, -1, "start", 
                                      validator=TimeValidator(), **fieldAtts)
        startLabel = wx.StaticText(self,-1,"Start:", **labelAtts)
        self.startUnits = wx.StaticText(self, -1, " ", **unitAtts)

        self.endField = wx.TextCtrl(self, -1, "end", 
                                    validator=TimeValidator(), **fieldAtts)
        endLabel = wx.StaticText(self,-1,"End:", **labelAtts)
        self.endUnits = wx.StaticText(self, -1, " ", **unitAtts)

        sizer = wx.FlexGridSizer(2,3, hgap=0, vgap=2)
        sizer.AddGrowableCol(0,-1)
        sizer.AddGrowableCol(1,-1)
        sizer.AddGrowableCol(2,-1)
        
        sizer.Add(startLabel,0,0,wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL)
        sizer.Add(self.startField)#,1,0)
        sizer.Add(self.startUnits)#, 2,0)
        
        sizer.Add(endLabel)#,0,1)
        sizer.Add(self.endField)#,1,1)
        sizer.Add(self.endUnits)#, 2,1)
        
        self.SetSizer(sizer)
        startLabel.SetSizerProps(valign="center")
        endLabel.SetSizerProps(valign="center")
        self.startUnits.SetSizerProps(valign="center")
        self.endUnits.SetSizerProps(valign="center")

        self.SetBackgroundColour(self.root.uiBgColor)
        self.setXUnits()
        
        self.startField.Bind(wx.EVT_KILL_FOCUS, self.OnRangeChanged)
        self.endField.Bind(wx.EVT_KILL_FOCUS, self.OnRangeChanged)
#         self.Bind(wx.EVT_TEXT_ENTER, self.OnRangeEntered)
        self.Bind(wx.EVT_TEXT_ENTER, self.OnRangeChanged)


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
            self._setValue(field, default)
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
        self.oldStart = start
        self.oldEnd = end
        self._setValue(self.startField, start)
        self._setValue(self.endField, end)
        self.updating = False
        

    def OnRangeChanged(self, evt):
        """ Process value changes after Enter or Tab.
        """
        start = self._getValue(self.startField, self.oldStart)
        end = self._getValue(self.endField, self.oldEnd)

        if start != self.oldStart or end != self.oldEnd:
            if not self.updating:
                self.Parent.setVisibleRange(start, end, None, False)
            
        evt.Skip()


    def OnRangeEntered(self, evt):
        """ Handle Enter. Does some work before `OnRangeChanged` is called.
        """
        evt.EventObject.SetSelection(-1,-1)
        self.OnRangeChanged(evt)


        