'''
Custom events, controls, dialogs, 'constants', functions, and other things 
used by multiple files. 

Created on Dec 31, 2013

@todo: Rewrite the whole date/time conversion stuff to be more time zone
    friendly. It's kind of a mess.

@author: dstokes
'''

import calendar as calendar
from datetime import datetime
import os.path
from threading import Thread as Thread

import wx

#===============================================================================
# Numeric and math-related helper functions
#===============================================================================

def expandRange(l, *vals):
    """ Given a two element list containing a minimum and maximum value, 
        expand it if the given value is outside that range. 
    """
    l[0] = min(l[0], *vals)
    l[1] = max(l[1], *vals)


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
    
    # Kind of a hack, but it's fast (the 'right' way uses slow bit shifting).
    return 2L**(len(bin(x))-2L)


#===============================================================================
# Formatting and parsing helpers
#===============================================================================

def multiReplace(s, *replacements):
    """
    """
    for old, new in replacements:
        s = s.replace(old, new)
    return s


def sanitizeFilename(f, ascii=True):
    """ A blunt instrument for coercing filenames into validity.
    """
    if not isinstance(f, unicode):
        f = unicode(f)
    path, name = os.path.split(f)
    if ascii:
        name = name.encode('ascii','replace')
    f = ''.join((x for x in f if ord(x) > 31))
    for c in """*?!;&$/\\:"', """:
        name = name.replace(c, '_')
    while '__' in f:
        name = name.replace('__','_')
    return os.path.join(path,name)


def cleanUnicode(obj, encoding='utf8', errors='replace'):
    """ Helper function to produce valid unicode text. Apps built with
        PyInstaller (under Windows) can choke on unicode conversions.
    """
    if isinstance(obj, unicode):
        return obj
    try:
        if isinstance(obj, str):
            return unicode(obj, encoding, errors)
        return unicode(obj)
    except (UnicodeDecodeError, TypeError):
        return repr(obj)


# def hex32(val):
#     """ Format an integer as an 8 digit hex number. """
#     return "0x%08x" % val

# def hex16(val):
#     """ Format an integer as an 4 digit hex number. """
#     return "0x%04x" % val

# def hex8(val):
#     """ Format an integer as a 2 digit hex number. """
#     return "0x%02x" % val

# def str2int(val):
#     """ Semi-smart conversion of string to integer; works for decimal and hex.
#     """
#     try:
#         return int(val)
#     except ValueError:
#         return int(val, 16)


def datetime2int(val, tzOffset=0):
    """ Convert a date/time object (either a standard Python datetime.datetime
        or wx.DateTime) into the UTC epoch time (i.e. UNIX time stamp).
    """
    if isinstance(val, wx.DateTime):
        return val.Ticks + tzOffset
#         val = datetime.strptime(str(val), '%m/%d/%y %H:%M:%S')
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
    if isinstance(val, (int, float)):
        return wx.DateTimeFromTimeT(float(val))
    elif isinstance(val, wx.DateTime):
        return wx.DateTimeFromDateTime(val)
    # Assume a struct_time or other sequence:
    return wx.DateTimeFromDMY(val[2], val[1]-1, val[0], val[3], val[4], val[5])
        

def parseTime(val):
    """ Convert a time entered in SMPTE-like format (seconds, M:S, or H:M:S)
        to seconds. Fractional values accepted.
    """
    result = 0
    mult = 1
    for p in reversed(str(val).strip().split(':')):
        try:
            result += float(p.strip()) * mult
        except ValueError:
            return None
        mult *= 60
    return result


def wordJoin(words, conj="and", oxford=True):
    """ Function to do an English joining of list items.
        @param words: A list (or other iterable) of items. Items will be cast
            to Unicode.
        @keyword conj: The conjunction to use, e.g. ``and`` or ``or``.
        @keyword oxford: If `True`, insert a comma after the penultimate word,
            if ``words`` contains three or more items.
    """
    words = map(cleanUnicode, words)
    numWords = len(words)
    if numWords > 2:
        if oxford:
            return "%s, %s %s" % (', '.join(words[:-1]), conj, words[-1])
        else:
            return "%s %s %s" % (', '.join(words[:-1]), conj, words[-1])
    else:
        return (" %s " % conj).join(words)


#===============================================================================
# 
#===============================================================================

def inRect(x, y, rect):
    if rect is None:
        return False
    if x < rect[0] or y < rect[1]:
        return False
    if x > rect[0]+rect[2] or y > rect[1]+rect[3]:
        return False
    return True


#===============================================================================
# Field validators
#===============================================================================

class TimeValidator(wx.PyValidator):
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


#===============================================================================
# 
#===============================================================================

class Job(Thread):
    """ A base class for background task threads. Adds a few viewer-specific
        features to the standard `threading.Thread` class.
        
        @cvar modal: Does this job take full control until it completes?
        @cvar cancelPrompt: Does canceling this job prompt the user first?
        @cvar cancelMessage: The text in the cancel dialog, if any.
        @cvar cancelTitle: The title of the cancel dialog, if any.
        @cvar cancelPromptPref: The name of the preference that suppresses the
            appearance of the cancel dialog (if applicable).
        @cvar cancelResponse: The message displayed in the status bar if the
            job is cancelled.
    """
    
    modal = False
    cancelPrompt = True
    cancelMessage = "Are you sure you want to cancel?"
    cancelTitle = "Cancel Operation"
    cancelPromptPref = None
    cancelResponse = "Cancelled."

    def __init__(self, root=None, dataset=None, numUpdates=100, 
                 updateInterval=1.0):
        """ Constructor.
            
            @param root: The Viewer.
            @param dataset: The Dataset being loaded, if applicable.
            @keyword numUpdates: The minimum number of calls to the updater to
                be made. There will be more than this number of updates if
                any takes longer than the specified `updateInterval` (below).
            @keyword updateInterval: The maximum number of seconds between
                calls to the updater
        """
        self.root = root
        self.dataset = dataset
        self.numUpdates = numUpdates
        self.updateInterval = updateInterval
        self.cancelled = False
        self.paused = False
        self.startTime = self.lastTime = self.pauseTime = None
        self.totalPauseTime = None
        self.pausable = True

        super(Job, self).__init__()


    def cancel(self, blocking=True):
        """ Attempt to abort the job. Note that subclasses must implement their
            `run()` methods to honor the `canceled` variable; this is more a
            suggestion to cancel than a command.
            
            @keyword blocking: If `True`, this method will not return until it
                is sure its thread has been stopped.
        """
        self.cancelled = True
        if blocking:
            while self.isAlive():
                pass
        return self.cancelled


    def pause(self, pause=True):
        self.paused = pause and self.pausable
        if pause:
            self.pauseTime = datetime.now()
        elif self.pauseTime is not None:
            pt = datetime.now() - self.pauseTime
            if self.totalPauseTime is None:
                self.totalPauseTime = pt
            else:
                self.totalPauseTime += pt
        return True
