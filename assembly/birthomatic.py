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
   *n. Notify user that recorder is ready for potting/calibration

PHASE 2: Offline work
    x. Potting, assembly, recording shaker sessions.

PHASE 3: Post-Calibration Recording
    1. Wait for an SSX in drive mode (see ssx_namer)
    2. Auto-rename device
    3. Set recorder clock
    4. Read device info to get serial number.
    5. Create serial number directory in product_database/_Calibration
    6. Generate calibration data from IDE files on recorder (see calibration.py)
    7. Generate calibration certificate
    8. Copy calibration certificate to device
    9. Copy documentation and software folders
   *10. Prompt user to enter bootloader mode
    11. Wait for an SSX in firmware mode (getSSXSerial)
    12. Upload new manifest/calibration to user page.
    13. Reset device
   *n. Tell user the device is ready.


Created on Sep 24, 2014

@author: dstokes
'''
# import csv
from datetime import datetime
from glob import glob
import os.path
import shutil
import string
import sys
import time
# from xml.etree import ElementTree as ET
# import xml.dom.minidom as minidom
# 
# import numpy as np
# import serial.tools.list_ports
# import serial

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

# from mide_ebml.importer import importFile, SimpleUpdater
from devices import SlamStickX
from mide_ebml import xml2ebml

import ssx_namer
import firmware
import calibration
import birth_utils as utils


#===============================================================================
# Helper functions
#===============================================================================

def autoRename(newName=RECORDER_NAME, timeout=60, callback=utils.spinner, quiet=True):
    """ Wait for the first SSX in disk mode to appear and change its name.
        Windows-specific!
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

def getFirmwareRev(partNum=None):
    return utils.readFileLine(APP_VER_FILE)

def getAccelSerialNum():
    return raw_input("Accelerometer serial number? ")

def getFirmwareFile(partNum=None, fwRev=None):
    return APP_FILE
    
#===============================================================================
# 
#===============================================================================

def copyContent(devPath):
    """ Copy the default Slam Stick X content (i.e. the documentation and 
        application folders) to a recorder.
    """
    files = filter(lambda x: not (x.startswith('.') or x == "Thumbs.db"), 
                   glob(os.path.join(CONTENT_PATH, '*')))
    for c in files:
        dest = os.path.join(devPath, os.path.basename(c))
        if os.path.exists(dest):
            shutil.rmtree(dest)
            print "\tReplacing %s" % c
        else:
            print "\tCopying %s" % c
        shutil.copytree(c, dest, ignore=shutil.ignore_patterns('.*','Thumbs.db'))
    

def uploadCalibration(devPort):
    """
    """
    pass


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
    ssxboot = firmware.getBootloaderSSX()
    if ssxboot is None:
        return
    
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
    firmware.makeManifestXml(TEMPLATE_PATH, partNum, hwRev, serialNum, accelSerialNum, manXmlFile)
    manEbml = xml2ebml.readXml(manXmlFile, schema='mide_ebml.ebml.schema.manifest')
    with open(utils.changeFilename(manXmlFile, ext="ebml"), 'wb') as f:
        f.write(manEbml)

    calXmlFile = os.path.join(chipDirName, 'cal.template.xml')
    calibration.makeCalTemplateXml(TEMPLATE_PATH, partNum, hwRev, calXmlFile)
    calEbml = xml2ebml.readXml(calXmlFile) 
    with open(utils.changeFilename(calXmlFile, ext="ebml"), 'wb') as f:
        f.write(calEbml)
    
#     # 7. Upload firmware, user page data (firmware.ssx_bootloadable_device)
    print "Uploading firmware version %s..." % fwRev
    ssxboot.send_app(getFirmwareFile(partNum, fwRev))
    print "Uploading manifest and generic calibration data..."
    ssxboot.sendUserpage(manEbml, calEbml)
    
    # 8. Update birth log
    print "Updating birthing logs and serial number..."
    logline = makeBirthLogEntry(chipId, serialNum, rebirth, bootVer, hwRev, fwRev, accelSerialNum, partNum)
    utils.writeFileLine(os.path.join(DB_PATH, BIRTH_LOG_NAME), logline, mode='at')
    utils.writeFileLine(os.path.join(calDirName, 'birth_log.txt'), logline)
    utils.writeFileLine(os.path.join(DB_PATH, "last_sn.txt"), serialNum)
    
    # 9. Reset device, immediately start autoRename
    print "Exiting bootloader..."
    ssxboot.disconnect()
    utils.waitForSSX(timeout=10)
    
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

def calibrate(devPath=None, rename=True):
    """ Do all the post-shaker stuff: calculate calibration constants, 
        copy content, et cetera.
    """
    startTime = datetime.now()
    
    #  1. Wait for an SSX in drive mode (see ssx_namer)
    if devPath is None:
        print "*" * 60
        print "Starting Slam Stick X Auto-Calibration. Attach a Slam Stick X to calibrate now."
        print "*" * 60
        print "Waiting for an SSX...",
        if rename:
            devPath = autoRename(timeout=None)
        else:
            devPath = utils.waitForSSX(timeout=None)
        print "Found SSX on %s" % devPath
    else:
        if not SlamStickX.isRecorder(devPath):
            print "!!! Specified path %s is not a Slam Stick X!"
            return
        print "*" * 60
        print "Starting Slam Stick X Auto-Calibration of device on %s." % devPath
        print "*" * 60
    
    # Set recorder clock
    print "Setting device clock..."
    SlamStickX(devPath).setTime()
    
    #  2. Read device info to get serial number.
    certNum = utils.readFileLine(os.path.join(DB_PATH, 'last_cal_sn.txt'))
    c = calibration.Calibrator(devPath, certNum)
    
    if c.productSerialNum is None:
        print "!!! Could not get serial number from recorder on %s" % devPath
        return
    
    #  2. Create serial number directory in product_database/_Calibration
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

    calTemplateName = os.path.join(chipDirName, 'cal.template.xml')
    calCurrentName = os.path.join(chipDirName, 'cal.current.ebml')
    calBackupPath = os.path.join(chipDirName, str(certNum))
    docsPath = os.path.join(devPath, 'DOCUMENTATION')
    
    if os.path.exists(calCurrentName):
        # Calibration EBML exists; recalculate anyway?
        q = ''
        while q.upper() not in ('Y','N'):
            q = raw_input("\x07\x07Calibration EBML already exists! Recompute (Y/N)? ")
            recompute = q == 'Y'
    else:
        recompute = True
    
    if recompute:
        #  3. Generate calibration data from IDE files on recorder (see calibration.py)
        print "Copying calibration recordings from device..."
        sourceFiles = [utils.copyFileTo(s, calDirName) for s in c.getFiles()]
    
        print "Calculating calibration constants from recordings..."
        c.calculate(sourceFiles)
        
        print "Building calibration EBML..."
        caldata = c.createEbml(calTemplateName)
        utils.writeFile(calCurrentName, caldata)
        
        print "Writing to product 'database' spreadsheet..."
        c.writeProductLog(DB_LOG_FILE)
    
        #  4. Generate calibration certificate
        print "Creating documentation:",
        print "text file,",
        txtFile = c.createTxt(calDirName)
        print "calibration recording plots,",
        plotFiles = c.createPlots(calDirName)
        print "certificate PDF"
        # BUG: TODO: This sometimes fails and takes Python with it. Move to end.
        certFile = c.createCertificate(calDirName)
    
        #  5. Copy calibration certificate to device
        print "Copying calibration documents..."
        copyfiles = plotFiles + [txtFile, certFile]
        for filename in copyfiles:
            utils.copyFileTo(filename, docsPath)
    else:
        caldata = utils.readFile(calCurrentName)

    if not os.path.exists(calBackupPath):
        os.mkdir(calBackupPath)
        utils.writeFile(os.path.join(calBackupPath, 'cal.ebml'), caldata)

    # 11. Copy documentation and software folders
    print "Copying content to device..."
    copyContent(devPath)
    
    print """\x07Press the Slam Stick X's "X" button to enter bootloader mode."""
    ssxboot = firmware.getBootloaderSSX()
    if ssxboot is None:
        return
 
    print "Uploading updated manifest and calibration data..."
    manifest = utils.readFile(os.path.join(chipDirName, 'manifest.ebml'))
    ssxboot.sendUserpage(manifest, caldata)
     
    print "Disconnecting from bootloader mode..."
    ssxboot.disconnect()
    utils.waitForSSX(timeout=10)
    
    print "*" * 60
    print "\x07Slam Stick X SN:%s calibration complete!" % (c.productSerialNum)
    print "    Calibration SN:", certNum
    print "       Part Number:", c.productPartNum
    print "       Hardware ID:", chipId
    print "  Accelerometer SN:", c.accelSerial
    print "Total time: %s" % (datetime.now() - startTime)
    print "Please disconnect the Slam Stick X now."
    

def resumeCalibration(devPath):
    """
    """
    