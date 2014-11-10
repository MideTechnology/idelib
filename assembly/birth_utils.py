'''
Functions and stuff used by multiple parts of the birthing/calibration
process.

Created on Nov 7, 2014

@author: dstokes
'''

import os
import shutil
import sys
import time

from devices import SlamStickX
import ssx_namer

#===============================================================================
# 
#===============================================================================

def inRange(v, minVal, maxVal):
    return v >= minVal and v <= maxVal

#===============================================================================
# 
#===============================================================================

def changeFilename(filename, ext=None, path=None):
    """ Modify the path or extension of a filename. 
    """
    if ext is not None:
        ext = ext.lstrip('.')
        filename = "%s.%s" % (os.path.splitext(filename)[0], ext)
    if path is not None:
        filename = os.path.join(path, os.path.basename(filename))
    return os.path.abspath(filename)


def readFileLine(filename, dataType=None, fail=True, last=True, default=None):
    """ Open a file and read a single line.
        @param filename: The full path and name of the file to read.
        @keyword dataType: The type to which to cast the data. Defaults to int.
        @keyword fail: If `False`, failures to cast the read data returns the
            raw string.
    """
    ex = ValueError if fail else None
    with open(filename, 'r') as f:
        if last:
            for l in f:
                l = l.strip()
                if len(l) > 0:
                    d = l
        else:
            d = f.readline().strip()
    try:
        if dataType is None:
            return int(float(d))
        return dataType(d)
    except ex:
        return d

def writeFileLine(filename, val, mode='w', newline=True):
    """ Open a file and write a line. """
    with open(filename, mode) as f:
        s = str(val)
        if newline and not s.endswith('\n'):
            s += "\n"
        return f.write(s)


def readFile(filename):
    with open(filename,'rb') as f:
        return f.read()

def writeFile(filename, data):
    with open(filename, 'wb') as f:
        if isinstance(data, basestring):
            f.write(data)
        else:
            f.write(str(data))
            
#===============================================================================
# 
#===============================================================================

def readBirthLog(filename):
    """
    """
    l = readFileLine(filename, str, last=True)
    sp = l.split(',')
    fields = (
        ('birthday', str),
        ('timestamp', int),
        ('chipId', str),
        ('serialNum', int),
        ('rebirth', lambda x: True if int(x) else False),
        ('bootVer', str),
        ('hwRev', int),
        ('fwRev', int),
        ('accelSerialNum', str),
        ('partNum', str)
    )
    result = dict()
    for val, field in zip(sp, fields):
        fname, ftype = field
        result[fname] = ftype(val.strip())
    return result


#===============================================================================
# 
#===============================================================================

class SpinnyCallback(object):
    FRAMES = "|/-\\"
    INTERVAL = 0.125
    
    def __init__(self, *args, **kwargs):
        self.frames = kwargs.pop('frames', self.FRAMES)
        self.spinIdx = 0
        self.clear = '\x08' * len(self.frames[0])
        self.cancelled = False
        self.nextTime = time.time() + self.INTERVAL
    
    def update(self, *args, **kwargs):
        if time.time() < self.nextTime:
            return
        sys.stdout.write("%s%s" % (self.frames[self.spinIdx], self.clear))
        sys.stdout.flush()
        self.spinIdx = (self.spinIdx + 1) % len(self.frames)
        self.nextTime = time.time() + self.INTERVAL

spinner = SpinnyCallback()
cylon = SpinnyCallback(frames=["----","*---","-*--","--*-", "---*"])

#===============================================================================
# 
#===============================================================================

def waitForSSX(onlyNew=False, timeout=60, callback=spinner):
    if onlyNew:
        excluded_drives = set(ssx_namer.getAllDrives())
    else:
        xd = []
        for d in ssx_namer.getAllDrives():
            if SlamStickX.isRecorder(d):
                return d
            xd.append(d)
        excluded_drives = set(xd)
    ssx_namer.deviceChanged()

    deadline = time.time() + timeout if timeout else None
    print excluded_drives
    while True:
        if ssx_namer.deviceChanged():
            vols = set(ssx_namer.getCurrentDrives()) - excluded_drives
            for v in vols:
                if SlamStickX.isRecorder(v):
                    return v
        
        time.sleep(.125)
        if callback:
            callback.update()
        
        if timeout and deadline < time.time():
            return False
    

#===============================================================================
# 
#===============================================================================

def copyFileTo(source, destPath):
    dest = changeFilename(source, path=destPath)
    if os.path.exists(dest):
        os.remove(dest)
    shutil.copy(source, dest)
    return dest
