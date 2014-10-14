"""
Tool to rename new SSX SD cards. While running, it scans for new drives,
and if they are removable volumes with a FAT* filesystem and don't already
have the new name, they get renamed. There are no open files, so they can be
unplugged immediately.

This is a standalone script. The canonical version is in source control with
the viewer, but it's independent.
"""

import ctypes
import os
import string
import sys
import time

kernel32 = ctypes.windll.kernel32


excluded_drives = None
win_last_devices = None

spinner = "|/-\\"
spinIdx = 0

def deviceChanged():
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
        
        @keyword recordersOnly: If `False`, any change to the mounted drives
            is reported as a change. If `True`, the mounted drives are checked
            and `True` is only returned if the change occurred to a recorder.
            Checking for recorders only takes marginally more time.
    """
    global win_last_devices
    newDevices = kernel32.GetLogicalDrives()
    changed = newDevices != win_last_devices
    win_last_devices = newDevices
    return changed


def getCurrentDrives():
    global excluded_drives
    drivebits = kernel32.GetLogicalDrives()
    result = []
    for letter in string.uppercase:
        if drivebits & 1:
            driveLetter = '%s:\\' % letter
            devtype = kernel32.GetDriveTypeA(driveLetter)
            # First cut: only consider devices of type 2 (removable
            if devtype == 2:
                result.append(driveLetter)
        drivebits >>= 1
    return result


def getAllDrives():
    drivebits = kernel32.GetLogicalDrives()
    result = []
    for letter in string.uppercase:
        if drivebits & 1:
            result.append('%s:\\' % letter)
        drivebits >>= 1
    return result


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
    return (dev, volumeNameBuffer.value, hex(serial_number.value), 
            fileSystemNameBuffer.value, kernel32.GetDriveTypeA(dev))



NEW_NAME = "SlamStick X".upper()

if __name__ == '__main__':
    print "\n\n*** ReNamer Ready to ReName 'Er! Remove all devices you may want to rename now."
    raw_input("*** Press [enter] to start!")
    
    excluded_drives = set(getAllDrives())
    deviceChanged()
    
    print "*** Start attaching volumes to rename to %s!" % NEW_NAME
    while True:
        if deviceChanged():
            vols = set(getCurrentDrives()) - excluded_drives
            for v in vols:
                info = getDriveInfo(v)
                if not info or 'FAT' not in info[-2]:
                    print "... Ignoring non-FAT drive %s..." % v
                    continue
                if info[1].upper() == NEW_NAME:
                    continue
                if os.system('label %s %s' % (v.strip("\\"), NEW_NAME)) == 0:
                    print "\x07*** Renamed %s from %s to %s" % (v, info[1], NEW_NAME)
                else:
                    print "\x07\x07!!! Failed to rename drive %s (labeled %r)!" % (v, info[1])
        
        time.sleep(.125)
        sys.stdout.write("%s\x0d" % spinner[spinIdx])
        sys.stdout.flush()
        spinIdx = (spinIdx + 1) % len(spinner)