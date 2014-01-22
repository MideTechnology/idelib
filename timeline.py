import math

import wx; wx=wx

try:
    from agw import rulerctrl as RC
    from agw.rulerctrl import EVT_INDICATOR_CHANGING, EVT_INDICATOR_CHANGED
except ImportError: # if it's not there locally, try the wxPython lib.
    import wx.lib.agw.rulerctrl as RC
    from  wx.lib.agw.rulerctrl import EVT_INDICATOR_CHANGING, EVT_INDICATOR_CHANGED



# ---------------------------------------------------------------------------- #
# Class RulerCtrl
# ---------------------------------------------------------------------------- #

class TimelineCtrl(RC.RulerCtrl):
    """
    A subclass of RulerCtrl customized for displaying time ranges. It does not
    have indicators, and it supports (or will support) click-and-drag adjustment.
    
    @todo: Replace more of the methods inherited from RulerCtrl, removing all
        the conditional bits that aren't applicable to a Timeline.
    """

    def __init__(self, *args, **kwargs):
        super(TimelineCtrl, self).__init__(*args, **kwargs)
        self._format = RC.RealFormat
        self._flip = True
#         self._labeledges = True


    def OnMouseEvents(self, event):
        """ Handles the wx.EVT_MOUSE_EVENTS event for TimelineCtrl. """

        mousePos = event.GetPosition()

        if event.LeftDown():
            self.CaptureMouse()
            self._mousePosition = mousePos
            # TODO: This
        elif event.Dragging():
            self._mousePosition = mousePos
            # TODO: This
        elif event.LeftUp():
            if self.HasCapture():
                self.ReleaseMouse()
            if self._drawingparent:
                self._drawingparent.Refresh()
            # TODO: This

        event.Skip()
        
        
    def Draw(self, dc):
        """ Actually draws the whole RulerCtrl. """
 
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

class TimeNavigatorCtrl(RC.RulerCtrl):
    
    ID_MIN = 100
    ID_MAX = 101
    
    def __init__(self, *args, **kwargs):
        super(TimeNavigatorCtrl, self).__init__(*args, **kwargs)
        self._format = RC.RealFormat
        self._labeledges = True
        
        self.root = self.GetParent().root
        
        self.AddIndicator(self.ID_MIN,0)
        self.AddIndicator(self.ID_MAX,0)
        
        self.marks = (self._indicators[0], self._indicators[1])
    
    def setVisibleRange(self, start, end):
        self.marks[0].SetValue(start)
        self.marks[1].SetValue(end)

    def getVisibleRange(self):
        return sorted((self.marks[0].GetValue(), self.marks[1].GetValue()))
#         v1 = self.marks[0].GetValue()
#         v2 = self.marks[1].GetValue()
#         return min(v1,v2), max(v1,v2)


#===============================================================================
# 
#===============================================================================

class VerticalScaleCtrl(RC.RulerCtrl):
    def __init__(self, *args, **kwargs):
        kwargs['style'] = kwargs.get('style', 0) | wx.VERTICAL
        kwargs['orient'] = wx.VERTICAL
        super(VerticalScaleCtrl, self).__init__(*args, **kwargs)
        self._format = RC.RealFormat
        
        
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
        if self._style & wx.NO_BORDER:
            wbound = width-1
            hbound = height-1
        elif self._style & wx.SIMPLE_BORDER:
            wbound = width-1
            hbound = height-1
        elif self._style & wx.STATIC_BORDER:
            wbound = width-3
            hbound = height-3
        elif self._style & wx.SUNKEN_BORDER:
            wbound = width-5
            hbound = height-5
        elif self._style & wx.RAISED_BORDER:
            wbound = width-7
            hbound = height-7
        elif self._style & wx.DOUBLE_BORDER:
            wbound = width-7
            hbound = height-7

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