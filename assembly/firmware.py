'''
Created on Sep 25, 2014

@author: dstokes
'''
# from collections import Sequence
from datetime import datetime
import io
import os
from StringIO import StringIO
import struct
import sys
import time
from xml.etree import ElementTree as ET
# import xml.dom.minidom as minidom

import serial #@UnusedImport
import serial.tools.list_ports

import xmodem
import birth_utils as utils

CWD = os.path.abspath(os.path.dirname(__file__))
sys.path.append(CWD)

try:
    import mide_ebml
except ImportError:
    if os.path.exists('../mide_ebml'):
        sys.path.append(os.path.abspath('..'))
    elif os.path.exists(os.path.join(CWD, '../mide_ebml')):
        sys.path.append(os.path.abspath(os.path.join(CWD, '../mide_ebml')))
    import mide_ebml #@UnusedImport

# from mide_ebml import util as ebml_util
from mide_ebml.ebmlite import loadSchema

#===============================================================================
# 
#===============================================================================

mideSchema = loadSchema('mide.xml')
manifestSchema = loadSchema('manifest.xml')

#===============================================================================
# 
#===============================================================================

class ssx_bootloadable_device(object):

    minfilesize = 1024 # Minimum file size to be considered a valid upload. Mainly paranoia to avoid writing 0-byte files over the bootloader

    SERIAL_PARAMS = {
#         'port':         'COM12',
        'baudrate':     115200, 
        'parity':       'N', 
        'bytesize':     8, 
        'stopbits':     1, 
        'timeout':      1.0, 
    }

    BOOT_FW_FILENAME = "boot.bin"
    BOOT_FW_VER_FILENAME = "boot_version.txt"
    APP_FW_FILENAME = "app.bin"
    APP_FW_VER_FILENAME = "app_version.txt"

    #===============================================================================
    # 
    #===============================================================================
    
    def msg(self, *msg):
        print ' '.join(map(str, msg))
    
    def flush(self):
        if self.myPort.inWaiting():
            return self.myPort.read(self.myPort.inWaiting())
        
    
    def __init__(self, portname, **kwargs):
        portParams = self.SERIAL_PARAMS.copy()
        portParams.update(kwargs)
        # open the port
        self.myPort = serial.Serial(portname, **portParams)
        self.modem = xmodem.XMODEM(self.myPort)

        if(self.myPort):
            flushed = self.flush()
            if flushed:
                self.msg("Flushed %d stale port bytes" % flushed)


    def sendCommand(self, command, response='Ready'):
        self.myPort.write(command[0]) # make sure it is 1 character.
        self.myPort.readline() # sent character echo
        instring = self.myPort.readline() # 'Ready' response
        if response in instring:
            return True
        self.msg('ERROR: Send command %r, received %r' % (command, instring))
        return False

    def disconnect(self):
        # Reset the device and close out the port
        self.myPort.write("r") # reset
        self.myPort.close()
        

    def get_version_string(self):
        self.myPort.write("i")
        # Hack: FW echoes this character (with newline), then another newline, THEN the string.
        tries = 3
        while tries != 0:
            instring = self.myPort.readline()
            if "BOOTLOADER" in instring:
                return instring.strip()
        return None

    def send_file(self, filename):
        # Since we are bootloading (potentially over top of the bootloader), it
        # is very important to check that this file actually exists before 
        # overwriting anything.

        # HACK: Try cleaning out the port before passing control to 'xmodem'
        # Somehow we are always getting 0x15 (NAK) in response to the first
        # packet, even though a byte-identical transfer from Teraterm gets an 
        # 0x06 (ACK)...
        # ^^^ Nevermind, this is from bootloader requiring the entire xmodem 
        # packet in a contiguous USB packet while xmodem lib uses individual 
        # calls to write some of the bytes...
        self.flush()

        time.sleep(1.0) # HACK: give bootloader some time to catch its breath?
                
        with open(filename, 'rb') as f:
            # check file length
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size < self.minfilesize:
                self.msg("ERROR: Input file too short to be valid, aborting (expect at least %d bytes, but file is %d bytes)" % (self.minfilesize, size))
                return False
            # rewind the file
            f.seek(0, os.SEEK_SET)
            #print "Sending file '%s' via xmodem..." % filename
            retval = self.modem.send(f)
            if not retval:
                self.msg("ERROR: File upload failed!")
                return retval
            #print "OK."
            return retval
        
        self.msg("ERROR: File not found: '%s'" % filename)
        return False

    def send_bootloader(self, filename):
        if self.sendCommand("d"):
            return self.send_file(filename)
        return False

    def send_app(self, filename):
        if self.sendCommand("u"):
            return self.send_file(filename)
        return False

#     def send_userpage(self, filename):
#         if self.sendCommand("t"):
#             return self.send_file(filename)
#         return False

    def send_userpage_payload(self, payload):
        if self.sendCommand('t'):
            self.flush()
            #print "Sending payload via xmodem..."
            retval = self.modem.send(io.BytesIO(payload))
            if not retval:
                self.msg("ERROR: File upload failed!")
                return retval
            self.msg("Userpage payload uploaded successfully.")
            return retval
        return False

    def send_debug_lock(self):
        if not self.sendCommand("l", "OK"):
            self.msg("ERROR: Bad response when setting debug lock!")
            return False
        return True
    
    #===========================================================================
    # 
    #===========================================================================

    @classmethod
    def makeUserpage(self, manifest, caldata, recprops=''):
        """ Combine a binary Manifest and Cal into a unified, correctly 
            formatted userpage block.
    
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
        calSize = len(caldata)
        propsSize = len(recprops)
        MANIFEST_OFFSET = 0x0010 # 16 byte offset from start
        CALDATA_OFFSET =  MANIFEST_OFFSET + manSize #0x0400 # 1k offset from start
        
        # Only set the offset for the recorder props if there are any.
        # Must be zero (or 0xFFFF?) if there are no props.
        if propsSize > 0:
            RECPROPS_OFFSET = CALDATA_OFFSET + calSize
        else:
            RECPROPS_OFFSET = 0
    
        data = struct.pack("<HHHHHH", 
                           MANIFEST_OFFSET, manSize, 
                           CALDATA_OFFSET, calSize,
                           RECPROPS_OFFSET, propsSize)
        data = bytearray(data.ljust(PAGE_SIZE, '\x00'))
        data[MANIFEST_OFFSET:MANIFEST_OFFSET+manSize] = manifest
        data[CALDATA_OFFSET:CALDATA_OFFSET+calSize] = caldata
        data[RECPROPS_OFFSET:RECPROPS_OFFSET+propsSize] = recprops
        
        if len(data) != PAGE_SIZE:
            raise ValueError("Userpage block was %d bytes; should be %d" % \
                             (len(data), PAGE_SIZE))
        
        return data


    def sendUserpage(self, manifest, caldata, recprops=''):
        return self.send_userpage_payload(self.makeUserpage(manifest, caldata, recprops))
    
    
    def getVersionAndId(self):
        """
            @return: A tuple containing the bootloader version and chip ID.
        """
        ver = self.get_version_string()
        if not ver:
            return None, None
        # Grab any salient information from the bootloader string (mainly 
        # CHIPID, but also bootloader version).
        # Example output: "BOOTLOADER version 1.01m2, Chip ID 2483670050B7D82F"
        (bootverstring, chipidstring) = ver.split(",")
        return bootverstring.rsplit(" ", 1)[-1], chipidstring.rsplit(" ", 1)[-1]
    

#===============================================================================
# 
#===============================================================================

def readUserPage(devPath):
    """
    """
    systemPath = os.path.join(devPath, 'SYSTEM', 'DEV')
    data = []
    for i in range(4):
        filename = os.path.join(systemPath, 'USERPG%d' % i)
        with open(filename, 'rb') as fs:
            data.append(fs.read())
    data = ''.join(data)
    
    manOffset, manSize, calOffset, calSize, propOffset, propSize = struct.unpack_from("<HHHHHH", data)
    manData = StringIO(data[manOffset:manOffset+manSize])
    calData = StringIO(data[calOffset:calOffset+calSize])
    if propOffset > 0:
        propData = StringIO(data[propOffset:propOffset+propSize])
#         props = ebml_util.read_ebml(propData)
        props = mideSchema.load(propData)
    else:
        props = None
#     manifest = ebml_util.read_ebml(manData, schema='mide_ebml.ebml.schema.manifest')
#     calibration = ebml_util.read_ebml(calData)
    manifest = manifestSchema.load(manData)
    calibration = mideSchema.load(calData)
 
    return manifest, calibration, props

#===============================================================================
# 
#===============================================================================

def makeManifestXml(templatePath, partNum, hwRev, device_sn, device_accel_sn, 
                    dest, birthday=None, batchId=''):
    """ Create the device manifest XML file.

        @param templatePath: The root directory of the data templates.
        @param partNum: The part number (subdirectory `templatePath`)
        @param hwRev: The hardware revision number (subdirectory of `partNum`)
        @param device_sn: The recording device's serial number.
        @param device_accel_sn: The device's sensor serial number(s). Can be
            `None`, a single serial number string, or a sequence of serial 
            numbers (a list/tuple or comma-separated string). These numbers
            will be applied to the templates sensors in order.
        @param dest: The output file.
        @keyword birthday: The device's creation date (defaults to current).
        @return: The root XML element (`xml.etree.ElementTree.Element`)
    """
    if birthday is None:
        birthday = int(time.mktime(time.gmtime()))
    elif isinstance(birthday, datetime):
        birthday = int(time.mktime(birthday.timetuple()))
        
    filename = os.path.join(templatePath, partNum, str(hwRev), "manifest.template.xml")
    xmltree = ET.parse(filename)
    xmlroot = xmltree.getroot()
    
    # Mostly good as-is, but need to update SerialNumber, DateOfManufacture 
    # and AnalogSensorSerialNumber. There is only one element with each name, 
    # so we can simply "find" by that name and update the value.
    el = xmlroot.find("./SystemInfo/SerialNumber")
    el.set('value', str(device_sn))
    el = xmlroot.find("./SystemInfo/DateOfManufacture")
    el.set('value', str(birthday))
    
    nums = utils.splitSerialNumbers(device_accel_sn)
    els = xmlroot.findall("./AnalogSensorInfo/AnalogSensorSerialNumber")
    for el, num in zip(els, nums):
        el.set('value', num)

    if batchId:
        el = xmlroot.find('./SystemInfo/BatchIDStr')
        if el:
            el.set('value', batchId)
        else:
            el = ET.Element('BatchIDStr', {'value': batchId})
            xmlroot.find('./SystemInfo').append(el)
        
    xmltree.write(dest)
    return xmlroot


def makeRecPropXml(templatePath, partNum, hwRev, device_accel_sn, dest):
    """ Create the XML for the RecordingProperties of a device.
    
        @param templatePath: The root directory of the data templates.
        @param partNum: The part number (subdirectory `templatePath`)
        @param hwRev: The hardware revision number (subdirectory of `partNum`)
        @param device_accel_sn: The device's sensor serial number(s). Can be
            `None`, a single serial number string, or a sequence of serial 
            numbers (a list/tuple or comma-separated string). These numbers
            will be applied to the templates sensors in order.
        @param dest: The output file.
        @return: The root XML element (`xml.etree.ElementTree.Element`)
    """
    filename = os.path.join(templatePath, partNum, str(hwRev), "recprop.template.xml")
    if not os.path.exists(filename):
        return None
    
    xmltree = ET.parse(filename)
    xmlroot = xmltree.getroot()

    # Update all sensors with a serial number. 
    nums = utils.splitSerialNumbers(device_accel_sn)
    els = xmlroot.findall("./SensorList/Sensor/TraceabilityData/SensorSerialNumber")
    for el, num in zip(els, nums):
        el.set('value', num)

    xmltree.write(dest)
    return xmlroot

#===============================================================================
# 
#===============================================================================

def getSSXSerial(block=False, timeout=30, delay=.25, callback=None):
    """ Get the names of all serial ports connected to bootloader-mode SSX.
    """
    if block:
        if timeout is not None:
            deadline = time.time() + timeout
        while timeout is None or deadline > time.time():
            p = getSSXSerial(block=False)
            time.sleep(delay)
            if p is not None:
                return p
            if callback:
                callback.update()
        
        return None
    
#     ports = filter(lambda x: 'EFM32 USB CDC Serial' in x[1], 
#                    serial.tools.list_ports.comports())
    # Different versions of driver change the name; this should be more reliable.
    ports = filter(lambda x: 'USB VID:PID=2544:0003' in x[2], 
                   serial.tools.list_ports.comports())
    if len(ports) > 0:
        return [x[0] for x in ports]


#===============================================================================
# 
#===============================================================================

def getBootloaderSSX(block=True, timeout=None, delay=0.25, callback=None, 
                     quiet=False, fail=False):
    """ Wait for and return a Slam Stick X in bootloader mode.
    """
    ex = None if fail else IOError
    if not quiet: print "Waiting for Slam Stick X in bootloader mode...",
    sp = getSSXSerial(block=block, timeout=timeout, delay=delay, callback=callback)
    if sp is None:
        # Should never happen if block == True
        return
    if not quiet: print "Found device on %s; connecting..." % sp[0]
    while True:
        try:
            ssxboot = ssx_bootloadable_device(sp[0])
            if not quiet: print "Connected to SSX bootloader via %s" % sp[0]
            return ssxboot
        except ex:
            print "Unable to connect to bootloader!"
            raw_input("Unplug the SSX, re-attach it, press the button, and type [enter]")


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    print "This is only a library. Don't try to run it!"
    exit(1)