'''

TODO: Make sure all data is loaded/generated before anything gets uploaded.

Created on Sep 2, 2015

@author: dstokes
'''
from fnmatch import fnmatch
import io
import json
import os.path
import struct
import time

import serial #@UnusedImport
import serial.tools.list_ports
import zipfile

import wx
import wx.lib.sized_controls as SC

import xmodem

import device_dialog
import devices
from logger import logger
from mide_ebml import util
import mide_ebml.ebml.schema.mide as schema_mide
import mide_ebml.ebml.schema.manifest as schema_manifest

from updater import isNewer

#===============================================================================
# 
#===============================================================================

def findItem(container, path):
    d = container
    for key in path.strip("\n\r\t /").split('/'):
        try:
            d = d[key]
        except TypeError:
            d = d[int(key)]
    return d


def changeItem(container, path, val):
    p, k = os.path.split(path.strip("\n\r\t /"))
    return findItem(p)[k]


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

    # Default serial communication parameters. Same as keyword arguments to
    # `serial.Serial`.
    SERIAL_PARAMS = {
        'baudrate':     115200, 
        'parity':       'N', 
        'bytesize':     8, 
        'stopbits':     1, 
        'timeout':      1.0, 
    }

    # Double-byte string: "MIDE Technology Corp". Should be found in firmware.
    MIDE_STRING = ('M\x00I\x00D\x00E\x00 \x00T\x00e\x00c\x00h\x00n\x00'
                   'o\x00l\x00o\x00g\x00y\x00 \x00C\x00o\x00r\x00p\x00')
    
    ZIPPW = None
    
    #===========================================================================
    # 
    #===========================================================================
    
    def __init__(self, device=None, filename=None, strict=True):
        self.device = device
        self.filename = filename
        self.password = self.ZIPPW
        self.info = None
        self.releaseNotes = None
        self.fwBin = None
        self.bootBin = None
        self.lastResponse = None
        
#         if self.device is not None:
#             self.manifest = device.getManifest()
#             self.cal = device.getFactoryCalPolynomials()
#             self.props = device.getProperties()
#         else:
#             self.manifest = self.cal = self.props = None
        
        if filename is not None:
            self.openFirmwareFile(filename, self.password, strict)
        
        
    #===========================================================================
    # 
    #===========================================================================
    
    def _readItem(self, z, name, pw=None):
        """ Helper method to read an item from a zip. """
        with z.open(name, 'r', pw) as f:
            return f.read()


    def openFirmwareFile(self, filename=None, password=None, strict=True):
        """
            @raise zipfile.BadZipfile: If the file isn't a zip
            @raise ValidationError: If the `info.json` file can't be parsed
            @raise KeyError: If a file couldn't be found in the zip
            @raise IOError: If the file doesn't exist, or other such issues
            @raise RuntimeError: If the password is incorrect
        """
        bootBin = None
        
        with zipfile.ZipFile(filename, 'r') as fwzip:
            try:
                fwzip.testzip()
            except RuntimeError as err:
                raise ValidationError('File failed CRC check', err)
                
            self.contents = contents = fwzip.namelist()

            try:
                info = json.loads(fwzip.read('fw_update.json', password))
            except ValueError as err:
                raise ValidationError('Could not read firmware info', err)
            
            fwBin = fwzip.read('app.bin', password)
            if len(fwBin) < self.MIN_FILE_SIZE:
                raise ValueError("Firmware binary too small (%d bytes)" % len(fwBin))
            
            if 'boot.bin' in contents:
                bootBin = fwzip.read('boot.bin', password)
                if len(bootBin) < self.MIN_FILE_SIZE:
                    raise ValueError("Bootloader binary too small (%d bytes)" % len(bootBin))

            for n in ('release_notes.html', 'release_notes.txt'):
                if n in contents:
                    self.releaseNotes = (n, fwzip.read(n, password))
        
        
        # Sanity check: Make sure the binary contains the expected string
        if strict and self.MIDE_STRING not in fwBin:
            raise ValidationError("Could not verify firmware binary's origin")
        
        self.info = info
        self.fwBin = fwBin
        self.bootBin = bootBin
        self.filename = filename


    def isNewerBootloader(self, vers):
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
            raise ValidationError('Device type not supported')
        
        template = 'templates/%s/%d/*' % (self.device.partNumber, 
                                          self.device.hardwareVersion)
        if not any(lambda x: fnmatch(x, template), self.contents):
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
        ports = filter(lambda x: 'EFM32 USB CDC Serial' in x[1], 
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
            return True
        logger.error('Bootloader: Send command %r, expected %r but received %r' % (command, response, instring))
        return False


    def uploadData(self, command, payload, response='Ready'):
        """ Helper method to upload data.
        """
        self.flush()
        if self.sendCommand(command, response):
            self.flush()
            time.sleep(1.0) # HACK: give bootloader some time to catch its breath?

            if not self.modem.send(io.BytesIO(payload)):
                logger.error("Bootloader: File upload failed!")
                return False
            logger.info("Bootloader: Data payload uploaded successfully.")
            return True
        
        return False
    
    
    def uploadBootloader(self, payload):
        if len(payload) < self.MIN_FILE_SIZE:
            raise ValueError("Bootloader upload payload too small")
        return self.uploadData("d", payload)


    def uploadApp(self, payload):
        if len(payload) < self.MIN_FILE_SIZE:
            raise ValueError("Firmware upload payload too small")
        return self.uploadData("u", payload)


    def uploadDebugLock(self):
        if not self.sendCommand("l", "OK"):
            logger.error("Bootloader: Bad response when setting debug lock!")
            return False
        return True
    
    
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
    
        PAGE_SIZE = 2048
        
        manSize = len(manifest)
        manOffset = 0x0010 # 16 byte offset from start
        calSize = len(caldata)
        calOffset =  manOffset + manSize #0x0400 # 1k offset from start
        propsSize = len(recprops)
        propsOffset = calOffset + calSize
    
        data = struct.pack("<HHHHHH", 
                           manOffset, manSize, 
                           calOffset, calSize,
                           propsOffset, propsSize)
        data = bytearray(data.ljust(PAGE_SIZE, '\x00'))
        data[manOffset:manOffset+manSize] = manifest
        data[calOffset:calOffset+calSize] = caldata
        data[propsOffset:propsOffset+propsSize] = recprops
        
        if len(data) != PAGE_SIZE:
            # Probably can never happen, but just in case...
            raise ValueError("Userpage block was %d bytes; should be %d" % \
                             (len(data), PAGE_SIZE))
        
        return data


    def sendUserpage(self):
        """ Upload the userpage data.
        """
        caldata = ''
        recprops = ''
        
        manifest = util.build_ebml('DeviceManifest', self.manifest, schema=schema_manifest)
        
        if self.cal:
            caldata = util.build_ebml('CalibrationList', self.cal, schema=schema_mide)
        if self.props:
            recprops = util.build_ebml('RecordingProperties', self.props, schema=schema_mide)

        payload = self.makeUserpage(manifest, caldata, recprops)
        return self.uploadData('t', payload)
    
    
    def getVersionAndId(self):
        """
            @return: A tuple containing the bootloader version and chip ID.
        """
        vers = None
        self.myPort.write("i")
        # Hack: FW echoes this character (with \n), then another \n, THEN the string.
        tries = 3
        while tries > 0:
            instring = self.myPort.readline()
            if "BOOTLOADER" in instring:
                vers = instring.strip()
                break
            tries -= 1
    
        if not vers:
            return None
        
        # Grab any salient information from the bootloader string (mainly 
        # CHIPID, but also bootloader version).
        # Example output: "BOOTLOADER version 1.01m2, Chip ID 2483670050B7D82F"
        (bootverstring, chipidstring) = vers.split(",")
        return (bootverstring.rsplit(" ", 1)[-1], 
                chipidstring.rsplit(" ", 1)[-1])


    #===========================================================================
    # 
    #===========================================================================
    
    def readTemplate(self, z, name, schema, password=None):
        with z.open(name, password) as f:
            return util.read_ebml(f, schema=schema)
    
    def updateManifest(self):
        """
        """
        templateBase = 'templates/%s/%d' % (self.device.partNumber, self.device.hardwareVersion)
        manTempName = "%s/manifest.template.ebml" % templateBase
        calTempName = "%s/cal.template.ebml" % templateBase
        propTempName = "%s/recprop.template.ebml" % templateBase
        
        with zipfile.ZipFile(self.filename, 'r') as fwzip:
            manTemplate = self.readTemplate(fwzip, manTempName, schema_manifest, self.password)
            calTemplate = self.readTemplate(fwzip, calTempName, schema_mide, self.password)
            propTemplate = self.readTemplate(fwzip, propTempName, schema_mide, self.password)

        accelSn = findItem(self.manifest, 'AnalogSensorInfo/AnalogSensorSerialNumber')
        manChanges = (
            ('DeviceManifest/SystemInfo/SerialNumber', self.device.serialInt),
            ('DeviceManifest/SystemInfo/DateOfManufacture', self.device.birthday),
            ('DeviceManifest/AnalogSensorInfo/AnalogSensorSerialNumber', accelSn),
        )
        propChanges = (
            ('RecordingProperties/SensorList/TraceabilityData/SensorSerialNumber', accelSn),
        )
        
        for k,v in manChanges:
            changeItem(manTemplate, k, v)
        for k,v in propChanges:
            changeItem(propTemplate, k, v)

        # Update transform channel IDs and references
        if 0 in self.cal:
            self.cal[0].id = 9
        self.cal[1].channelId = 36
        self.cal[2].channelId = 36
        self.cal[3].channelId = 36
        
        if not all((manTemplate, calTemplate, propTemplate)):
            raise ValueError("Could not find template")
        
        

#===============================================================================
# 
#===============================================================================

class FirmwareUpdaterDialog(SC.SizedDialog):
    """ UI for updating recorder firmware.
    """
    TITLE = None
    
    def __init__(self, *args, **kwargs):
        style = wx.DEFAULT_DIALOG_STYLE \
            | wx.RESIZE_BORDER \
            | wx.MAXIMIZE_BOX \
            | wx.MINIMIZE_BOX \
            | wx.DIALOG_EX_CONTEXTHELP \
            | wx.SYSTEM_MENU
        
        kwargs.setdefault('style', style)
        self.device = kwargs.pop('device', None)
        self.fwFile = kwargs.pop('filename', None)
        super(FirmwareUpdaterDialog, self).__init__(*args, **kwargs)
        
        if self.TITLE and not self.GetTitle():
            self.SetTitle(self.TITLE)
            
        self.app = wx.GetApp()
        self.prefSection = "tools.%s" % self.__class__.__name__
        
        if self.device is None:
            self.device = device_dialog.selectDevice(hideClock=True)
        
        
        if self.fwFile is None:
            dlg = wx.FileDialog(self, message="Select a Slam Stick Firmware File",
                                wildcard="Slam Stick Firmware Package (*.fw)|*.fw",
                                style=wx.OPEN | wx.CHANGE_DIR)
            if dlg.ShowModal() == wx.ID_OK:
                self.fwFile = dlg.GetPath()
            dlg.Destroy()
            print self.fwFile
#         self.updater = FirmwareUpdater(device=self.device)

#===============================================================================
# 
#===============================================================================

def updateFirmware(parent=None, device=None, filename=None):
    """ Wrapper for starting the firmware update.
    """
    if device is None:
        device = device_dialog.selectDevice(parent=parent, hideClock=True)
    if device is None:
        return False
    if len(devices.getDevices()) > 1:
        # warn user.
        wx.MessageBox("Too many recorders!\n\nWarning text.", "Update Firmware")
    if filename is None:
        dlg = wx.FileDialog(parent, message="Select a Slam Stick Firmware File",
                            wildcard="MIDE Firmware Package (*.fw)|*.fw",
                            style=wx.OPEN | wx.CHANGE_DIR)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        dlg.Destroy()
    if filename is None:
        return False
    
#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    app = wx.App()
    updateFirmware()
#     dlg = FirmwareUpdaterDialog(None)
#     dlg.ShowModal()