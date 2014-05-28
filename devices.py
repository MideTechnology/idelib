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
from mide_ebml.classic import config as classic_config

SYSTEM_PATH = "SYSTEM"
INFO_FILE = os.path.join(SYSTEM_PATH, "DEV", "DEVINFO")
CLOCK_FILE = os.path.join(SYSTEM_PATH, "DEV", "CLOCK")
CONFIG_FILE = os.path.join(SYSTEM_PATH, "config.cfg")

CLASSIC_CONFIG_FILE = "config.dat"
CLASSIC_DATA_FILE = "data.dat"

timeParser = struct.Struct("<L")

#===============================================================================
# Cross-platform functions
#===============================================================================

def isClassicRecorder(dev):
    try:
        return (os.path.exists(os.path.join(dev, CLASSIC_CONFIG_FILE)) and \
                os.path.exists(os.path.join(dev, CLASSIC_DATA_FILE)))
    except (IOError, TypeError):
        return False


def isRecorder(dev, classic=True):
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
        result = os.path.exists(os.path.join(dev, INFO_FILE))
        if classic:
            result = result or isClassicRecorder(dev)
        return result
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
    if isClassicRecorder(dev):
        return {'_IS_CLASSIC': True, '_PATH': dev}
    elif isRecorder(dev, classic=False):
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
    if isClassicRecorder(dev):
        return classic_config.readConfig(os.path.join(dev, CLASSIC_CONFIG_FILE))
    elif isRecorder(dev, classic=False):
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
# 
#===============================================================================

class Recorder(object):
    """ Base class for all data recorders.
    
        XXX: Complete and use, or remove.
    """
    INFO_FILE = ''
    CONFIG_FILE = ''
    
    @classmethod
    def fromPath(cls, path):
        """ 
        """
        return cls(path)


    def __init__(self, path):
        path = os.path.realpath(os.path.expandvars(path))
        if not self.isRecorder(path):
            raise IOError("Specified path isn't a %s: %r" % \
                          (self.__class__.__name__, path))
        self.path = path
        self.configFile = os.path.join(self.path, self.CONFIG_FILE)
        self.infoFile = os.path.join(self.path, self.INFO_FILE)
        self._info = None
        self._config = None
        self._name = None
        self._sn = None
        


    def onDevice(self, filename):
        """ Determines if a file is on the recording device. 
        
            The test is only whether the path refers to a recorder, not whether 
            or not the path or file actually exists; if you need to know if the 
            path is valid, perform your own checks first.
        """
        filename = os.path.realpath(os.path.expandvars(filename))
        return os.path.commonprefix((self.path, filename)) == self.path



#===============================================================================

class SlamStickX(Recorder):
    """
    """
    SYSTEM_PATH = "SYSTEM"
    INFO_FILE = os.path.join(SYSTEM_PATH, "DEV", "DEVINFO")
    CLOCK_FILE = os.path.join(SYSTEM_PATH, "DEV", "CLOCK")
    CONFIG_FILE = os.path.join(SYSTEM_PATH, "config.cfg")
    TIME_PARSER = struct.Struct("<L")


    def __init__(self, path):
        super(SlamStickX, self).__init__(path)
        self.clockFile = os.path.join(self.path, self.CLOCK_FILE)


    @classmethod
    def isRecorder(cls, dev):
        """
        """
        try:
            result = os.path.exists(os.path.join(dev, cls.INFO_FILE))
            return result
        except (IOError, TypeError):
            return False


    def getInfo(self, default=None, refresh=False):
        """ Retrieve a recorder's device information.
        
            @return: A dictionary containing the device data. An additional key,
                `"_PATH"`, is added with the path to the device (e.g. the drive
                letter under Windows).
        """
        if self._info is not None and not refresh:
            return self._info
        try:
            devinfo = util.read_ebml(self.infoFile)
            props = devinfo.get('RecordingProperties', '')
            if 'RecorderInfo' in props:
                self._info = props['RecorderInfo']
                self._info['_PATH'] = self.path
                
                return self._info
        except IOError:
            pass
        return default

    
    def getConfig(self, default=None, refresh=False):
        """
        """
        if self._config is not None and not refresh:
            return self._config
        try:
            devinfo = util.read_ebml(self.configFile)
            self._config = devinfo.get('RecorderConfiguration', '')
            return self._config
        except IOError:
            pass
        return default


    def saveConfig(self, data, verify=True):
        """ Write a dictionary of configuration data to a device. 
        
            @param dev: The path to the recording device.
            @param data: The configuration data to write, as a set of nested
                dictionaries.
            @keyword verify: If `True`, the validity of the EBML is checked 
                before the data is written.
        """
        ebml = util.build_ebml("RecorderConfiguration", data)
        if verify and not util.verify(ebml):
            raise ValueError("Generated config EBML could not be verified")
        with open(self.configFile, 'wb') as f:
            f.write(ebml)
        self._config = self._info = None
        return len(ebml)
    

    @property
    def name(self):
        if self._name is not None:
            return self._name
        userdata = self.getConfig().get('RecorderUserData', {})
        self._name = userdata.get('RecorderName', '')
        return self._name

    @property
    def productName(self):
        return self.getInfo().get('ProductName', '')
    
    @property
    def serial(self):
        if self._sn is None:
            self._sn = self.getInfo().get('RecorderSerial', '')
        return self._sn


    def getTime(self):
        """ Read the date/time from the device. 
        
            @note: This is currently unreliable under Windows due to its caching
                mechanism.
    
            @param dev: The path to the recording device.
            @return: The time, as integer seconds since the epoch ('Unix time').
        """
        f = open(self.clockFile, 'rb', 0)
        t = f.read(8)
        f.close()
        return self.TIME_PARSER.unpack_from(t)
    
    
    def setTime(self, t=None):
        """ Set a recorder's date/time. A variety of standard time types are
            accepted.
        
            @param dev: The path to the recording device.
            @keyword t: The time to write, as either seconds since the epoch 
                (i.e. 'Unix time'), `datetime.datetime` or a UTC 
                `time.struct_time`. The current time  (from the host) is used 
                if `None` (default).
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
            
        with open(self.clockFile, 'wb') as f:
            f.write(self.TIME_PARSER.pack(t))
        return t


#===============================================================================

class SlamStickClassic(Recorder):
    """
    """
    CONFIG_FILE = "config.dat"
    INFO_FILE = "config.dat"
    DATA_FILE = "data.dat"


    @classmethod
    def isRecorder(cls, dev):
        dev = os.path.realpath(dev)
        try:
            return (os.path.exists(os.path.join(dev, cls.CONFIG_FILE)) and \
                    os.path.exists(os.path.join(dev, cls.DATA_FILE)))
        except (IOError, TypeError):
            return False


    def getConfig(self, default=None, refresh=False):
        """
        """
        if self._config is not None and not refresh:
            return self._config
        try:
            self._config = classic_config.readConfig(self.configFile)
            return self._config
        except IOError:
            pass
        return default


    def saveConfig(self, data, verify=True):
        """ Write a dictionary of configuration data to a device. 
        
            @param dev: The path to the recording device.
            @param data: The configuration data to write, as a set of nested
                dictionaries.
            @keyword verify: If `True`, the validity of the EBML is checked 
                before the data is written.
        """
        return classic_config.writeConfig(self.configFile, data, verify)


    def getInfo(self, default=None, refresh=False):
        """ Get information on the recorder. For Classic, this is in the
            configuration file, so this method is the same as `getConfig()`.
        """
        return self.getConfig(default, refresh)


    @property
    def name(self):
        if self._name is None:
            n = self.getConfig().get('USERUID_RESERVE', '').strip()
            self._name = n or "Slam Stick"
        return self._name


    @property
    def productName(self):
        return "Slam Stick Classic"


    @property
    def serial(self):
        if self._sn is None:
            self._sn = self.getConfig().get('SYSUID_RESERVE', '').strip()
        return self._sn


#===============================================================================
# 
#===============================================================================

RECORDER_TYPES = (SlamStickClassic, SlamStickX)


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


def win_getDeviceList(types=RECORDER_TYPES):
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
                        continue
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

def win_deviceChanged(recordersOnly=True, types=RECORDER_TYPES):
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
    
    newRecorders = tuple(win_getDeviceList(types=types))
    changed = newRecorders != win_last_recorders
    win_last_recorders = newRecorders
    return changed
 

#===============================================================================
# 
#===============================================================================

def getDeviceList(types=RECORDER_TYPES):
    """ Get a list of data recorder, as the paths to their root directory (or
        drive letter under Windows).
    """
    raise NotImplementedError("Only windows version currently implemented!")


def deviceChanged(recordersOnly=True, types=RECORDER_TYPES):
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
    """
    raise NotImplementedError("Only windows version currently implemented!")


if "win" in sys.platform:
    getDeviceList = win_getDeviceList
    deviceChanged = win_deviceChanged


def getDevices(types=RECORDER_TYPES):
    """ Get a list of data recorder objects.
    """
    result = []
    for dev in getDeviceList(types=types):
        for t in types:
            if t.isRecorder(dev):
                result.append(t(dev))
                continue
    return result


def getRecorder(dev, types=RECORDER_TYPES):
    for t in types:
        if t.isRecorder(dev):
            return t(dev)
    return None

#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    print "recorders:"
    print getDevices()