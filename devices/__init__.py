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
import json
import os
import string
from StringIO import StringIO
import struct
import sys
import time

# from mide_ebml import devices
from mide_ebml import util
from mide_ebml.classic import config as classic_config

if sys.platform == 'darwin':
    import macos 
    platform_specific = macos
elif 'win' in sys.platform:
    import win
    platform_specific = win


#===============================================================================
# 
#===============================================================================

class ConfigError(ValueError):
    pass


class ConfigVersionError(ConfigError):
    pass


def getDriveInfo(dev):
    return
    raise NotImplementedError

#===============================================================================
# 
#===============================================================================

class Recorder(object):
    """ Base class for all data recorders.
    """
    INFO_FILE = ''
    CONFIG_FILE = ''
    
    POST_CONFIG_MSG = None
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


    @classmethod
    def _isRecorder(cls, dev, strict=True):
        """ Basic test whether a path points to a recorder. """
        if strict is False:
            return True
        try:
            return "fat" in getDriveInfo(dev)[3].lower()
        except (TypeError, IndexError):
            return False
    

    def _getInfoAttr(self, name, default=None):
        info = self.getInfo()
        if info is None:
            return default
        return info.get(name, default)

    
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
        return self.productName
    
    @property
    def serial(self):
        """ The recorder's manufacturer-issued serial number. """
        return None

    @property
    def hardwareVersion(self):
        return 0
    
    @property
    def firmwareVersion(self):
        return 0
    
    def _configVersion(self):
        return self.productName, self.firmwareVersion
    
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
            json.dump([self.productName, self.firmwareVersion],f)
            f.write('\n')
            self._saveConfig(f, data, verify)
            return True
        
        
    def importConfig(self, filename, update=True, allowOlder=False, 
                     allowNewer=False):
        """ Read device configuration data from a file. The file must contain
            the device's product name, a newline, and then the data in the
            device's native format. If the product name doesn't match the
            device's product name a `ConfigVersionError` is raised.
            
            @param filename: The name of the exported config file to import.
            @keyword update: If `True`, the config data is applied to the
                device. If `False`, it is just imported.
            @return: A dictionary of configuration attributes.
        """
        with open(filename,'rb') as f:
            cname, cvers = json.loads(f.readline().strip())
            if cname == self.productName:
                if cvers < self.firmwareVersion:
                    good = allowOlder
                elif cvers > self.firmwareVersion:
                    good = allowOlder
                else:
                    good = True
            else:
                good = False

            versions = (cname, cvers, self.productName, self.firmwareVersion)
            if not good:
                raise ConfigVersionError(
                    "Device mismatch: this is %r v.%r, file is %r v.%r" % \
                    versions, versions)
        
            config = self._loadConfig(StringIO(f.read()))
            
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

    LIFESPAN = 31 #3 * 365
    CAL_LIFESPAN = 31

    TYPE_RANGES = {
       0x10: (-25,25),
       0x12: (-100,100),
       0x13: (-200,200),
       0x14: (-500, 500),
    }

    POST_CONFIG_MSG  = ("""When ready...\n"""
                        """    1. Disconnect Slam Stick X\n"""
                        """    2. Mount to surface\n"""
                        """    3. Press the "X" button """)

    baseName = "Slam Stick X"

    def __init__(self, path):
        super(SlamStickX, self).__init__(path)
        self._manifest = None
        self.clockFile = os.path.join(self.path, self.CLOCK_FILE)

    @classmethod
    def isRecorder(cls, dev, strict=True):
        """ Test whether a given filesystem path refers to the root directory
            of a Slam Stick X recorder.
        
            @param dev: The path to the possible recording device (e.g. a
                mount point under *NIX, or a drive letter under Windows)
            @keyword strict: If `False`, only the directory structure is used
                to identify a recorder. If `True`, non-FAT file systems will
                be automatically rejected. 
        """
        try:
            return (cls._isRecorder(dev, strict) and
                    os.path.exists(os.path.join(dev, cls.INFO_FILE)))

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
        return self._getInfoAttr('HwRev', -1)
    
    @property
    def firmwareVersion(self):
        return self._getInfoAttr('FwRev', -1)

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

    
            @param dev: The path to the recording device.
            @return: The system time and the device time, as integer seconds 
                since the epoch ('Unix time').
        """
        if sys.platform != "darwin" and "win" in sys.platform:
            return platform_specific.readRecorderClock(self.clockFile)
        t0 = time.time()
        f = open(self.clockFile, 'rb', 0)
        t = f.read(8)
        t1 = (time.time() + t0) / 2
        f.close()
        return t1, self.TIME_PARSER.unpack_from(t)
    
    
    def setTime(self, t=None, pause=True, retries=1):
        """ Set a recorder's date/time. A variety of standard time types are
            accepted. Note that the minimum unit of time is the whole second.
        
            @param dev: The path to the recording device.
            @keyword t: The time to write, as either seconds since the epoch 
                (i.e. 'Unix time'), `datetime.datetime` or a UTC 
                `time.struct_time`. The current time  (from the host) is used 
                if `None` (default).
            @keyword pause: If `True` (default), the system waits until a
                whole-numbered second before setting the clock. This may
                improve accuracy across multiple recorders.
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
        
        try:
            with open(self.clockFile, 'wb') as f:
                if pause:
                    t0 = int(time.time())
                    while int(t) <= t0:
                        t = time.time()
                f.write(self.TIME_PARSER.pack(t))
        except IOError as err:
            if retries > 0:
                time.sleep(.5)
                return self.setTime(pause=pause, retries=retries-1)
            else:
                raise err
        
        return t


    def getManifest(self, refresh=False):
        """ Read the device's manifest data. The data is a superset of the
            information returned by `getInfo()`.
        """
        if refresh is True:
            self._manifest = None
        
        if self._manifest is not None:
            return self._manifest
        
        # Recombine all the 'user page' files
        systemPath = os.path.join(self.path, 'SYSTEM', 'DEV')
        data = []
        for i in range(4):
            filename = os.path.join(systemPath, 'USERPG%d' % i)
            with open(filename, 'rb') as fs:
                data.append(fs.read())
        data = ''.join(data)
        
        manOffset, manSize, calOffset, calSize = struct.unpack_from("<HHHH", data)
        manData = StringIO(data[manOffset:manOffset+manSize])
        calData = StringIO(data[calOffset:calOffset+calSize])
        
        try:
            self._manifest = util.read_ebml(manData, schema='mide_ebml.ebml.schema.manifest').get('DeviceManifest', None)
            self._calibration = util.read_ebml(calData, schema='mide_ebml.ebml.schema.mide').get('CalibrationList', None)
        except (AttributeError, KeyError):
            pass
        
        return self._manifest


    def getCalibration(self, refresh=False):
        """ Get the recorder's factory calibration information.
        """
        self.getManifest(refresh=refresh)
        return self._calibration


    def getAge(self, refresh=False):
        """ Get the number of days since the recorder's date of manufacture.
        """
        try:
            birth = self.getInfo(refresh=refresh)['DateOfManufacture']
            return (time.time() - birth) / (60 * 60 * 24) 
        except (AttributeError, KeyError):
            return None
        

    def getEstLife(self, refresh=False):
        """ Get the recorder's estimated remaining life span in days. This is
            (currently) only a very basic approximation based on days since 
            the device's recorded date of manufacture.
            
            @return: The estimated days of life remaining. Negative values
                indicate the device is past its estimated life span. `None`
                is returned if no estimation could be made.
        """
        try:
            birth = self.getInfo(refresh=refresh)['DateOfManufacture']
            age = (time.time() - birth) / (60 * 60 * 24) 
            return int(0.5 + self.LIFESPAN - age)
        except (AttributeError, KeyError):
            return None


    def getCalExpiration(self, refresh=False):
        """ Get the expiration date of the recorder's factory calibration.
        """
        self.getCalibration(refresh=refresh)
        caldate = self._calibration.get('CalibrationDate', None)
        calexp = self._calibration.get('CalibrationExpiry', None)
        
        if caldate is None and calexp is None:
            return None
        
        if isinstance(calexp, int) and calexp > caldate:
            return calexp
        
        return  caldate + self.CAL_LIFESPAN
    

#===============================================================================

class SlamStickClassic(Recorder):
    """
    """
    CONFIG_FILE = "config.dat"
    INFO_FILE = "config.dat"
    DATA_FILE = "data.dat"

    baseName = "Slam Stick Classic"

    @classmethod
    def isRecorder(cls, dev, strict=True):
        """ Does the specified path refer to a recorder?
        
            @param dev: The path to the possible recording device (e.g. a
                mount point under *NIX, or a drive letter under Windows)
            @keyword strict: If `False`, only the directory structure is used
                to identify a recorder. If `True`, non-FAT file systems will
                be automatically rejected. 
        """
        dev = os.path.realpath(dev)
        try:
            return (cls._isRecorder(dev, strict) and
                    os.path.exists(os.path.join(dev, cls.CONFIG_FILE)) and
                    os.path.exists(os.path.join(dev, cls.DATA_FILE)))
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
    def _unpackUID(cls, s):
        if '\x00' in s:
            s = s.split('\x00')[0]
        return s.rstrip(u'\x00\xff')


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
            n = self.getConfig().get('USER_NAME', '').strip()
            self._name = str(n or self.volumeName)
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
   
    
    def setTime(self, t=None, pause=True, retries=1):
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
        pause = False if t is None else pause
        
        if t is None:
            t = int(time.time())
        elif isinstance(t, datetime):
            t = calendar.timegm(t.timetuple())
        elif isinstance(t, (time.struct_time, tuple)):
            t = calendar.timegm(t)
        else:
            t = int(t)
        
        conf['RTCC_TIME'] = t
        conf['WR_RTCC'] = 0x5A
        
        try:
            with open(self.configFile, 'wb') as f:
                if pause:
                    t0 = int(time.time())
                    while int(t) <= t0:
                        t = time.time()
                conf['RTCC_TIME'] = t
                classic_config.writeConfig(f, conf)
        except IOError as err:
            if retries > 0:
                time.sleep(.5)
                return self.setTime(pause=pause, retries=retries-1)
            else:
                raise err
        
        return t


    def getAccelRange(self):
        """ Get the range of the device's acceleration measurement.
        """
        # Slam Stick Classic only comes in one flavor: 16 G.
        return (-16,16) 
 
 
    def getCalibration(self, refresh=False):
        """ Get the recorder's calibration information. On a Slam Stick Classic,
            this is just a subset of the data returned by `getInfo()`.
        """
        self.getInfo(refresh=refresh)
        cal = {}
        for a in ('CALOFFSX', 'CALOFFSY', 'CALOFFSZ', 'CALGAINX', 'CALGAINY', 'CALGAINZ'):
            cal[a] = self._getInfoAttr(a)
        return cal
        
 
    def getEstLife(self):
        """
        """
        return None
    
    
#===============================================================================
# 
#===============================================================================

RECORDER_TYPES = (SlamStickClassic, SlamStickX)


#===============================================================================
# 
#===============================================================================

def deviceChanged(recordersOnly=True, types=RECORDER_TYPES):
    return platform_specific.deviceChanged(recordersOnly, types)


def getDeviceList(types=RECORDER_TYPES):
    return platform_specific.getDeviceList(types)


def getDevices(paths=None, types=RECORDER_TYPES):
    """ Get a list of data recorder objects.
    
        @keyword paths: A list of specific paths to recording devices. 
            Defaults to all found devices (as returned by `getDeviceList()`).
        @keyword types: A list of `Recorder` subclasses to find.
        @return: A list of instances of `Recorder` subclasses.
    """
    result = []
    paths = platform_specific.getDeviceList(types) if paths is None else paths
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