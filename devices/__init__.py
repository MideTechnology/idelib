'''
Functions for detecting, identifying, and retrieving information about
data-logging devices.
'''

__author__ = "David Stokes"
__date__ = "Nov 14, 2013"

import os

from base import Recorder, ConfigError, ConfigVersionError, os_specific

from ssx import SlamStickX
from ssc import SlamStickC
from classic import SlamStickClassic


#===============================================================================
# 
#===============================================================================

# TODO: Modularize device type registration, so new ones can be added cleanly.
RECORDER_TYPES = [SlamStickClassic, SlamStickC, SlamStickX]


#===============================================================================
# 
#===============================================================================

def deviceChanged(recordersOnly=True, types=RECORDER_TYPES):
    return os_specific.deviceChanged(recordersOnly, types)


def getDeviceList(types=RECORDER_TYPES):
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
                continue
    return result


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
    if productName is None:
        raise TypeError("Could not create virtual recorder from file (no ProductName)")
    recType = None #SlamStickX
    for rec in RECORDER_TYPES:
        if rec.baseName in productName:
            recType = rec
            break
    if recType is None:
        return None
    return recType.fromRecording(doc)
    
    
#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    print "recorders:"
    print getDevices()