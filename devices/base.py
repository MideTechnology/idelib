'''
Items common to all recorder types. Separate from module's __init__.py to
eliminate circular dependencies.

Created on Jan 28, 2015

@author: dstokes
'''

from collections import OrderedDict
import json
import os.path
import sys

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

if sys.platform == 'darwin':
    import macos 
    os_specific = macos
elif 'win' in sys.platform:
    import win
    os_specific = win

#===============================================================================
# 
#===============================================================================

class ConfigError(ValueError):
    """ Exception raised when configuration data is invalid. 
    """


class ConfigVersionError(ConfigError):
    """ Exception raised when configuration format doesn't match the recorder
        hardware or firmware version.
    """

#===============================================================================
# 
#===============================================================================

class Recorder(object):
    """ Base class for all data recorders. Should be considered 'abstract' and
        never actually instantiated.
    """
    INFO_FILE = ''
    CONFIG_FILE = ''
    
    POST_CONFIG_MSG = None
    productName = "Generic Recorder"
    baseName = productName
    homepage = None
    
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
        self.volumeName = os_specific.getDriveInfo(self.path).label
        self.configFile = os.path.join(self.path, self.CONFIG_FILE)
        self.infoFile = os.path.join(self.path, self.INFO_FILE)
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
            return "fat" in os_specific.getDriveInfo(dev).fs.lower()
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
        return self.baseName
    
    @property
    def serial(self):
        """ The recorder's manufacturer-issued serial number. """
        return None

    @property
    def hardwareVersion(self):
        """ The recorder's manufacturer-issued hardware version number. """
        return 0
    
    @property
    def firmwareVersion(self):
        """ The recorder's manufacturer-issued firmware version number. """
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
    
    def getCalibration(self, refresh=False):
        """ Get the recorder's factory calibration information.
        """
        return None

    def getAge(self, refresh=False):
        """ Get the number of days since the recorder's date of manufacture.
        """
        return None
        
    def getEstLife(self, refresh=False):
        """ Get the recorder's estimated remaining life span in days. This is
            (currently) only a very basic approximation based on days since 
            the device's recorded date of manufacture.
            
            @return: The estimated days of life remaining. Negative values
                indicate the device is past its estimated life span. `None`
                is returned if no estimation could be made.
        """
        return None

    def getCalExpiration(self, refresh=False):
        """ Get the expiration date of the recorder's factory calibration.
        """
        return None
