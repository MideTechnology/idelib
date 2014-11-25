'''
Here's how it should work:

PHASE 1: Before calibration
    1. Wait for an SSX in firmware mode (getSSXSerial)
    2. Get bootloader version, chip ID from device
    3. Get previous birth info from log (if any exists)
   *4. Prompt user for part number, hardware revision number, accelerometer SN
    5. Get next recorder serial number
    6. Create chip ID directory in product_database
    7. Generate manifest and generic calibration list for model
    8. Upload firmware, user page data (firmware.ssx_bootloadable_device)
    9. Update birth log
    10. Reset device, immediately start autoRename
   *11. Notify user that recorder is ready for potting/calibration

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

from datetime import datetime, timedelta
from glob import glob
import os.path
import shutil
import socket
import string
import sys
import time

#===============================================================================
# 
#===============================================================================

RECORDER_NAME = "SlamStick X"

PRODUCT_ROOT_PATH = "R:/LOG-Data_Loggers/LOG-0002_Slam_Stick_X/"
BIRTHER_PATH = os.path.join(PRODUCT_ROOT_PATH, "Design_Files/Firmware_and_Software/Manufacturing/LOG-XXXX-SlamStickX_Birther/")

# XXX: TESTING: REMOVE LATER
if socket.gethostname() == "DEDHAM":
    PRODUCT_ROOT_PATH = r"C:\Users\dstokes\workspace\SSXViewer\assembly\temp"

FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "firmware")
TEMPLATE_PATH = os.path.join(BIRTHER_PATH, "data_templates")
DB_PATH = os.path.join(PRODUCT_ROOT_PATH, "Product_Database")
CAL_PATH = os.path.join(DB_PATH, '_Calibration')

DEV_SN_FILE = os.path.join(DB_PATH, 'last_sn.txt')
CAL_SN_FILE = os.path.join(DB_PATH, 'last_cal_sn.txt')

BIRTH_LOG_FILE = os.path.join(DB_PATH, "product_log.csv")
CAL_LOG_FILE = os.path.join(DB_PATH, "calibration_log.csv")

DB_LOG_FILE = os.path.join(CAL_PATH, 'SSX_Calibration_Sheet.csv') 

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

def getPartNumbers():
    return map(os.path.basename, glob(os.path.join(TEMPLATE_PATH, "LOG*")))

def getPartNumber(default=None):
    dirs = getPartNumbers()
    if default in dirs:
        default = dirs.index(default)
        prompt = "Part Number (default=%s)? " % default
    else:
        prompt="Part Number? "
    
    print "Select a part number:"
    for i in range(len(dirs)):
        print "  %d: %s" % (i, dirs[i])
    p = utils.getNumber(prompt, dataType=int, minmax=(0, len(dirs)-1), default=default)
    return dirs[p]

def getHardwareRevs(partNum, default=None):
    return map(os.path.basename, glob(os.path.join(TEMPLATE_PATH, partNum, '*')))

def getHardwareRev(partNum, default=None):
    dirs = getHardwareRevs(partNum)
    if default is None:
        default = dirs[-1]
    if len(dirs) == 1:
        return int(dirs[0])
    p = raw_input("Hardware revision number (%s; default=%s)? " % (', '.join(dirs),default)).strip()
    if p == "":
        p = default
    try:
        return int(p)
    except TypeError:
        return None

def getFirmwareRevs(partNum):
    return [utils.readFileLine(APP_VER_FILE)]

def getFirmwareRev(partNum=None):
    return utils.readFileLine(APP_VER_FILE)

def getBootloaderRev(partNum=None):
    return utils.readFileLine(BOOT_VER_FILE, dataType=str)

def isValidAccelSerial(sn):
    if not isinstance(sn, basestring):
        return False
    sn = sn.strip()
    return len(sn) == 8 and sn[4] == '-'

def getAccelSerialNum(default=None):
    d = "" if default is None else " (default: %s)" % default
    prompt = "Accelerometer serial number%s? " % d
    while True:
        sn = raw_input(prompt).strip() or default
        if isValidAccelSerial(sn):
            return sn
        print "Bad accelerometer number: enter in format nnnn-nnn"
        

def getFirmwareFile(partNum=None, fwRev=None):
    return APP_FILE

def getBootloaderFile(partNum=None, fwRev=None):
    return BOOT_FILE

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
    

#===============================================================================
# 
#===============================================================================

def birth(serialNum=None, partNum=None, hwRev=None, fwRev=None, accelSerialNum=None):
    """
    """
    rebirth = serialNum is not None
    accelSerialNum = None
    
    print "*" * 60
    print "Starting Slam Stick X Auto-Birther."
    print "Plug in a new Slam Stick X and press the button to enter bootloader mode."
    print "*" * 60
    
    # 1. Wait for an SSX in firmware mode (getSSXSerial)
    ssxboot = firmware.getBootloaderSSX()
    if ssxboot is None:
        utils.errMsg("Failed to find bootloader SSX!")
        return
    
    # 2. Get bootloader version, chip ID from device
    print "Getting bootloader version and chip ID...",
    bootVer, chipId = ssxboot.getVersionAndId()
    if bootVer is None or chipId is None:
        return
    print bootVer, chipId
    
    # 3. Get previous birth info from log (if any exists)
    logInfo = utils.findBirthLog(BIRTH_LOG_FILE, 'chipId', chipId)
    if logInfo:
        # Get rid of info we don't care about right now
        for k in ('timestamp','rebirth', 'bootVer'):
            logInfo.pop(k, None)
        print "Birthing log entry for this device already exists:"
        for k,v in logInfo.items():
            if k == 'serialNum': v = "SSX%07d" % v
            print "%s: %s" % (k.rjust(16), v)
        if utils.getYesNo("Use existing data (Y)?", default="Y") == "Y":
            serialNum = logInfo.get('serialNum', None)
            partNum = logInfo.get('partNum', None)
            hwRev = logInfo.get('hwRev', None)
            fwRev = logInfo.get('fwRev', None) 
            accelSerialNum = logInfo.get('accelSerialNum', None)
            rebirth = True
    
    # 4. Prompt user for part number, hardware revision number, firmware rev.
    if partNum is not None:
        if partNum not in getPartNumbers():
            print "Invalid part number: %s" % partNum
            partNum = None
    
    partNum = getPartNumber(default=partNum)
    if partNum is None:
        utils.errMsg("Failed to get part number!")
        return
    
    if hwRev is not None:
        if str(hwRev) not in getHardwareRevs(partNum):
            print "Invalid hardware revision number: %s" % hwRev
            hwRev = None
    
    hwRev = hwRev if hwRev else getHardwareRev(partNum)
    if hwRev is None:
        utils.errMsg("Failed to get hardware revision number!")
        return
    
    fwRev = fwRev if fwRev else getFirmwareRev(partNum)
    if not isinstance(fwRev, int):
        utils.errMsg("Failed to get firmware revision number!")
        return
    
    bootRev = getBootloaderRev(partNum)
    if not bootRev:
        utils.errMsg("Failed to get bootloader revision number!")
        return
    
    accelSerialNum = getAccelSerialNum(default=accelSerialNum)
    if not accelSerialNum:
        utils.errMsg("Failed to get accelerometer serial number!")
        return
        
    # 5. Get next recorder serial number
    if serialNum is None:
        print "Getting new serial number...",
        serialNum = utils.readFileLine(DEV_SN_FILE)+1
#         utils.writeFileLine(os.path.join(DB_PATH, "last_sn.txt"), serialNum)
    elif isinstance(serialNum, basestring):
        # In case the serial number is the print version ("SSXxxxxxxx")
        serialNum = int(serialNum.strip(string.ascii_letters + string.punctuation + string.whitespace))
    
    # 6. Create chip ID directory in product_database
    chipDirName = os.path.realpath(os.path.join(DB_PATH, chipId))
    if not os.path.exists(chipDirName):
        print "Creating chip ID folder..."
        os.mkdir(chipDirName)
        
    serialNumStr = "SSX%07d" % serialNum
    print "SN: %s, accelerometer SN: %s" % (serialNumStr, accelSerialNum)
        
    calDirName = os.path.realpath(os.path.join(CAL_PATH, serialNumStr))
    if not os.path.exists(calDirName):
        print "Creating calibration folder..."
        os.mkdir(calDirName)
    
    # 7. Generate manifest and generic calibration list for model
    print "Creating manifest and default calibration files..."
    manXmlFile = os.path.join(chipDirName, 'manifest.xml')
    firmware.makeManifestXml(TEMPLATE_PATH, partNum, hwRev, serialNum, accelSerialNum, manXmlFile)
    manEbml = xml2ebml.readXml(manXmlFile, schema='mide_ebml.ebml.schema.manifest')
    with open(utils.changeFilename(manXmlFile, ext="ebml"), 'wb') as f:
        f.write(manEbml)

    calXmlFile = os.path.join(chipDirName, 'cal.template.xml')
    calibration.makeCalTemplateXml(TEMPLATE_PATH, partNum, hwRev, calXmlFile)
    calEbml = xml2ebml.readXml(calXmlFile, schema='mide_ebml.ebml.schema.mide') 
    with open(utils.changeFilename(calXmlFile, ext="ebml"), 'wb') as f:
        f.write(calEbml)

    # Copy template as 'current' (original script did this).
    curCalXmlFile = os.path.join(chipDirName, 'cal.current.xml')
    if not os.path.exists(curCalXmlFile):
        shutil.copy(calXmlFile, curCalXmlFile)
    
    # 8. Upload firmware, user page data (firmware.ssx_bootloadable_device)
    print "Uploading bootloader version %s..." % bootRev
    ssxboot.send_bootloader(getBootloaderFile(partNum, fwRev))
    print "Uploading firmware version %s..." % fwRev
    ssxboot.send_app(getFirmwareFile(partNum, fwRev))
    print "Uploading manifest and generic calibration data..."
    ssxboot.sendUserpage(manEbml, calEbml)
    
    # 9. Update birth log
    print "Updating birthing logs and serial number..."
    logline = makeBirthLogEntry(chipId, serialNum, rebirth, bootVer, hwRev, fwRev, accelSerialNum, partNum)
    utils.writeFileLine(BIRTH_LOG_FILE, logline, mode='at')
    utils.writeFileLine(os.path.join(calDirName, 'birth_log.txt'), logline)
    if not rebirth:
        utils.writeFileLine(DEV_SN_FILE, serialNum)
    utils.writeFileLine(os.path.join(chipDirName, 'mide_sn.txt'), serialNum)
    utils.writeFileLine(os.path.join(chipDirName, 'accel_sn.txt'), accelSerialNum)
   
    # 10. Reset device, immediately start autoRename
    print "Exiting bootloader..."
    ssxboot.disconnect()
    utils.waitForSSX(timeout=10)
    
    # 11. Notify user that recorder is ready for potting/calibration
    print "*" * 60
    print "\x07Slam Stick X SN:%s ready for calibration and potting!" % (serialNumStr)
    print "       Part Number:", partNum
    print "       Hardware ID:", chipId
    print "  Accelerometer SN:", accelSerialNum
    print " Hardware Revision:", hwRev
    print " Firmware Revision:", fwRev
    print "Please disconnect it now."
    
        
#===============================================================================
# 
#===============================================================================

def calibrate(devPath=None, rename=True, recalculate=False, certNum=None):
    """ Do all the post-shaker stuff: calculate calibration constants, 
        copy content, et cetera.
        
        @todo: consider modularizing this more for future reusability. This has
            grown somewhat organically.
    """
    startTime = time.time()
    totalTime = 0
    
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
            utils.errMsg( "!!! Specified path %s is not a Slam Stick X!")
            return
        print "*" * 60
        print "Starting Slam Stick X Auto-Calibration of device on %s." % devPath
        print "*" * 60
    
    # Set recorder clock
    print "Setting device clock..."
    SlamStickX(devPath).setTime()
    
    #  2. Read device info to get serial number.
    if certNum is None:
        certNum = utils.readFileLine(CAL_SN_FILE)+1
        writeCertNum = True
    else:
        writeCertNum = False
    calRev = utils.readFileLine(os.path.join(CAL_PATH, 'cal_rev.txt'), str, default='C')
    
    c = calibration.Calibrator(devPath, certNum, calRev, isUpdate=recalculate)
    
    if c.productSerialNum is None:
        utils.errMsg( "!!! Could not get serial number from recorder on %s" % devPath)
        return
    
    print "Recorder SN: %s, calibration SN: %s" % (c.productSerialNum, certNum)
    
    #  2. Create serial number directory in product_database/_Calibration
    calDirName = os.path.realpath(os.path.join(CAL_PATH, c.productSerialNum))
    if not os.path.exists(calDirName):
        print "Calibration directory %s does not exist; attempting to create..." % c.productSerialNum
        os.mkdir(calDirName)
    
    print "Reading birth log data..."
    birthFile = os.path.join(CAL_PATH, c.productSerialNum, 'birth_log.txt')
    try:
        if not os.path.exists(birthFile):
            # Possibly birthed by old script; copy data from main log.
            birthInfo = utils.findBirthLog(BIRTH_LOG_FILE, val=c.productSerialNumInt)
            if not birthInfo:
                utils.errMsg("Could not get birth log info from either file:",
                             birthFile, BIRTH_LOG_FILE)
                return
            logline = makeBirthLogEntry(*birthInfo.values()[2:])
            utils.writeFileLine(birthFile, logline)
        else:
            birthInfo = utils.readBirthLog(birthFile)
    except IOError as err:
        utils.errMsg("!!! %s" % err)
        return

    if not birthInfo:
        utils.errMsg("!!! Could not get birth info!")
        return
        
    chipId = birthInfo.get('chipId', None)
    if chipId is None:
        utils.errMsg( "!!! Could not get chipId from %s" % birthFile)
        return
        
    chipDirName = os.path.realpath(os.path.join(DB_PATH, chipId))
    if not os.path.exists(chipDirName):
        utils.errMsg( "!!! Directory %s does not exist!" % chipDirName)
        return

    calTemplateName = os.path.join(chipDirName, 'cal.template.xml')
    calCurrentName = os.path.join(chipDirName, 'cal.current.ebml')
    calBackupPath = os.path.join(chipDirName, str(certNum))
    docsPath = os.path.join(devPath, 'DOCUMENTATION')
    
    compute = True
    
    calCurrentXml = utils.changeFilename(calCurrentName, ext='.xml')
    if os.path.exists(calCurrentXml) and not recalculate:
        try:
            x = utils.readFile(calCurrentXml)
        except IOError:
            x = ''
        if 'CalibrationSerialNumber' in x:
            # Calibration EBML exists; recalculate anyway?
            totalTime += time.time() - startTime
            q = utils.getYesNo("\x07\x07Calibration data already exists! Recompute (Y/N)? ")
            startTime = time.time()
            compute = q == 'Y'
    else:
        compute = True
    
    if compute:
        copyData = True
        dataDir = os.path.join(devPath, "DATA")
        dataCopyDir = os.path.join(calDirName, "DATA")
        if not os.path.exists(dataDir):
            if os.path.exists(dataCopyDir):
                print "!!! Recorder has no DATA, but a copy exists in the Calibration directory."
                q = utils.getYesNo("Use existing copy of DATA and continue (Y/N)? ")
                if q == "Y":
                    copyData = False
                else:
                    utils.errMsg("!!! Calibration cancelled!")
                    return
            else:
                utils.errMsg("!!! Recorder has no DATA directory!")
                return
        
        
        totalTime += time.time() - startTime
        c.calHumidity = utils.getNumber("Humidity at recording time (default: %.2f)? " % c.calHumidity, default=c.calHumidity)
        startTime = time.time()
        
        print "Copying calibration recordings from device..."
        if copyData:
            utils.copyTreeTo(dataDir, dataCopyDir)
        utils.copyTreeTo(os.path.join(devPath, "SYSTEM"), os.path.join(calDirName, "SYSTEM"))
        
        #  3. Generate calibration data from IDE files on recorder (see calibration.py)
        sourceFiles = c.getFiles(calDirName)

        print "Calculating calibration constants from recordings..."
        c.calculate(sourceFiles)
        c.closeFiles()
        
        if (c.Sxy is None or c.Syz is None or c.Sxz is None):
            result = ["!!! Error in calculating transverse sensitivity (bad file?)"]
            result.append("Only found the following:")
            if c.Sxy is not None:
                result.append("%s, Transverse Sensitivity in XY = %.2f percent" % (c.Sxy_file, c.Sxy))
            if c.Syz is not None:
                result.append("%s, Transverse Sensitivity in YZ = %.2f percent" % (c.Syz_file, c.Syz))
            if c.Sxz is not None:
                result.append("%s, Transverse Sensitivity in ZX = %.2f percent" % (c.Sxz_file, c.Sxz))
            utils.errMsg(*result)
            return
        
        if c.Sxy > 10 or c.Syz > 10 or c.Sxz > 10:
            print "!!! Extreme transverse sensitivity detected in recording(s)!"
            print "%s, Transverse Sensitivity in XY = %.2f percent" % (c.Sxy_file, c.Sxy)
            print "%s, Transverse Sensitivity in YZ = %.2f percent" % (c.Syz_file, c.Syz)
            print "%s, Transverse Sensitivity in ZX = %.2f percent" % (c.Sxz_file, c.Sxz)
            q = utils.getYesNo("Continue with device calibration (Y/N)? ")
            if q == "N":
                return
        
        if not all([utils.inRange(x.cal_temp, 15, 27) for x in c.cal_vals]):
            print "!!! Extreme temperature detected in recording(s)!"
            for x in c.cal_vals:
                print "%s: %.2f degrees C" % (os.path.basename(x.filename), x.cal_temp)
            q = utils.getYesNo("Continue with device calibration (Y/N)? ")
            if q == "N":
                return
            
        if not all([utils.inRange(x.cal_press, 96235, 106365) for x in c.cal_vals]):
            print "!!! Extreme air pressure detected in recording(s)!"
            q = utils.getYesNo("Continue with device calibration (Y/N)? ")
            for x in c.cal_vals:
                print "%s: %.2f Pa" % (os.path.basename(x.filename), x.cal_press)
            if q == "N":
                return
        
        print c.createTxt()
        
        print "Building calibration EBML..."
        caldata = c.createEbml(calTemplateName)
        utils.writeFile(calCurrentName, caldata)
        
        #  4. Generate calibration certificate
        print "Creating documentation: text file, ",
        c.createTxt(calDirName)
        print "calibration recording plots,",
        c.createPlots(calDirName)
        print "certificate PDF"
        # BUG: TODO: This sometimes fails and takes Python with it. Move to end.
        certFile = c.createCertificate(calDirName)
    
        copyfiles = [certFile]
        
        print "Writing to product 'database' spreadsheet..."
        c.writeProductLog(DB_LOG_FILE)
    
        if writeCertNum:
            print "Incrementing calibration serial number..."
            utils.writeFileLine(CAL_SN_FILE, certNum)
    
    else:
        copyfiles = []
        certFiles = glob(os.path.join(calDirName, '*.pdf'))
        if certFiles:
            copyfiles = [certFiles[-1]]
        caldata = utils.readFile(calCurrentName)

    if not os.path.exists(calBackupPath):
        os.mkdir(calBackupPath)
        utils.writeFile(os.path.join(calBackupPath, 'cal.ebml'), caldata)

    # 11. Copy documentation and software folders
    copyStart = datetime.now()
    print "Copying standard content to device..."
    copyContent(devPath)
    print "Copying calibration documentation to device..."
    for filename in copyfiles:
        utils.copyFileTo(filename, docsPath)
    copyTime = datetime.now()-copyStart
    
    print "Removing old DATA directory from device..."
    shutil.rmtree(os.path.join(devPath, "DATA"))
    
    print """\x07Press the Slam Stick X's "X" button to enter bootloader mode."""
    # Don't count the time spent waiting for the user to press the button.
    totalTime += (time.time() - startTime)
    ssxboot = firmware.getBootloaderSSX()
    if ssxboot is None:
        utils.errMsg( "!!! Failed to connect to bootloader!")
        return
    # Reset startTime to resume counting elapsed time
    startTime = time.time()
    
    print "Uploading updated manifest and calibration data..."
    manifest = utils.readFile(os.path.join(chipDirName, 'manifest.ebml'))
    ssxboot.sendUserpage(manifest, caldata)
     
    print "Disconnecting from bootloader mode..."
    ssxboot.disconnect()
    utils.waitForSSX(timeout=10)
    
    totalTime += (time.time() - startTime)
    totalTime = str(timedelta(seconds=int(totalTime)))
    copyTime = str(copyTime).rsplit('.',1)[0]
    print "*" * 60
    print "\x07Slam Stick X SN:%s calibration complete!" % (c.productSerialNum)
    print "    Calibration SN:", certNum
    print "       Part Number:", c.productPartNum
    print "       Hardware ID:", chipId
    print "  Accelerometer SN:", c.accelSerial
    print "Total time: %s (%s spent copying files)" % (totalTime, copyTime)
    print "Please disconnect the Slam Stick X now."


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Improved SSX Birthing/Calibration Suite")
    parser.add_argument("mode", help="The job to do", choices=["birth", "calibrate", "cal"])
    parser.add_argument("--serialNum", "-s", help="Serial number of the device being birthed. Defaults to a fresh one.")
#     parser.add_argument("--partNum", "-p", help="Part number to birth.")
#     parser.add_argument("--hwRev", "-w", help="Hardware revision to birth.")
#     parser.add_argument("--fwRev", "-f", help="Firmware revision to birth.")
#     parser.add_argument("--accelSerialNum", "-a", help="Accelerometer serial number to birth.")
    args = parser.parse_args()
    
    try:
        if args.mode == "birth":
            birth(serialNum=args.serialNum)
        elif args.mode.startswith("cal"):
            calibrate()
    except KeyboardInterrupt:
        print "Quitting..."