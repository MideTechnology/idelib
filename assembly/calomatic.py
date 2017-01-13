'''
Slam Stick X/C/etc. Calibration Script. Originally part of the birthomatic.

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


Created on Nov 10, 2014

@author: dstokes
'''

from collections import OrderedDict
from datetime import datetime, timedelta
from glob import glob
import os.path
import shutil
import sys
import time

#===============================================================================
# Rigmarole to ensure the right libraries are located.
#===============================================================================

from birthomatic import VIEWER_PATH

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

#===============================================================================
# 
#===============================================================================

import devices
from mide_ebml import xml2ebml

import firmware
import calibration
import birth_utils as utils

from birthomatic import RECORDER_NAME, DC_DEFAULT_SAMPLE_RATE
from birthomatic import TEMPLATE_PATH
from birthomatic import DB_PATH, CONTENT_PATH, BIRTH_LOG_FILE
from birthomatic import DB_LOG_FILE, DB_BAD_LOG_FILE
from birthomatic import CAL_PATH, CAL_SN_FILE

LOCK_FILE = os.path.join(DB_PATH, 'cal_in_use')

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
    
    if not os.path.exists(contentPath):
        contentPath = os.path.join(DB_PATH, "_LOG-0002_Contents")
    
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


def setDCSampleRate(dev, sampRate=DC_DEFAULT_SAMPLE_RATE):
    # Change default DC sample rate
    if dev.getAccelChannel(dc=True):
        print "Setting default DC accelerometer sample rate (%s Hz)..." % sampRate 
        conf = dev.getConfig()
        conf['SSXChannelConfiguration'] = [
            OrderedDict([('ChannelSampleFreq', sampRate), 
                         ('ConfigChannel', 32), 
                         ('SubChannelEnableMap', 7)])]
        dev.saveConfig(conf)
    

#===============================================================================
# 
#===============================================================================

def calibrate(devPath=None, rename=True, recalculate=False, certNum=None,
              noCopy=False, writeLog=True):
    """ Do all the post-shaker stuff: calculate calibration constants, 
        copy content, et cetera.
        
        @todo: consider modularizing this more for future re-usability. This has
            grown somewhat organically.
    """
    startTime = time.time()
    totalTime = 0
    
    #  1. Wait for an SSX in drive mode (see ssx_namer)
    if devPath is None:
        print "*" * 60
        print "Starting Slam Stick Auto-Calibration. Attach a Slam Stick to calibrate now."
        print "*" * 60
        print "Waiting for a recorder...",
        dev = utils.waitForRecorder(timeout=None)
        devPath = dev.path
    else:
        dev = devices.getRecorder(devPath)
        if dev is None:
            utils.errMsg( "!!! Specified path %s is not a Slam Stick device!")
            return
    if not isinstance(dev, devices.SlamStickX):
        raise NotImplementedError("Not a Slam Stick X derivative?")
    
    print
    print "*" * 60
    print "Starting Auto-Calibration of %s on %s." % (dev.baseName, devPath)
    print "*" * 60

    try:
        certTemplate = calibration.Calibrator.getCertTemplate(dev)
    except (ValueError, IOError) as err:
        print "!!! %s" % err
        totalTime += time.time() - startTime
        q = utils.getYesNo("No certificate will be generated (and calibration may fail). Continue (Y/N)? ")
        startTime = time.time()
        if q == 'Y':
            exit(0)
        certTemplate = None
    

    if dev.serial is None:
        utils.errMsg( "!!! Could not get serial number from recorder on %s" % devPath)
        return
        
    # Set recorder clock
    print "Setting device clock..."
    dev.setTime()
    
    #  2. Create serial number directory in product_database/_Calibration
    calDirName = os.path.realpath(os.path.join(CAL_PATH, dev.serial))
    if not os.path.exists(calDirName):
        print "Calibration directory %s does not exist; attempting to create..." % dev.serial
        os.mkdir(calDirName)
    
    #  2. Read device info to get serial number.
    if certNum is None:
        certNum = utils.readFileLine(CAL_SN_FILE)+1
        writeCertNum = True
    else:
        writeCertNum = False
    calRev = utils.readFileLine(os.path.join(CAL_PATH, 'cal_rev.txt'), str, default='C')
    
    print "Recorder SN: %s, calibration SN: %s" % (dev.serial, certNum)
    
    print "Reading birth log data..."
    birthFile = os.path.join(CAL_PATH, dev.serial, 'birth_log.txt')
    try:
        if not os.path.exists(birthFile):
            # Possibly birthed by old script; copy data from main log.
            birthInfo = utils.findBirthLog(BIRTH_LOG_FILE, val=dev.serialInt)
            if not birthInfo:
                utils.errMsg("Could not get birth log info from either file:",
                             birthFile, BIRTH_LOG_FILE)
                return
            logline = utils.makeBirthLogEntry(*birthInfo.values()[2:])
            if writeLog:
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

    # Make convenience shortcuts
    try:
        utils.makeShortcut(chipDirName, calDirName)
        utils.makeShortcut(calDirName, chipDirName)
    except Exception:
        # Naked exceptions are bad medicine. 
        pass

    try:
        volNameFile = os.path.join(*map(str, (TEMPLATE_PATH, birthInfo['partNum'], 'volume_name.txt')))
        volName = utils.readFileLine(volNameFile, str, default=RECORDER_NAME)
    except (TypeError, KeyError, WindowsError, IOError) as err:
        volName = RECORDER_NAME

    calTemplateName = os.path.join(chipDirName, 'cal.template.xml')
    calCurrentName = os.path.join(chipDirName, 'cal.current.ebml')
    calBackupPath = os.path.join(chipDirName, str(certNum))
    docsPath = os.path.join(devPath, 'DOCUMENTATION')
    
    compute = True
    
    calCurrentXml = utils.changeFilename(calCurrentName, ext='.xml')
    if os.path.exists(calCurrentXml) and os.path.exists(calTemplateName) and not recalculate:
        # TODO: Comparing the XML is brittle; comparing EBML would be better.
        try:
            curr = utils.readFile(calCurrentXml)
            temp = utils.readFile(calTemplateName) 
        except IOError:
            curr = 0
            temp = 1
        if curr != temp:
            # Calibration EBML exists; recalculate anyway?
            totalTime += time.time() - startTime
            q = utils.getYesNo("\x07\x07Calibration data already exists! Recompute (Y/N)? ")
            startTime = time.time()
            compute = q == 'Y'
    else:
        compute = True

    #-------------------------------------------------------------------------- 
    # THE DEVICE-SPECIFIC STUFF IS HERE:
    if compute:
        copyfiles = calibrateSSX(dev, certNum, calRev, calDirName, 
                                 calTemplateName, calCurrentName, calCurrentXml,
                                 recalculate, writeCertNum, certTemplate)
    
        if not copyfiles:
            return
    #-------------------------------------------------------------------------- 

    else:
        copyfiles = []
        certFiles = glob(os.path.join(calDirName, '*.pdf'))
        if certFiles:
            copyfiles = [certFiles[-1]]
    
    if os.path.exists(calCurrentName):
        caldata = utils.readFile(calCurrentName)

        if not os.path.exists(calBackupPath):
            os.mkdir(calBackupPath)
            utils.writeFile(os.path.join(calBackupPath, 'cal.ebml'), caldata)
    else:
        print "No calibration EBML data, continuing..."
        caldata = ''

    # 11. Copy documentation and software folders
    copyStart = datetime.now()
    if noCopy:
        print "Not copying standard contents."
        if not os.path.isdir(docsPath):
            print "Creating directory %s..." % docsPath
            os.mkdir(docsPath)
    else:
        print "Copying standard %s content to device..." % dev.partNumber
        copyContent(devPath, dev.partNumber)
    print "Copying calibration documentation to device..."
    for filename in copyfiles:
        utils.copyFileTo(filename, docsPath)
    copyTime = datetime.now()-copyStart
    
    print "Removing old DATA directory from device..."
    try:
        shutil.rmtree(os.path.join(devPath, "DATA"))
    except WindowsError:
        pass
    
    print "Changing the volume name..."
    if os.system('label %s %s' % (devPath.strip("\\"), volName)) != 0:
        print "!!! Couldn't rename %s, continuing..."

    # Reset the DC accelerometer sample rate (if present)
    setDCSampleRate(dev)
    
    print """\x07Press and hold the %s's "%s" button to enter bootloader mode.""" % (dev.baseName, dev.baseName.split()[-1])
    # Don't count the time spent waiting for the user to press the button.
    totalTime += (time.time() - startTime)
    ssxboot = None
    while ssxboot is None:
        ssxboot = firmware.getBootloaderSSX(callback=utils.spinner)
        if ssxboot is None:
            print "Could not connect! Disconnect the recorder and try again!"
            
    # Reset startTime to resume counting elapsed time
    startTime = time.time()
    
    print "Uploading updated manifest and calibration data..."
    manifest = utils.readFile(os.path.join(chipDirName, 'manifest.ebml'))
    try:
        recprops = utils.readFile(os.path.join(chipDirName, 'recprop.ebml'))
    except IOError:
        recprops = ''
    ssxboot.sendUserpage(manifest, caldata, recprops)
     
    print "Disconnecting from bootloader mode..."
    ssxboot.disconnect()
    utils.waitForSSX(timeout=10)
    
    totalTime += (time.time() - startTime)
    totalTime = str(timedelta(seconds=int(totalTime)))
    copyTime = str(copyTime).rsplit('.',1)[0]
    print "*" * 60
    print "\x07%s SN:%s calibration complete!" % (dev.baseName, dev.serial)
    print "    Calibration SN:", certNum
    print "       Part Number:", dev.partNumber
    print "       Hardware ID:", chipId
    print "  Accelerometer SN:", birthInfo.get('accelSerialNum', None)
    print "Total time: %s (%s spent copying files)" % (totalTime, copyTime)
    print "Please disconnect the %s now." % dev.baseName


#------------------------------------------------------------------------------ 

def calibrateSSX(dev, certNum, calRev, calDirName, calTemplateName, 
                 calCurrentName, calCurrentXml, recalculate, writeCertNum,
                 certTemplate=None, writeLog=True):
    """ Do all the post-shaker stuff: calculate calibration constants, 
        copy content, et cetera.
        
        @todo: consider modularizing this more for future re-usability. This has
            grown somewhat organically.
    """
    devPath = dev.path

    c = calibration.Calibrator(devPath, certNum, calRev, isUpdate=recalculate)

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
            if writeLog:
                c.writeProductLog(DB_BAD_LOG_FILE, err="No DATA directory")
            return
    
#     totalTime += time.time() - startTime
    try:
        hum = utils.readCalLog(DB_LOG_FILE).get('Rel. Hum. (%)', calibration.DEFAULT_HUMIDITY)
    except (ValueError, TypeError, AttributeError, IOError):
        hum = calibration.DEFAULT_HUMIDITY
    c.calHumidity = utils.getNumber("Humidity at recording time (default: %.2f)? " % hum, default=hum)
#     startTime = time.time()
    
    print "Copying calibration recordings from device..."
    if copyData:
        utils.copyTreeTo(dataDir, dataCopyDir)
    utils.copyTreeTo(os.path.join(devPath, "SYSTEM"), os.path.join(calDirName, "SYSTEM"))
    
    #  3. Generate calibration data from IDE files on recorder (see calibration.py)
    sourceFiles = c.getFiles(calDirName)
    if len(sourceFiles) != 3:
        if writeLog:
            c.writeProductLog(DB_BAD_LOG_FILE, err="Wrong number of files (%d)" % len(sourceFiles))
        utils.errMsg(["!!! Wrong number of recordings found (need 3, found %d)!" % len(sourceFiles)])
        return

    print "Calculating calibration constants from recordings..."
    c.calculate(sourceFiles)
    c.closeFiles()
    
    if None in (c.Sxy, c.Syz, c.Sxz):
        result = ["!!! Error in calculating transverse sensitivity (bad file?)"]
        result.append("Only found the following:")
        if c.Sxy is not None:
            result.append("%s, Transverse Sensitivity in XY = %.2f percent" % (c.Sxy_file, c.Sxy))
        if c.Syz is not None:
            result.append("%s, Transverse Sensitivity in YZ = %.2f percent" % (c.Syz_file, c.Syz))
        if c.Sxz is not None:
            result.append("%s, Transverse Sensitivity in ZX = %.2f percent" % (c.Sxz_file, c.Sxz))
            
        if writeLog:
            c.writeProductLog(DB_BAD_LOG_FILE, err="Bad Transverse")
        utils.errMsg(*result)
        return
    
    if any((x > 10 for x in (c.Sxy, c.Syz, c.Sxz))):
        print "!!! Extreme transverse sensitivity detected in recording(s)!"
        print "%s, Transverse Sensitivity in XY = %.2f percent" % (c.Sxy_file, c.Sxy)
        print "%s, Transverse Sensitivity in YZ = %.2f percent" % (c.Syz_file, c.Syz)
        print "%s, Transverse Sensitivity in ZX = %.2f percent" % (c.Sxz_file, c.Sxz)
        q = utils.getYesNo("Continue with device calibration (Y/N)? ")
        if q == "N":
            if writeLog:
                c.writeProductLog(DB_BAD_LOG_FILE, err="Transverse out of range")
            return
        if writeLog:
            c.writeProductLog(DB_BAD_LOG_FILE, err="High transverse warning (process continued)")
    
    if not utils.allInRange([x.cal_temp for x in c.calFiles], 15, 27):
        print "!!! Extreme temperature detected in recording(s)!"
        for x in c.calFiles:
            print "%s: %.2f degrees C" % (os.path.basename(x.filename), x.cal_temp)
        q = utils.getYesNo("Continue with device calibration (Y/N)? ")
        if q == "N":
            if writeLog:
                c.writeProductLog(DB_BAD_LOG_FILE, err="Temperature out of range")
            return
        if writeLog:
            c.writeProductLog(DB_BAD_LOG_FILE, err="Temp. out of range warning (process continued)")
        
        
    if not utils.allInRange([x.cal_press for x in c.calFiles], 96235, 106365):
        print "!!! Extreme air pressure detected in recording(s)!"
        for x in c.calFiles:
            print "%s: %.2f Pa" % (os.path.basename(x.filename), x.cal_press)
        q = utils.getYesNo("Continue with device calibration (Y/N)? ")
        if q == "N":
            if writeLog:
                c.writeProductLog(DB_BAD_LOG_FILE, err="Pressure out of range")
            return
        if writeLog:
            c.writeProductLog(DB_BAD_LOG_FILE, err="Pressure out of range warning (process continued)")
    
    print c.createTxt()
    
    if c.hasHiAccel and not utils.allInRange(c.cal, 0.5, 2.5, absolute=True):
        print "!!! Out-of-range calibration coefficient(s) detected!"
        q = utils.getYesNo("Continue with device calibration (Y/N)? ")
        if q == "N":
            if writeLog:
                c.writeProductLog(DB_BAD_LOG_FILE, err="Coefficient(s) out of range")
            return
        if writeLog:
            c.writeProductLog(DB_BAD_LOG_FILE, err="Coefficient(s) out of range warning (process continued)")
    
    if c.hasLoAccel and not utils.allInRange(c.calLo, 0.5, 2.5):
        print "!!! Out-of-range calibration coefficient(s) detected for DC accelerometer!"
        q = utils.getYesNo("Continue with device calibration (Y/N)? ")
        if q == "N":
            if writeLog:
                c.writeProductLog(DB_BAD_LOG_FILE, err="Coefficient(s) out of range (DC)")
            return        
        if writeLog:
            c.writeProductLog(DB_BAD_LOG_FILE, err="Coefficient(s) (DC) out of range warning (process continued)")
    
    print "Building calibration EBML..."
    caldata = c.createEbml(calTemplateName)
    utils.writeFile(calCurrentName, caldata)
    
    # Create current calibration XML
    try:
        calXml = xml2ebml.dumpXmlElement(xml2ebml.readEbml(caldata, schema='mide_ebml.ebml.schema.mide').roots[0])
        utils.writeFile(calCurrentXml, calXml)
    except (IndexError, AttributeError) as err:
        print "!!! Problem writing calibration XML: %s"  % err.message
        print "!!! Ignoring the problem and continuing..."
        pass
    
    #  4. Generate calibration certificate
    print "Creating documentation: text file, ",
    c.createTxt(calDirName)
    print "calibration recording plots,",
    c.createPlots(calDirName)
    
    copyfiles = []
    
    # BUG: TODO: This sometimes fails and takes Python with it. Move to end.
    if certTemplate:
        print "certificate PDF"
        certFile = c.createCertificate(calDirName, template=certTemplate)
        copyfiles.append(certFile)
    else:
        print "skipping certificate generation"
    
    if writeLog:
        print "Writing to product 'database' spreadsheet..."
        c.writeProductLog(DB_LOG_FILE)
        
        if writeCertNum:
            print "Incrementing calibration serial number..."
            utils.writeFileLine(CAL_SN_FILE, certNum)
    
    else:
        print "NOT writing to product 'database' spreadsheet!"

    return copyfiles


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse
#     global TEMPLATE_PATH
    
    parser = argparse.ArgumentParser(description="Improved SSX Calibration Suite")
    parser.add_argument("mode", help="(for backwards compatibility; has no effect)", nargs="*")
    parser.add_argument("--templates", "-t", help="An alternate birth template directory.", default=TEMPLATE_PATH)
    parser.add_argument("--nocopy", "-n", help="Do not copy software to SSX after calibration.", action='store_true')
    parser.add_argument("--exclude", "-x", help="Exclude this birth/calibration from the log (for testing only!)", action='store_true')
    args = parser.parse_args()
    
    TEMPLATE_PATH = args.templates
    
    print "*" * 78
    print "Starting Slam Stick X calibration script." 
    print "*" * 78
    
    if not utils.checkLockFile(LOCK_FILE):
        exit(0)
        
    try:
        noCopy = args.nocopy is True
        writeLog = args.exclude is not True
        calibrate(noCopy=noCopy, writeLog=writeLog)
    except KeyboardInterrupt:
        print "Quitting..."
    finally:
        utils.releaseLockFile(LOCK_FILE)