'''
Functions for detecting, identifying, and retrieving information about
data-logging devices.
'''

__author__ = "David Stokes"
__date__ = "Nov 14, 2013"


import calendar
import ctypes
from datetime import datetime
import os
import string
import struct
import sys
import time

# from mide_ebml import devices
from mide_ebml import util

SYSTEM_PATH = "SYSTEM"
INFO_FILE = os.path.join(SYSTEM_PATH, "DEV", "DEVINFO")
CLOCK_FILE = os.path.join(SYSTEM_PATH, "DEV", "CLOCK")
CONFIG_FILE = os.path.join(SYSTEM_PATH, "config.cfg")

timeParser = struct.Struct("<L")

#===============================================================================
# 
#===============================================================================

class Recorder(object):
    """ XXX: Complete and use, or remove.
    """
    @classmethod
    def fromPath(cls, path):
        """ 
        """
        return Recorder(path)


    def __init__(self, path=None):
        self.path = path
        
        
    

#===============================================================================
# Cross-platform functions
#===============================================================================

def isRecorder(dev):
    """ Simple test whether a given path/drive letter refers to a recorder,
        based on the presence (or absence) of its /SYSTEM/DEV/DEVINFO file.
        Invalid paths return `False` (i.e. not a recorder); if you need to
        differentiate bad paths from non-recorders you should perform 
        your own checks first.
        
        @param dev: The path to the recording device.
        @return: `True` if the path is a device, `False` if not (or the path
            is bad).
    """
    try:
        return os.path.exists(os.path.join(dev, INFO_FILE))
    except (IOError, TypeError):
        return False
    

def onRecorder(path):
    """ Returns the root directory of a recorder from a path to a directory or
        file on that recorder. It can be used to test whether a file is on
        a recorder. `False` is returned if the path is not on a recorder.
        The test is only whether the path refers to a recorder, not whether or 
        not the path or file actually exists; if you need to know if the path 
        is valid, perform your own checks first.
        
        @param path: The full path/name of a file.
        @return: The path to the root directory of a recorder (e.g. the drive
            letter in Windows) if the path is to a subdirectory on a recording 
            device, `False` if not.
    """
    oldp = None
    path = os.path.realpath(path)
    while path != oldp:
        if isRecorder(path):
            return path
        oldp = path
        path = os.path.dirname(path)
    return False


def getRecorderInfo(dev, default=None):
    """ Retrieve a recorder's device information.
    
        @param dev: The path to the recording device.
        @return: A dictionary containing the device data. An additional key,
            `"_PATH"`, is added with the path to the device (e.g. the drive
            letter under Windows).
    """
    if isRecorder(dev):
        try:
            devinfo = util.read_ebml(os.path.join(dev, INFO_FILE))
            props = devinfo.get('RecordingProperties', '')
            if 'RecorderInfo' in props:
                info = props['RecorderInfo']
                info['_PATH'] = dev
                    
                return info
        except IOError:
            pass
    return default


def getRecorderConfig(dev, default=None):
    """ Retrieve a recorder's device information.
    
        @param dev: The path to the recording device.
        @return: A set of nested dictionaries containing the device data.
    """
    if isRecorder(dev):
        try:
            devinfo = util.read_ebml(os.path.join(dev, CONFIG_FILE))
            return devinfo.get('RecorderConfiguration', '')
        except IOError:
            pass
    return default


def setRecorderConfig(dev, data, verify=True):
    """ Write a dictionary of configuration data to a device. 
    
        @param dev: The path to the recording device.
        @param data: The configuration data to write, as a set of nested
            dictionaries.
        @keyword verify: If `True`, the validity of the EBML is checked before
            the data is written.
    """
    ebml = util.build_ebml("RecorderConfiguration", data)
    if verify and not util.verify(ebml):
        raise ValueError("Generated config EBML could not be verified")
    with open(os.path.join(dev, CONFIG_FILE), 'wb') as f:
        f.write(ebml)
    return len(ebml)


def getDeviceTime(dev):
    """ Read the date/time from the device. 
    
        @note: This is currently unreliable under Windows due to its caching
            mechanism.

        @param dev: The path to the recording device.
        @return: The time, as integer seconds since the epoch ('Unix time').
    """
    f = open(os.path.join(dev,CLOCK_FILE), 'rb', 0)
    t = f.read(8)
    f.close()
    return timeParser.unpack_from(t)


def setDeviceTime(dev, t=None):
    """ Set a recorder's date/time. A variety of standard time types are
        accepted.
    
        @param dev: The path to the recording device.
        @keyword t: The time to write, as either seconds since the epoch (i.e.
            'Unix time'), `datetime.datetime` or a UTC `time.struct_time`. The 
            current time  (from the host) is used if `None` (default).
        @return: The time that was set, as integer seconds since the epoch.
    """
    if t is None:
        t = int(time.time())
    elif isinstance(t, datetime):
        t = calendar.timegm(t.timetuple())
    elif isinstance(t, (time.struct_time, tuple)):
        t = calendar.timegm(t)
    else:
        t = int(t)
        
    with open(os.path.join(dev,CLOCK_FILE),'wb') as f:
        f.write(timeParser.pack(t))
    return t
    
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
win_last_recorders = None

def win_deviceChanged(recordersOnly=True):
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
        
        @keyword recordersOnly: If `False`, any change to the mounted drives
            is reported as a change. If `True`, the mounted drives are checked
            and `True` is only returned if the change occurred to a recorder.
            Checking for recorders only takes marginally more time.
    """
    global win_last_devices, win_last_recorders
    newDevices = kernel32.GetLogicalDrives()
    changed = newDevices != win_last_devices
    win_last_devices = newDevices
    
#     if not changed or not recordersOnly:
    if not recordersOnly:
        return changed
    
    newRecorders = tuple(win_getDevices())
    changed = newRecorders != win_last_recorders
    win_last_recorders = newRecorders
    return changed
 

#===============================================================================
# 
#===============================================================================

def getDevices():
    """ Get a list of data recorder, as the paths to their root directory (or
        drive letter under Windows).
    """
    raise NotImplementedError("Only windows version currently implemented!")


def deviceChanged(recordersOnly=True):
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
