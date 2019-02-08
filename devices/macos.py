'''
Created on Jan 27, 2015

@author: stokes
'''

from collections import namedtuple
import os
import time

Drive = namedtuple("Drive", ("path","label","sn","fs","type"))

#===============================================================================
#
#===============================================================================

def getDriveInfo(dev):
    # XXX: Total hack.
    return Drive(dev, os.path.basename(dev), None, 'fat', None)


def readRecorderClock(clockfile):
    t0 = time.time()
    f = open(clockfile, 'rb', 0)
    t = f.read(8)
    t1 = (time.time() + t0) / 2
    f.close()
    return t1, t


def getDeviceList(types, paths=None):
    """ Get a list of data recorders, as their respective drive letter.
    """
    paths = os.listdir("/Volumes/") if paths is None else paths
    paths = filter(lambda x: x not in ("Mobile Backups", "Macintosh HD"), paths)
    result = []
    for p in paths:
        for t in types:
            if t.isRecorder(p):
                result.append(p)
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
    newDevices = os.listdir("/Volumes/")
    changed = newDevices != last_devices
    last_devices = newDevices

#     if not changed or not recordersOnly:
    if not recordersOnly:
        return changed

    newRecorders = tuple(getDeviceList(types=types))
    changed = newRecorders != last_recorders
    last_recorders = newRecorders
    return changed


def getFreeSpace(path):
    """ Return the free space (in bytes) on a drive.

        @param path: The path to the drive to check. Can be a subdirectory.
        @return: The free space on the drive, in bytes.
        @rtype: int
    """
    # TODO: Make sure this actually works. Should work on all POSIX OSes.
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def getBlockSize(path):
    """ Return the bytes per sector and sectors per cluster of a drive.

        @param path: The path to the drive to check. Can be a subdirectory.
        @return: A tuple containing the bytes/sector and sectors/cluster.
    """
    raise NotImplementedError("XXX: IMPLEMENT macos.getBlockSize()!")
