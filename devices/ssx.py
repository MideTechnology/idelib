'''
Created on Jan 28, 2015

@author: dstokes
'''
import calendar
from datetime import datetime, timedelta
import os
from StringIO import StringIO
import struct
import time

from mide_ebml import util
from mide_ebml.parsers import CalibrationListParser #PolynomialParser
from mide_ebml.ebml.schema.mide import MideDocument

from base import Recorder, os_specific
# from base import ConfigError, ConfigVersionError

#===============================================================================
# 
#===============================================================================

class SlamStickX(Recorder):
    """ A Slam Stick X data recorder from Mide Technology Corporation. 
    """
    
    SYSTEM_PATH = "SYSTEM"
    INFO_FILE = os.path.join(SYSTEM_PATH, "DEV", "DEVINFO")
    CLOCK_FILE = os.path.join(SYSTEM_PATH, "DEV", "CLOCK")
    CONFIG_FILE = os.path.join(SYSTEM_PATH, "config.cfg")
    TIME_PARSER = struct.Struct("<L")

    LIFESPAN = timedelta(2 * 365)
    CAL_LIFESPAN = timedelta(365)

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
    manufacturer = u"Mid\xe9 Technology Corp."
    homepage = "http://www.mide.com/products/slamstick/slam-stick-x-vibration-temperature-pressure-data-logger.php"

    def __init__(self, path):
        super(SlamStickX, self).__init__(path)
        self._manifest = None
        self._calibration = None
        self._calData = None
        self._calPolys = None
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
        sysTime, devTime = os_specific.readRecorderClock(self.clockFile)
        return sysTime, self.TIME_PARSER.unpack_from(devTime)
    
    
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
            @keyword retries: The number of attempts to make, should the first
                fail. Random filesystem things can potentially cause hiccups.
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
            self._calibration = None
        
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
        self._calData = StringIO(data[calOffset:calOffset+calSize])
        
        try:
            self._manifest = util.read_ebml(manData, 
                schema='mide_ebml.ebml.schema.manifest').get('DeviceManifest', None)
            self._calibration = util.read_ebml(self._calData, 
               schema='mide_ebml.ebml.schema.mide').get('CalibrationList', None)
        except (AttributeError, KeyError):
            pass
        
        return self._manifest


    def getCalibration(self, refresh=False):
        """ Get the recorder's factory calibration information.
        """
        self.getManifest(refresh=refresh)
        return self._calibration


    def getCalPolynomials(self, refresh=False):
        """ Get the constructed Polynomial objects created from the device's
            calibration data.
        """
        self.getManifest(refresh=refresh)
        if self._calPolys is None:
            try:
                PP = CalibrationListParser(None)
                self._calData.seek(0)
                cal = MideDocument(self._calData)
                self._calPolys = filter(None, PP.parse(cal.roots[0]))
                return self._calPolys
            except (KeyError, IndexError, ValueError):
                pass
        
        return self._calPolys
            

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
            return int(0.5 + self.LIFESPAN.total_seconds() - age)
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
        
        return  caldate + self.CAL_LIFESPAN.total_seconds()
    