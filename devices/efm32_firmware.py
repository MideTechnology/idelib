'''
Tool for updating the firmware on a SSX-based data recorder. Requires the
EFM32 CDC USB Serial driver for Windows.

Created on Sep 2, 2015

@author: dstokes
'''

from fnmatch import fnmatch
from glob import glob
import io
import json
import os.path
from StringIO import StringIO
import struct
import time
import zipfile

import serial #@UnusedImport
import serial.tools.list_ports

import wx
from wx.lib.dialogs import ScrolledMessageDialog
from wx.lib.throbber import Throbber
from wx.lib.wordwrap import wordwrap

import xmodem

from widgets import device_dialog
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
    findItem(container, p)[k] = val


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
                    self.releaseNotes = (n,fwzip.read(n, password))
                    break
        
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


    def uploadData(self, command, payload, response='Ready'):
        ex = None
        for i in range(5):
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
        """
            @keyword payload: An alternative payload, to be used instead of the
                object's `bootBin` attribute.
        """
        payload = self.bootBin if payload is None else payload
        if payload is None:
            logger.info("No bootloader in package")
            return True
        if len(payload) < self.MIN_FILE_SIZE:
            raise ValueError("Bootloader upload payload too small")
        
        return self.uploadData("d", payload)


    def uploadApp(self, payload=None):
        """
            @keyword payload: An alternative payload, to be used instead of the
                object's `fwBin` attribute.
        """
        payload = self.fwBin if payload is None else payload
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
        data = bytearray(data.ljust(self.PAGE_SIZE, '\x00'))
        data[manOffset:manOffset+manSize] = manifest
        data[calOffset:calOffset+calSize] = caldata
        data[propsOffset:propsOffset+propsSize] = recprops
        
        if len(data) != self.PAGE_SIZE:
            # Probably can never happen, but just in case...
            raise ValueError("Userpage block was %d bytes; should be %d" % \
                             (len(data), self.PAGE_SIZE))
        
        return data


    def sendUserpage(self, payload=None):
        """ Upload the userpage data.
            @keyword payload: An alternative payload, to be used instead of the
                object's `payload` attribute.
        """
        payload = self.userpage if payload is None else payload
        if len(payload) != self.PAGE_SIZE:
            raise ValueError("Userpage block was %d bytes; should be %d" % \
                             (len(payload), self.PAGE_SIZE))
        
        return self.uploadData("t", payload)
        
    
    def getVersionAndId(self):
        """
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
        return util.read_ebml(StringIO(z.read(name, password)), schema=schema)
    
    
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

        if not all((manTemplate, calTemplate, propTemplate)):
            raise ValueError("Could not find template")

        try:
            accelSn = findItem(self.device.getManifest(), 'AnalogSensorInfo/AnalogSensorSerialNumber')
        except (KeyError, IndexError):
            accelSn = None
            
        manChanges = (
            ('DeviceManifest/SystemInfo/SerialNumber', self.device.serialInt),
            ('DeviceManifest/SystemInfo/DateOfManufacture', self.device.birthday),
            ('DeviceManifest/AnalogSensorInfo/AnalogSensorSerialNumber', accelSn),
        )
        propChanges = (
            ('RecordingProperties/SensorList/Sensor/0/TraceabilityData/SensorSerialNumber', accelSn),
        )
        
        for k,v in manChanges:
            try:
                changeItem(manTemplate, k, v)
            except (KeyError, IndexError):
                logger.info("Missing manifest item %s, probably okay." %
                            os.path.basename(k))
                pass
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
        
        if calEx:
            calTemplate['CalibrationList']['CalibrationSerialNumber'] = calSer
        if calDate:
            calTemplate['CalibrationList']['CalibrationDate'] = int(calDate)
        if calEx:
            calTemplate['CalibrationList']['CalibrationExpiry'] = int(calEx)
        
        self.manifest = util.build_ebml('DeviceManifest', 
                                        manTemplate['DeviceManifest'], 
                                        schema=schema_manifest)
        self.cal = util.build_ebml('CalibrationList', 
                                   calTemplate['CalibrationList'], 
                                   schema=schema_mide)
        self.props = util.build_ebml('RecordingProperties', 
                                     propTemplate['RecordingProperties'], 
                                     schema=schema_mide)
        
        self.userpage = self.makeUserpage(self.manifest, self.cal, self.props)
        

#===============================================================================
# 
#===============================================================================

class FirmwareUpdateDialog(wx.Dialog):
    """
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
            logger.info('No driver required if not running Windows.')
            return True
    
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.firmware = kwargs.pop('firmware', None)
        self.device = kwargs.pop('device', None)
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
        else:
            self.but = 'main'

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
        """
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
        self.throbber.Rest()        
        self.scanTimer.Stop()
        self.timeoutTimer.Stop()
        wx.MessageBox("No recording device was found.\n\n"
                      "Make sure the required driver has been installed and "
                      "try again.", "No Device Found", wx.OK|wx.ICON_ERROR)
        self.Close()


    def updateFirmware(self):
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
            self.firmware.sendUserpage()

            try:
                self.firmware.disconnect()
                wx.MilliSleep(250)
            except IOError:
                pass
            
            wx.MessageBox("Firmware Update Complete!\n\n"
                          "You may now disconnect your recorder.", 
                          "Update Complete")
            
        except (ValueError, IOError) as _err:
            logger.error(str(_err))
            try:
                self.firmware.disconnect()
            except IOError:
                pass
            wx.MessageBox("Firmware update failed!\n\n"
                          "The update failed while %s. \n"
                          "Please try again." % msg,
                          "Update Failure", wx.OK|wx.ICON_ERROR)
        
        self.Close()
            

#===============================================================================
# 
#===============================================================================

def updateFirmware(parent=None, device=None, filename=None):
    """ Wrapper for starting the firmware update.
    """
    logger.info("Searching for EFM32 USB CDC Serial driver...")
    if not FirmwareUpdateDialog.driverInstalled():
        x = wx.MessageBox(
            "A basic system test could not locate the required driver.\n\n"
            "This test is not perfect, however, and could be inaccurate. "
            "If you know you have already installed the driver successfully, "
            "press OK.", 
            "No Driver?", wx.OK|wx.CANCEL|wx.HELP)
        if x == wx.HELP:
            wx.MessageBox("No help yet.", "Firmware Update Help")
            return
        if x != wx.OK:
            return False
        
    if len(devices.getDevices()) > 1:
        # warn user.
        wx.MessageBox("Multiple recorders found!\n\n"
                      "It is strongly recommended that you remove all "
                      "recorders except the one you wish to update.", 
                      "Update Firmware")
    if device is None:
        device = device_dialog.selectDevice(parent=parent, hideClock=True)
    if device is None:
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
        update = FirmwareUpdater(device, filename)
        logger.info("Passed basic validation")
    except (ValidationError, ValueError, KeyError) as _err:
        # Various causes
        logger.error(str(_err))
        if "CRC" in str(_err.message):
            msg = ("This firmware update package appears to be damaged "
                   "(CRC test of contents failed).")
        else:
            msg = ("This firmware update package appears to be missing vital "
                   "components,and is likely damaged.")
        wx.MessageBox(msg, "Validation Error")
        return False
    except IOError as _err:
        # Bad file
        logger.error(str(_err))
        wx.MessageBox("This firmware file could not be read.", 
                      "Validation Error")
        return False
    except RuntimeError as _err:
        # Bad password
        logger.error(str(_err))
        wx.MessageBox("This firmware update package could not be authenticated.", 
                      "Validation Error")
        return False
    
    if update.releaseNotes:
        dlg = ScrolledMessageDialog(parent, update.releaseNotes[1], 
                                "%s Release Notes" % os.path.basename(filename))
        dlg.ShowModal()
        
    try:
        update.checkCompatibility()
        logger.info("Passed compatibility check")
    except ValidationError as _err:
        msg = _err.message.rstrip('.')+'.'
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
    
    dlg = FirmwareUpdateDialog(parent, device=device, firmware=update)
    dlg.ShowModal()
    
        
#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    app = wx.App()
    print updateFirmware()
