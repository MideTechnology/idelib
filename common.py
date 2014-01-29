'''
Custom events, controls, dialogs, 'constants', functions, and other things 
used by multiple files. 

Created on Dec 31, 2013

@author: dstokes
'''

import calendar as _calendar
from datetime import datetime as _datetime
import sys as _sys

import wx; wx = wx;
import wx.lib.masked as wx_mc

import images as _images

#===============================================================================
# 
#===============================================================================

def expandRange(l, v):
    """ Given a two element list containing a minimum and maximum value, 
        expand it if the given value is outside that range. 
    """
    l[0] = min(l[0],v)
    l[1] = max(l[1],v)


def mapRange(x, in_min, in_max, out_min, out_max):
    """ Given a value `x` between `in_min` and `in_max`, get the equivalent
        value relative to `out_min` and `out_max`.
    """
    return ((x - in_min + 0.0) * (out_max - out_min) / 
            (in_max - in_min) + out_min)


def nextPow2(x):
    """ Round up to the next greater than or equal to power-of-two.
    """
    x = long(x)
    if x & (x-1L) == 0L:
        # already a power of 2
        return x
    x -= 1L
    for i in xrange(5):
        x |= x >> (2**long(i))
    return x+1L

#===============================================================================
# Formatting and parsing helpers
#===============================================================================

def hex32(val):
    """ Format an integer as an 8 digit hex number. """
    return "0x%08x" % val

def hex16(val):
    """ Format an integer as an 4 digit hex number. """
    return "0x%04x" % val

def hex8(val):
    """ Format an integer as a 2 digit hex number. """
    return "0x%02x" % val

def str2int(val):
    """ Semi-smart conversion of string to integer; works for decimal and hex.
    """
    try:
        return int(val)
    except ValueError:
        return int(val, 16)

def datetime2int(val, tzOffset=0):
    """ Convert a date/time object (either a standard Python datetime.datetime
        or wx.DateTime) into the UTC epoch time (i.e. UNIX time stamp).
    """
    if isinstance(val, wx.DateTime):
        return val.Ticks
        val = _datetime.strptime(str(val), '%m/%d/%y %H:%M:%S')
    return int(_calendar.timegm(val.timetuple()) + tzOffset)
        

def time2int(val, tzOffset=0):
    """ Parse a time string (as returned from `TimeCtrl.GetValue()`) into
        seconds since midnight.
    """
    t = _datetime.strptime(str(val), '%H:%M:%S')
    return int((t.hour * 60 * 60) + (t.minute * 60) + t.second + tzOffset)



#===============================================================================
# 
#===============================================================================

# class TimeValidator(wx.PyValidator):
#     """
#     """
#     validCharacters = "-+.0123456789"
#     
#     def __init__(self):
#         super(TimeValidator, self).__init__()
#         self.Bind(wx.EVT_CHAR, self.OnChar)
# 
#     def Validate(self, win):
#         val = self.GetWindow.GetValue()
#         return all((c in self.validCharacters for c in val))
# 
#     def OnChar(self, evt):
#         key = evt.GetKeyCode()
# 
#         if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
#             evt.Skip()
#             return
# 
#         if chr(key) in self.validCharacters:
#             evt.Skip()
#             return
# 
#         if not wx.Validator_IsSilent():
#             wx.Bell()
#             
#         return        

#===============================================================================
# 
#===============================================================================

class DateTimeCtrl(wx.Panel):
    """ A dual date/time combination widget. Not sure why wxPython doesn't
        have one.
    """
    
    def __init__(self, *args, **kwargs):
        dateStyle = kwargs.pop('dateStyle', wx.DP_DROPDOWN)
        fmt24hr = kwargs.pop('fmt24hr', True)
        super(DateTimeCtrl, self).__init__(*args, **kwargs)
            
        self.dateCtrl = wx.DatePickerCtrl(self, -1, style=dateStyle)
        self.timeCtrl = wx_mc.TimeCtrl(self, 1, fmt24hr=fmt24hr)
        timeSpin = wx.SpinButton(self, 1, style=wx.SP_VERTICAL)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.dateCtrl, 1, wx.EXPAND)
        sizer.Add(self.timeCtrl, 1, wx.EXPAND)
        sizer.Add(timeSpin, -1, wx.EXPAND)
        self.SetSizer(sizer)
        self.timeCtrl.BindSpinButton(timeSpin)
        
        
    def SetValue(self, value):
        """ Set the value from a `wx.DateTime` object.
        """
        self.dateCtrl.SetValue(value)
        self.timeCtrl.ChangeValue(value)


    def GetValue(self):
        """ Get the value as a `wx.DateTime` object.
        """
        t = _datetime.strptime(self.timeCtrl.GetValue(), '%H:%M:%S')
        dt = self.dateCtrl.GetValue()
        dt.SetHour(t.hour)
        dt.SetMinute(t.minute)
        dt.SetSecond(t.second)
        return dt

    
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
    numFields = 7
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments, plus:
        
            @keyword root: The viewer's 'root' window.
        """
        self.root = kwargs.pop('root', None)
        wx.StatusBar.__init__(self, *args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        
        logo = _images.MideLogo.GetBitmap()
        self.logo = wx.StaticBitmap(self, -1, logo)

        self.progressBar = wx.Gauge(self, -1, 1000)
        self.cancelButton = wx.Button(self, wx.ID_CANCEL, style=wx.BU_EXACTFIT)
        bwidth, bheight = self.cancelButton.GetBestSize()
        self.buttonWidth = bwidth + 2
        self.cancelButton.SetSize((bwidth, bheight-4))

        fieldWidths = [-1] * self.numFields

        self.buttonFieldNum = self.numFields-1
        self.progressFieldNum = self.numFields-2
        self.messageFieldNum = self.numFields-3
        self.warnFieldNum = self.numFields-4
        self.yFieldNum = 2
        self.xFieldNum = 1
        self.logoFieldNum = 0

        fieldWidths[self.logoFieldNum] = logo.GetSize()[0]
        fieldWidths[self.messageFieldNum] = -4
        fieldWidths[self.warnFieldNum] = -4
        fieldWidths[self.progressFieldNum] = -2
        fieldWidths[self.buttonFieldNum] = bwidth

        self.SetFieldsCount(self.numFields)
        self.SetStatusWidths(fieldWidths)

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
# Automatically build list of things for 'from base import *'
#===============================================================================

if __name__ in _sys.modules:
    _moduleDict = _sys.modules[__name__].__dict__
else:
    _moduleDict = globals()

__all__ = filter(lambda x: not(x.startswith("_") or x.startswith('wx')),
                 _moduleDict.keys())

del _moduleDict