'''
Windows-specific functions; primarily filesystem-related.

Created on Jan 27, 2015

@author: stokes
'''
from __future__ import absolute_import, print_function

from collections import namedtuple
import ctypes
import os
import string
import sys
import time

import pywintypes

#===============================================================================
# 
#===============================================================================

Drive = namedtuple("Drive", ("path","label","sn","fs","type"))

#===============================================================================
# Platform specific version of functions: Windows
#===============================================================================

if 'win' in sys.platform and sys.platform != 'darwin':
    kernel32 = ctypes.windll.kernel32
    import win32api, win32con, win32file
else:
    kernel32 = None


def getDriveInfo(dev):
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
    return Drive(dev, volumeNameBuffer.value, hex(serial_number.value), 
            fileSystemNameBuffer.value, kernel32.GetDriveTypeA(dev))


def readRecorderClock(dev):
    """ Read a (SSX) clock file, circumventing the disk cache. Returns the
        system time and the encoded device time.
    """
    root = os.path.abspath(os.path.join(os.path.dirname(dev), '..','..'))
    
    try:
        f1 = win32file.CreateFile(dev, win32con.GENERIC_READ, 
                                  win32con.FILE_SHARE_READ,
                                  None,
                                  win32con.OPEN_EXISTING,
                                  win32con.FILE_FLAG_NO_BUFFERING,
                                  0)
    except pywintypes.error as err: #@UndefinedVariable (error)
        raise IOError(err.strerror)

    spc, bps, _fc, _tc  = win32file.GetDiskFreeSpace(root)
    bpc = spc * bps

    _hr, lastTime = win32file.ReadFile( f1, bpc )
    thisTime = lastTime
    win32file.SetFilePointer(f1, 0, win32file.FILE_BEGIN)
    
    while lastTime == thisTime:
        sysTime = time.time()
        _hr, thisTime = win32file.ReadFile( f1, bpc )
        sysTime = (time.time() + sysTime)/2
        win32file.SetFilePointer(f1, 0, win32file.FILE_BEGIN)

    win32api.CloseHandle(f1)
    return sysTime, thisTime

#===============================================================================
# 
#===============================================================================

def getDeviceList(types):
    """ Get a list of data recorders, as their respective drive letter.
    """
    drivebits = kernel32.GetLogicalDrives()
    result = []
    for letter in string.uppercase:
        if drivebits & 1:
            driveLetter = '%s:\\' % letter
            devtype = kernel32.GetDriveTypeA(driveLetter)
            # First cut: only consider devices of type 2 (removable
            if devtype == 2:
                for t in types:
                    if t.isRecorder(driveLetter):
                        result.append(driveLetter)
                        break
        drivebits >>= 1
    return result


last_devices = 0
last_recorders = None


def deviceChanged(recordersOnly, types):
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
        
        @keyword recordersOnly: If `False`, any change to the mounted drives
            is reported as a change. If `True`, the mounted drives are checked
            and `True` is only returned if the change occurred to a recorder.
            Checking for recorders only takes marginally more time.
    """
    global last_devices, last_recorders
    newDevices = kernel32.GetLogicalDrives()
    changed = newDevices != last_devices
    last_devices = newDevices
    
#     if not changed or not recordersOnly:
    if not recordersOnly:
        return changed
    
    newRecorders = tuple(getDeviceList(types=types))
    changed = newRecorders != last_recorders
    last_recorders = newRecorders
    return changed

#===============================================================================
# 
#===============================================================================

def getFreeSpace(path):
    """ Return the free space (in bytes) on a drive.
        
        @param path: The path to the drive to check. Can be a subdirectory.
        @return: The free space on the drive, in bytes.
        @rtype: int
    """
    free_bytes = ctypes.c_ulonglong(0)
    kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(path), None, None, 
                                 ctypes.pointer(free_bytes))
    return free_bytes.value


def getBlockSize(path):
    """ Return the bytes per sector and sectors per cluster of a drive.

        @param path: The path to the drive to check. Can be a subdirectory.
        @return: A tuple containing the bytes/sector and sectors/cluster.
    """
    sectorsPerCluster = ctypes.c_ulonglong(0)
    bytesPerSector = ctypes.c_ulonglong(0)
    kernel32.GetDiskFreeSpaceW(ctypes.c_wchar_p(path), 
                                 ctypes.pointer(sectorsPerCluster),
                                 ctypes.pointer(bytesPerSector),
                                 None, None)
    
    return bytesPerSector.value, sectorsPerCluster.value
