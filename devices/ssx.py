'''
Created on Jan 28, 2015

@author: dstokes
'''
import calendar
from collections import OrderedDict
from datetime import datetime
import os
import struct
import time

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from mide_ebml import util
from mide_ebml.dataset import Dataset
from mide_ebml import importer
from mide_ebml.parsers import CalibrationListParser, RecordingPropertiesParser
from mide_ebml.parsers import getParserRanges
from mide_ebml.ebml.schema.mide import MideDocument
import mide_ebml.ebml.schema.mide as schema_mide
import mide_ebml.ebml.schema.manifest as schema_manifest

from base import Recorder, os_specific
from devices.base import ConfigError


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
    USERCAL_FILE = os.path.join(SYSTEM_PATH, "usercal.dat")
    TIME_PARSER = struct.Struct("<L")

    # TODO: This really belongs in the configuration UI
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
        self._userCalPolys = None
        self._userCalDict = None
        self._factoryCalPolys = None
        self._factoryCalDict = None
        self._accelChannels = None
        if self.path is not None:
            self.clockFile = os.path.join(self.path, self.CLOCK_FILE)
            self.userCalFile = os.path.join(self.path, self.USERCAL_FILE)
        else:
            self.clockFile = self.userCalFile = None

        # Parameters for importing saved config data.
        self._importOlderFwConfig = False
        self._importNewerFwConfig = False
        self._importOlderHwConfig = False
        self._importNewerHwConfig = False
        self._defaultHwRev = 4


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
            if cls._isRecorder(dev, strict):
                infoFile = os.path.join(dev, cls.INFO_FILE)
                if os.path.exists(infoFile):
                    if not strict:
                        return True
                    devinfo = util.read_ebml(infoFile, schema=schema_mide)
                    props = devinfo['RecordingProperties']['RecorderInfo']
                    return "Slam Stick X" in props['RecorderTypeUID']
        except (KeyError, TypeError, AttributeError, IOError):
            pass
        return False


    def getInfo(self, default=None, refresh=False):
        """ Retrieve a recorder's device information.
        
            @return: A dictionary containing the device data.
        """
        if self.path is None:
            # No path: probably a recorder description from a recording.
            return self._info
        
        if self._info is not None and not refresh:
            return self._info
        try:
            devinfo = util.read_ebml(self.infoFile, schema=schema_mide)
            props = devinfo.get('RecordingProperties', '')
            if 'RecorderInfo' in props:
                self._info = props['RecorderInfo']
                
                return self._info
        except IOError:
            pass
        return default


    def _loadConfig(self, source, hwRev=None, fwRev=None, default=None):
        """ Helper method to read configuration info from a file. Used
            internally.
        """
        devinfo = util.read_ebml(source, schema=schema_mide)
        return devinfo.get('RecorderConfiguration', default)


    def _saveConfig(self, dest, data, verify=True):
        """ Device-specific configuration file saver. Used internally; call
            `SlamStickX.saveConfig()` instead.
        """
        ebml = util.build_ebml("RecorderConfiguration", data, schema=schema_mide)
        if verify and not util.verify(ebml, schema=schema_mide):
            raise ValueError("Generated config EBML could not be verified")
        if isinstance(dest, basestring):
            with open(dest, 'wb') as f:
                f.write(ebml)
        else:
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
    def productId(self):
        return self._getInfoAttr('RecorderTypeUID', 0x12) & 0xff
    
    @property
    def partNumber(self):
        return self._getInfoAttr('PartNumber', '')
    
    @property
    def serial(self):
        """ The recorder's manufacturer-issued serial number. """
        if self._sn is None:
            self._snInt = self._getInfoAttr('RecorderSerial', None)
            if self._snInt == None:
                self._sn = ""
            else:
                self._sn = "SSX%07d" % self._snInt
        return self._sn

    @property
    def serialInt(self):
        _ = self.serial
        return self._snInt

    @property
    def hardwareVersion(self):
        return self._getInfoAttr('HwRev', -1)

    
    @property
    def firmwareVersion(self):
        return self._getInfoAttr('FwRev', -1)

    @property
    def birthday(self):
        return self._getInfoAttr('DateOfManufacture')


    def getAccelRange(self, channel=8, subchannel=0, rounded=True, refresh=False):
        """ Get the range of the device's acceleration measurement.
        """
        # TODO: This can be made more general and be used for any channel.
        # This is also very kludgey.  
        key = (channel, subchannel)
        if key in self._channelRanges and not refresh:
            return self._channelRanges[key]
        
        channels = self.getChannels(refresh=refresh)
        xforms = self.getCalPolynomials()
        
        if channels is None:
            raise ConfigError("Could not read any channels from device!")
        if xforms is None:
            raise ConfigError("Could not read any transform polynomials from device!")
        
        # TODO: Make this more generic by finding the accelerometer channels.
        # Also, it could fall back to the AnalogSensorScaleHintF.
        try:
            chId = channel if channel in channels else 32
            ch = channels[chId if chId in channels else 0]
        except KeyError:
            raise ConfigError("Could not find any accelerometer channels "
                              "(tried %r, %r, and %r)" % (channel, 32, 0))
        xform = ch.transform
        if isinstance(xform, int):
            try:
                xform = xforms[ch.transform]
            except KeyError:
                raise ConfigError("No such transform polynomial ID %r" % \
                                  ch.transform)
            
        r = getParserRanges(ch.parser)[subchannel]
        hi = xform.function(r[1])
        
        # HACK: The old parser minimum is slightly low; use negative max.
#         lo = xform.function(r[0])
        lo = -hi
        
        if rounded:
            self._channelRanges[key] = (float("%.2f" % lo), float("%.2f" % hi))
        else:
            self._channelRanges[key] = (lo, hi)
            
        return self._channelRanges[key]

    
    def getAccelChannel(self, dc=False):
        """ Retrieve the accelerometer parent channel.
            
            @keyword dc: If `True`, return the digital, 'low-g' DC 
                accelerometer, if present.
        """
        try:
            # TODO: Make this more generic by finding the actual channel
            channels = self.getChannels()
            if dc:
                return channels[32]
            return channels[8 if 8 in channels else 0]
        except KeyError:
            return None


    def getAccelAxisChannels(self, dc=False):
        """ Retrieve a list of all accelerometer axis subchannels, ordered 
            alphabetically (X, Y, Z).
            
            @keyword dc: If `True`, return the digital, 'low-g' DC 
                accelerometer, if present.
        """
        try:
            accel = self.getAccelChannel(dc=dc)
            return sorted(accel.subchannels, key=lambda x: x.axisName)
        except (IndexError, KeyError, AttributeError):
            return None
        

    def getPressureChannel(self):
        """ Retrieve the pressure channel.
        """
        try:
            # TODO: Make this more generic by finding the actual channel
            channels = self.getChannels()
            return channels[36 if 36 in channels else 1][0]
        except KeyError:
            return None
        
    
    def getTempChannel(self):
        """ Retrieve the temperature channel.
        """
        try:
            # TODO: Make this more generic by finding the actual channel
            channels = self.getChannels()
            return channels[36 if 36 in channels else 1][1]
        except KeyError:
            return None

    
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
        if self.path is None:
            raise ConfigError('Could not get time: Not a real device!')
        
        sysTime, devTime = os_specific.readRecorderClock(self.clockFile)
        return sysTime, self.TIME_PARSER.unpack_from(devTime)[0]
    
    
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
        if self.path is None:
            raise ConfigError('Could not set time: Not a real device!')
        
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


    def _parsePolynomials(self, stream):
        """ Helper method to parse CalibrationList EBML into `Transform`
            objects. 
        """
        try:
            PP = CalibrationListParser(None)
            stream.seek(0)
            cal = MideDocument(stream)
            calPolys = PP.parse(cal.roots[0])
            if calPolys:
                calPolys = {p.id: p for p in calPolys if p is not None}
            return calPolys
        except (KeyError, IndexError, ValueError):
            pass


    def getManifest(self, refresh=False):
        """ Read the device's manifest data. The data is a superset of the
            information returned by `getInfo()`.
        """
        if self.path is None:
            return self._manifest
        
        if refresh is True:
            self._manifest = None
            self._calibration = None
            self._properties = None
            self._channels = None
            self._sensors = None
            self._warnings = None
        
        if self._manifest is not None:
            return self._manifest
        
        # Recombine all the 'user page' files
        systemPath = os.path.join(self.path, 'SYSTEM', 'DEV')
        data = bytearray()
        for i in range(4):
            filename = os.path.join(systemPath, 'USERPG%d' % i)
            with open(filename, 'rb') as fs:
                data.extend(fs.read())
        
        (manOffset, manSize, 
         calOffset, calSize, 
         propOffset, propSize) = struct.unpack_from("<HHHHHH", data)
        
        manData = StringIO(data[manOffset:manOffset+manSize])
        self._calData = StringIO(data[calOffset:calOffset+calSize])
        
        # _propData is read here but parsed in `getSensors()`
        # Zero offset means no property data. Size should also be zero, but JIC:
        propSize = 0 if propOffset == 0 else propSize
        self._propData = data[propOffset:propOffset+propSize]
        
        try:
            self._manifest = util.read_ebml(manData, schema=schema_manifest
                                            ).get('DeviceManifest', None)
            self._calibration = util.read_ebml(self._calData, schema=schema_mide,
                                               ).get('CalibrationList', None)
        except (AttributeError, KeyError):
            pass
        
        return self._manifest


    def getFactoryCalibration(self, refresh=False):
        """ Get the recorder's factory calibration information.
        """
        self.getManifest(refresh=refresh)
        return self._calibration


    def getFactoryCalPolynomials(self, refresh=False):
        """ Get the constructed Polynomial objects created from the device's
            calibration data.
        """
        self.getSensors(refresh=refresh)
        if self._calPolys is None:
            self._calPolys = self._parsePolynomials(self._calData)
        
        return self._calPolys
            
    
    def getUserCalibration(self, refresh=False):
        """ Get the recorder's user-defined calibration data as a dictionary
            of parameters.
        """
        if self.userCalFile is None or not os.path.exists(self.userCalFile):
            return None
        if self._userCalDict is None or refresh:
            with open(self.userCalFile, 'rb') as f:
                d = util.read_ebml(f, schema=schema_mide)
                self._userCalDict = d.get('CalibrationList', None)
        return self._userCalDict


    def getUserCalPolynomials(self, filename=None, refresh=False):
        """ Get the recorder's user-defined calibration data as a dictionary
            of `mide_ebml.transforms.Transform` subclass objects.
        """
        filename = self.userCalFile if filename is None else filename
        if filename is None or not os.path.exists(filename):
            return None
        if self._userCalPolys is None or refresh:
            with open(filename, 'rb') as f:
                self._userCalPolys = self._parsePolynomials(f)
        return self._userCalPolys
        

    def getCalibration(self, refresh=False):
        """ Get the recorder's current calibration information. User-supplied
            calibration, if present, takes priority.
        """
        c = self.getUserCalibration(refresh=refresh)
        if c is not None:
            return c
        return self.getFactoryCalibration(refresh=refresh)


    def getCalPolynomials(self, refresh=False):
        """ Get the constructed Polynomial objects created from the device's
            current calibration data. User-supplied calibration, if present, 
            takes priority.
        """
        c = self.getUserCalPolynomials(refresh=refresh)
        if c is not None:
            return c
        return self.getFactoryCalPolynomials(refresh=refresh)

    
    def getProperties(self, refresh=False):
        """ Get the raw Recording Properties from the device. 
        """
        # TODO: Optimize. Cache data like getManifest and such.
        self.getManifest(refresh=refresh)
        data = util.read_ebml(StringIO(self._propData), schema=schema_mide)
        return data.get('RecordingProperties', {})
        

    def getSensors(self, refresh=False):
        """ Get the recorder sensor description data.
            @todo: Merge with manifest sensor data?
        """
        self.getManifest(refresh=refresh)

        if self._sensors is not None:
            return self._sensors
        
        # Use dataset parsers to read the recorder properties. 
        # This also caches the channels, polynomials, and warning ranges.
        # This is nice in theory but kind of ugly in practice.
        try:
            doc = Dataset(None)
            if not self._propData:
                # No recorder property data; use defaults
                if 'SystemInfo' in self._manifest:
                    doc.recorderInfo = self._manifest['SystemInfo'].copy()
                # Manifest uses different name for element.
                doc.recorderInfo['RecorderTypeUID'] = doc.recorderInfo['DeviceTypeUID']
                importer.createDefaultSensors(doc)
                doc.transforms.setdefault(0, doc.channels[0].transform)
#                 if self._calPolys is None:
#                     self._calPolys = doc.transforms
            else:
                # Parse userpage recorder property data
                parser = RecordingPropertiesParser(doc)
                doc._parsers = {'RecordingProperties': parser}
                parser.parse(MideDocument(StringIO(self._propData)).roots[0])
            self._channels = doc.channels
            self._sensors = doc.sensors
            self._warnings = doc.warningRanges
        except (IndexError, AttributeError):
            pass
        
        return self._sensors
        

    def getChannels(self, refresh=False):
        """ Get the recorder channel/subchannel description data.
        """
        # `getSensors()` does all the real work
        self.getSensors(refresh=refresh)
        return self._channels


    def getUserCalDate(self, refresh=False):
        """ Get the date of the recorder's user-defined calibration. This data
            may or may not be available.
        """
        try:
            return self.getUserCalibration(refresh)['CalibrationDate']
        except (KeyError, TypeError):
            return None
        
        
    def getFactoryCalDate(self, refresh=False):
        """ Get the date of the recorder's factory calibration.
        """
        try:
            return self.getFactoryCalibration(refresh)['CalibrationDate']
        except (KeyError, TypeError):
            return None


    def getCalDate(self, refresh=False):
        """ Get the date of the recorder's active calibration.
            User-supplied calibration, if present, takes priority.
        """
        try:
            return self.getCalibration(refresh)['CalibrationDate']
        except (KeyError, TypeError):
            return None
    
    
    def _getCalExpiration(self, data):
        """ Get the expiration date of the recorder's factory calibration.
        """
        if data is None:
            return None
        caldate = data.get('CalibrationDate', None)
        calexp = data.get('CalibrationExpiry', None)
        
        if caldate is None and calexp is None:
            return None
        
        if isinstance(calexp, int) and calexp > caldate:
            return calexp
        
        return  caldate + self.CAL_LIFESPAN.total_seconds()


    def getFactoryCalExpiration(self, refresh=False):
        """ Get the expiration date of the recorder's factory calibration.
        """
        return self._getCalExpiration(self.getFactoryCalibration(refresh))


    def getUserCalExpiration(self, refresh=False):
        """ Get the expiration date of the recorder's user-defined calibration.
            This data may or may not be available.
        """
        return self._getCalExpiration(self.getUserCalibration(refresh))


    def getCalExpiration(self, refresh=False):
        """ Get the expiration date of the recorder's active calibration.
            User-supplied calibration, if present, takes priority.
        """
        return self._getCalExpiration(self.getCalibration(refresh))
        

    def getCalSerial(self, refresh=False):
        """ Get the recorder's factory calibration serial number.
        """
        try:
            return self.getCalibration(refresh)['CalibrationSerialNumber']
        except (KeyError, TypeError):
            return None


    def getFactoryCalSerial(self, refresh=False):
        """ Get the recorder's factory calibration serial number.
        """
        try:
            return self.getFactoryCalibration(refresh)['CalibrationSerialNumber']
        except (KeyError, TypeError):
            return None

    
    @classmethod
    def generateCalEbml(cls, transforms, date=None, expires=None, calSerial=0):
        """ Write a set of calibration to a file. For the keyword arguments, a
            value of `False` will simply not write the corresponding element.
        
            @param transforms: A dictionary or list of `mide_ebml.calibration`
                objects.
            @keyword date: The date of calibration. If `None`, the current
                date/time is used. 
            @keyword expires: The calibration expiration date. If `None`, the
                calibration date plus default calibration lifespan is used.
            @keyword calSerial: The calibration serial number (integer). 0 is
                assumed to be user-created calibration.
        """
        if isinstance(transforms, dict):
            transforms = transforms.values()
        if date is None:
            date = time.time()
        if expires is None:
            expires = date + cls.CAL_LIFESPAN.total_seconds()
            
        data = OrderedDict()
        for xform in transforms:
            if xform.id is None:
                continue
            n = "%sPolynomial" % xform.__class__.__name__
            data.setdefault(n, []).append(xform.asDict())

        if date:
            data['CalibrationDate'] = int(date)
        if expires:
            data['CalibrationExpiry'] = int(expires)
        if isinstance(calSerial, int):
            data['CalibrationSerialNumber'] = calSerial
            
        return util.build_ebml('CalibrationList', data, schema=schema_mide)
    
    
    def writeUserCal(self, transforms, filename=None):
        """ Write user calibration to the SSX.
        
            @param transforms: A dictionary or list of `mide_ebml.calibration`
                objects.
            @keyword filename: An alternate file to which to write the data,
                instead of the standard user calibration file.
        """
        filename = self.userCalFile if filename is None else filename
        if filename is None:
            raise ConfigError('Could not write user calibration data: '
                              'Not a real recorder!')
        cal = self.generateCalEbml(transforms)
        with open(filename, 'wb') as f:
            f.write(cal)
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    @classmethod
    def fromRecording(cls, dataset):
        """ Create a 'fake' recorder from the recorder description in a
            recording.
        """
        ssx = cls(None)
        ssx._info = dataset.recorderInfo.copy()
        ssx._calPolys = dataset.transforms.copy()
        ssx._channels = dataset.channels.copy()
        ssx._warnings = dataset.warningRanges.copy()
        
        # Datasets merge calibration info info recorderInfo; separate them.
        ssx._calibration = {}
        for k in ('CalibrationDate', 
                  'CalibrationExpiry', 
                  'CalibrationSerialNumber'):
            v = ssx._info.pop(k, None)
            if v is not None:
                ssx._calibration[k] = v
        
        return ssx
        
        
        