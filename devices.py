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
# Platform specific version of functions: Windows
#===============================================================================

if 'win' in sys.platform:
    kernel32 = ctypes.windll.kernel32
else:
    kernel32 = None


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


def getDriveInfo(dev):
    raise NotImplementedError

#===============================================================================
# 
#===============================================================================

class Recorder(object):
    """ Base class for all data recorders.
    
        XXX: Complete and use, or remove.
    """
    INFO_FILE = ''
    CONFIG_FILE = ''
    
    productName = "Generic Recorder"
    baseName = productName
    
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
        self.volumeName = getDriveInfo(self.path)[1]
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

    baseName = "Slam Stick X"

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
            if isinstance(default, dict):
                d = default.copy()
                d.update(self._config)
                self._config = d
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
        """ The recording device's (user-assigned) name. """
        if self._name is not None:
            return self._name
        userdata = self.getConfig().get('RecorderUserData', {})
        self._name = userdata.get('RecorderName', '')
        return self._name

    @property
    def productName(self):
        """ The recording device's manufacturer-issued name. """
        return self.getInfo().get('ProductName', '')
    
    @property
    def serial(self):
        """ The recorder's manufacturer-issued serial number. """
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

    baseName = "Slam Stick Classic"

    @classmethod
    def isRecorder(cls, dev):
        """ Does the specified path refer to a recorder?
        
            @param dev: The path to the possible recording device (e.g. a
                mount point under *NIX, or a drive letter under Windows)
        """
        dev = os.path.realpath(dev)
        try:
            return (os.path.exists(os.path.join(dev, cls.CONFIG_FILE)) and \
                    os.path.exists(os.path.join(dev, cls.DATA_FILE)))
        except (IOError, TypeError):
            return False


    @classmethod
    def _packTime(cls, t=None):
        """ Helper method to convert a time into the BCD format used in the 
            config file.
            
            @keyword t: The time to encode, or `None` for the current time.
            @return: A string of 7 bytes (BCD encoded year, month, day, day of week,
                hour, minute, second).
        """
        def bin2bcd(val):
            return chr((int(val/10)<<4) + (val%10))
        
        if t == 0:
            return '\0' * 7
        
        if t is None:
            t = datetime.now().timetuple()
        elif isinstance(t, datetime):
            t = t.timetuple()
        
        result = (t[0]-2000, t[1], t[2], t[6], t[3], t[4], t[5])
        return ''.join(map(bin2bcd, result))


    @classmethod
    def _unpackTime(cls, t):
        """ Helper method to convert a BCD encoded time into a standard
            `datetime.datetime` object.
            
            @param t: The encoded time as a 7-byte string.
            @return: The time as a `datetime.datetime`.
        """
        def bcd2bin(val):
            return (val & 0x0F) + ((val >> 4) * 10)
        
        t = bytearray(t)
        t[0] = datetime.now().year-2000 if t[0] == 0 else t[0]
            
        try:
            d = map(bcd2bin, t)
            return datetime(d[0]+2000, d[1], d[2], d[4], d[5], d[6])
        except ValueError:
            return 0
    
    @classmethod
    def _packUID(cls, s):
        if not s:
            return '\x00' * 8
        return str(s)[:8].ljust(8,'\x00')
    
    @classmethod
    def _unpackUID(cls, s):
        return s.rstrip('\x00')


    def getConfig(self, default=None, refresh=False):
        """ Get the device's configuration data. 
        
            @param default: A dictionary of default values, if no configuration
                data was read or any fields are missing.
            @keyword refresh: If `True`, the configuration data will be read
                fresh from the devices. If `False`, cached data will be
                returned (if available).
        """
        if self._config is not None and not refresh:
            return self._config
        try:
            self._config = classic_config.readConfig(self.configFile)
            if isinstance(default, dict):
                d = default.copy()
                d.update(self._config)
                self._config = d
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
        self._config = self._info = data
        return classic_config.writeConfig(self.configFile, data, verify)


    def getInfo(self, default=None, refresh=False):
        """ Get information on the recorder. For Classic, this is in the
            configuration file, so this method is the same as `getConfig()`.
        """
        return self.getConfig(default, refresh)


    @property
    def name(self):
        """ The recording device's (user-assigned) name. """
        if self._name is None:
            n = self.getConfig().get('USERUID_RESERVE', '').strip()
            self._name = str(n or self.volumeName or "Slam Stick")
        return self._name


    @property
    def productName(self):
        """ The recording device's manufacturer-issued name. """
        return self.baseName


    @property
    def serial(self):
        """ The recording device's manufacturer-issued serial number. """
        if self._sn is None:
            self._sn = self.getConfig().get('SYSUID_RESERVE', '').strip()
        return self._sn


    def getTime(self):
        """ Read the date/time from the device. 
        
            @param dev: The path to the recording device.
            @return: The time, as integer seconds since the epoch ('Unix time').
        """
        return self.getConfig(refresh=True)['RTCC_TIME']
   
    
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
        conf = self.getConfig(refresh=True)
        
        if t is None:
            t = datetime.now()
        elif isinstance(t, (float, int)):
            t = datetime.fromtimestamp(t)
        elif isinstance(t, (time.struct_time, tuple)):
            t = datetime(*t[:6])
        
        conf['RTCC_TIME'] = t
        conf['WR_RTCC'] = 0x5A
        self.saveConfig(conf)
        
        return t

#===============================================================================
# 
#===============================================================================

RECORDER_TYPES = (SlamStickClassic, SlamStickX)


#===============================================================================
# More Windows-specific versions of the functions
#===============================================================================

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
    getDriveInfo = win_getDriveInfo
    getDeviceList = win_getDeviceList
    deviceChanged = win_deviceChanged

#===============================================================================
# 
#===============================================================================

def getDevices(paths=None, types=RECORDER_TYPES):
    """ Get a list of data recorder objects.
    
        @keyword paths: A list of specific paths to recording devices. 
            Defaults to all found devices (as returned by `getDeviceList()`).
        @keyword types: A list of `Recorder` subclasses to find.
        @return: A list of instances of `Recorder` subclasses.
    """
    result = []
    paths = getDeviceList(types=types) if paths is None else paths
    for dev in paths:
        for t in types:
            if t.isRecorder(dev):
                result.append(t(dev))
                continue
    return result


def getRecorder(dev, types=RECORDER_TYPES):
    """ Get a specific recorder by its path.
    """
    for t in types:
        if t.isRecorder(dev):
            return t(dev)
    return None


def isRecorder(dev, types=RECORDER_TYPES):
    """ Determine if the given path is a recording device.
    """
    for t in types:
        if t.isRecorder(dev):
            True
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
    

#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    print "recorders:"
    print getDevices()