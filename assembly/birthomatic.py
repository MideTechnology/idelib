'''
Here's how it should work:

PHASE 1: Before calibration
    1. Wait for an SSX in firmware mode (getSSXSerial)
    2. Upload firmware, user page data (firmware.ssx_bootloadable_device)
    3. Reset device, immediately start autoRename
    4. Set recorder clock
    5. Copy documentation and software folders

PHASE 2: Post-Calibration (TBD. Manual for now.)
    1. Wait for an SSX in drive mode (see ssx_namer)
    2. Generate CSV from IDE
    X. TBD, currently MATLAB stuff.


    



Created on Sep 24, 2014

@author: dstokes
'''

import os.path
import sys
import time
from xml.etree import ElementTree as ET
import xml.dom.minidom as minidom

import numpy as np
import serial.tools.list_ports
import serial

import ssx_namer
import firmware

#===============================================================================
# 
#===============================================================================

RECORDER_NAME = "SlamStick X"

PRODUCT_ROOT_PATH = "R:/LOG-Data_Loggers/LOG-0002_Slam_Stick_X/"
BIRTHER_PATH = os.path.join(PRODUCT_ROOT_PATH, "Design_Files/Firmware_and_Software/Manufacturing/LOG-XXXX-SlamStickX_Birther/")
FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "/firmware")
SOURCE_DATA_PATH = os.path.join(BIRTHER_PATH, "/data_templates")
DB_PATH = os.path.join(PRODUCT_ROOT_PATH, "/Product_Database")

BIRTH_LOG_NAME = "product_log.csv"
CAL_LOG_NAME = "calibration_log.csv"

BOOT_FILE = os.path.join(FIRMWARE_PATH, "boot.bin")
BOOT_VER_FILE = os.path.join(FIRMWARE_PATH, "boot_version.txt")
APP_FILE = os.path.join(FIRMWARE_PATH, "app.bin")
APP_VER_FILE = os.path.join(FIRMWARE_PATH, "app_version.txt")


#===============================================================================
# Rigamarole to ensure the right libraries are located.
#===============================================================================

VIEWER_PATH = "P:/WVR_RIF/04_Design/Electronic/Software/SSX_Viewer"

CWD = os.path.abspath(os.path.dirname(__file__))
sys.path.append(CWD)

try:
    import mide_ebml
except ImportError:
    if os.path.exists('../mide_ebml'):
        sys.path.append(os.path.abspath('..'))
    elif os.path.exists(os.path.join(CWD, '../mide_ebml')):
        sys.path.append(os.path.abspath(os.path.join(CWD, '../mide_ebml')))
    elif os.path.exists(VIEWER_PATH):
        sys.path.append(VIEWER_PATH)
    import mide_ebml

from mide_ebml.importer import importFile, SimpleUpdater
from devices import SlamStickX


#===============================================================================
# 
#===============================================================================

class SpinnyCallback(object):
    FRAMES = "|/-\\"
    INTERVAL = 0.125
    
    def __init__(self, *args, **kwargs):
        self.spinIdx = 0
        self.cancelled = False
        self.nextTime = time.time() + self.INTERVAL
    
    def update(self, *args, **kwargs):
        if time.time() < self.nextTime:
            return
        sys.stdout.write("%s\x0d" % self.FRAMES[self.spinIdx])
        sys.stdout.flush()
        self.spinIdx = (self.spinIdx + 1) % len(self.FRAMES)
        self.nextTime = time.time() + self.INTERVAL

spinner = SpinnyCallback()

#===============================================================================
# 
#===============================================================================

def getSSXSerial(block=False, timeout=30, delay=.5):
    """ Get the names of all serial ports connected to bootloader-mode SSX.
    """
    if block:
        if timeout is not None:
            deadline = time.time() + timeout
        while timeout is None or deadline > time.time():
            p = getSSXSerial(block=False)
            if p is not None:
                return p
            time.sleep(delay)
        return None
    
    ports = filter(lambda x: 'EFM32 USB CDC Serial' in x[1], 
                   serial.tools.list_ports.comports())
    if len(ports) > 0:
        return [x[0] for x in ports]

#===============================================================================
# Helper functions
#===============================================================================

def changeFilename(filename, ext=None, path=None):
    """ Change the path and/or extension of a filename. """
    if ext is not None:
        ext = ext.lstrip('.')
        filename = "%s.%s" % (os.path.splitext(filename)[0], ext)
    if path is not None:
        filename = os.path.join(path, os.path.basename(filename))
    return os.path.abspath(filename)

def readFileLine(filename, dataType=None, fail=True):
    """ Open a file and read a single line.
        @param filename: The full path and name of the file to read.
        @keyword dataType: The type to which to cast the data. Defaults to int.
        @keyword fail: If `False`, failures to cast the read data returns the
            raw string.
    """
    ex = ValueError if fail else None
    with open(filename, 'r') as f:
        d = f.readline()
    try:
        if dataType is None:
            return int(float(d))
        return dataType(d)
    except ex:
        return d

def writeFileLine(filename, val, mode='w'):
    """ Open a file and write a line. """
    with open(filename, mode) as f:
        return f.write(str(val))

def prettify_xml(elem):
    """Return a pretty-printed XML string for the Element.
    """
    # First clean out any element and tail text (e.g. tabs, other whitespace, 
    # linebreaks) and other materials that will confuse the pretty-printer
    for element in elem.iter("*"):
        element.text = None
        element.tail = None
            
    rough_string = ET.tostring(elem)
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="\t")

def write_pretty_xml(fname,elem):
    """Write a pretty-printed XML string to a file.
    """
    writeFileLine(fname, prettify_xml(elem), mode="wt")


#===============================================================================
# 
#===============================================================================

def autoRename(newName=RECORDER_NAME, timeout=60, callback=spinner):
    """ Wait for the first SSX in disk mode to appear and change its name.
    """
    excluded_drives = set(ssx_namer.getAllDrives())
    ssx_namer.deviceChanged()

    deadline = time.time() + timeout if timeout else None
        
    while True:
        if ssx_namer.deviceChanged():
            vols = set(ssx_namer.getCurrentDrives()) - excluded_drives
            for v in vols:
                info = ssx_namer.getDriveInfo(v)
                if not info or 'FAT' not in info[-2].upper():
                    print "... Ignoring non-FAT drive %s..." % v
                    continue
                if os.system('label %s %s' % (v.strip("\\"), newName)) == 0:
                    print "\x07*** Renamed %s from %s to %s" % (v, info[1], newName)
                    return True
                else:
                    print "\x07\x07!!! Failed to rename drive %s (labeled %r)!" % (v, info[1])
                    return False
        
        time.sleep(.125)
        if callback:
            callback.update()
        
        if timeout and deadline < time.time():
            print "\x07\x07!!! Timed out waiting for a recorder (%s sec.)!" % timeout
            return False


def writeBirthLog(filename, chipid, device_sn, rebirth, bootver, hwrev, fwrev, device_accel_sn, partnum):
    data = map(str, (time.asctime(), 
                     int(time.mktime(time.gmtime())), 
                     chipid, 
                     device_sn, 
                     int(rebirth), 
                     bootver, 
                     hwrev, 
                     fwrev, 
                     device_accel_sn, 
                     partnum))
    writeFileLine(filename, ','.join(data)+'\n', mode='at')


def makeManifestXml(templateFilename, device_sn, device_accel_sn):
    xmltree = ET.parse(templateFilename)
    xmlroot = xmltree.getroot()
    # Mostly good as-is, but need to update SerialNumber, DateOfManufacture 
    # and AnalogSensorSerialNumber. There is only one element with each name, 
    # so we can simply "find" by that name and update the value.
    el = xmlroot.find("./SystemInfo/SerialNumber")
    el.set('value', str(device_sn))
    el = xmlroot.find("./SystemInfo/DateOfManufacture")
    el.set('value', str(int(time.mktime(time.gmtime()))) )
    el = xmlroot.find("./AnalogSensorInfo/AnalogSensorSerialNumber")
    el.set('value', device_accel_sn) # already a string
    return xmlroot

def makeCalXml(templateFilename):
    pass