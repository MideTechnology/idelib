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
import csv
from datetime import datetime
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

#===============================================================================
# 
#===============================================================================

RECORDER_NAME = "SlamStick X"

PRODUCT_ROOT_PATH = "R:/LOG-Data_Loggers/LOG-0002_Slam_Stick_X/"
BIRTHER_PATH = os.path.join(PRODUCT_ROOT_PATH, "Design_Files/Firmware_and_Software/Manufacturing/LOG-XXXX-SlamStickX_Birther/")

# XXX: TESTING: REMOVE LATER
PRODUCT_ROOT_PATH = r"C:\Users\dstokes\workspace\SSXViewer\assembly\temp"

FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "firmware")
TEMPLATE_PATH = os.path.join(BIRTHER_PATH, "data_templates")
DB_PATH = os.path.join(PRODUCT_ROOT_PATH, "Product_Database")
CAL_PATH = os.path.join(DB_PATH, '_Calibration')

BIRTH_LOG_NAME = "product_log.csv"
CAL_LOG_NAME = "calibration_log.csv"

DB_LOG_FILE = os.path.join(DB_PATH, 'SlamStickX_Product_Database.csv') 

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

import ssx_namer
import firmware
import calibration
import birth_utils as utils

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
                    print "%sRenamed %s from %s to %s" % (beep, v, info[1], newName)
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
    xmltree.write(dest)
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
    return utils.readFileLine(APP_VER_FILE)

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
    print "*" * 60
    print "Starting Slam Stick X Auto-Birther."
    print "Plug in a new Slam Stick X and press the button to enter bootloader mode."
    print "*" * 60
    
    # 1. Wait for an SSX in firmware mode (getSSXSerial)
    print "Waiting for an SSX in bootloader mode...",
    sp = getSSXSerial(block=True, timeout=None)
    if sp is None:
        return
    print "\nFound device on %s" % sp[0]
    ssxboot = firmware.ssx_bootloadable_device(sp[0])
    print "Connected to SSX bootloader via %s" % sp[0]
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
    
    print "\nGetting serial number...",
    # 3. Get next recorder serial number
    if serialNum is None:
        serialNum = utils.readFileLine(os.path.join(DB_PATH, "last_sn.txt"))+1
    elif isinstance(serialNum, basestring):
        # In case the serial number is the print version ("SSXxxxxxxx")
        serialNum = int(serialNum.strip(string.ascii_letters + string.punctuation + string.whitespace))
    
    serialNumStr = "SSX%07d" % serialNum
    print "SN: %s" % serialNumStr
    
    # 4. Get bootloader version, chip ID from device
    print "Getting bootloader version and chip ID...",
    bootVer, chipId = ssxboot.getVersionAndId()
    if bootVer is None or chipId is None:
        return
    print bootVer, chipId
    
    # 5. Create chip ID directory in product_database
    print "Creating database folders..."
    chipDirName = os.path.realpath(os.path.join(DB_PATH, chipId))
    if not os.path.exists(chipDirName):
        os.mkdir(chipDirName)
    
    calDirName = os.path.realpath(os.path.join(CAL_PATH, serialNumStr))
    if not os.path.exists(calDirName):
        os.mkdir(calDirName)
    
    utils.writeFileLine(os.path.join(chipDirName, 'accel_sn.txt'), accelSerialNum)
    utils.writeFileLine(os.path.join(chipDirName, 'mide_sn.txt'), serialNum)
    
    # 6. Generate manifest and generic calibration list for model
    print "Creating manifest and default calibration files..."
    manXmlFile = os.path.join(chipDirName, 'manifest.xml')
    makeManifestXml(partNum, hwRev, serialNum, accelSerialNum, manXmlFile)
    manEbml = xml2ebml.readXml(manXmlFile, schema='mide_ebml.ebml.schema.manifest')
    with open(utils.changeFilename(manXmlFile, ext="ebml"), 'wb') as f:
        f.write(manEbml)

    calXmlFile = os.path.join(chipDirName, 'cal.template.xml')
    makeCalTemplateXml(partNum, hwRev, calXmlFile)
    calEbml = xml2ebml.readXml(calXmlFile) 
    with open(utils.changeFilename(calXmlFile, ext="ebml"), 'wb') as f:
        f.write(calEbml)
    
#     # 7. Upload firmware, user page data (firmware.ssx_bootloadable_device)
    print "Uploading firmware and manifest/calibration data..."
    # XXX: TODO: RESTORE THESE LINES
#     print "Uploading firmware version %s..." % fwRev
#     ssxboot.send_app(getFirmwareFile(partNum, fwRev))
#     print "Uploading manifest and generic calibration data..."
#     ssxboot.sendUserpage(manEbml, calEbml)
    
    # 9. Reset device, immediately start autoRename
    print "Exiting bootloader and attempting to auto-rename...",
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
        dest = os.path.join(devPath, os.path.basename(c))
        if os.path.exists(dest):
            shutil.rmtree(dest)
            print "\tReplacing %s" % c
        else:
            print "\tCopying %s" % c
        shutil.copytree(c, dest, ignore=shutil.ignore_patterns('.*','Thumbs.db'))
    
    # 8. Update birth log
    print "Updating birthing logs and serial number..."
    logline = makeBirthLogEntry(chipId, serialNum, rebirth, bootVer, hwRev, fwRev, accelSerialNum, partNum)
    utils.writeFileLine(os.path.join(DB_PATH, BIRTH_LOG_NAME), logline, mode='at')
    utils.writeFileLine(os.path.join(calDirName, 'birth_log.txt'), logline)
    utils.writeFileLine(os.path.join(DB_PATH, "last_sn.txt"), serialNum)
    
    # n. Notify user that recorder is ready for potting/calibration
    print "*" * 60
    print "\x07Slam Stick X SN:%s ready for calibration and potting!" % (serialNumStr)
    print "       Part Number:", partNum
    print "       Hardware ID:", chipId
    print "  Accelerometer SN:", accelSerialNum
    print "Please disconnect it now."
    
        
#===============================================================================
# 
#===============================================================================

def calibrate(devPath=None):
    startTime = datetime.now()
    
    if devPath is None:
        print "*" * 60
        print "Starting Slam Stick X Auto-Calibration. Attach a Slam Stick X to calibrate now."
        print "*" * 60
        print "Waiting for an SSX...",
        devPath = utils.waitForSSX(timeout=None)
        print "Found SSX on %s" % devPath
    else:
        if not SlamStickX.isRecorder(devPath):
            print "!!! Specified path %s is not a Slam Stick X!"
            return
        print "*" * 60
        print "Starting Slam Stick X Auto-Calibration of device on %s." % devPath
        print "*" * 60
    
    certNum = utils.readFileLine(os.path.join(DB_PATH, 'last_cal_sn.txt'))
    c = calibration.Calibrator(devPath, certNum)
    
    if c.productSerialNum is None:
        print "!!! Could not get serial number from recorder on %s" % devPath
        return
    
    calDirName = os.path.realpath(os.path.join(CAL_PATH, c.productSerialNum))
    if not os.path.exists(calDirName):
        print "!!! Directory %s does not exist!" % calDirName
        return
    
    print "Reading birth log data..."
    try:
        birthFile = os.path.join(CAL_PATH, c.productSerialNum, 'birth_log.txt')
        birthInfo = utils.readBirthLog(birthFile)
        chipId = birthInfo.get('chipId', None)
        if chipId is None:
            print "!!! Could not get chipId from %s" % birthFile
            return
    except IOError as err:
        print "!!! %s" % err
        return
        
    chipDirName = os.path.realpath(os.path.join(DB_PATH, chipId))
    if not os.path.exists(chipDirName):
        print "!!! Directory %s does not exist!" % chipDirName
        return

    print "Copying calibration recordings..."
    sourceFiles = [utils.copyFileTo(s, calDirName) for s in c.getFiles()]

    print "Calculating calibration constants..."
    c.calculate(sourceFiles)
    print "Creating documentation:",
    print "text file,",
    txtFile = c.createTxt(calDirName)
    print "calibration recording plots,",
    plotFiles = c.createPlots(calDirName)
    print "certificate PDF",
    # BUG: TODO: This sometimes fails and takes Python with it. Move to end.
    certFile = c.createCertificate(calDirName)
    print
    
    calTemplateName = os.path.join(chipDirName, 'cal.template.xml')
    calCurrentName = os.path.join(chipDirName, 'cal.current.ebml')
    calBackupPath = os.path.join(chipDirName, str(certNum))
    docsPath = os.path.join(devPath, 'DOCUMENTATION')

    print "Copying calibration documents..."
    copyfiles = plotFiles + [txtFile, certFile]
    for filename in copyfiles:
        utils.copyFileTo(filename, docsPath)

    print "Building calibration EBML..."
    caldata = c.createEbml(calTemplateName)
    utils.writeFile(calCurrentName, caldata)
    if not os.path.exists(calBackupPath):
        os.mkdir(calBackupPath)
        utils.writeFile(os.path.join(calBackupPath, 'cal.ebml'), caldata)
        
#     manifest = utils.readFile(os.path.join(chipDirName, 'manifest.ebml'))
#     
#     print """Press the Slam Stick X's "X" button to enter bootloader mode."""
#     print "Waiting for Slam Stick X in bootloader mode...",
#     sp = getSSXSerial(block=True, timeout=None)
#     if sp is None:
#         return
#     print "\nFound device on %s" % sp[0]
#     ssxboot = firmware.ssx_bootloadable_device(sp[0])
#     print "Connected to SSX bootloader via %s" % sp[0]
# 
#     print "Uploading updated manifest and calibration data..."
# #    ssxboot.sendUserpage(manifest, caldata)
#     
#     print "Disconnecting from bootloader mode..."
#     ssxboot.disconnect()
    
    print "Writing to product 'database' spreadsheet..."
    c.writeProductLog(DB_LOG_FILE)
    
    
    print "*" * 60
    print "\x07Slam Stick X SN:%s calibration complete!" % (c.productSerialNum)
    print "    Calibration SN:", certNum
    print "       Part Number:", c.productPartNum
    print "       Hardware ID:", chipId
    print "  Accelerometer SN:", c.accelSerial
    print "Total time: %s" % (datetime.now() - startTime)
    print "Please disconnect the Slam Stick X now."
    
    
    