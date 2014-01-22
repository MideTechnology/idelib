'''
Functions for detecting, identifying, and retrieving information about
data-logging devices.
'''

__author__ = "David Stokes"
__date__ = "Nov 14, 2013"


import ctypes
import os
import string
import struct
import sys

from mide_ebml import devices

SYSTEM_PATH = "/SYSTEM/DEV/".replace("/",os.sep)
INFO_FILE = os.path.join(SYSTEM_PATH, "DEVINFO")
CLOCK_FILE = os.path.join(SYSTEM_PATH, "CLOCK")

timeParser = struct.Struct("Q")

#===============================================================================
# Cross-platform functions
#===============================================================================

def isRecorder(dev):
    """ Simple test whether a given path/drive letter refers to a recorder,
        based on the presence (or absence) of its /SYSTEM/DEV/DEVINFO file.
    """
    try:
        return os.path.exists(os.path.join(dev, INFO_FILE))
    except IOError:
        return False
    

def getRecorderInfo(dev):
    """ Retrieve recorder device information, such as .
    """
    if isRecorder(dev):
        try:
            with open(INFO_FILE, 'rb') as stream:
                devinfo = devices.importDeviceInfo(stream)
            props = devinfo.get('RecordingProperties', '')
            if 'RecorderInfo' in props:
                info = props['RecorderInfo']
                info['PATH'] = dev
                return info
        except IOError:
            pass
    return False


def getDeviceTime(dev):
    f = open(os.path.join(dev,CLOCK_FILE), 'rb', 0)
    t = f.read(8)
    f.close()
    return timeParser.unpack_from(t)

#===============================================================================
# Windows-specific versions of the functions
#===============================================================================

if 'win' in sys.platform:
    kernel32 = ctypes.windll.kernel32
    FILE_SHARE_READ =           0x00000001
    OPEN_EXISTING =             0x00000003
    FILE_FLAG_NO_BUFFERING =    0x20000000
    GENERIC_READ =              0x80000000

else:
    kernel32 = None


def win_getDevices():
    """ Get a list of data recorders, as their respective drive letter.
    """
    drivebits = kernel32.GetLogicalDrives()
    result = []
    for letter in string.uppercase:
        if drivebits & 1:
            driveLetter = '%s:\\' % letter
            devtype = kernel32.GetDriveTypeA(driveLetter)
            # First cut: only consider devices of type 2 (removable
            if devtype == 2 and isRecorder(driveLetter):
                result.append(driveLetter)
        drivebits >>= 1
    return result


def win_getDriveInfo(dev):
    """ Get general device information. Not currently used.
    """
    volumeNameBuffer = ctypes.create_unicode_buffer(1024)
    fileSystemNameBuffer = ctypes.create_unicode_buffer(1024)
    serial_number = ctypes.c_uint(0)
#     file_system_flags =  ctypes.c_uint(0)
    kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(dev),
        volumeNameBuffer,
        ctypes.sizeof(volumeNameBuffer),
        ctypes.byref(serial_number),
        None, #max_component_length,
        None, #ctypes.byref(file_system_flags),
        fileSystemNameBuffer,
        ctypes.sizeof(fileSystemNameBuffer)
    )
    return (dev, volumeNameBuffer.value, hex(serial_number.value), 
            fileSystemNameBuffer.value, kernel32.GetDriveTypeA(dev))


win_last_devices = 0

def win_deviceChanged():
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
    """
    global win_last_devices
    newDevices = kernel32.GetLogicalDrives()
    result = newDevices != win_last_devices
    win_last_devices = newDevices
    return result
 

#===============================================================================
# 
#===============================================================================

def getDevices():
    """ Get a list of data recorder, as the paths to their root directory (or
        drive letter under Windows).
    """
    raise NotImplementedError("Only windows version currently implemented!")


def deviceChanged():
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
    """
    raise NotImplementedError("Only windows version currently implemented!")


if "win" in sys.platform:
    getDevices = win_getDevices
    deviceChanged = win_deviceChanged


#===============================================================================
# 
#===============================================================================

class Recorder(object):
    """
    """
    
    @classmethod
    def fromPath(cls, path):
        """ 
        """
        return Recorder(path)


    def __init__(self, path=None):
        self.path = path
        
        