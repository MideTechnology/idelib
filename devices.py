'''
Functions for detecting, identifying, and retrieving information about
data-logging devices.
'''

__author__ = "David Stokes"
__date__ = "Nov 14, 2013"


import calendar
from collections import OrderedDict
import ctypes
from datetime import datetime
import os
import string
from StringIO import StringIO
import struct
import sys
import time

# from mide_ebml import devices
from mide_ebml import util
from mide_ebml.classic import config as classic_config

#===============================================================================
# 
#===============================================================================

class ConfigError(ValueError):
    pass

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
        self.clearCache()
    
    def clearCache(self):
        self._info = None
        self._config = None
        self._name = None
        self._sn = None
        self._accelRange = None


    def _getInfoAttr(self, name, default=None):
        info = self.getInfo()
        if info is None:
            return default
        return info.get(name, default)

    
    def getInfo(self, default=None, refresh=False):
        """ Retrieve a recorder's device information. Subclasses need to
            implement this.
        """
        raise NotImplementedError

    def onDevice(self, filename):
        """ Determines if a file is on the recording device. 
        
            The test is only whether the path refers to a recorder, not whether 
            or not the path or file actually exists; if you need to know if the 
            path is valid, perform your own checks first.
        """
        filename = os.path.realpath(os.path.expandvars(filename))
        return os.path.commonprefix((self.path, filename)) == self.path


    def _loadConfig(self, source, default=None):
        """ Stub for the method that does device-specific config loading. 
            Must be implemented for each `Recorder` subclass!
        """
        raise NotImplementedError
    
    def _saveConfig(self, dest, data=None, verify=True):
        """ Stub for the method that does device-specific config saving. 
            Must be implemented for each `Recorder` subclass!
        """
        raise NotImplementedError
    

    def exportConfig(self, filename, data=None, verify=True):
        """ Write device configuration data to a file. The file contains the
            device product name, a newline, and then the data in the device's
            native format.
            
            @param filename: The name of the file to which to export.
            @keyword data: A dictionary of configuration data to export. If
                `None`, the device's own configuration data is exported.
            @keyword verify: If `True`, the configuration data will be
                validated prior to export.
        """
        if data is None:
            data = self.getConfig()
        if not data:
            raise ConfigError("No configuration data!")
        with open(filename, 'wb') as f:
            f.write("%s\n" % self.productName)
            self._saveConfig(f, data, verify)
            return True
        
        
    def importConfig(self, filename, update=True):
        """ Read device configuration data from a file. The file must contain
            the device's product name, a newline, and then the data in the
            device's native format. If the product name doesn't match the
            device's product name an `TypeError` is raised.
            
            @param filename: The name of the exported config file to import.
            @keyword update: If `True`, the config data is applied to the
                device. If `False`, it is just imported.
            @return: A dictionary of configuration attributes.
        """
        with open(filename,'rb') as f:
            pname = f.readline().strip()
            if pname != self.productName:
                raise ConfigError("Device mismatch: this is %r, file is %r" % \
                                (pname, self.productName))
        
            config = self._loadConfig(f)
        if update:
            self.getConfig().update(config)
        else:
            self._config = config
        return self._config


    def getConfig(self, default=None, refresh=False):
        """ Get the recorder's configuration data.
        """
        if self._config is not None and not refresh:
            return self._config
        default = OrderedDict() if default is None else default
        try:
            self._config = self._loadConfig(self.configFile)
            if isinstance(default, dict):
                d = default.copy()
                d.update(self._config)
                self._config = d
            return self._config
        except IOError:
            pass
        return default


    def saveConfig(self, data=None, verify=True):
        """ Write a dictionary of configuration data to a device. 
        
            @keyword data: The configuration data to write, as a set of nested
                dictionaries. Defaults to the device's loaded config data.
            @keyword verify: If `True`, the validity of the configuration data
                is checked before the data is written.
        """
        if data is None:
            data = self.getConfig()
            if not data:
                raise ValueError("Device configuration data has not been loaded")
        with open(self.configFile, 'wb') as f:
            return self._saveConfig(f, data, verify)
    


#===============================================================================

class SlamStickX(Recorder):
    """
    """
    SYSTEM_PATH = "SYSTEM"
    INFO_FILE = os.path.join(SYSTEM_PATH, "DEV", "DEVINFO")
    CLOCK_FILE = os.path.join(SYSTEM_PATH, "DEV", "CLOCK")
    CONFIG_FILE = os.path.join(SYSTEM_PATH, "config.cfg")
    TIME_PARSER = struct.Struct("<L")

    TYPE_RANGES = {
       0x10: (-25,25),
       0x12: (-100,100)
    }

    baseName = "Slam Stick X"

    def __init__(self, path):
        super(SlamStickX, self).__init__(path)
        self.clockFile = os.path.join(self.path, self.CLOCK_FILE)

    @classmethod
    def isRecorder(cls, dev):
        """ Test whether a given filesystem path refers to the root directory
            of a Slam Stick X recorder.
        """
        try:
            result = os.path.exists(os.path.join(dev, cls.INFO_FILE))
            if result:
                return getDriveInfo(dev)[3] in (u'FAT',)
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

    
    def _loadConfig(self, source):
        """ Helper method to read configuration info from a file. Used
            internally.
        """
        devinfo = util.read_ebml(source)
        return devinfo.get('RecorderConfiguration', None)


    def _saveConfig(self, dest, data, verify=True):
        """
        """
        ebml = util.build_ebml("RecorderConfiguration", data)
        if verify and not util.verify(ebml):
            raise ValueError("Generated config EBML could not be verified")
        dest.write(ebml)
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
        return self._getInfoAttr('ProductName', '')
    
    @property
    def serial(self):
        """ The recorder's manufacturer-issued serial number. """
        if self._sn is None:
            sn = self.getInfo().get('RecorderSerial', None)
            if sn is None:
                self._sn = ""
            else:
                self._sn = "SSX%08d" % self.getInfo().get('RecorderSerial', '')
        return self._sn

    @property
    def hardwareVersion(self):
        return self._getInfoAttr('HwRev', '')
    
    @property
    def firmwareVersion(self):
        return self._getInfoAttr('SwRev', '')

    def getAccelRange(self):
        """ Get the range of the device's acceleration measurement.
        """
        if self._accelRange is None:
            t = self.getInfo().get('RecorderTypeUID', 0x12) & 0xff
            self._accelRange = self.TYPE_RANGES.get(t, (-100,100))
        return self._accelRange
    
    def _packAccel(self, v):
        """ Convert an acceleration from G to native units.
        
            Note: Currently not used to save data, unlike the classic '_pack' 
            methods.
        """
        x = self.getAccelRange()[1]
        return min(65535, max(0, int(((v + x)/(2.0*x)) * 65535)))

    def _unpackAccel(self, v):
        """ Convert an acceleration from native units to G.
        
            Note: Currently not used to save data, unlike the classic '_unpack' 
            methods.
        """
        x = self.getAccelRange()[1]
        return min(x, max(-x, (v * x * 2.0) / 65535 - x))

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

    def importConfig(self, filename, update=True):
        """ Read device configuration data from a file. The file must contain
            the device's product name, a newline, and then the data in the
            device's native format. If the product name doesn't match the
            device's product name an `TypeError` is raised.
            
            @param filename: The name of the exported config file to import.
            @keyword update: If `True`, the config data is applied to the
                device. If `False`, it is just imported.
            @return: A dictionary of configuration attributes.
        """
        with open(filename,'rb') as f:
            pname = f.readline().strip()
            if pname != self.productName:
                raise ConfigError("Device mismatch: this is %r, file is %r" % \
                                (pname, self.productName))
        
            # the python-ebml library doesn't respect an initial offset
            config = self._loadConfig(StringIO(f.read()))
        if update:
            self.getConfig().update(config)
        else:
            self._config = config
        return self._config

        
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
            return (os.path.exists(os.path.join(dev, cls.CONFIG_FILE)) and
                    os.path.exists(os.path.join(dev, cls.DATA_FILE)) and
                    getDriveInfo(dev)[3] in (u'FAT',))
        except (IOError, TypeError):
            return False


    @classmethod
    def _packTime(cls, t=None):
        """ Helper method to convert a time into the BCD format used in the 
            config file.
            
            @keyword t: The time to encode, either seconds since the epoch 
                (i.e. 'Unix time'), `datetime.datetime` or a UTC 
                `time.struct_time`. The current UTC time (from the host) is used 
                if `None` (default).
            @return: A string of 7 bytes (BCD encoded year, month, day, day of 
                week, hour, minute, second).
        """
        def bin2bcd(val):
            return chr((int(val/10)<<4) + (val%10))
        
        if t == 0:
            return '\0' * 7
        
        if t is None:
            t = time.gmtime()
        elif isinstance(t, (int, float)):
            t = time.gmtime(t)
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


    def _loadConfig(self, source):
        """
        """
        return classic_config.readConfig(source)
    

    def _saveConfig(self, dest, data, verify=True):
        return classic_config.writeConfig(dest, data, verify)
    

    def getInfo(self, default=None, refresh=False):
        """ Get information on the recorder. For Classic, this is in the
            configuration file, so this method is the same as `getConfig()`.
        """
        if self._info is None:
            self._info = self.getConfig(default, refresh)
        return self._info


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
            self._sn = self._getInfoAttr('SYSUID_RESERVE', '').strip()
        return self._sn

    @property
    def hardwareVersion(self):
        return self._getInfoAttr('HWREV', None)
    
    @property
    def firmwareVersion(self):
        return self._getInfoAttr('SWREV', None)

    def getTime(self):
        """ Read the date/time from the device. 
        
            @param dev: The path to the recording device.
            @return: The time, as integer seconds since the epoch ('Unix time').
        """
        return self.getConfig(refresh=True).get('RTCC_TIME', None)
   
    
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


    def getAccelRange(self):
        return (-16,16) 
 
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


#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    print "recorders:"
    print getDevices()