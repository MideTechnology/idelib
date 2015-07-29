'''
Class defintion and supporting items for Mide Slam Stick Classic data recorders.

@todo: Move everything from mide_ebml.classic.config into this module. It is 
    more appropriate here.

Created on Jan 28, 2015

@author: dstokes
'''

import calendar
from datetime import datetime
import os
import time

from mide_ebml.classic import config as classic_config
from base import Recorder

#===============================================================================
# 
#===============================================================================

class SlamStickClassic(Recorder):
    """ A Slam Stick Classic data recorder.
    """
    
    CONFIG_FILE = "config.dat"
    INFO_FILE = "config.dat"
    DATA_FILE = "data.dat"

    baseName = "Slam Stick Classic"
    manufacturer = u"Mid\xe9 Technology Corp."
    homepage = "http://www.mide.com/products/slamstick/slamstick-vibration-data-logger.php"

    def __init__(self, *args, **kwargs):
        super(SlamStickClassic, self).__init__(*args, **kwargs)
        
        # Parameters for importing saved config data.
        self._importOlderFwConfig = True
        self._importNewerFwConfig = False
        self._importOlderHwConfig = True
        self._importNewerHwConfig = False
        self._defaultHwRev = 0


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


    def _loadConfig(self, source, hwRev=None, fwRev=None, default=None):
        """ Device-specific configuration data reader. """
        return classic_config.readConfig(source)
    

    def _saveConfig(self, dest, data, verify=True):
        """ Device-specific configuration data writer. """
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
    
    