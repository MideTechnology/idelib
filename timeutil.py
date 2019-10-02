"""
Some utility functions and the like for handling `wxPython.DateTime` objects.

@todo: Rewrite the whole date/time conversion stuff to be more time zone
    friendly. It's kind of a mess.
"""

import calendar
from datetime import datetime
import time

import wx

#===============================================================================
# 
#===============================================================================

def datetime2int(val, tzOffset=0):
    """ Convert a date/time object (either a standard Python datetime.datetime
        or wx.DateTime) into the UTC epoch time (i.e. UNIX time stamp).
    """
    if isinstance(val, wx.DateTime):
        return val.Ticks + tzOffset
    return int(calendar.timegm(val.utctimetuple()) + tzOffset)
        

def time2int(val, tzOffset=0):
    """ Parse a time string (as returned from `TimeCtrl.GetValue()`) into
        seconds since midnight.
    """
    t = datetime.strptime(str(val), '%H:%M:%S')
    return int((t.hour * 60 * 60) + (t.minute * 60) + t.second + tzOffset)


def makeWxDateTime(val):
    """ Create a `wx.DateTime` instance from a standard `datetime`, time tuple
        (or a similar 'normal' tuple), epoch timestamp, or another 
        `wx.DateTime` object.
    """
    if isinstance(val, datetime):
        val = datetime2int(val)
    if isinstance(val, (int, long, float)):
        val = time.gmtime(val)
    elif isinstance(val, wx.DateTime):
        # XXX: Not sure this is correct for wxPython4
        # return wx.DateTimeFromDateTime(val)
        return val
    # Assume a struct_time or other sequence:
    return wx.DateTimeFromDMY(val[2], val[1]-1, val[0], val[3], val[4], val[5])
        

def getUtcOffset():
    """ Get the local offset from UTC time, in hours (float).
    """
    gt = time.gmtime()
    lt = time.localtime()
    val = (time.mktime(lt) - time.mktime(gt)) / 60.0 / 60.0
    if lt.tm_isdst == 1:
        val += 1
    return val


#===============================================================================
# Field validators
#===============================================================================

class TimeValidator(wx.Validator):
    """
    """
    validCharacters = "-.0123456789"
     
    def __init__(self):
        super(TimeValidator, self).__init__()
        self.Bind(wx.EVT_CHAR, self.OnChar)
 
    def Clone(self):
        return TimeValidator()
 
    def Validate(self, win):
        val = self.GetWindow.GetValue()
        return all((c in self.validCharacters for c in val))
 
    def OnChar(self, evt):
        key = evt.GetKeyCode()
        
        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
            evt.Skip()
            return
 
        if chr(key) in self.validCharacters:
            evt.Skip()
            return
        
#         if not wx.Validator_IsSilent():
#             wx.Bell()
        return        


