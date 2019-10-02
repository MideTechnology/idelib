'''
Functions for detecting, identifying, and retrieving information about
data-logging devices.
'''
from __future__ import absolute_import, print_function

__author__ = "David Stokes"
__date__ = "Nov 14, 2013"

import os

from devices.base import Recorder, ConfigError, ConfigVersionError, os_specific

from .ssx import SlamStickX
from .ssc import SlamStickC
from .sss import SlamStickS
from .endaq import EndaqS
from .classic import SlamStickClassic


#===============================================================================
# 
#===============================================================================

# TODO: Modularize device type registration, so new ones can be added cleanly.
RECORDER_TYPES = [SlamStickClassic, SlamStickC, SlamStickS, EndaqS, SlamStickX]


#===============================================================================
# Platform-specific stuff. 
# TODO: Clean this up, use OS-specific functions directly. 
#===============================================================================

def deviceChanged(recordersOnly=True, types=RECORDER_TYPES):
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
        
        @keyword recordersOnly: If `False`, any change to the mounted drives
            is reported as a change. If `True`, the mounted drives are checked
            and `True` is only returned if the change occurred to a recorder.
            Checking for recorders only takes marginally more time.
    """
    return os_specific.deviceChanged(recordersOnly, types)


def getDeviceList(types=RECORDER_TYPES):
    """ Get a list of data recorders, as their respective path (or the drive
        letter under Windows).
    """
    return os_specific.getDeviceList(types)


def getDevices(paths=None, types=RECORDER_TYPES):
    """ Get a list of data recorder objects.
    
        @keyword paths: A list of specific paths to recording devices. 
            Defaults to all found devices (as returned by `getDeviceList()`).
        @keyword types: A list of `Recorder` subclasses to find.
        @return: A list of instances of `Recorder` subclasses.
    """
    result = []
    paths = os_specific.getDeviceList(types) if paths is None else paths
    for dev in paths:
        for t in types:
            if t.isRecorder(dev):
                result.append(t(dev))
                break
    return result


#===============================================================================
# 
#===============================================================================

def getRecorder(path, types=RECORDER_TYPES):
    """ Get a specific recorder by its path.
    
        @param path: The filesystem path to the recorder's root directory.
        @keyword types: A list of `Recorder` subclasses to find.
        @return: An instance of a `Recorder` subclass.
    """
    for t in types:
        if t.isRecorder(path):
            return t(path)
    return None


def isRecorder(dev, types=RECORDER_TYPES):
    """ Determine if the given path is a recording device.
    """
    for t in types:
        if t.isRecorder(dev):
            return True
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


def fromRecording(doc):
    """ Create a 'virtual' recorder from the data contained in a recording
        file.
    """
    productName = doc.recorderInfo.get('ProductName')
    if not productName:
        productName = doc.recorderInfo.get('PartNumber')
    if productName is None:
        raise TypeError("Could not create virtual recorder from file (no ProductName)")
    recType = None #SlamStickX
    for rec in RECORDER_TYPES:
        if rec._matchName(productName):
            recType = rec
            break
    if recType is None:
        return None
    return recType.fromRecording(doc)
    
    
#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    print("recorders:", getDevices())
