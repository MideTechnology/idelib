'''
Created on Sep 2, 2015

@author: dstokes
'''
from fnmatch import fnmatch
import io
import json
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

#===============================================================================
# 
#===============================================================================

class ValidationError(ValueError):
    """
    """

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
        self.fwBin = None
        self.bootBin = None
        self.lastResponse = None
        
        if self.device is not None:
            pass
        
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
            contents = fwzip.namelist()
            
            with fwzip.open('info.json', 'r', password) as f:
                try:
                    info = json.load(f)
                except ValueError:
                    raise ValidationError('Could not read firmware info')
                
            fwBin = self._readItem(fwzip, 'app.bin', password)
            if 'boot.bin' in contents:
                bootBin = self._readItem(fwzip, 'boot.bin', password)
        
        if len(fwBin) < self.MIN_FILE_SIZE:
            raise ValueError("Firmware binary too small (%d bytes)" % len(fwBin))
        
        # Sanity check: Make sure the binary contains the expected string
        if strict and self.MIDE_STRING not in fwBin:
            raise ValidationError("Could not verify firmware binary's origin")
        
        # Recorder-specific tests: types, versions, etc.
        if self.device is not None:
            # Check recorder types and such
            if 'types' in info:
                if self.device.productId not in info['types']:
                    raise ValidationError("Incompatible recorder type")
            if 'hwRevs' in info:
                if self.device.hardwareVersion not in info['hwRevs']:
                    raise ValidationError("")
            
        self.info = info
        self.fwBin = fwBin
        self.bootBin = bootBin
        self.filename = filename


    #===========================================================================
    # 
    #===========================================================================
    
    def findDevice(self):
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
    # 
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


    def sendUserpage(self, manifest, caldata, recprops=''):
        """
        """
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
    """
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