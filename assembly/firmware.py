'''
Created on Sep 25, 2014

@author: dstokes
'''
import io
import os
import struct
import time

import serial.tools.list_ports
import serial

import xmodem


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
        if self.sendCommand("U"):
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
            self.msg("OK.")
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
    def makeUserpage(self, manifest, caldata):
        """ Combine a binary Manifest and Cal into a unified, correctly 
            formatted userpage block.
    
            USERPAGE memory map:
                0x0000 (2): Offset of manifest, LE
                0x0002 (2): Length of manifest, LE
                0x0004 (2): Offset of calibration, LE
                0x0006 (2): Length of calibration, LE
                0x0008 ~ 0x000F: (RESERVED)
                0x0010: Manifest data
                0x0400: Factory Calibration data
        """
    
        PAGE_SIZE = 2048
    #     USERPAGE_OFFSET = 0x0000
        MANIFEST_OFFSET = 0x0010 # 16 byte offset from start
        CALDATA_OFFSET =  0x0400 # 1k offset from start
    
        manSize = len(manifest)
        calSize = len(caldata)
        data = bytearray(struct.pack("<HHHH2040x", (MANIFEST_OFFSET, manSize, 
                                                    CALDATA_OFFSET, calSize)))
        data[MANIFEST_OFFSET:MANIFEST_OFFSET+manSize] = manifest
        data[CALDATA_OFFSET:CALDATA_OFFSET+calSize] = caldata
        
        if len(data) != PAGE_SIZE:
            raise ValueError("Userpage block was %d bytes; should be %d" % \
                             (len(data), PAGE_SIZE))
        
        return data


    def sendUserpage(self, manifest, caldata):
        return self.send_userpage_payload(self.makeUserpage(manifest, caldata))
    
    
    def getVersionAndId(self):
        """
            @return: A tuple containing the bootloader version and chip ID.
        """
        ver = self.get_version_string()
        if not ver:
            return False
        # Grab any salient information from the bootloader string (mainly 
        # CHIPID, but also bootloader version).
        # Example output: "BOOTLOADER version 1.01m2, Chip ID 2483670050B7D82F"
        (bootverstring, chipidstring) = ver.split(",")
        return bootverstring.rsplit(" ", 1)[-1], chipidstring.rsplit(" ", 1)[-1]
    
    
#===============================================================================
# 
#===============================================================================

def getSSXSerial(block=False, timeout=30, delay=.5):
    """
    """
    if block:
        if timeout is not None:
            deadline = time.time() + timeout
        while timeout is None or deadline > time.time():
            p = getSSXSerial(block=False)
            if p is not None:
                return p
            time.sleep(delay)
        return None
    
    ports = filter(lambda x: 'EFM32 USB CDC Serial' in x[1], 
                   serial.tools.list_ports.comports())
    if len(ports) > 0:
        return [x[0] for x in ports]

#===============================================================================
# 
#===============================================================================

