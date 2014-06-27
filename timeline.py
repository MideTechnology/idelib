"""

@todo: Completely replace RulerCtrl with a lighter-weight base class.
"""


import wx; wx=wx
import wx.lib.agw.rulerctrl as RC

# from wx.lib.embeddedimage import PyEmbeddedImage


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