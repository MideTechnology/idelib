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

from collections import OrderedDict
from glob import glob
import os.path
import shutil
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
# import socket
# if socket.gethostname() == "DEDHAM":
#     PRODUCT_ROOT_PATH = r"C:\Users\dstokes\workspace\SSXViewer\assembly\temp"

FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "firmware")
TEMPLATE_PATH = os.path.join(BIRTHER_PATH, "data_templates")
DB_PATH = os.path.join(PRODUCT_ROOT_PATH, "Product_Database")
CAL_PATH = os.path.join(DB_PATH, '_Calibration')

DEV_SN_FILE = os.path.join(DB_PATH, 'last_sn.txt')
CAL_SN_FILE = os.path.join(DB_PATH, 'last_cal_sn.txt')

BIRTH_LOG_FILE = os.path.join(DB_PATH, "product_log.csv")
CAL_LOG_FILE = os.path.join(DB_PATH, "calibration_log.csv")

DB_LOG_FILE = os.path.join(CAL_PATH, 'SSX_Calibration_Sheet.csv') 
DB_BAD_LOG_FILE = os.path.join(CAL_PATH, 'SSX_Bad_Calibration.csv') 

BOOT_FILE = os.path.join(FIRMWARE_PATH, "boot.bin")
BOOT_VER_FILE = os.path.join(FIRMWARE_PATH, "boot_version.txt")
APP_FILE = os.path.join(FIRMWARE_PATH, "app.bin")
APP_VER_FILE = os.path.join(FIRMWARE_PATH, "app_version.txt")

CONTENT_PATH = os.path.join(DB_PATH, '_Copy_Folder')

LOCK_FILE = os.path.join(DB_PATH, 'birth_in_use')

DC_CAL_SAMPLE_RATE = 3200
DC_DEFAULT_SAMPLE_RATE = 400

#===============================================================================
# Rigmarole to ensure the right libraries are located.
#===============================================================================

# VIEWER_PATH = "P:/WVR_RIF/04_Design/Electronic/Software/SSX_Viewer"
VIEWER_PATH = r"R:\LOG-Data_Loggers\LOG-0002_Slam_Stick_X\Design_Files\Firmware_and_Software\Development\Source\Slam_Stick_Lab"

CWD = os.path.abspath(os.path.dirname(__file__))
sys.path.append(CWD)
sys.path.append(os.path.abspath(os.path.join(CWD, '..')))

try:
    import mide_ebml
except ImportError:
    if os.path.exists('../mide_ebml'):
        sys.path.append(os.path.abspath('..'))
    elif os.path.exists(os.path.join(CWD, '../mide_ebml')):
        sys.path.append(os.path.abspath(os.path.join(CWD, '../mide_ebml')))
    elif os.path.exists(VIEWER_PATH):
        sys.path.append(VIEWER_PATH)
    import mide_ebml #@UnusedImport

# from mide_ebml.importer import importFile, SimpleUpdater
import devices
# from mide_ebml import xml2ebml
from mide_ebml.ebmlite import loadSchema
from mide_ebml.ebmlite import util as ebml_util

import birth_utils as utils
import calibration
import firmware
import jig_birther
import ssx_namer

from birth_utils import errMsg, changeFilename, getSerialPrefix

#===============================================================================
# 
#===============================================================================

mideSchema = loadSchema('mide.xml')
manifestSchema = loadSchema('manifest.xml')

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
                    print ("%s%s!!! Failed to rename drive %s (labeled %r)!" % \
                           (beep, beep, v, info[1]))
                    return False
        
        time.sleep(.125)
        if callback:
            callback.update()
        
        if timeout and deadline < time.time():
            print ("%s%s!!! Timed out waiting for a recorder (%s sec.)!" % \
                   (beep, beep, timeout))
            return False


#===============================================================================
# 
#===============================================================================

def getPartNumbers():
    """ Get a list of all known Part Numbers. """
    return map(os.path.basename, glob(os.path.join(TEMPLATE_PATH, "LOG*")))

def getPartNumber(default=None):
    """ Prompt the user for a Part Number. """
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
    """ Get a list of all known Hardware Revisions. """
    revs = filter(os.path.isdir, glob(os.path.join(TEMPLATE_PATH, partNum, '*')))
    revs = map(os.path.basename, revs)
    result = []
    for rev in revs:
        try:
            result.append(int(rev))
        except ValueError:
            pass
    if len(result) == 0:
        raise ValueError("Found no hardware rev dirs for %r!" % partNum)
    result.sort()
    return map(str, result)


def getHardwareRev(partNum, default=None):
    """ Prompt the user for a Hardware Revision number. """
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
    """ Get a list of all known Firmware Revisions. """
    # There's only one:
    return [utils.readFileLine(APP_VER_FILE)]


def getFirmwareRev(partNum=None):
    """ Prompt the user for a Firmware Revision number. """
    # There's only one:
    return utils.readFileLine(APP_VER_FILE)


def getBootloaderRev(partNum=None):
    """ Get the latest bootloader revision number. """
    return utils.readFileLine(BOOT_VER_FILE, dataType=str)


def isValidAccelSerial(sn):
    """ Simple sanity-check for accelerometer serial numbers, either ####-###
        (for 832M1) or ####-#### (3255A). A comma-separated series of
        serial numbers is also acceptable.
    """
    # TODO: This is kind of brittle. Maybe use regex and/or consult used SNs.
    if not isinstance(sn, basestring):
        return False
    sn = sn.strip()
    return sn[4] == '-' and (len(sn) == 8 or len(sn) == 9)


def getAccelSerialNum(default=None):
    """ Prompt the user for an accelerometer serial number. """
    d = "" if default is None else " (default: %s)" % default
    prompt = "Accelerometer serial number%s? " % d
    while True:
        sn = raw_input(prompt).strip() or default
        sn = str(sn).replace(',', ' ')
        if all(map(isValidAccelSerial, sn.split())):
            return sn
        print "Bad accelerometer number(s): enter in format nnnn-nnn or nnnn-nnnn"
        

def getFirmwareFile(partNum=None, fwRev=None):
    """ Get the path and name of the latest firmware file. """
    return APP_FILE


def getBootloaderFile(partNum=None, fwRev=None):
    """ Get the path and name of the latest bootloader file. """
    return BOOT_FILE


def getBatchId(default=None):
    """ Get the batch number. """
    prompt = "Batch Number"
    if default is not None:
        prompt += " (default: '%s')" % default
    prompt += "? "
    return utils.getString(prompt, default=default, minmax=(0,100))


#===============================================================================
# 
#===============================================================================

def copyContent(devPath, partNum=None):
    """ Copy the default Slam Stick X content (i.e. the documentation and 
        application folders) to a recorder.
    """
    if partNum is None:
        contentPath = CONTENT_PATH
    else:
        contentPath = os.path.join(DB_PATH, '_%s_Contents' % partNum[:8])
        
    files = filter(lambda x: not (x.startswith('.') or x == "Thumbs.db"), 
                   glob(os.path.join(contentPath, '*')))
    for c in files:
        c = os.path.realpath(c)
        dest = os.path.realpath(os.path.join(devPath, os.path.basename(c)))
        if os.path.exists(dest):
            shutil.rmtree(dest)
            print "\tReplacing %s" % c
        else:
            print "\tCopying %s" % c
        shutil.copytree(c, dest, ignore=shutil.ignore_patterns('.*','Thumbs.db'))
    

def cleanDevice(dev, chipDirName):
    """ Remove old recordings and user calibration data from device.
        @todo: Maybe just delete everything.
    """
    dataDir = os.path.join(dev.path, 'DATA')
    if os.path.exists(dataDir):
        print "Removing old DATA directory from device..."
        try:
            shutil.rmtree(dataDir)
        except WindowsError:
            pass

    userCalFile = getattr(dev, 'userCalFile', None) 
    if os.path.exists(userCalFile):
        shutil.copy(userCalFile, changeFilename(userCalFile, path=chipDirName))
        print "Removing usercal.dat file from device..."
        os.remove(userCalFile)


#===============================================================================
# 
#===============================================================================

def birth(serialNum=None, partNum=None, hwRev=None, fwRev=None, accelSerialNum=None,
          fwFile=None, firmwareOnly=False, writeLog=True):
    """ Perform initial configuration of a Slam Stick X.
    """
    rebirth = serialNum is not None
    accelSerialNum = None
    birthday = None
    
    if fwFile and not os.path.exists(fwFile):
        print "Could not find firmware file %s!" % fwFile
        exit(1)
    
    print "*" * 60
    print "Starting Slam Stick Auto-Birther."
    print "Plug in a new Slam Stick and press the button to enter bootloader mode."
    print "*" * 60
    
    # 1. Wait for an SSX in firmware mode (getSSXSerial)
    ssxboot = firmware.getBootloaderSSX(callback=utils.spinner)
    if ssxboot is None:
        errMsg("Failed to find SlamStick bootloader!")
        return
    
    # 2. Get bootloader version, chip ID from device
    print "Getting bootloader version and chip ID...",
    bootVer, chipId = ssxboot.getVersionAndId()
    if bootVer is None or chipId is None:
        return
    print bootVer, chipId
    
    # 3. Get previous birth info from log (if any exists)
    # User gets prompted if they want to use existing data; those become defaults.
    lastBirth = utils.getLastBirthLog(BIRTH_LOG_FILE)
    batchId = lastBirth.get('batchId', '')
    logInfo = utils.findBirthLog(BIRTH_LOG_FILE, 'chipId', chipId)
    if logInfo:
        print "Birthing log entry for this device already exists:"
        serPrefix = getSerialPrefix(logInfo.get('partNum', "LOG-0002"))
        for k,v in logInfo.items():
            if k in ('timestamp','rebirth', 'bootVer'):
                continue
            if k == 'serialNum': 
                v = "%s%07d" % (serPrefix, v)
            print "%s: %s" % (k.rjust(16), v)
        if utils.getYesNo("Use existing data (Y)?", default="Y") == "Y":
            serialNum = logInfo.get('serialNum', None)
            partNum = logInfo.get('partNum', None)
            hwRev = logInfo.get('hwRev', None)
#             fwRev = logInfo.get('fwRev', None) 
            accelSerialNum = logInfo.get('accelSerialNum', None)
            batchId = logInfo.get('batchId', batchId)
            
            firstlog = utils.findBirthLog(BIRTH_LOG_FILE, 'chipId', chipId, last=False)
            birthday = firstlog.get('timestamp', None)
            rebirth = True
    
    # 4. Prompt user for part number, hardware revision number, firmware rev.
    if partNum is not None:
        if partNum not in getPartNumbers():
            print "Invalid part number: %s" % partNum
            partNum = None
    
    partNum = getPartNumber(default=partNum)
    if partNum is None:
        errMsg("Failed to get part number!")
        return
    
    if hwRev is not None:
        if str(hwRev) not in getHardwareRevs(partNum):
#             print "Invalid hardware revision number: %s" % hwRev
            hwRev = None
    
    hwRev = hwRev if hwRev else getHardwareRev(partNum)
    if hwRev is None:
        errMsg("Failed to get hardware revision number!")
        return
    
    fwRev = fwRev if fwRev else getFirmwareRev(partNum)
    if not isinstance(fwRev, int):
        errMsg("Failed to get firmware revision number!")
        return
    
    bootRev = getBootloaderRev(partNum)
    if not bootRev:
        errMsg("Failed to get bootloader revision number!")
        return
    
    batchId = getBatchId(batchId)
    
    # The SlamStick C has no analog accelerometer!
    has_832M1 = utils.hasAnalogAccel(TEMPLATE_PATH, partNum, hwRev)
    if has_832M1:
        accelSerialNum = getAccelSerialNum(default=accelSerialNum)
        if not accelSerialNum:
            errMsg("Failed to get accelerometer serial number!")
            return
    else:
        accelSerialNum = None
        
    # 5. Get next recorder serial number
    if serialNum is None:
        print "Getting new serial number...",
        serialNum = utils.readFileLine(DEV_SN_FILE)+1
#         utils.writeFileLine(os.path.join(DB_PATH, "last_sn.txt"), serialNum)
    elif isinstance(serialNum, basestring):
        # In case the serial number is the print version ("SSXxxxxxxx")
        print "(Re-)Using serial number %s" % serialNum
        serialNum = int(serialNum.strip(string.ascii_letters + string.punctuation + string.whitespace))

    # HACK: Use better means of getting the serial number prefix!
    serialNumStr = "%s%07d" % (getSerialPrefix(partNum), serialNum)
    print "SN: %s, accelerometer SN: %s" % (serialNumStr, accelSerialNum)
        
    # 6. Create chip ID directory in product_database
    chipDirName = os.path.realpath(os.path.join(DB_PATH, chipId))
    if not os.path.exists(chipDirName):
        print "Creating chip ID folder..."
        os.mkdir(chipDirName)
        
    calDirName = os.path.realpath(os.path.join(CAL_PATH, serialNumStr))
    if not os.path.exists(calDirName):
        print "Creating calibration folder..."
        os.mkdir(calDirName)

    # Make convenience shortcuts
    try:
        utils.makeShortcut(chipDirName, calDirName)
        utils.makeShortcut(calDirName, chipDirName)
    except Exception:
        # Naked exceptions are bad medicine. 
        pass
    
    # 7. Generate manifest and generic calibration list for model
    if not firmwareOnly:
        print "Creating manifest and default calibration files..."
        manXmlFile = os.path.join(chipDirName, 'manifest.xml')
        firmware.makeManifestXml(TEMPLATE_PATH, partNum, hwRev, serialNum, 
                                 accelSerialNum, manXmlFile, birthday=birthday,
                                 batchId=batchId)
#         manEbml = xml2ebml.readXml(manXmlFile, schema='mide_ebml.ebml.schema.manifest')
        manEbml = ebml_util.loadXml(manXmlFile, manifestSchema)
        with open(changeFilename(manXmlFile, ext="ebml"), 'wb') as f:
            f.write(manEbml)
    
        calXmlFile = os.path.join(chipDirName, 'cal.template.xml')
        calibration.makeCalTemplateXml(TEMPLATE_PATH, partNum, hwRev, calXmlFile)
#         calEbml = xml2ebml.readXml(calXmlFile, schema='mide_ebml.ebml.schema.mide') 
        calEbml = ebml_util.loadXml(calXmlFile, mideSchema)
        with open(changeFilename(calXmlFile, ext="ebml"), 'wb') as f:
            f.write(calEbml)
    
        propXmlFile = os.path.join(chipDirName, 'recprop.xml')
        propTemplate = firmware.makeRecPropXml(TEMPLATE_PATH, partNum, hwRev, accelSerialNum, propXmlFile)
        if propTemplate is not None and os.path.exists(propXmlFile):
#             propEbml = xml2ebml.readXml(propXmlFile, schema='mide_ebml.ebml.schema.mide')
            propEbml = ebml_util.loadXml(propXmlFile, mideSchema) 
            with open(changeFilename(propXmlFile, ext="ebml"), 'wb') as f:
                f.write(propEbml)
        else:
            print "No recording properties template found, skipping."
            propEbml = bytearray()

        # Copy template as 'current' (original script did this).
        curCalXmlFile = os.path.join(chipDirName, 'cal.current.xml')
        if not os.path.exists(curCalXmlFile):
            shutil.copy(calXmlFile, curCalXmlFile)
    
    # 8. Upload firmware, user page data (firmware.ssx_bootloadable_device)
    if not firmwareOnly:
        print "Uploading bootloader version %s..." % bootRev
        ssxboot.send_bootloader(getBootloaderFile(partNum, fwRev))
    if not fwFile:
        print "Uploading firmware version %s..." % fwRev
        ssxboot.send_app(getFirmwareFile(partNum, fwRev))
    else:
        print "Uploading firmware %s..." % fwFile
        ssxboot.send_app(fwFile)
    
    if not firmwareOnly:
        print "Uploading manifest and generic calibration data..."
        ssxboot.sendUserpage(manEbml, calEbml, propEbml)
    
    # 9. Update birth log
    print "Updating birthing logs and serial number..."
    if writeLog:
        logline = utils.makeBirthLogEntry(chipId, serialNum, rebirth, bootVer, hwRev, fwRev, accelSerialNum, partNum, batchId)
        utils.writeFileLine(BIRTH_LOG_FILE, logline, mode='at')
        utils.writeFileLine(os.path.join(calDirName, 'birth_log.txt'), logline)
        if not rebirth:
            print "Writing serial number to file: %s" % serialNum
            utils.writeFileLine(DEV_SN_FILE, serialNum)
    utils.writeFileLine(os.path.join(chipDirName, 'mide_sn.txt'), serialNum)
    utils.writeFileLine(os.path.join(chipDirName, 'accel_sn.txt'), accelSerialNum)
   
    # 10. Reset device, immediately start autoRename
    print "Exiting bootloader..."
    ssxboot.disconnect()

    # TODO: Improve this    
    volNameFile = os.path.join(TEMPLATE_PATH, partNum, 'volume_name.txt')
    volName = utils.readFileLine(volNameFile, str, default=RECORDER_NAME)
    _devPath = autoRename(volName, timeout=20)
    
    # 10.1 Set device clock, change DC sample rate (if present)
    devs = [d for d in devices.getDevices() if d.serialInt == serialNum]
    if devs:
        dev = devs[0]
        dev.setTime()
        if dev.getAccelChannel(dc=True):
            print "Setting DC accelerometer to test rate (%s)..." % DC_CAL_SAMPLE_RATE 
            conf = dev.getConfig()
            conf['SSXChannelConfiguration'] = [
                OrderedDict([('ChannelSampleFreq', 3200), 
                             ('ConfigChannel', 32), 
                             ('SubChannelEnableMap', 7)])]
            dev.saveConfig(conf)
        else:
            print "No DC accelerometer found; continuing."
    
        cleanDevice(dev, chipDirName)
            
    else:
        print "Could not find recorder! Check configuration in Lab before calibrating!"
    
    # 11. Notify user that recorder is ready for potting/calibration
    print "*" * 60
    print "\x07%s SN:%s ready for calibration and potting!" % (volName, serialNumStr)
    if batchId:
        print "          Batch ID:", batchId
    print "       Part Number:", partNum
    print "       Hardware ID:", chipId
    if accelSerialNum is not None:
        print "  Accelerometer SN:", accelSerialNum
    print " Hardware Revision:", hwRev
    print " Firmware Revision:", fwRev
    print "Please disconnect it now."
    
    errMsg()


#===============================================================================
# 
#===============================================================================

def getJigBootloader():
    """
    """
    c = jig_birther.TestJig() # open FTDI chip in bitbang mode
    
    c.set_test_mode_run()
    c.raise_pin(c.PIN_NRECORD_SW);
    print "Waiting for board on test jig..."

    # Wait until a board is detected on the jig by pulling !BOARD_SENSE low.
    while c.read_pin(c.PIN_NBOARD_SENSE):
        utils.spinner.update()
        time.sleep(0.25)

    c.set_test_mode_boot()
    c.reset_target()
    time.sleep(1)
    c.raise_pin(c.PIN_NRECORD_SW)


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse
    import subprocess
#     global TEMPLATE_PATH
    
    parser = argparse.ArgumentParser(description="Improved SSX Birthing/Calibration Suite")
    parser.add_argument("mode", help="The job to do", choices=["birth", "rebirth", "calibrate", "cal"])
    parser.add_argument("--jig", "-j", action="store_true", help="Use the jig for birthing.")
    parser.add_argument("--serialNum", "-s", help="Serial number of the device being birthed. Defaults to a fresh one.")
#     parser.add_argument("--partNum", "-p", help="Part number to birth.")
#     parser.add_argument("--hwRev", "-w", help="Hardware revision to birth.")
#     parser.add_argument("--fwRev", "-f", help="Firmware revision to birth.")
#     parser.add_argument("--accelSerialNum", "-a", help="Accelerometer serial number to birth.")
    parser.add_argument("--binfile", "-b", help="An alternate firmware file to upload in birth mode.", default=None)
    parser.add_argument("--templates", "-t", help="An alternate birth template directory.", default=TEMPLATE_PATH)
    parser.add_argument("--nocopy", "-n", help="Do not copy software to SSX after calibration.", action='store_true')
    parser.add_argument("--firmwareonly", "-f", help="Only upload the firmware; do not replace the userpage data.", action='store_true')
    parser.add_argument("--exclude", "-x", help="Exclude this birth/calibration from the log (for testing only!)", action='store_true')
    args = parser.parse_args()
    
    TEMPLATE_PATH = args.templates
    
    print "*" * 78
    print "Starting Slam Stick X %r script." % (args.mode)
    print "Template path: %s" % TEMPLATE_PATH
    print "*" * 78
    
    try:
        if "birth" in str(args.mode):
            if not utils.checkLockFile(LOCK_FILE):
                exit(0)
            if args.jig:
                getJigBootloader()
            birth(serialNum=args.serialNum, fwFile=args.binfile, firmwareOnly=args.firmwareonly, writeLog=(not args.exclude))
        elif args.mode.startswith("cal"):
            # HACK to keep the procedure the same; will remove cal in future.
            try:
                subprocess.call(["python","calomatic.py"]+sys.argv[1:], shell=True)
            except KeyboardInterrupt:
                pass
    except KeyboardInterrupt:
        print "\nQuitting..."
    finally:
        utils.releaseLockFile(LOCK_FILE)
 

