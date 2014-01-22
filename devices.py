'''
Functions for retrieving lists of devices and information on said
devices.

Created on Nov 14, 2013

@author: dstokes
'''

import ctypes
import string
import sys


def getDeviceInfo(cls, dev):
    """
    """
    if "win" in sys.platform:
        kernel32 = ctypes.windll.kernel32
        volumeNameBuffer = ctypes.create_unicode_buffer(1024)
        fileSystemNameBuffer = ctypes.create_unicode_buffer(1024)
        serial_number = ctypes.c_uint(0)
#         file_system_flags =  ctypes.c_uint(0)
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
        return dev, volumeNameBuffer.value, hex(serial_number.value), fileSystemNameBuffer.value


def getDevices():
    """
    """
    if "win" in sys.platform:
        kernel32 = ctypes.windll.kernel32
        drivebits = kernel32.GetLogicalDrives()
        result = []
        for letter in string.uppercase:
            if drivebits & 1:
                result.append(getDeviceInfo('%s:\\' % letter))
            drivebits >>= 1
        return result
            
        
