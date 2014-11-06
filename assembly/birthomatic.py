'''
Here's how it should work:

PHASE 1: Before calibration
    1. Wait for an SSX in firmware mode (getSSXSerial)
   *2. Prompt user for part number, hardware revision number, accelerometer SN
    3. Get next recorder serial number
    4. Get bootloader version, chip ID from device
    5. Create chip ID directory in product_database
    6. Generate manifest and generic calibration list for model
    7. Upload firmware, user page data (firmware.ssx_bootloadable_device)
    8. Update birth log
    9. Reset device, immediately start autoRename
    10. Set recorder clock
    11. Copy documentation and software folders
   *n. Notify user that recorder is ready for potting/calibration

PHASE 2: Offline work
    x. Potting, assembly, recording shaker sessions.

PHASE 3: Post-Calibration 
    1. Wait for an SSX in drive mode (see ssx_namer)
    2. Read device info to get serial number.
    2. Create serial number directory in product_database/_Calibration
    3. Generate calibration data from IDE files on recorder (see calibration.py)
    4. Generate calibration certificate
    5. Copy calibration certificate to device
   *6. Prompt user to enter bootloader mode
    7. Wait for an SSX in firmware mode (getSSXSerial)
    8. Upload new manifest/calibration to user page.
    9. Reset device
   *n. Tell user the device is ready.


Created on Sep 24, 2014

@author: dstokes
'''

from glob import glob
import os.path
import shutil
import string
import sys
import time
from xml.etree import ElementTree as ET
import xml.dom.minidom as minidom

import numpy as np
import serial.tools.list_ports
import serial

import ssx_namer
import firmware
from assembly.firmware import getSSXSerial

#===============================================================================
# 
#===============================================================================

RECORDER_NAME = "SlamStick X"

PRODUCT_ROOT_PATH = "R:/LOG-Data_Loggers/LOG-0002_Slam_Stick_X/"
BIRTHER_PATH = os.path.join(PRODUCT_ROOT_PATH, "Design_Files/Firmware_and_Software/Manufacturing/LOG-XXXX-SlamStickX_Birther/")
FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "firmware")
TEMPLATE_PATH = os.path.join(BIRTHER_PATH, "data_templates")
DB_PATH = os.path.join(PRODUCT_ROOT_PATH, "Product_Database")
CAL_PATH = os.path.join(DB_PATH, '_Calibration')

BIRTH_LOG_NAME = "product_log.csv"
CAL_LOG_NAME = "calibration_log.csv"

BOOT_FILE = os.path.join(FIRMWARE_PATH, "boot.bin")
BOOT_VER_FILE = os.path.join(FIRMWARE_PATH, "boot_version.txt")
APP_FILE = os.path.join(FIRMWARE_PATH, "app.bin")
APP_VER_FILE = os.path.join(FIRMWARE_PATH, "app_version.txt")

CONTENT_PATH = os.path.join(DB_PATH, '_Copy_Folder')

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
from mide_ebml import xml2ebml


#===============================================================================
# 
#===============================================================================

class SpinnyCallback(object):
    FRAMES = "|/-\\"
    INTERVAL = 0.125
    
    def __init__(self, *args, **kwargs):
        self.frames = kwargs.pop('frames', self.FRAMES)
        self.spinIdx = 0
        self.clear = '\x0d' * len(self.frames[0])
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

def getSSXSerial(block=False, timeout=30, delay=.25, callback=spinner):
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
            if callback:
                callback.update()
        
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

def readFileLine(filename, dataType=None, fail=True, last=True):
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


#===============================================================================
# 
#===============================================================================


def autoRename(newName=RECORDER_NAME, timeout=60, callback=spinner, quiet=True):
    """ Wait for the first SSX in disk mode to appear and change its name.
    """
    excluded_drives = set(ssx_namer.getAllDrives())
    ssx_namer.deviceChanged()

    deadline = time.time() + timeout if timeout else None
    beep = '' if quiet else '\x07'
    
    while True:
        if ssx_namer.deviceChanged():
            vols = set(ssx_namer.getCurrentDrives()) - excluded_drives
            for v in vols:
                info = ssx_namer.getDriveInfo(v)
                if not info or 'FAT' not in info[-2].upper():
                    print "... Ignoring non-FAT drive %s..." % v
                    continue
                if os.system('label %s %s' % (v.strip("\\"), newName)) == 0:
                    print "%s*** Renamed %s from %s to %s" % (beep, v, info[1], newName)
                    return v
                else:
                    print "%s%s!!! Failed to rename drive %s (labeled %r)!" % (beep, beep, v, info[1])
                    return False
        
        time.sleep(.125)
        if callback:
            callback.update()
        
        if timeout and deadline < time.time():
            print "%s%s!!! Timed out waiting for a recorder (%s sec.)!" % (beep, beep, timeout)
            return False


def makeBirthLogEntry(chipid, device_sn, rebirth, bootver, hwrev, fwrev, device_accel_sn, partnum):
    """
    """
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
    return ','.join(data)+'\n'

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
        result[fname] = ftype(val)
    return result


def makeManifestXml(partNum, hwRev, device_sn, device_accel_sn, dest):
    """
    """
    filename = os.path.join(TEMPLATE_PATH, partNum, str(hwRev), "manifest.template.xml")
    xmltree = ET.parse(filename)
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
    xmlroot.write(dest)
    return xmlroot


def makeCalTemplateXml(partNum, hwRev, dest):
    filename = os.path.join(TEMPLATE_PATH, partNum, str(hwRev), "cal.template.xml")
    shutil.copy(filename, dest)

#===============================================================================
# 
#===============================================================================

def getPartNumber():
    dirs = map(os.path.basename, glob(os.path.join(TEMPLATE_PATH, "LOG*")))
    print "Select a part number:"
    for i in range(len(dirs)):
        print "  %d: %s" % (i, dirs[i])
    p = raw_input("Part number? ")
    try:
        return dirs[int(p)]
    except TypeError:
        return None
    
def getHardwareRev(partNum):
    dirs = map(os.path.basename, glob(os.path.join(TEMPLATE_PATH, partNum, '*')))
    if len(dirs) == 1:
        return int(dirs[0])
    p = raw_input("Hardware revision number (%s; default=%s)? " % (', '.join(dirs),dirs[-1])).strip()
    if p == "":
        p = dirs[-1]
    try:
        return int(p)
    except TypeError:
        return None

def getFirmwareRev(partNum):
    return readFileLine(APP_VER_FILE)

def getAccelSerialNum():
    return raw_input("Accelerometer serial number? ")

def getCopyFiles(partNum):
    return filter(lambda x: not (x.startswith('.') or x == "Thumbs.db"), 
                  glob(os.path.join(CONTENT_PATH, '*')))

def getFirmwareFile(partNum, fwRev):
    return APP_FILE
    
#===============================================================================
# 
#===============================================================================

def birth(serialNum=None):
    """
    """
    rebirth = serialNum is not None
    
    # 1. Wait for an SSX in firmware mode (getSSXSerial)
    print "Waiting for an SSX in bootloader mode. Plug one in and press the button."
    sp = getSSXSerial(timeout=None)
    if sp is None:
        return
    ssxboot = firmware.ssx_bootloadable_device(sp)
    print "Connected to SSX bootloader via %s" % sp
    print
    
    # 2. Prompt user for part number, hardware revision number, firmware rev.
    partNum = getPartNumber()
    if partNum is None:
        return
    hwRev = getHardwareRev(partNum)
    if hwRev is None:
        return
    
    accelSerialNum = getAccelSerialNum()
    if not accelSerialNum:
        return
    
    fwRev = getFirmwareRev(partNum)
    if not isinstance(fwRev, int):
        return
    
    # 3. Get next recorder serial number
    if serialNum is None:
        serialNum = readFileLine(os.path.join(DB_PATH, "last_sn.txt"))
    elif isinstance(serialNum, basestring):
        # In case the serial number is the print version ("SSXxxxxxxx")
        serialNum = int(serialNum.strip(string.ascii_letters + string.punctuation + string.whitespace))
    
    serialNumStr = "SSX%07d" % serialNum
    
    # 4. Get bootloader version, chip ID from device
    bootVer, chipId = ssxboot.getVersionAndId()
    if bootVer is None or chipId is None:
        return
    
    # 5. Create chip ID directory in product_database
    chipDirName = os.path.realpath(os.path.join(DB_PATH, chipId))
    if not os.path.exists(chipDirName):
        os.mkdir(chipDirName)
    
    calDirName = os.path.realpath(os.path.join(CAL_PATH, serialNumStr))
    if not os.path.exists(calDirName):
        os.mkdir(calDirName)
    
    # 6. Generate manifest and generic calibration list for model
    manXmlFile = os.path.join(chipDirName, 'manifest.xml')
    makeManifestXml(partNum, hwRev, serialNum, accelSerialNum, manXmlFile)
    manEbml = xml2ebml.readXml(manXmlFile, schema='mide_ebml.ebml.schema.manifest')
    with open(changeFilename(manXmlFile, ext="ebml"), 'wb') as f:
        f.write(manEbml)

    calXmlFile = os.path.join(chipDirName, 'cal.template.xml')
    makeCalTemplateXml(partNum, hwRev, calXmlFile)
    calEbml = xml2ebml.readXml(calXmlFile) 
    with open(changeFilename(calXmlFile, ext="ebml"), 'wb') as f:
        f.write(calEbml)
    
    # 7. Upload firmware, user page data (firmware.ssx_bootloadable_device)
    print "Uploading firmware version %s..." % fwRev
    ssxboot.send_app(getFirmwareFile(partNum, fwRev))
    print "Uploading manifest and generic calibration data..."
    ssxboot.sendUserpage(manEbml, calEbml)
    
    # 8. Update birth log
    logline = makeBirthLogEntry(chipId, serialNum, rebirth, bootVer, hwRev, fwRev, accelSerialNum, partNum)
    writeFileLine(os.path.join(DB_PATH, BIRTH_LOG_NAME), logline, mode='at')
    writeFileLine(os.path.join(calDirName, 'birth_log.txt'))
    
    # 9. Reset device, immediately start autoRename
    print "Exiting bootloader and attempting to auto-rename..."
    ssxboot.disconnect()
    devPath = autoRename(timeout=None)
    if not devPath:
        return
    
    # 10. Set recorder clock
    print "Setting device clock..."
    SlamStickX(devPath).setTime()
    
    # 11. Copy documentation and software folders
    print "Copying content to device..."
    for c in getCopyFiles(partNum):
        print "\t%s" % c
        dest = os.path.join(devPath, os.path.basename(c))
        shutil.copytree(c, dest, ignore=shutil.ignore_patterns('.*','Thumbs.db'))
    
    # n. Notify user that recorder is ready for potting/calibration
    print "*" * 60
    print "\x07Slam Stick X SN:%s ready for calibration and potting!" % (serialNumStr)
    print "       Part Number:", partNum
    print "       Hardware ID:", chipId
    print "  Accelerometer SN:", accelSerialNum
    print "Please disconnect it now."
        
        