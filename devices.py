'''
Functions for detecting, identifying, and retrieving information about
data-logging devices.
'''

__author__ = "David Stokes"
__date__ = "Nov 14, 2013"


import ctypes
import os
import string
import sys

SYSTEM_PATH = "/SYSTEM/DEV/".replace("/",os.sep)
INFO_FILE = os.path.join(SYSTEM_PATH, "DEVINFO")
CLOCK_FILE = os.path.join(SYSTEM_PATH, "CLOCK")

#===============================================================================
# Cross-platform functions
#===============================================================================

def isRecorder(dev):
    """ Check to see if a given path (or drive letter under Windows) refers to
        a data recorder.
    """
    if not os.path.exists(os.path.join(dev, INFO_FILE)):
        return False
    # TODO: Read device info
    return True


#===============================================================================
# Windows-specific versions of the functions
#===============================================================================

if 'win' in sys.platform:
    kernel32 = ctypes.windll.kernel32
else:
    kernel32 = None


def win_getDevices():
    """ Get a list of data recorder, as their respective drive letter.
    """
    drivebits = kernel32.GetLogicalDrives()
    result = []
    for letter in string.uppercase:
        if drivebits & 1:
            driveLetter = '%s:\\' % letter
            devtype = kernel32.GetDriveTypeA(driveLetter)
            # Device type 2 is removable
            if devtype == 2 and isRecorder(driveLetter):
                result.append(driveLetter)
        drivebits >>= 1
    return result


def win_getDeviceInfo(dev):
    """
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


