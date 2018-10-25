'''
Tool for updating the firmware on a SSX-based data recorder. Requires the
EFM32 CDC USB Serial driver for Windows.

Created on Sep 2, 2015

@author: dstokes
'''

from collections import Sequence
from fnmatch import fnmatch
from glob import glob
import io
import json
import locale
import os.path
import struct
import time
import zipfile

import serial #@UnusedImport
import serial.tools.list_ports

import wx
from wx.lib.throbber import Throbber
from wx.lib.wordwrap import wordwrap

import xmodem

from widgets import device_dialog, html_dialog
import devices
from logger import logger

from mide_ebml.ebmlite import loadSchema

from common import roundUp
from updater import isNewer


# TODO: Better way of identifying valid devices, probably part of the class.
RECORDER_TYPES = [devices.SlamStickC, devices.SlamStickS, devices.SlamStickX]


#===============================================================================
# 
#===============================================================================

def findItem(container, path):
    """ Retrieve an item in a nested dictionary, list, or combination of
        the two.

        @param container: A list or dictionary, possibly containing other
            lists/dictionaries.
        @param path: The 'path' of the item to find, with keys/indices
            delimited by a slash (``/``).
    """
    d = container
    for key in path.strip("\n\r\t /").split('/'):
        if isinstance(d, Sequence):
            key = int(key)
        d = d[key]
    return d


def changeItem(container, path, val):
    """ Replace an item in a nested dictionary, list, or combination of
        the two.

        @param container: A list or dictionary, possibly containing other
            lists/dictionaries.
        @param path: The 'path' of the item to find, with keys/indices
            delimited by a slash (``/``).
        @param val: The replacement value.
    """
    p, k = os.path.split(path.strip("\n\r\t /"))
    parent = findItem(container, p)
    if isinstance(parent, Sequence):
        k = int(k)
    parent[k] = val


#===============================================================================
# 
#===============================================================================

class ValidationError(ValueError):
    """ Exception raised when the firmware package fails validation. Mainly
        provides an easy way to differentiate from other exceptions that can
        be raised, as several failure conditions natively raise the same type.
    """
    def __init__(self, msg, exception=None):
        super(ValidationError, self).__init__(msg)
        self.exception = exception


#===============================================================================
# 
#===============================================================================

class FirmwareUpdater(object):
    """ Object to handle validating firmware files and uploading them to a
        recorder in bootloader mode. A cleaned up version of the code used
        in the birthing script.
        
        Firmware files are zips containing the firmware binary plus additional
        metadata.
    """
    
    PACKAGE_FORMAT_VERSION = 1
    
    MIN_FILE_SIZE = 1024
    PAGE_SIZE = 2048
    
    MAX_FW_SIZE = 507 * 1024
    MAX_BOOT_SIZE = 16 * 1024

    # Default serial communication parameters. Same as keyword arguments to
    # `serial.Serial`.
    SERIAL_PARAMS = {
        'baudrate':     115200, 
        'parity':       'N', 
        'bytesize':     8, 
        'stopbits':     1, 
        'timeout':      5.0,
        'writeTimeout': 5.0, 
    }

    # Double-byte string: "MIDE Technology Corp". Should be found in firmware.
    MIDE_STRING = ('M\x00I\x00D\x00E\x00 \x00T\x00e\x00c\x00h\x00n\x00'
                   'o\x00l\x00o\x00g\x00y\x00 \x00C\x00o\x00r\x00p\x00')
    
    ZIPPW = None
    
    #===========================================================================
    # 
    #===========================================================================
    
    def __init__(self, device=None, filename=None, strict=True):
        """ Constructor.
        
            @keyword device: The `devices.base.Recorder` object to update.
            @keyword filename: The name of the .FW file to use.
            @keyword strict: If `True`, perform more rigorous validation.
        """
        self.strict = strict
        self.device = device
        self.filename = filename
        self.password = self.ZIPPW
        self.info = None
        self.releaseNotes = None
        self.releaseNotesHtml = None
        self.fwBin = None
        self.bootBin = None
        self.lastResponse = None
        
        self.schema_mide = loadSchema('mide.xml')
        self.schema_manifest = loadSchema('manifest.xml')

#         if self.device is not None:
#             self.manifest = device.getManifest()
#             self.cal = device.getFactoryCalPolynomials()
#             self.props = device.getProperties()
#         else:
#             self.manifest = self.cal = self.props = None
        
        if filename is not None:
            self.openFirmwareFile()
        
        
    #===========================================================================
    # 
    #===========================================================================
    
    def validateFirmware(self, fwBin, **kwargs):
        """ Perform basic firmware validation (file size, etc.).
        
            @param fwBin: The firmware binary's data.
            @keyword strict:  If `True`, use more stringent validation tests.
                Overrides the object's `strict` attribute if supplied.
        """
        strict = kwargs.get('strict', self.strict)
        
        fwLen = len(fwBin)
        if fwLen < self.MIN_FILE_SIZE:
            raise ValueError("Firmware binary too small (%d bytes)" % fwLen)
        elif fwLen > self.MAX_FW_SIZE:
            raise ValueError("Firmware binary too large (%d bytes)" % fwLen)
    
        # Sanity check: Make sure the binary contains the expected string
        if strict and self.MIDE_STRING not in fwBin:
            raise ValidationError("Could not verify firmware binary's origin")
        
        return True
    
    
    def validateBootloader(self, bootBin, **kwargs):
        """ Perform basic bootloader validation (file size, etc.).
        
            @param fwBin: The bootloader binary's data.
            @keyword strict:  If `True`, use more stringent validation tests.
                Overrides the object's `strict` attribute if supplied.
        """
        bootLen = len(bootBin)
        if bootLen < self.MIN_FILE_SIZE:
            raise ValueError("Bootloader binary too small (%d bytes)" % bootLen)
        elif bootLen > self.MAX_BOOT_SIZE:
            raise ValueError("Bootloader binary too large (%d bytes)" % bootLen)

        # FUTURE: Additional bootloader validation (raising `ValidationError`)?
        return True

    
    def validateUserpage(self, payload, **kwargs):
        """ Perform basic firmware validation (file size, etc.).
        
            @param fwBin: The userpage EBML data.
            @keyword strict:  If `True`, use more stringent validation tests.
                Overrides the object's `strict` attribute if supplied.
        """
        if len(payload) != self.PAGE_SIZE:
            raise ValueError("Userpage block was %d bytes; should be %d" % \
                             (len(payload), self.PAGE_SIZE))
            
        # FUTURE: Additional userpage validation (raising `ValidationError`)?
        return True
    
    
    def openFirmwareFile(self, **kwargs):
        """ Open a firmware package, and read and test its contents.
        
            @keyword filename: The name of the firmware package. Overrides
                the object's `filename` attribute if supplied.
            @keyword password: The firmware package's zip password (if any).
                Overrides the object's `password` attribute if supplied.
            @keyword strict:  If `True`, use more stringent validation tests.
                Overrides the object's `strict` attribute if supplied.
                
            @raise IOError: If the file doesn't exist, or other such issues
            @raise KeyError: If a file couldn't be found in the zip
            @raise RuntimeError: If the password is incorrect
            @raise ValidationError: If the `info.json` file can't be parsed,
                or the firmware binary fails validation.
            @raise ValueError: If the firmware or bootloader are an invalid
                size.
            @raise zipfile.BadZipfile: If the file isn't a zip
        """
        filename = kwargs.get('filename', self.filename)
        password = kwargs.get('password', self.password)
        strict = kwargs.get('strict', self.strict)
        
        bootBin = None
        
        with zipfile.ZipFile(filename, 'r') as fwzip:
            try:
                fwzip.testzip()
            except RuntimeError as err:
                raise ValidationError('File failed CRC check', err)
                
            self.contents = fwzip.namelist()

            try:
                info = json.loads(fwzip.read('fw_update.json', password))
            except ValueError as err:
                raise ValidationError('Could not read firmware info', err)
            
            packageFormat = info.get('package_format_version', 0)
            if packageFormat > self.PACKAGE_FORMAT_VERSION:
                raise ValueError("Can't read package format version %d" % packageFormat)
            
            appName = info.get('app_name', 'app.bin')
            fwBin = fwzip.read(appName, password)
            self.validateFirmware(fwBin, strict=strict)
            
            bootName = info.get('boot_name', 'boot.bin')
            if bootName in self.contents:
                bootBin = fwzip.read(bootName, password)
                self.validateBootloader(bootBin, strict=strict)

            if 'release_notes.txt' in self.contents:
                self.releaseNotes = fwzip.read('release_notes.txt', password)
            if 'release_notes.html' in self.contents:
                self.releaseNotesHtml = fwzip.read('release_notes.html', password)
            
#             for n in ('release_notes.html', 'release_notes.txt'):
#                 if n in self.contents:
#                     self.releaseNotes = (n,fwzip.read(n, password))
#                     break
        
        self.info = info
        self.fwBin = fwBin
        self.bootBin = bootBin
        self.filename = filename


    def isNewerBootloader(self, vers):
        """ Is the update package's bootloader newer than the one installed?
        """
        try:
            bootVers = self.info.get('boot_version', None)
            if self.bootBin is None or not bootVers:
                return False
            return isNewer(map(int, bootVers.replace('m','.').split('.')),
                           map(int, vers.replace('m','.').split('.')))
        except TypeError:
            return False
        

    def checkCompatibility(self, device=None):
        """ Determine if the loaded firmware package is compatible with a 
            recorder. 
            
            @keyword device: A `Recorder` object. Defaults to the one specified
                when the `FirmwareUpdater` was instantiated.
        """
        device = device if device is not None else self.device
        
        if not any((device.partNumber in d for d in self.contents)):
            raise ValidationError('Device type %s not supported' % device.partNumber)
        
        template = 'templates/%s/%d/*' % (self.device.partNumber, 
                                          self.device.hardwareVersion)

        if not any((fnmatch(x, template) for x in self.contents)):
            raise ValidationError("Device hardware revision %d not supported" % \
                                  self.device.hardwareVersion)
    

    def openRawFirmware(self, filename, boot=None):
        """ Explicitly load a .bin file, skipping all the checks. For Mide use.
        """
        with open(filename, 'rb') as f:
            fwBin = f.read()
        if len(fwBin) < self.MIN_FILE_SIZE:
            raise ValueError("Firmware binary too small (%d bytes)" % len(fwBin))
        if boot is not None:
            with open(boot, 'rb') as f:
                bootBin = f.read()
                if len(bootBin) < self.MIN_FILE_SIZE:
                    raise ValueError("Bootloader binary too small (%d bytes)" % len(bootBin))
        
        self.fwBin = fwBin
        self.bootBin = bootBin
        self.filename = filename


    #===========================================================================
    # 
    #===========================================================================
    
    def findBootloader(self):
        """ Check available serial ports for a Slam Stick in bootloader mode.
            @return: The name of the port, or `None` if no device was found.
        """
        ports = filter(lambda x: 'USB VID:PID=2544:0003' in x[2], 
                       serial.tools.list_ports.comports())
        if len(ports) > 0:
            return ports[0][0]


    def connect(self, portName, **kwargs):
        """ Attempt to establish a connection to a recorder in bootloader mode.
            Takes same keyword arguments as `serial.Serial`.
        """
        portParams = self.SERIAL_PARAMS.copy()
        portParams.update(kwargs)
        self.myPort = serial.Serial(portName, **portParams)
        self.modem = xmodem.XMODEM(self.myPort)

        self.flush()
        vers = self.getVersionAndId()
        if vers is None:
            raise IOError('Could not get ID data from bootloader!')

        self.flush()
        return vers


    def disconnect(self):
        """ Reset the device and close out the port.
        """
        self.myPort.write("r") # reset
        self.myPort.close()
    

    #===============================================================================
    # Low-level bootloader communication stuff
    #===============================================================================
    
    def flush(self):
        """ Flush the serial port.
        """
        if self.myPort.inWaiting():
            return self.myPort.read(self.myPort.inWaiting())


    def sendCommand(self, command, response='Ready'):
        """ Send a command byte.
        
            @param command: The bootloader command character, one of 
                `bcdilmnprtuv`. See SiLabs EFM32 Bootloader docs.
            @keyword response: The expected response. Can be a glob-style
                wildcard.
            @return: `True` if the response matches `response`, `False`
                if the command gets a different response.
        """
        self.myPort.write(command[0]) # make sure it is 1 character.
        self.myPort.readline() # sent character echo
        instring = self.myPort.readline() # 'Ready' response
        self.lastResponse = instring
        if response in instring or fnmatch(instring, response):
            return instring or True
        logger.error('Bootloader: Sent command %r, expected %r but received %r' % (command, response, instring))
        return False


    def _uploadData(self, command, payload, response='Ready'):
        """ Helper method to upload data.
            @see: `FirmwareUpdater.uploadData()`
        """
        self.flush()
        if self.sendCommand(command, response):
            time.sleep(1.0) # HACK: give bootloader some time to catch its breath?

            if not self.modem.send(io.BytesIO(payload)):
                logger.error("Bootloader: File upload failed!")
                return False
            logger.info("Bootloader: Data payload uploaded successfully.")
            return True
        
        return False


    def uploadData(self, command, payload, response='Ready', retries=5):
        """ Helper method to upload data. Will try repeatedly before failing.
        
            @param command: The bootloader command character.
            @param payload: The binary data to upload.
            @keyword response: The expected response from the bootloader.
            @keyword retries: The number of attempts to make.
        """
        ex = None
        for i in xrange(retries):
            try:
                return self._uploadData(command, payload)
            except serial.SerialTimeoutException as ex:
                logger.info('upload got serial timeout on try %d' % (i+1))
                time.sleep(1)
        if ex is not None:
            raise ex
        else:
            raise IOError("Upload failed!")
    
    
    def uploadBootloader(self, payload=None):
        """ Upload a new bootloader binary.
        
            @keyword payload: An alternative payload, to be used instead of the
                object's `bootBin` attribute.
        """
        if payload is None:
            payload = self.bootBin
        else:
            self.validateBootloader(payload, strict=self.strict)
        
        if not payload:
            logger.info('No bootloader binary, continuing...')
            return False
        
        return self.uploadData("d", payload)


    def uploadApp(self, payload=None):
        """ Upload new firmware.
        
            @keyword payload: An alternative payload, to be used instead of the
                object's `fwBin` attribute.
        """
        if payload is None:
            payload = self.fwBin
        else:
            self.validateFirmware(payload, strict=self.strict)

        if not payload:
            logger.info('No firmware binary, continuing...')
            return False
        
        return self.uploadData("u", payload)


    def uploadUserpage(self, payload=None):
        """ Upload the userpage data.
        
            @keyword payload: An alternative payload, to be used instead of the
                object's `payload` attribute.
        """
        if payload is None:
            payload = self.userpage
        else:
            self.validateUserpage(payload, strict=self.strict)

        if not payload:
            logger.info('No USERPAGE data, continuing...')
            return False
        
        return self.uploadData("t", payload)
        
    
    def uploadDebugLock(self):
        if not self.sendCommand("l", "OK"):
            logger.error("Bootloader: Bad response when setting debug lock!")
            return False
        return True
    
    
    def finalize(self):
        """ Apply the finishing touches to the firmware/bootloader/userpage
            update.
        """
        # Bootloader serial connection doesn't need to do anything extra.
        self.disconnect()
    
    
    #===========================================================================
    # 
    #===========================================================================

    @classmethod
    def makeUserpage(self, manifest, caldata, recprops=''):
        """ Combine a binary Manifest, Calibration, and Recorder Properties EBML
            into a unified, correctly formatted userpage block.
    
            USERPAGE memory map:
                0x0000 (2): Offset of manifest, LE
                0x0002 (2): Length of manifest, LE
                0x0004 (2): Offset of factory calibration, LE
                0x0006 (2): Length of factory calibration, LE
                0x0008 (2): Offset of recorder properties, LE
                0x000A (2): Length of recorder properties, LE
                0x000C ~ 0x000F: (RESERVED)
                0x0010: Data (Manifest, calibration, recorder properties)
                0x07FF: End of userpage data (2048 bytes total)
        """
    
        manSize = len(manifest)
        manOffset = 0x0010 # 16 byte offset from start
        calSize = len(caldata)
        calOffset =  manOffset + manSize #0x0400 # 1k offset from start
        propsSize = len(recprops)
        
        if propsSize > 0:
            propsOffset = calOffset + calSize
        else:
            propsOffset = 0
    
        data = struct.pack("<HHHHHH", 
                           manOffset, manSize, 
                           calOffset, calSize,
                           propsOffset, propsSize)
        data = bytearray(data.ljust(self.PAGE_SIZE, '\x00'))
        data[manOffset:manOffset+manSize] = manifest
        data[calOffset:calOffset+calSize] = caldata
        data[propsOffset:propsOffset+propsSize] = recprops
        
        if len(data) != self.PAGE_SIZE:
            # Probably can never happen, but just in case...
            raise ValueError("Userpage block was %d bytes; should be %d" % \
                             (len(data), self.PAGE_SIZE))
        
        return data


    def getVersionAndId(self):
        """ Get the bootloader version and the EFM32 chip UID.
        
            @return: A tuple containing the bootloader version and chip ID.
        """
        self.myPort.write("i")
        # Hack: FW echoes this character (with \n), then another \n, THEN the string.
        for _i in range(3):
            instring = self.myPort.readline()
            if "BOOTLOADER" in instring:
                break
     
        if "BOOTLOADER" not in instring:
            return None
        
        # Grab any salient information from the bootloader string (mainly 
        # CHIPID, but also bootloader version).
        # Example output: "BOOTLOADER version 1.01m2, Chip ID 2483670050B7D82F"
        (bootverstring, chipidstring) = instring.strip().split(",")
        return (bootverstring.rsplit(" ", 1)[-1], 
                chipidstring.rsplit(" ", 1)[-1])


    #===========================================================================
    # 
    #===========================================================================
    
    def readTemplate(self, z, name, schema, password=None):
        """ Read an EBML template from a compressed file.
        
            @param z: The archive (zip) file to read.
            @param name: The name of the EBML file within the zip.
            @param schema: The EBML file's schema.
            @keyword password: The archive password (if any).
        """
        if name not in self.contents:
            return None
        try:
            return schema.loads(z.read(name, password)).dump()
        except (IOError, TypeError):
            logger.info("Error reading %s; probably okay, ignoring.")
            return {}
    
    
    def updateManifest(self):
        """ Generate a new, updated set of USERPAGE data (manifest, calibration,
            and (optionally) userpage).
        """
        templateBase = 'templates/%s/%d' % (self.device.partNumber, self.device.hardwareVersion)
        manTempName = "%s/manifest.template.ebml" % templateBase
        calTempName = "%s/cal.template.ebml" % templateBase
        propTempName = "%s/recprop.template.ebml" % templateBase
        
        with zipfile.ZipFile(self.filename, 'r') as fwzip:
            manTemplate = self.readTemplate(fwzip, manTempName, self.schema_manifest, self.password)
            calTemplate = self.readTemplate(fwzip, calTempName, self.schema_mide, self.password)
            propTemplate = self.readTemplate(fwzip, propTempName, self.schema_mide, self.password)

        if not all((manTemplate, calTemplate)):
            raise ValueError("Could not find template")

        # Collect sensor serial numbers (which are now 'multiple' elements)
        accelSerials = []
        manifest = self.device.getManifest()
        for s in manifest.get('AnalogSensorInfo', []):
            accelSerials.append(s.get('AnalogSensorSerialNumber', None))
            
        manChanges = [
            ('DeviceManifest/SystemInfo/SerialNumber', self.device.serialInt),
            ('DeviceManifest/SystemInfo/DateOfManufacture', self.device.birthday),
        ]
        propChanges = []
        
        # Add (analog) sensor serial numbers to change lists for the manifest
        # and recorder properties. 
        for i, sn in enumerate(accelSerials):
            if sn is None:
                continue
            manChanges.append(('DeviceManifest/AnalogSensorInfo/%d/AnalogSensorSerialNumber' % i, sn))
            propChanges.append(('RecordingProperties/SensorList/Sensor/%d/TraceabilityData/SensorSerialNumber' %i, sn))
        

        # Apply manifest changes
        for k,v in manChanges:
            try:
                changeItem(manTemplate, k, v)
            except (KeyError, IndexError):
                logger.info("Missing manifest item %s, probably okay." %
                            os.path.basename(k))
                pass
            
        # Apply recorder properties changes
        if propTemplate is not None:
            for k,v in propChanges:
                try:
                    changeItem(propTemplate, k, v)
                except (KeyError, IndexError):
                    logger.info("Missing props item %s, probably okay." %
                                os.path.basename(k))
                    pass
        
        # Update transform channel IDs and references
        cal = self.device.getFactoryCalPolynomials()
        calEx = self.device.getFactoryCalExpiration()
        calDate = self.device.getFactoryCalDate()
        calSer = self.device.getFactoryCalSerial()
         
        try:
            polys = findItem(calTemplate, 'CalibrationList/BivariatePolynomial')
        except (KeyError, IndexError):
            polys = None
         
        if polys is not None:
            for p in polys:
                calId = p['CalID']
                if calId in cal:
                    p['PolynomialCoef'] = cal[calId].coefficients
                    p['CalReferenceValue'] = cal[calId].references[0]
                    p['BivariateCalReferenceValue'] = cal[calId].references[1]
        else:
            logger.info("No Bivariate polynomials; expected for SSC.")
         
        try:
            polys = findItem(calTemplate, 'CalibrationList/UnivariatePolynomial')
        except (KeyError, IndexError):
            polys = None
 
        if polys is not None:
            for p in polys:
                calId = p['CalID']
                if calId in cal:
                    p['PolynomialCoef'] = cal[calId].coefficients
                    p['CalReferenceValue'] = cal[calId].references[0]
        else:
            logger.warn("No Univariate polynomials: this should not happen!")
         
        if calEx:
            calTemplate['CalibrationList']['CalibrationSerialNumber'] = calSer
        if calDate:
            calTemplate['CalibrationList']['CalibrationDate'] = int(calDate)
        if calEx:
            calTemplate['CalibrationList']['CalibrationExpiry'] = int(calEx)
        
        # TODO: Remove the calibration updating above, use updateCalibration()
#         calTemplate = self.updateCalibration(calTemplate)
        
        # Build it.
        manData = {'DeviceManifest': manTemplate['DeviceManifest']}
        self.manifest = self.schema_manifest.encodes(manData)
        
        calData = {'CalibrationList': calTemplate['CalibrationList']}
        self.cal = self.schema_mide.encodes(calData)
        
        if propTemplate is not None:
            propData = {'RecordingProperties': propTemplate['RecordingProperties']}
            self.props = self.schema_mide.encodes(propData)
        else:
            self.props = ''
        
        self.userpage = self.makeUserpage(self.manifest, self.cal, self.props)


    def updateCalibration(self, calTemplate):
        """ Update the calibration template using the device's existing values.
        
            @param calTemplate: The calibration template, as nested
                lists/dicts. Note: the template will get modified in place!
        """
        # Update transform channel IDs and references
        cal = self.device.getFactoryCalPolynomials()
        calEx = self.device.getFactoryCalExpiration()
        calDate = self.device.getFactoryCalDate()
        calSer = self.device.getFactoryCalSerial()
        
        try:
            polys = findItem(calTemplate, 'CalibrationList/BivariatePolynomial')
        except (KeyError, IndexError):
            polys = None
        
        if polys is not None:
            for p in polys:
                calId = p['CalID']
                if calId in cal:
                    p['PolynomialCoef'] = cal[calId].coefficients
                    p['CalReferenceValue'] = cal[calId].references[0]
                    p['BivariateCalReferenceValue'] = cal[calId].references[1]
        else:
            logger.info("No Bivariate polynomials; expected for SSC.")
        
        try:
            polys = findItem(calTemplate, 'CalibrationList/UnivariatePolynomial')
        except (KeyError, IndexError):
            polys = None

        if polys is not None:
            for p in polys:
                calId = p['CalID']
                if calId in cal:
                    p['PolynomialCoef'] = cal[calId].coefficients
                    p['CalReferenceValue'] = cal[calId].references[0]
        else:
            logger.warn("No Univariate polynomials: this should not happen!")
        
        if calEx:
            calTemplate['CalibrationList']['CalibrationSerialNumber'] = calSer
        if calDate:
            calTemplate['CalibrationList']['CalibrationDate'] = int(calDate)
        if calEx:
            calTemplate['CalibrationList']['CalibrationExpiry'] = int(calEx)
        
        return calTemplate


#===============================================================================
# 
#===============================================================================

class FirmwareFileUpdater(FirmwareUpdater):
    """ Object to handle validating firmware files and uploading them to a
        recorder via files copied to the device.
        
        Firmware files are zips containing the firmware binary plus additional
        metadata.
    """
    
    def getSpace(self):
        """ Get the space required for the update and the device's free space,
            both rounded up to the device filesystem's block size.
        """
        blockSize = devices.os_specific.getBlockSize(self.device.path)[0]
        
        needed = roundUp(self.PAGE_SIZE, blockSize)
        if self.bootBin:
            needed += roundUp(len(self.bootBin), blockSize)
        if self.fwBin:
            needed += roundUp(len(self.fwBin), blockSize)

        return needed, self.device.getFreeSpace()
        
 
    def isNewerBootloader(self, vers):
        """ Is the update package's bootloader newer than the one installed?
        """
        # There is currently no way to get the bootloader version without
        # entering the bootloader.
        return True
    
    
    def connect(self, *args, **kwargs):
        """ Do preparation for the firmware update. 
        """
        self.clean()
    

    def clean(self):
        """ Remove any old update files.
        """
        for f in (self.device.BOOTLOADER_UPDATE_FILE, 
                  self.device.FW_UPDATE_FILE,
                  self.device.USERPAGE_UPDATE_FILE):
            
            filename = os.path.join(self.device.path, f)
            try:
                if os.path.exists(filename):
                    logger.info('Removing old file: %s' % filename)
                    os.remove(filename)
            except (IOError, WindowsError):
                logger.error('Could not remove file %s' % filename)
                return False
            
        return True
    
    
    def _writeFile(self, filename, content):
        """ Helper method to write to a file on the current device.
        """
        filename = os.path.join(self.device.path, filename)
        try:
            logger.info("Writing %s" % filename)
            with open(filename, 'wb') as f:
                f.write(content)
            return True
        except (IOError, WindowsError) as err:
            logger.error(str(err))
            return False
        
    
    def uploadBootloader(self, payload=None):
        """ Install a new bootloader binary via an update file (specified in 
            the device's `BOOTLOADER_UPDATE_FILE`).
        
            @keyword payload: An alternative payload, to be used instead of the
                object's `bootBin` attribute.
        """
        if payload is None:
            payload = self.bootBin
        else:
            self.validateBootloader(payload)

        if not payload:
            logger.info('No bootloader binary, continuing...')
            return False

        return self._writeFile(self.device.BOOTLOADER_UPDATE_FILE, payload)


    def uploadApp(self, payload=None):
        """ Install new firmware via an update file (specified in the device's
            `FW_UPDATE_FILE`).
        
            @keyword payload: An alternative payload, to be used instead of the
                object's `fwBin` attribute.
        """
        if payload is None:
            payload = self.fwBin
        else:
            self.validateFirmware(payload)
        
        if not payload:
            logger.info('No firmware binary, continuing...')
            return False

        return self._writeFile(self.device.FW_UPDATE_FILE, payload)


    def uploadUserpage(self, payload=None):
        """ Install new userpage data via an update file (specified in the 
            device's `USERPAGE_UPDATE_FILE`).
        
            @keyword payload: An alternative payload, to be used instead of the
                object's `userpage` attribute.
        """
        if payload is None:
            payload = self.userpage
        else:
            self.validateUserpage(payload)
            
        if not payload:
            logger.info('No USERPAGE data, continuing...')
            return False

        return self._writeFile(self.device.USERPAGE_UPDATE_FILE, payload)


    def finalize(self):
        """ Apply the finishing touches to the firmware/bootloader/userpage
            update.
        """
        with open(self.device.commandFile, 'wb') as f:
            f.write('ua')
    

    def disconnect(self):
        """ Reset the device.
        """
        # Doesn't actually reset, since the device isn't in bootloader mode.
        self.clean()


#===============================================================================
# 
#===============================================================================

class FirmwareUpdateDialog(wx.Dialog):
    """ UI for uploading new firmware to a SSX/SSC/etc. recorder.
    """
    
    SCAN_MS = 250
    TIMEOUT_MS = 60000    
    
    @classmethod
    def driverInstalled(cls):
        """ Utility method to perform a basic check for the EFM32 USB serial
            driver. Not especially robust.
        """
        if wx.Platform == '__WXMSW__':
            win = wx.PlatformInformation_GetOperatingSystemDirectory()
            for inf in glob(os.path.join(win, 'inf', 'oem*.inf')):
                try:
                    with open(inf, 'rb') as f:
                        for l in f:
                            # Different versions use different names
                            if 'EFM32 USB' in l or 'Silicon Labs CDC' in l:
                                logger.info("Identified possible driver: %s" % inf)
                                return True
                except WindowsError:
                    pass
            return False
        else:
            logger.info('No serial driver required if not running Windows.')
            return True
    
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Dialog` arguments, plus:
            
            @keyword firmware: The firmware file to upload.
            @keyword device: The `devices.base.Recorder` subclass instance to
                update.
        """
        self.firmware = kwargs.pop('firmware', None)
        self.device = kwargs.pop('device', None)
        self.useFiles = kwargs.pop('useFiles', False)
        kwargs.setdefault('style', wx.CAPTION|wx.CENTRE)
        kwargs.setdefault('title', "Update Firmware")
        
        wx.Dialog.__init__(self, *args, **kwargs)#, parent, -1)
        self.SetBackgroundColour("WHITE")
        
        frameFiles = glob(os.path.join(os.path.dirname(__file__), '..',
                                       'resources','ssx_throbber*.png'))
        frames = [wx.Image(f, wx.BITMAP_TYPE_PNG).ConvertToBitmap() for f in frameFiles]
        self.throbber = Throbber(self, -1, frames, rest=0, frameDelay=1.0/len(frames))
        
        headerText = "Please Stand By..."
        messageText = "\n"*4
        
        self.header = wx.StaticText(self, -1, headerText, size=(400,40), 
                                    style=wx.ALIGN_CENTRE_HORIZONTAL)
        self.header.SetFont(self.GetFont().Bold().Scaled(1.5))
        self.message = wx.StaticText(self, -1, messageText, size=(400,40), 
                                     style=wx.ALIGN_CENTRE_HORIZONTAL)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.Panel(self, -1), 0, wx.EXPAND)
        sizer.Add(self.throbber, 0, wx.ALIGN_CENTER)
        sizer.Add(self.header, 0, wx.ALIGN_CENTER | wx.EXPAND)
        sizer.Add(self.message, 0, wx.ALIGN_CENTER)
        sizer.Add(wx.Panel(self, -1), 1, wx.EXPAND)
        
        b = wx.Button(self, wx.ID_CANCEL)
        sizer.Add(b, 0, wx.EXPAND)
        
        self.scanTimer = wx.Timer(self)
        self.timeoutTimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.checkSerial, self.scanTimer)
        self.Bind(wx.EVT_TIMER, self.OnTimeout, self.timeoutTimer)

        self.SetSizerAndFit(sizer)
        self.SetSizeWH(400,-1)

        if "LOG-0002" in self.device.partNumber:
            self.but = '"X"'
        elif "LOG-0003" in self.device.partNumber:
            self.but = '"C"'
        elif "LOG-0004" in self.device.partNumber:
            self.but = '"S"'
        else:
            self.but = 'main'
    
        if isinstance(self.firmware, FirmwareFileUpdater):
            self.setLabels('Starting firmware update...')
            self.updateFirmware()
        else:
            self.startSerialScan()

    
    def setLabels(self, title=None, msg=None):
        """ Helper method to display a new message.
        """
        changed = False
        if title is not None and title != self.header.GetLabelText():
            logger.info(title)
            self.header.SetLabelText(title)
            changed = True
        if msg is not None and msg != self.message.GetLabelText():
            self.message.SetLabelMarkup(wordwrap(msg, 350, wx.ClientDC(self)))
            changed = True
        if changed:
            self.Update()
        
    
    def startSerialScan(self):
        """ Start searching for a recorder in bootloader mode.
        """
        self.setLabels("Waiting for Recorder...",
                        "Press and hold the recorder's %s button "
                        "for 3 seconds." % self.but)
        
        self.throbber.Start()
        self.scanTimer.Start(self.SCAN_MS)
        self.timeoutTimer.Start(self.TIMEOUT_MS)


    def checkSerial(self, evt):
        """ Timer event handler to look for a bootloader serial connection.
        """
        if not os.path.exists(self.device.path):
            self.setLabels(msg="Release the recorder's %s button now!" % 
                           self.but)
            
        s = self.firmware.findBootloader()
        if s is None:
            return

        logger.info("Found possible device on %s" % s)
        
        self.timeoutTimer.Stop()
        self.scanTimer.Stop()
        self.throbber.Rest()        
        
        connected = False
        for i in range(3):
            try:
                c = self.firmware.connect(s)
                connected = True
                logger.info('Connected to bootloader {}'.format(c))
                break
            except IOError as err:
                logger.error("Connection failure, try %d: %s" % (i+1,err))
                wx.Sleep(1)
        
        if not connected:
            x = wx.MessageBox("Unable to connect to recorder\n\n"
                              "Please disconnect the recorder, re-attach, "
                              "and press and hold the button", 
                              "Connection Error", wx.OK|wx.CANCEL)
            if x != wx.OK:
                self.Close()
                return
            
            self.startSerialScan()
            return
        
        logger.info("Connected to bootloader.")
        self.updateFirmware()
                

    def OnTimeout(self, evt):
        """ Handle serial scan timeout.
        """
        self.throbber.Rest()        
        self.scanTimer.Stop()
        self.timeoutTimer.Stop()
        wx.MessageBox("No recording device was found.\n\n"
                      "Make sure the required driver has been installed and "
                      "try again.", "No Device Found", wx.OK|wx.ICON_ERROR)
        self.Close()


    def updateFirmware(self):
        """ Perform the firmware/userpage and/or bootloader update.
        """
        self.setLabels(msg="Do not disconnect your recorder!")
        msg = "performing the update"
        
        wx.Sleep(1)
        try:
            msg = "uploading the bootloader"
            self.setLabels("%s..." % msg.title())
            self.firmware.uploadBootloader()
            wx.MilliSleep(500)
            
            msg = "uploading the Slam Stick firmware"
            self.setLabels("%s..." % msg.title())
            self.firmware.uploadApp()
            wx.MilliSleep(500)
            
            msg = "uploading Manifest data"
            self.setLabels("%s..." % msg.title())
            self.firmware.uploadUserpage()

            try:
                self.firmware.finalize()
                wx.MilliSleep(250)
            except IOError:
                pass
            
            wx.MessageBox("Firmware Update Complete!\n\n"
                          "You may now disconnect your recorder.", 
                          "Update Complete")
            
        except (ValueError, IOError) as err:
            logger.error(str(err))
            try:
                self.firmware.disconnect()
            except IOError:
                pass
            wx.MessageBox("Firmware update failed!\n\n"
                          "The update failed while %s. \n"
                          "Please try again." % msg,
                          "Update Failure", wx.OK|wx.ICON_ERROR)
        
        self.Close()


    @classmethod
    def showReleaseNotes(cls, firmware, parent=None):
        """
        """
        if firmware.releaseNotesHtml:
            content = firmware.releaseNotesHtml
        elif firmware.releaseNotes:
            # Plain text release notes. Do basic fixes for HTML display.
            content = firmware.releaseNotes.replace('\n', '<br/>')
        else:
            content = None
        
        if not content:
            return
        
        title = "%s Release Notes" % os.path.basename(firmware.filename)
        dlg = html_dialog.HtmlDialog(parent, content, title, setBgColor=False)
        dlg.Center()
        dlg.ShowModal()
            

#===============================================================================
# 
#===============================================================================

def updateFirmware(parent=None, device=None, filename=None, useFiles=True):
    """ Wrapper for starting the firmware update.
        
        @keyword parent: The parent window.
        @keyword device: The device to configure. If `None`, the user is
            prompted to select one.
        @keyword filename: The firmware update package to use. If `None`, the
            user will be prompted to select one.
        @keyword useFiles: If `True`, the filesystem-based update will be
            used with devices that support it. If `False`, the serial-based
            method will be used for all devices.
    """
    if len(devices.getDevices()) > 1:
        # warn user.
        wx.MessageBox("Multiple recorders found!\n\n"
                      "It is strongly recommended that you remove all "
                      "recorders except the one you wish to update.", 
                      "Update Firmware", parent=parent)
    if device is None:
        device = device_dialog.selectDevice(parent=parent, types=RECORDER_TYPES,
                        showWarnings=False, hideClock=True, hideRecord=True, 
                        okHelp="Start firmware update on selected device",
                        okText="Update")
    if device is None:
        return False
    
    logger.info("Device: %s, SN: %s, FwRev: %r" % (device.productName, 
                                                   device.serial, 
                                                   device.firmwareVersion))
    
    useFiles = useFiles and device.canCopyFirmware
    
    if useFiles:
        logger.info("Preparing to use file transfer update method")
    else:
        logger.info("Searching for EFM32 USB CDC Serial driver...")
        if not FirmwareUpdateDialog.driverInstalled():
            x = wx.MessageBox(
                "A basic system test could not locate the required driver.\n\n"
                "This test is not perfect, however, and could be inaccurate. "
                "If you know you have already installed the driver "
                "successfully, press OK.", 
                "No Driver?", parent=parent, style=wx.OK|wx.CANCEL)#|wx.HELP)
#             if x == wx.HELP:
#                 wx.MessageBox("No help yet.", "Firmware Update Help")
#                 return
            if x != wx.OK:
                return False
        
    if filename is None:
        dlg = wx.FileDialog(parent, message="Select a Slam Stick Firmware File",
                            wildcard="MIDE Firmware Package (*.fw)|*.fw",
                            style=wx.OPEN | wx.CHANGE_DIR)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
        
    if filename is None:
        return False
    
    try:
        if useFiles:
            update = FirmwareFileUpdater(device, filename)
            
            need, free = update.getSpace()
            need = roundUp(need, 1024)/1024
            free = roundUp(free, 1024)/1024
            if need > free:
                free = locale.format("%d", free, grouping=True)
                need = locale.format("%d", need, grouping=True)
                wx.MessageBox(
                  "The selected device does not have enough free space to update."
                  "\n\nAt least %s KB required; only %s KB is free. Please delete "
                  "some data from %s and try again." % (need, free, device.path), 
                  "Firmware Update Error", parent=parent)
                return False
        else:
            update = FirmwareUpdater(device, filename)
            
        logger.info("Passed basic validation")
        
    except (ValidationError, ValueError, KeyError) as err:
        # Various causes
        logger.error(str(err))
        if "CRC" in str(err.message):
            msg = ("This firmware update package appears to be damaged "
                   "(CRC test of contents failed).")
        else:
            msg = ("This firmware update package appears to be missing vital "
                   "components, and is likely damaged.")
        wx.MessageBox(msg, "Validation Error", parent=parent)
        return False
    
    except IOError as err:
        # Bad file
        logger.error(str(err))
        wx.MessageBox("This firmware update package could not be read.", 
                      "Validation Error", parent=parent)
        return False
    
    except RuntimeError as err:
        # Bad password
        logger.error(str(err))
        wx.MessageBox("This firmware update package could not be authenticated.", 
                      "Validation Error", parent=parent)
        return False

    FirmwareUpdateDialog.showReleaseNotes(update, parent)
        
    try:
        update.checkCompatibility()
        logger.info("Passed compatibility check")
    except ValidationError as err:
        msg = err.message.rstrip('.')+'.'
        wx.MessageBox(msg, "Compatibility Error")
        return

    updateVer = update.info['app_version']
    if updateVer <= device.firmwareVersion:
        msg = ("This update package contains firmware version %d.\n"
               "Your recorder is running firmware version %d." % 
               (updateVer, device.firmwareVersion))
        if updateVer < device.firmwareVersion:
            msg += "\nUpdating with older firmware is not recommended."
        dlg = wx.MessageBox("%s\n\nContinue?" % msg, "Old Firmware", 
                            wx.OK|wx.CANCEL|wx.ICON_WARNING)
        if dlg != wx.OK:
            return

    logger.info("Creating updated manifest data")
    update.updateManifest()
    
    dlg = FirmwareUpdateDialog(parent, device=device, firmware=update,
                               useFiles=useFiles)
    dlg.ShowModal()
    
        
#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    app = wx.App()
    print updateFirmware()
