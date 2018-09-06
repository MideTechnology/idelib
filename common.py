'''
Small utility functions, 'constants', and such, used by multiple files. 

@author: dstokes

@todo: Some of these aren't used; identify and refactor/remove at some point.
'''

from datetime import datetime
import os.path
import shutil
import sys
from threading import Thread as Thread


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


def constrain(x, minVal, maxVal):
    """ Return a value within a given range. Values outside the given range
        will produce the specified minimum or maximum, respectively.
        Functionally equivalent to ``min(maxVal, max(x, minVal))`` but much
        faster.
    """
    if x < minVal:
        return minVal
    elif x > maxVal:
        return maxVal
    else:
        return x


def lesser(x, y):
    """ Return the lesser of two values. Faster than ``min()`` for only two
        values. Note: does not work like ``min()`` with sequences!
    """
    return x if x < y else y


def greater(x, y):
    """ Return the greater of two values. Faster than ``max()`` for only two
        values. Note: does not work like ``max()`` with sequences!
    """
    return x if x > y else y



#===============================================================================
# Formatting and parsing helpers
#===============================================================================

def multiReplace(s, *replacements):
    """ Perform multiple substring replacements, provided as one or more 
        two-item tuples containing pairs of old and new substrings.
    """
    for old, new in replacements:
        s = s.replace(old, new)
    return s


def sanitizeFilename(f, ascii=True, keepPaths=True):
    """ A blunt instrument for coercing filenames into validity.
    """
    if not isinstance(f, unicode):
        f = unicode(f)
    if keepPaths:
        path, name = os.path.split(f)
    else:
        path, name = "", f
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
            return u"%s, %s %s" % (', '.join(words[:-1]), conj, words[-1])
        else:
            return u"%s %s %s" % (', '.join(words[:-1]), conj, words[-1])
    else:
        return (u" %s " % conj).join(words)


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


#===============================================================================
# 
#===============================================================================

def makeBackup(filename):
    """ Create a backup copy of the given file. For use in conjunction with
        `restoreBackup()`.
        
        @param filename: The name of the original file.
        @return: `True` if successful, `False` if not (e.g. the original file
            does not exist).
    """
    backupFilename = filename + "~"
    if os.path.exists(filename):
        shutil.copy(filename, backupFilename)
        return True
    return False


def restoreBackup(filename):
    """ Restore a backup copy of a file, overwriting the file. For use in 
        conjunction with `makeBackup()`.
        
        @param filename: The name of the original file.
        @return: `True` if successful, `False` if not (e.g. the backup file
            does not exist).
    """
    backupFilename = filename + "~"
    if os.path.exists(backupFilename):
        shutil.copy(backupFilename, filename)
        return True
    return False


def removeBackup(filename):
    """ Delete the backup of the given filename, if it exists. For use in 
        conjunction with `makeBackup()`, e.g. after saving a file was 
        successful.
        
        @param filename: The name of the original file.
        @return: `True` if successful, `False` if not (e.g. the backup file
            does not exist).
    """
    backupFilename = filename + "~"
    try:
        os.remove(backupFilename)
        return True
    except (IOError, WindowsError):
        return False
            
#===============================================================================
# 
#===============================================================================

def getAppPath():
    """ Get the application's home directory.
    """
    if getattr(sys, 'frozen', False):
        # 'Compiled' executable
        return os.path.dirname(sys.executable)
    
    return os.path.dirname(os.path.abspath(__file__))


#===============================================================================
# 
#===============================================================================

def inRect(x, y, rect):
    """ Does a point fall within the specified rectangle?
    
        @param x: Point X coordinate.
        @param y: Point Y coordinate.
        @param rect: A four-item list/tuple containing the coordinates of the
            rectangle's upper left corner and its width/height.
    """
    if rect is None:
        return False
    if x < rect[0] or y < rect[1]:
        return False
    if x > rect[0]+rect[2] or y > rect[1]+rect[3]:
        return False
    return True


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
