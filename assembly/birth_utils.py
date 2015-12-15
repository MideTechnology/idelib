'''
Functions and stuff used by multiple parts of the birthing/calibration
process.

Created on Nov 7, 2014

@author: dstokes
'''

from collections import OrderedDict
import os
import shutil
import sys
import time
from xml.etree import ElementTree as ET

from win32com.client import Dispatch

import devices
import ssx_namer

#===============================================================================
# 
#===============================================================================

def inRange(v, minVal, maxVal):
    return v >= minVal and v <= maxVal


def allInRange(vals, minVal, maxVal):
    return all((inRange(x, minVal, maxVal) for x in vals))

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


def readFileLine(filename, dataType=None, fail=False, last=True, default=None):
    """ Open a file and read a single line.
        @param filename: The full path and name of the file to read.
        @keyword dataType: The type to which to cast the data. Defaults to int.
        @keyword fail: If `False`, failures to cast the read data returns the
            raw string.
    """
    ex = ValueError if fail else None
    try:
        with open(filename, 'r') as f:
            if last:
                for l in f:
                    l = l.strip()
                    if len(l) > 0:
                        d = l
            else:
                d = f.readline().strip()
        if len(d) == 0:
            return default
        try:
            if dataType is None:
                return int(float(d))
            return dataType(d)
        except ex:
            return d
    except IOError:
        return default


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

def parseBirthLog(l):
    """
    """
    sp = l.strip().split(',')
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
    result = OrderedDict()
    for val, field in zip(sp, fields):
        fname, ftype = field
        val = ftype(val.strip())
        val = None if val == 'None' else val
        result[fname] = val
    return result


def readBirthLog(filename):
    return parseBirthLog(readFileLine(filename, str, last=True))


def findBirthLog(filename, key="serialNum", val=None, last=True):
    result = None
    with open(filename, 'rb') as f:
        for l in f:
            try:
                line = parseBirthLog(l)
            except (ValueError, IOError):
                continue
            if line:
                if line[key] == val:
                    result = line
                    if not last:
                        break
    return result

#===============================================================================
# 
#===============================================================================

def parseCalLog(l):
    if l is None:
        return None
    sp = l.strip().split(',')
    fields = (('Cal #',             int),
              ('Rev',               str),
              ('Cal Date',          str),
              ('Serial #',          str),
              ('Hardware',          int),
              ('Firmware',          int),
              ('Product Name',      str),
              ('Part Number',       str),
              ('Date of Manufacture', str),
              ('Ref Manufacturer',  str),
              ('Ref Model #',       str),
              ('Ref Serial #',      str),
              ('NIST #',            str),
              ('832M1 Serial #',    str),
              ('Temp. (C)',         float),
              ('Rel. Hum. (%)',     float),
              ('Temp Comp. (%/C)',  float),
              ('X-Axis',            float),
              ('Y-Axis',            float),
              ('Z-Axis',            float),
              ('Pressure (Pa)',     float),
              ("X-Axis (DC)",       float),
              ("Y-Axis (DC)",       float),
              ("Z-Axis (DC)",       float),
              ("X Offset (DC)",     float),
              ("Y Offset (DC)",     float),
              ("Z Offset (DC)",     float))
    
    result = OrderedDict()
    for val, field in zip(sp, fields):
        fname, ftype = field
        try:
            val = ftype(val.strip())
        except (TypeError, ValueError):
            if val == '' and ftype != str:
                val = None
        val = None if val == 'None' else val
        result[fname] = val
    return result


def readCalLog(filename):
    return parseCalLog(readFileLine(filename, str, last=True))


def findCalLog(filename, key="Serial #", val=None, last=True):
    result = None
    with open(filename, 'rb') as f:
        for l in f:
            try:
                line = parseCalLog(l)
            except (ValueError, IOError):
                continue
            if line:
                if line[key] == val:
                    result = line
                    if not last:
                        break
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

def waitForSSX(onlyNew=False, timeout=60, callback=spinner, strict=False):
    if onlyNew:
        excluded_drives = set(ssx_namer.getAllDrives())
    else:
        xd = []
        for d in ssx_namer.getAllDrives():
            if devices.SlamStickX.isRecorder(d, strict=strict):
                return d
            xd.append(d)
        excluded_drives = set(xd)
    ssx_namer.deviceChanged()

    deadline = time.time() + timeout if timeout else None
#     print excluded_drives
    while True:
        if ssx_namer.deviceChanged():
            vols = set(ssx_namer.getCurrentDrives()) - excluded_drives
            for v in vols:
                if devices.SlamStickX.isRecorder(v, strict=strict):
                    return v
        
        time.sleep(.125)
        if callback:
            callback.update()
        
        if timeout and deadline < time.time():
            return False
    

def waitForRecorder(onlyNew=False, timeout=60, callback=spinner):
    """
    """
    if onlyNew:
        excluded_drives = set(ssx_namer.getAllDrives())
        ssx_namer.deviceChanged()
    else:
        excluded_drives = set()

    deadline = time.time() + timeout if timeout else None
    while True:
        if ssx_namer.deviceChanged():
            devs = devices.getDevices(list(set(devices.getDeviceList()) - excluded_drives))
            if len(devs) > 0:
                return devs[0]
            
        time.sleep(.125)
        if callback:
            callback.update()
        
        if timeout and deadline < time.time():
            return False

#===============================================================================
# 
#===============================================================================

def copyFileTo(source, destPath):
    if not os.path.exists(source):
        raise IOError("No such file/directory: %r" % source)
    dest = changeFilename(source, path=destPath)
    if os.path.exists(dest):
        os.remove(dest)
    shutil.copy(source, dest)
    return dest

def copyTreeTo(source, dest):
    if not os.path.exists(source):
        raise IOError("No such file/directory: %r" % source)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    return dest

    

#===============================================================================
# 
#===============================================================================

def getYesNo(prompt, default=None):
    """ Prompt user for a yes-or-no answer. """
    q = ''
    while q not in ('Y','N'):
        q = raw_input(prompt).strip().upper()
        if len(q) == 0 and default is not None:
            return default
        q = q[0]
    return q

def getNumber(prompt, dataType=float, default=None, minmax=None):
    """ Prompt user for a number. """
    while True:
        try:
            q = raw_input(prompt).strip()
            if q == '':
                if default is not None:
                    return default
                continue
            val = dataType(q)
            if minmax is not None and not inRange(val, *minmax):
                print "Enter a value between %s and %s." % minmax
            else:
                return val
        except ValueError as err:
            print str(err).capitalize()
            
#===============================================================================
# 
#===============================================================================

def errMsg(*msg):
    print "\x07\x07\x07%s" % '\n'.join(map(str,msg))
    raw_input("Press enter to continue.")
    
#===============================================================================
# 
#===============================================================================

def makeShortcut(path, target):
    """ Create a Windows Shortcut.
    """
    scName = os.path.realpath(os.path.join(path, os.path.basename(target)+".lnk"))
    shell = Dispatch("WScript.Shell")
    sc = shell.CreateShortcut(scName)
    sc.Targetpath = os.path.realpath(target)
    sc.save()
    return scName


#===============================================================================
# 
#===============================================================================

def hasAnalogAccel(templatePath, partNum, hwRev):
    """
    """
    template = os.path.join(templatePath, partNum, str(hwRev), 'manifest.template.xml')
    doc = ET.parse(template)
    return doc.find('./AnalogSensorInfo/AnalogSensorSerialNumber') is not None

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    print "This is only a library. Don't try to run it!"
    exit(1)