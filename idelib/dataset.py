"""
Module for reading and analyzing Mide Instrumentation Data Exchange (MIDE)
files.

Created on Sep 26, 2013

:author: dstokes

"""

# TODO: Sensor subchannels. Requires schema/firmware updates.
#
# TODO: Transforms on Sensors. It's stubbed out, but not used in combo
#    transforms.
# 
# TODO: Clean out some of the unused features. They make the code less clear,
#    creating more than one way to do the same thing. More often than not, 
#    they are the result of over-engineering things.
#
# TODO: The new, cached EventArray transforms save the combined transforms on
#    the parent EventArray. This should probably be revised to have the cached
#    transforms saved on the children; this will allow multiple copies of
#    EventArrays to have different transforms, simplifying the whole regular
#    versus 'display' things and make 'useAllTransforms' unnecessary. 
#
# TODO: Handle files with channels containing a single sample better. Right now,
#    they are ignored, causing problems with other calculations.
#
# TODO: Consider an EventArray subclass for subchannels to reduce the number
#    of conditionals evaluated, and/or see about making parent Channels' 
#    EventArrays flat.
#   
# TODO: Nice discontinuity handing. This will probably be conveyed as events 
#     with null values. An attribute/keyword may be needed to suppress this when 
#     getting data for processing (FFT, etc.). Low priority.
#     
# TODO: Look at remaining places where lists are returned, consider using 
#    `yield`  instead (e.g. parseElement(), etc.)
# 
# TODO: Consider thread safety. Use a `threading.RLock` around adding/ending
#    a Session, updating/using Transforms, appending/accessing EventArray data,
#    etc. Not (yet?) a serious problem, but it could be in the future; current
#    handling of race conditions is a hack. Also make some flags (like
#    `Dataset.loading`) properties that get/set a `threading.Event`?

__all__ = ['Channel', 'Dataset', 'EventArray', 'Plot', 'Sensor', 'Session',
           'SubChannel', 'WarningRange', 'Cascading', 'Transformable']

from bisect import bisect_right
from collections.abc import Iterable, Sequence
from datetime import datetime
from threading import Lock
import warnings

from functools import partial
import os.path
import random
import struct
import sys
from time import sleep

from ebmlite.core import loadSchema
import numpy as np
import numpy.lib.recfunctions as np_recfunctions

from .transforms import Transform, CombinedPoly, PolyPoly
from .parsers import getParserTypes, getParserRanges, ChannelDataBlock


SCHEMA_FILE = 'mide_ide.xml'

#===============================================================================
# DEBUGGING: XXX: Remove later!
#===============================================================================

import logging
logger = logging.getLogger('idelib')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")


# __DEBUG__ = False

__DEBUG__ = str(os.environ.get('MIDE_DEV', 0)) == '1'
    
if __DEBUG__:
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.ERROR)
    
# import ebml
# logger.info("Loaded python-ebml from %s" % os.path.abspath(ebml.__file__))


#===============================================================================
# Mix-In Classes
#===============================================================================

class Cascading(object):
    """ A base/mix-in class for objects in a hierarchy. 
    """

    parent = None
    name = ""

    def path(self):
        """ Get the combined names of all the object's parents/grandparents.
        """
        if self.parent is None:
            return self.name
        p = self.parent.path()
        if not p:
            return self.name
        return "%s:%s" % (p, self.name)
    
    
    def hierarchy(self):
        """ Get a list of parents/grandparents all the way back to the root.
            The root is the first item in the list.
        """
        if self.parent is None:
            return [self]
        result = self.parent.hierarchy()
        result.append(self)
        return result


    def __repr__(self):
        return "<%s %r at 0x%08x>" % (self.__class__.__name__, self.path(), 
                                      id(self))
    
    
class Transformable(Cascading):
    """ A mix-in class for objects that transform data (apply calibration,
        etc.), making it easy to turn the transformation on or off.
        
        :ivar transform: The transformation function/object
        :ivar raw: If `False`, the transform will not be applied to data.
            Note: The object's `transform` attribute will not change; it will
            just be ignored.
    """

    def setTransform(self, transform, update=True):
        """ Set the transforming function/object. This does not change the
            value of `raw`, however; the new transform will not be applied
            unless it is `True`.
        """
        self.transform = transform
        if isinstance(transform, int):
            self.transformId = transform
        else:
            self.transformId = getattr(transform, 'id', None)
            
        if transform is None:
            self._transform = Transform.null
        else:
            self._transform = transform
        if update:
            self.updateTransforms()
        
        
    def _updateXformIds(self):
        xform = self.transform
        if isinstance(self.transform, int):
            xform = self.dataset.transforms.get(xform, None)
        elif isinstance(self.transform, Transform):
            xform = self.dataset.transforms.get(xform.id, xform)
        self.transform = xform


    def updateTransforms(self):
        """ Recompute cached transform functions.
        """
        # Convert ID references (as will be in a fresh import) to the
        # actual Transform objects
        self._updateXformIds()
        for c in self.children:
            c.updateTransforms()
            

    def getTransforms(self, id_=None, _tlist=None):
        """ Get a list of all transforms applied to the data, from first (the
            lowest-level parent) to last (the transform, if any, on the
            object itself).
            
        """
        _tlist = [] if _tlist is None else _tlist
        if getattr(self, "_transform", None) is not None:
            if isinstance(self._transform, Iterable) and id_ is not None:
                x = self._transform[id_]
            else:
                x = self._transform
            if x != Transform.null:
                _tlist.insert(0, x)
        if isinstance(self.parent, Transformable):
            subchannelId = getattr(self, "id", None)
            self.parent.getTransforms(subchannelId, _tlist)
        return _tlist


#===============================================================================
# 
#===============================================================================

class Dataset(Cascading):
    """ A collection of sensor data and associated configuration info. 
        Typically represents a single MIDE EMBL file.
        
        Dictionary attributes are all keyed by the relevant ID (sensor ID,
        channel ID, etc.).
        
        :ivar loading: Boolean; `True` if a file is still loading (or has not
            yet been loaded).
        :ivar fileDamaged: Boolean; `True` if the file ended prematurely.
        :ivar loadCancelled: Boolean; `True` if the file loading was aborted 
            part way through.
        :ivar sessions: A list of individual Session objects in the data set.
            A valid file will have at least one, even if there are no 
            `Session` elements in the data.
        :ivar sensors: A dictionary of Sensors.
        :ivar channels: A dictionary of individual Sensor channels.
        :ivar plots: A dictionary of individual Plots, the modified output of
            a Channel (or even another plot).
        :ivar transforms: A dictionary of functions (or function-like objects)
            for adjusting/calibrating sensor data.
    """

    def __init__(self, stream, name=None, quiet=True, attributes=None):
        """ Constructor. Typically, these objects will be instantiated by
            functions in the `importer` module.
        
            :param stream: A file-like stream object containing EBML data.
            :keyword name: An optional name for the Dataset. Defaults to the
                base name of the file (if applicable).
            :keyword quiet: If `True`, non-fatal errors (e.g. schema/file
                version mismatches) are suppressed. 
            :keyword attributes: A dictionary of arbitrary attributes, e.g.
                ``Attribute`` elements parsed from the file. Typically
                used for diagnostic data.
        """
        self.lastUtcTime = None
        self.sessions = []
        self.sensors = {}
        self._channels = {}
        self.warningRanges = {}
        self.plots = {}
        self.transforms = {}
        self.parent = None
        self.currentSession = None
        self.recorderInfo = {}
        self.recorderConfig = None

        self.attributes = attributes if attributes else {}

        # For keeping track of element parsers in import.
        self._parsers = None
        
        self.fileDamaged = False
        self.loadCancelled = False
        self.loading = True
        self.filename = getattr(stream, "name", None)

        self._channelDataLock = Lock()
        
        # Subsets: used when importing multiple files into the same dataset.
        self.subsets = []

        if name is None:
            if self.filename is not None:
                self.name = os.path.splitext(os.path.basename(self.filename))[0]
            else:
                self.name = ""
        else:
            self.name = name

        if stream is not None:
            schema = loadSchema(SCHEMA_FILE)
            self.schemaVersion = schema.version
            self.ebmldoc = schema.load(stream, 'MideDocument', headers=True)
            if self.ebmldoc.version is None:
                logger.info('IDE has no EBML header data, older schema version being assumed.')
            elif not quiet:
                # It is currently assumed future versions will be backwards
                # compatible. Change if/when not, or if certain old versions aren't.
                if self.schemaVersion < self.ebmldoc.version:
                    raise IOError("EBML schema version mismatch: file is %d, "
                                  "library is %d" % (self.ebmldoc.version,
                                                     self.schemaVersion))


    @property
    def exitCondition(self):
        """ The numeric code number for the condition that stopped the recording. """
        return self.attributes.get('ExitCond', [None])[0]


    @property
    def channels(self):
        """ A dictionary of individual Sensor channels. """
        # Only return channels with subchannels. If all analog subchannels are
        # disabled, the recording properties will still show the parent channel.
        return {k:v for k,v in self._channels.items() if v.subchannels}


    def close(self):
        """ Close the recording file.
        """
        stream = self.ebmldoc.stream
        if hasattr(stream, 'closeAll'):
            # File is a ThreadAwareFile; close for all threads.
            result = stream.closeAll()
        else:
            result = stream.close()
            
        for s in self.subsets:
            try:
                s.close()
            except (AttributeError, IOError):
                pass
            
        return result
                
    
    @property
    def closed(self):
        """ Has the recording file been closed? """
        return getattr(self.ebmldoc.stream, "closed", True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


    def addSession(self, startTime=None, endTime=None, utcStartTime=None):
        """ Create a new session, add it to the Dataset, and return it.
            Part of the import process.
        """
        self.endSession()
        utcStartTime = self.lastUtcTime if utcStartTime is None else utcStartTime
        self.currentSession = Session(self, 
                                      sessionId=len(self.sessions), 
                                      startTime=startTime, 
                                      endTime=endTime,
                                      utcStartTime=utcStartTime)
        self.sessions.append(self.currentSession)
        return self.currentSession


    def endSession(self):
        """ Set the current session's start/end times. Part of the import
            process.
        """
        cs = self.currentSession
        if cs is not None:
            if cs.startTime is None:
                cs.startTime = cs.firstTime
            if cs.endTime is None:
                cs.endTime = cs.lastTime
                
            self.currentSession = None
        
    
    def addSensor(self, sensorId=None, name=None, sensorClass=None, 
                  traceData=None, transform=None, attributes=None,
                  bandwidthLimitId=None):
        """ Create a new Sensor object, and add it to the dataset, and return
            it. If the given sensor ID already exists, the existing sensor is 
            returned instead. To modify a sensor or add a sensor object created 
            elsewhere, use `Dataset.sensors[sensorId]` directly.
            
            Note that the `sensorId` keyword argument is *not* optional.
            
            :param sensorId: The ID of the new sensor.
            :keyword name: The new sensor's name
            :keyword sensorClass: An alternate (sub)class of sensor. Defaults
                to `None`, which creates a `Sensor`.
            :return: The new sensor.
        """
        # `sensorId` is mandatory; it's a keyword argument to streamline import.
        if sensorId is None:
            raise TypeError("%s.addSensor() requires a sensorId" %
                            self.__class__.__name__)
            
        if sensorId in self.sensors:
            return self.sensors[sensorId]
        
        sensorClass = Sensor if sensorClass is None else sensorClass
        sensor = sensorClass(self,sensorId,name=name, transform=transform,
                             traceData=traceData, attributes=attributes,
                             bandwidthLimitId=bandwidthLimitId)
        self.sensors[sensorId] = sensor
        return sensor


    def addChannel(self, channelId=None, parser=None, channelClass=None,
                   **kwargs):
        """ Add a Channel to a Sensor. Note that the `channelId` and `parser`
            keyword arguments are *not* optional.
        
            :keyword channelId: An unique ID number for the channel.
            :keyword parser: The Channel's data parser
            :keyword channelClass: An alternate (sub)class of channel.
                Defaults to `None`, which creates a standard `Channel`.
        """
        if channelId is None or parser is None:
            raise TypeError("addChannel() requires a channel ID")
        if parser is None:
            raise TypeError("addChannel() requires a parser")
        
        if channelId in self._channels:
            return self._channels[channelId]
        channelClass = channelClass or Channel
        channel = channelClass(self, channelId, parser, **kwargs)
        self._channels[channelId] = channel
            
        return channel


    def addTransform(self, transform):
        """ Add a transform (calibration, etc.) to the dataset. Various child
            objects will reference them by ID. Note: unlike the other `add`
            methods, this does not instantiate new objects.
        """
        if transform.id is None:
            raise ValueError("Added transform did not have an ID")
        
        self.transforms[transform.id] = transform
    
    
    def addWarning(self, warningId=None, channelId=None, subchannelId=None, 
                   low=None, high=None, **kwargs):
        """ Add a `WarningRange` to the dataset, which indicates when a sensor
            is reporting values outside of a given range.
        
            :keyword warningId: A unique numeric ID for the `WarningRange`.
            :keyword channelId: The channel ID of the source being monitored.
            :keyword subchannelId: The monitored source's subchannel ID.
            :keyword low: The minimum value of the acceptable range.
            :keyword high: The maximum value of the acceptable range.
            :return: The new `WarningRange` instance.
        """
        w = WarningRange(self, warningId=warningId, channelId=channelId, 
                         subchannelId=subchannelId, low=low, high=high, 
                         **kwargs)
        self.warningRanges[warningId] = w
        return w
        

    def path(self):
        """ Get the combined names of all the object's parents/grandparents.
        """
        # Dataset is the root.
        return self.name
    
    
    @property
    def lastSession(self):
        """ Retrieve the latest Session.
        """
        if len(self.sessions) == 0:
            return None
        return self.sessions[-1]
    
    
    def hasSession(self, sessionId):
        """ Does the Dataset contain a specific session number?
        """
        if len(self.sessions) == 0:
            return False
        if sessionId is None:
            return True
        return sessionId >= 0 and sessionId < len(self.sessions)
        
    
    def getPlots(self, subchannels=True, plots=True, debug=True, sort=True):
        """ Get all plotable data sources: sensor SubChannels and/or Plots.
        
            :keyword subchannels: Include subchannels if `True`.
            :keyword plots: Include Plots if `True`.
            :keyword debug: If `False`, exclude debugging/diagnostic channels.
            :keyword sort: Sort the plots by name if `True`. 
        """
        result = []
        test = lambda x: debug or not x.name.startswith("DEBUG")
        if plots:
            result = [x for x in self.plots.values() if test(x)]
        if subchannels:
            for c in self._channels.values():
                for i in range(len(c.subchannels)):
                    subc = c.getSubChannel(i)
                    if test(subc):
                        result.append(subc)
        if sort:
            result.sort(key=lambda x: x.displayName)
        return result
            

    def updateTransforms(self):
        """ Update the transforms (e.g. the calibration functions) in this
            dataset. This should be called before utilizing data in the set.
        """
        for ch in self.channels.values():
            ch.updateTransforms()

    def fillCaches(self):
        for channel in self.channels.values():
            for ea in channel.sessions.values():
                ea.fillCache()


#===============================================================================
# 
#===============================================================================

class Session(object):
    """ A collection of data within a dataset, e.g. one test run. A Dataset is
        expected to contain one or more Sessions.
    """
    
    def __init__(self, dataset, sessionId=0, startTime=None, endTime=None,
                 utcStartTime=None):
        """ Constructor. This should generally be done indirectly via
            `Dataset.addSession()`.
            
            :param dataset: The parent `Dataset`
            :keyword sessionId: The Session's numeric ID. Typically
                sequential, starting at 0.
            :keyword startTime: The session's start time, in microseconds,
                relative to the start of the recording.
            :keyword endTime: The session's end time, in microseconds,
                relative to the end of the recording.
            :keyword utcStartTime: The session's start time, as an absolute
                POSIX/epoch timestamp.
        """
        self.dataset = dataset
        self.startTime = startTime
        self.endTime = endTime
        self.sessionId = sessionId
        self.utcStartTime = utcStartTime or dataset.lastUtcTime
        
        # firstTime and lastTime are the actual last event time. These will
        # typically be the same as startTime and endTime, but not necessarily
        # so.
        self.firstTime = self.lastTime = None


    def __repr__(self):
        return "<%s (id=%s) at 0x%08X>" % (self.__class__.__name__, 
                                           self.sessionId, id(self))
    
    
    def __eq__(self, other):
        """ x.__eq__(y) <==> x==y """
        if other is self:
            return True
        elif not isinstance(other, self.__class__):
            return False
        else:
            return self.dataset == other.dataset \
               and self.startTime == other.startTime \
               and self.endTime == other.endTime \
               and self.sessionId == other.sessionId \
               and self.utcStartTime == other.utcStartTime \
               and self.firstTime == other.firstTime \
               and self.lastTime == other.lastTime
        
#===============================================================================
# 
#===============================================================================

class Sensor(Cascading):
    """ One Sensor object. A Dataset contains at least one.
    """
    
    def __init__(self, dataset, sensorId, name=None, transform=None,
                  traceData=None, attributes=None, bandwidthLimitId=None):
        """ Constructor. This should generally be done indirectly via
            `Dataset.addSensor()`.
        
            :param dataset: The parent `Dataset`.
            :param sensorId: The ID of the new sensor.
            :keyword name: The new sensor's name.
            :keyword transform: A sensor-level data pre-processing function.
            :keyword traceData: Sensor traceability data.
            :keyword attributes: A dictionary of arbitrary attributes, e.g.
                ``Attribute`` elements parsed from the file.
        """
        if isinstance(name, bytes):
            name.decode()
        self.name = "Sensor%02d" if name is None else name
        self.dataset = dataset
        self.parent = dataset
        self.id = sensorId
        self.channels = {}
        self.traceData = traceData
        self.attributes = attributes
        self.bandwidthLimitId = bandwidthLimitId
        self._bandwidthCutoff = None
        self._bandwidthRolloff = None


    def __getitem__(self, idx):
        return self.channels[idx]


    @property
    def children(self):
        return list(self.channels.values())

    
    @property
    def bandwidthCutoff(self):
        if self._bandwidthCutoff is None:
            try:
                bw = self.dataset.bandwidthLimits[self.bandwidthLimitId]
                self._bandwidthCutoff = (bw.get('LowerCutoff', None),
                                         bw.get('UpperCutoff', None))
            except (KeyError, AttributeError):
                pass
    
        return self._bandwidthCutoff


    @property
    def bandwidthRolloff(self):
        if self._bandwidthRolloff is None:
            try:
                bw = self.dataset.bandwidthLimits[self.bandwidthLimitId]
                self._bandwidthCutoff = (bw.get('LowerRolloff', None),
                                         bw.get('UpperRolloff', None))
                # Should that be rolloff or is cutoff still correct?
            except (KeyError, AttributeError):
                pass
    
        return self._bandwidthRolloff


    def __eq__(self, other):
        if other is self:
            return True
        if not isinstance(other, self.__class__):
            return False
        else:
            return self.name == other.name \
               and self.dataset == other.dataset \
               and self.parent == other.parent \
               and self.id == other.id \
               and self.channels == other.channels \
               and self.traceData == other.traceData \
               and self.attributes == other.attributes \
               and self.bandwidthLimitId == other.bandwidthLimitId


#===============================================================================
# Channels
#===============================================================================

class Channel(Transformable):
    """ Output from a Sensor, containing one or more SubChannels. A Sensor
        contains one or more Channels. SubChannels of a Channel can be
        accessed by index like a list or tuple.
        
        :ivar types: A tuple with the type of data in each of the Channel's
            Subchannels.
        :ivar displayRange: The possible ranges of each subchannel, dictated
            by the parser. Not necessarily the same as the range of actual
            values recorded in the file!
    """
    
    def __init__(self, dataset, channelId=None, parser=None, sensor=None, 
                 name=None, units=None, transform=None, displayRange=None, 
                 sampleRate=None, cache=False, singleSample=None,
                 attributes=None):
        """ Constructor. This should generally be done indirectly via
            `Dataset.addChannel()`.
        
            :param sensor: The parent sensor, if this Channel contains only
                data from a single sensor.
            :param channelId: The channel's ID, unique within the file.
            :param parser: The channel's EBML data parser.
            :keyword name: A custom name for this channel.
            :keyword units: The units measured in this channel, used if units
                are not explicitly indicated in the Channel's SubChannels.
            :keyword transform: A Transform object for adjusting sensor
                readings at the Channel level. 
            :keyword displayRange: A 'hint' to the minimum and maximum values
                of data in this channel.
            :keyword cache: If `True`, this channel's data will be kept in
                memory rather than lazy-loaded.
            :keyword singleSample: A 'hint' that the data blocks for this
                channel each contain only a single sample (e.g. temperature/
                pressure on an SSX). If `None`, this will be determined from
                the sample data.
            :keyword attributes: A dictionary of arbitrary attributes, e.g.
                ``Attribute`` elements parsed from the file.
        """
        self.id = channelId
        self.sensor = sensor
        self.parser = parser
        self.units = units or ('', '')
        self.parent = sensor
        self.dataset = dataset
        self.sampleRate = sampleRate
        self.attributes = attributes
       
        self._unitsStr = None

        self.cache = bool(cache)
        self.singleSample = singleSample

        if isinstance(sensor, int):
            sensor = self.dataset.sensors.get(sensor, None)
        if sensor is not None:
            sensor.channels[channelId] = self
            sensorname = sensor.name
        
        if name is None:
            sensorname = sensor.name if sensor is not None else "Unknown Sensor"
            name = "%s:%02d" % (sensorname, channelId)
        elif isinstance(name, (bytes, bytearray)):
            name = name.decode()
        self.name = name
        self.displayName = self.name
        
        # Custom parsers will define `types`, otherwise generate it.
        self.types = getParserTypes(parser)
        self.displayRange = displayRange if displayRange is not None \
                            else getParserRanges(parser)
        
        self.hasDisplayRange = displayRange is not None
        
        # Channels have 1 or more subchannels
        self.subchannels = [None] * len(self.types)
        
        # A set of session EventLists. Populated dynamically with
        # each call to getSession(). 
        self.sessions = {}
        
        self.subsampleCount = [0,sys.maxsize]

        self.setTransform(transform, update=False)
        
        # Optimization. Memoization-like cache of the last block parsed.
        self._lastParsed = (None, None)

        # HACK! Disallowing mean removal should be sensor-defined.
        # TODO: Add this to the manifest?
        self.allowMeanRemoval = self.id in (0, 8, 32, 80)


    @property
    def children(self):
        return list(iter(self))


    def __repr__(self):
        try:
            if self._unitsStr is None:
                # If there's no cached string of measurement types and units, make it.
                if not self.children:
                    units = [self.units]
                else:
                    units = [c.units for c in self.children]

                    # If all subchannel units are the same, show only one.
                    if len(set(units)) == 1:  # Cheesy test for identical units tuples
                        units = [units[0]]

                names = []
                for measurement, name in units:
                    if name:
                        name = "(%s)" % name
                    names.append(("%s %s" % (measurement, name)).strip())
                self._unitsStr = ", ".join(names)

            s = (": %s" % self._unitsStr) if self._unitsStr else ""
            return '<%s %d %r%s>' % (self.__class__.__name__,
                                     self.id, self.path(), s)

        except (AttributeError, TypeError, ValueError):
            # Just in case, so __repr__() never completely fails.
            return object.__repr__(self)


    def __getitem__(self, idx):
        return self.getSubChannel(idx)


    def __len__(self):
        return len(self.subchannels)

    
    def __iter__(self):
        for i in range(len(self)):
            yield self.getSubChannel(i)


    def addSubChannel(self, subchannelId=None, channelClass=None, **kwargs):
        """ Create a new SubChannel of the Channel.
        """
        if subchannelId is None:
            raise TypeError("addSubChannel() requires a subchannelId")
        
        if subchannelId >= len(self.subchannels):
            raise IndexError(
                "Channel's parser only generates %d subchannels" %
                 len(self.subchannels))
        else:
            channelClass = channelClass or SubChannel
            sc = self.subchannels[subchannelId]
            if sc is not None:
                return self.subchannels[subchannelId]
            sc = channelClass(self, subchannelId, **kwargs)
            self.subchannels[subchannelId] = sc
            return sc
        

    def getSubChannel(self, subchannelId):
        """ Retrieve one of the Channel's SubChannels. All Channels have at
            least one. A SubChannel object will be automatically generated if
            one hasn't already explicitly been defined.
            
            :param subchannelId: 
            :return: The SubChannel matching the given ID.
        """
        # If there is no SubChannel explicitly defined for a subchannel, 
        # dynamically generate one.
        if self.subchannels[subchannelId] is None:
            self.subchannels[subchannelId] = SubChannel(self, subchannelId)
            
        self.subchannels[subchannelId].singleSample = self.singleSample
        return self.subchannels[subchannelId]


    def getSession(self, sessionId=None):
        """ Retrieve data recorded in a Session. 
            
            :keyword sessionId: The ID of the session to retrieve.
            :return: The recorded data.
            :rtype: `EventArray`
        """
        self._updateXformIds()
        if sessionId is None:
            session = self.dataset.lastSession
            sessionId = session.sessionId
        if sessionId is None or not self.dataset.hasSession(sessionId):
            raise KeyError("Dataset has no Session id=%r" % sessionId)

        if sessionId in self.sessions:
            return self.sessions[sessionId]
        
        session = self.dataset.sessions[sessionId]
        return self.sessions.setdefault(sessionId, EventArray(self, session))
    
    
    def parseBlock(self, block, start=None, end=None, step=1, subchannel=None):
        """ Parse subsamples out of a data block. Used internally.
        
            :param block: The data block from which to parse subsamples.
            :keyword start: The first block index to retrieve.
            :keyword end: The last block index to retrieve.
            :keyword step: The number of steps between samples.
            :keyword subchannel: If supplied, return only the values for a 
                specific subchannel (i.e. the method is being called by a
                SubChannel).
            :return: A list of tuples, one for each subsample.
        """
        # TODO: Cache this; a Channel's SubChannels will often be used together.
        p = (block, start, end, step, subchannel)
        if self._lastParsed[0] == p:
            return self._lastParsed[1]
        if self.singleSample:
            start = 0
            end = 1
        result = block.parseWith(self.parser, start=start, end=end,
                                 step=step, subchannel=subchannel)
        if not isinstance(result, np.ndarray):
            result = list(result)
        
        self._lastParsed = (p, result)
        return result


    def parseBlockByIndex(self, block, indices, subchannel=None):
        """ Convert raw data into a set of subchannel values, returning only
             specific items from the result by index.
            
            :param block: The data block element to parse.
            :param indices: A list of sample index numbers to retrieve.
            :keyword subchannel: If supplied, return only the values for a 
                specific subchannel
            :return: A list of tuples, one for each subsample.
        """
        result = block.parseByIndexWith(self.parser, indices, 
                                        subchannel=subchannel)
        if not isinstance(result, np.ndarray):
            result = list(result)
        return result


    def updateTransforms(self):
        """ Recompute cached transform functions.
        """
        super(Channel, self).updateTransforms()
        if self.sessions is not None:
            for s in self.sessions.values():
                s.updateTransforms()
                
                
    def __eq__(self, other):
        """ x.__eq__(y) <==> x==y """
        if other is self:
            return True
        elif not isinstance(other, self.__class__):
            return False
        else:
            return self.id == other.id \
               and self.sensor == other.sensor \
               and self.parser == other.parser \
               and self.units == other.units \
               and self.dataset == other.dataset \
               and self.sampleRate == other.sampleRate \
               and self.attributes == other.attributes \
               and self.cache == other.cache \
               and self.singleSample == other.singleSample \
               and self.name == other.name \
               and self.displayName == other.displayName \
               and self.types == other.types \
               and self.displayRange == other.displayRange \
               and self.hasDisplayRange == other.hasDisplayRange \
               and self.subchannels == other.subchannels \
               and self.sessions == other.sessions \
               and self.subsampleCount == other.subsampleCount \
               and self._lastParsed == other._lastParsed \
               and self.allowMeanRemoval == other.allowMeanRemoval        


#===============================================================================

class SubChannel(Channel):
    """ Output from a sensor, derived from a channel containing multiple
        pieces of data (e.g. the Y from an accelerometer's XYZ). Looks
        like a 'real' channel.
    """
    
    def __init__(self, parent, subchannelId, name=None, units=('', ''),
                 transform=None, displayRange=None, sensorId=None, 
                 warningId=None, axisName=None, attributes=None, color=None):
        """ Constructor. This should generally be done indirectly via
            `Channel.addSubChannel()`.
        
            :param sensor: The parent sensor.
            :param channelId: The channel's ID, unique within the file.
            :param parser: The channel's payload data parser.
            :keyword name: A custom name for this channel.
            :keyword units: The units measured in this channel, used if units
                are not explicitly indicated in the Channel's SubChannels. A
                tuple containing the 'axis name' (e.g. 'Acceleration') and the
                unit symbol ('g').
            :keyword transform: A Transform object for adjusting sensor
                readings at the Channel level. 
            :keyword displayRange: A 'hint' to the minimum and maximum values
                of data in this channel.
            :keyword sensorId: The ID of the sensor that generates this
                SubChannel's data.
            :keyword warningId: The ID of the `WarningRange` that indicates
                conditions that may adversely affect data recorded in this
                SubChannel.
            :keyword axisName: The name of the axis this SubChannel represents.
                Use if the `name` contains additional text (e.g. "X" if the 
                name is "Accelerometer X (low-g)").
            :keyword attributes: A dictionary of arbitrary attributes, e.g.
                ``Attribute`` elements parsed from the file.
        """
        self.id = subchannelId
        self.parent = parent
        self.warningId = warningId
        self.cache = self.parent.cache
        self.dataset = parent.dataset
        self.axisName = axisName
        self.attributes = attributes
        
        self._unitsStr = None

        if name is None:
            self.name = "%s:%02d" % (parent.name, subchannelId)
        else:
            if isinstance(name, (bytes, bytearray)):
                name = name.decode()
            self.name = name
            if axisName is None:
                if self.name:
                    self.axisName = self.name.split()[0]
                else:
                    self.axisName = name
        
        # XXX: HACK HACK HACK REMOVE ME REMOVE ME
        if self.name == "Control Pad P":
            self.name = "Control Pad Pressure"
        elif self.name == "Control Pad T":
            self.name = "Control Pad Temperature"

        units = tuple(isinstance(s, (bytes, bytearray)) and s.decode() or s for s in units)
        self.units = units

        # Generate a 'display name' (e.g. for display in a plot legend)
        # Combines the given name (if any) and the units (if any)
        if self.units[0]:
            if name is None: 
                self.displayName = units[0]
            elif units[0] in self.name:
                self.displayName = self.name
            else:
                self.displayName = "%s: %s" % (units[0], self.name)
        else:
            self.displayName = self.name

        if isinstance(sensorId, int):
            self.sensor = self.dataset.sensors.get(sensorId, None)
        elif sensorId is None:
            if isinstance(parent.sensor, int):
                self.sensor = self.dataset.sensors.get(parent.sensor, None)
            else:
                self.sensor = parent.sensor
        else:
            self.sensor = sensorId
        
        self.types = (parent.types[subchannelId], )
        
        self._sessions = None
        
        # Set the transform, but don't immediately update. It might be an index.
        self.setTransform(transform, update=False)
        
        if displayRange is None:
            self.displayRange = self.parent.displayRange[self.id]
            self.hasDisplayRange = self.parent.hasDisplayRange
        else:
            self.hasDisplayRange = True
            self.displayRange = displayRange
        
        self.allowMeanRemoval = parent.allowMeanRemoval
        self.removeMean = False
        self.singleSample = parent.singleSample
        
        # Is `color` a set of R/G/B values? Check for `__getitem__` instead of
        # using `instance`, since various things (bytearray, wx.Colour, etc.)
        # don't pass `isinstance(color, Sequence)`.
        if hasattr(color, "__getitem__") and len(color) >= 3:
            color = tuple(color[:3])
        self.color = color


    def __repr__(self):
        try:
            super().__repr__()  # Superclass' `__repr__()` generates `_unitsStr`
            s = (": %s" % self._unitsStr) if self._unitsStr else ""
            return '<%s %d.%d %r%s>' % (self.__class__.__name__,
                                        self.parent.id, self.id,
                                        self.path(), s)

        except (AttributeError, TypeError, ValueError):
            # Just in case, so __repr__() never completely fails.
            return object.__repr__(self)


    @property
    def children(self):
        return []


    @property
    def sampleRate(self):
        return self.parent.sampleRate


    def __len__(self):
        raise AttributeError('SubChannel has no children.')


    @property
    def parser(self):
        return self.parent.parser


    @property
    def sessions(self):
        if self._sessions is None:
            self._sessions = {}
            for s in self.parent.sessions:
                self._sessions[s] = self.getSession(s)
        return self._sessions
    

    def parseBlock(self, block, start=None, end=None, step=1):
        """ Parse subsamples out of a data block. Used internally.
        
            :param block: The data block from which to parse subsamples.
            :keyword start: The first block index to retrieve.
            :keyword end: The last block index to retrieve.
            :keyword step: The number of steps between samples.
        """
        return self.parent.parseBlock(block, start, end, step=step) 


    def parseBlockByIndex(self, block, indices):
        """ Parse specific subsamples out of a data block. Used internally.
        
            :param block: The data block from which to parse subsamples.
            :param indices: A list of individual index numbers to get.
        """
        return self.parent.parseBlockByIndex(block, indices)

        
    def getSession(self, sessionId=None):
        """ Retrieve a session by ID. If none is provided, the last session in
            the Dataset is returned.
        """
        self._updateXformIds()
        if sessionId is None:
            sessionId = self.dataset.lastSession.sessionId
        if self._sessions is None:
            self._sessions = {}
        elif sessionId in self._sessions:
            return self._sessions[sessionId]
        el = self.parent.getSession(sessionId).copy(self)
        sessionId = el.session.sessionId
        self._sessions[sessionId] = el
        return el
    
    
    def addSubChannel(self, *args, **kwargs):
        raise AttributeError("SubChannels have no SubChannels")


    def getSubChannel(self, *args, **kwargs):
        raise AttributeError("SubChannels have no SubChannels")


    def __eq__(self, other):
        """ x.__eq__(y) <==> x==y """
        if other is self:
            return True
        if not isinstance(other, self.__class__):
            return False
        else:
            return self.id == other.id \
               and self.sensor == other.sensor \
               and self.parser == other.parser \
               and self.units == other.units \
               and self.dataset == other.dataset \
               and self.sampleRate == other.sampleRate \
               and self.attributes == other.attributes \
               and self.cache == other.cache \
               and self.singleSample == other.singleSample \
               and self.name == other.name \
               and self.displayName == other.displayName \
               and self.types == other.types \
               and self.displayRange == other.displayRange \
               and self.hasDisplayRange == other.hasDisplayRange \
               and self.sessions == other.sessions \
               and self.allowMeanRemoval == other.allowMeanRemoval  
               

#===============================================================================
#
#===============================================================================


class EventArray(Transformable):
    """ A list-like object containing discrete time/value pairs. Data is 
        dynamically read from the underlying EBML file. 
    """

    # Width of rolling mean (microseconds), or -1 for total mean removal.
    DEFAULT_MEAN_SPAN = -1

    def __init__(self, parentChannel, session=None, parentList=None):
        """ Constructor. This should almost always be done indirectly via
            the `getSession()` method of `Channel` and `SubChannel` objects.
        """
        self.parent = parentChannel
        self.session = session
        self._data = []
        self._length = 0
        self.dataset = parentChannel.dataset
        self.hasSubchannels = not isinstance(self.parent, SubChannel)
        self._parentList = parentList
        self._childLists = []
        
        self.noBivariates = False

        if self._parentList is not None:
            self._singleSample = self._parentList._singleSample
        else:
            self._singleSample = parentChannel.singleSample

        if self.hasSubchannels or not isinstance(parentChannel.parent, Channel):
            # Cache of block start times and sample indices for faster search
            self._blockTimes = []
            self._blockIndices = []
        else:
            s = self.session.sessionId if session is not None else None
            ps = parentChannel.parent.getSession(s)
            self._blockTimes = ps._blockTimes
            self._blockIndices = ps._blockIndices

            self.noBivariates = ps.noBivariates
        
        if self.hasSubchannels:
            self.channelId = self.parent.id
            self.subchannelId = None
        else:
            self.channelId = self.parent.parent.id
            self.subchannelId = self.parent.id
        
        self._hasSubsamples = False
        
        self.hasDisplayRange = self.parent.hasDisplayRange
        self.displayRange = self.parent.displayRange

        self.removeMean = False
        self.hasMinMeanMax = True
        self._rollingMeanSpan = None
        self.rollingMeanSpan = self.DEFAULT_MEAN_SPAN

        self.transform = None
        self.useAllTransforms = True
        self.updateTransforms(recurse=False)
        self.allowMeanRemoval = parentChannel.allowMeanRemoval    

        if self.hasSubchannels:
            self.parseBlock = self.parent.parseBlock
        else:
            self.parseBlock = self.parent.parent.parseBlock

        self._blockIndicesArray = np.array([], dtype=np.float64)
        self._blockTimesArray = np.array([], dtype=np.float64)

        self._mean = None

        _format = self.parent.parser.format
        if isinstance(self.parent, SubChannel):
            self._npType = self.parent.parent.getSession()._npType[self.subchannelId]
        elif len(_format) == 0:
            self._npType = np.uint8
        else:
            if isinstance(_format, bytes):
                _format = _format.decode()

            if _format[0] in ['<', '>', '=']:
                endian = _format[0]
                dtypes = [endian + ChannelDataBlock.TO_NP_TYPESTR[x] for x in _format[1:]]
            else:
                dtypes = [ChannelDataBlock.TO_NP_TYPESTR[x] for x in str(_format)]

            self._npType = np.dtype([(str(i), dtype) for i, dtype in enumerate(dtypes)])

        self._channelDataLock = parentChannel.dataset._channelDataLock
        self._cacheArray = None
        self._cacheBytes = None
        self._fullyCached = False
        self._cacheStart = None
        self._cacheEnd = None
        self._cacheBlockStart = None
        self._cacheBlockEnd = None
        self._cacheLen = 0


    @property
    def rollingMeanSpan(self):
        return self._rollingMeanSpan


    @rollingMeanSpan.setter
    def rollingMeanSpan(self, value):
        if value != -1:
            warnings.warn('Rolling mean has been deprecated, this behavior has '
                          'been replaced with total mean removal.')
        self._rollingMeanSpan = value


    def updateTransforms(self, recurse=True):
        """ (Re-)Build and (re-)apply the transformation functions.
        """
        # _comboXform is the channel's transform, with as many parameters as
        # subchannels. _fullXform is the channel's transform plus the 
        # subchannel's transform. Subchannels will always use the latter. Parent
        # channels can use either (see useAllTransforms).
        self._comboXform = self._fullXform = self._displayXform = None
        if self.hasSubchannels:
            self._comboXform = PolyPoly([self.parent.transform]*len(self.parent.types))
            xs = [c.transform if c is not None else None for c in self.parent.subchannels]
            xs = [CombinedPoly(t, x=self.parent.transform, dataset=self.dataset) for t in xs]
            self._fullXform = PolyPoly(xs, dataset=self.dataset)
            
            if recurse:
                sessionId = self.session.sessionId if self.session is not None else None
                children = []
                dispX = []
                for x,sc in zip(xs,self.parent.subchannels):
                    if sessionId in sc.sessions:
                        cl = sc.sessions[sessionId]
                        if cl.transform is None:
                            dispX.append(x)
                        else:
                            dispX.append(CombinedPoly(cl.transform, x=x, dataset=self.dataset))
                        children.append(cl)
                    else:
                        dispX.append(x)
                        
                self._displayXform = PolyPoly(dispX, dataset=self.dataset)
                for el in children:
                    el._comboXform = el._fullXform = self._fullXform
                    el._displayXform = self._displayXform
                    
        else:
            self._parentList.updateTransforms()#(recurse=False)
            # FIXME: These cached combination transforms *should* already be set
            self._comboXform = self._fullXform = self._parentList._fullXform
            self._displayXform = self._parentList._displayXform


    @property
    def units(self):
        if self.transform is not None:
            return self.transform.units or self.parent.units
        return self.parent.units


    def path(self):
        """ Get the combined names of all the object's parents/grandparents.
        """
        if self.session and self.session.sessionId:
            return "%s (session %s)" % (self.parent.path(), self.session.sessionId)
        return self.parent.path()


    def copy(self, newParent=None):
        """ Create a shallow copy of the event list.
        """
        parent = self.parent if newParent is None else newParent
        newList = self.__class__(parent, self.session, self)
        newList._data = self._data
        newList._length = self._length
        newList.dataset = self.dataset
        newList.hasMinMeanMax = self.hasMinMeanMax
        newList.removeMean = self.removeMean
        newList.allowMeanRemoval = self.allowMeanRemoval
        newList.noBivariates = self.noBivariates
        newList._blockIndices = self._blockIndices
        newList._blockTimes = self._blockTimes
        newList._channelDataLock = self._channelDataLock
        newList._cacheArray = self._cacheArray
        newList._cacheBytes = self._cacheBytes
        newList._fullyCached = self._fullyCached
        newList._cacheStart = self._cacheStart
        newList._cacheEnd = self._cacheEnd
        newList._cacheBlockStart = self._cacheBlockStart
        newList._cacheBlockEnd = self._cacheBlockEnd
        return newList
    

    def append(self, block):
        """ Add one data block's contents to the Channel's list of data.
            Note that this doesn't double-check the channel ID specified in
            the data, but it is inadvisable to include data from different
            channels.
            
            :attention: Added elements must be in chronological order!
        """
        with self._channelDataLock:
            if block.numSamples is None:
                block.numSamples = block.getNumSamples(self.parent.parser)

            # Set the session first/last times if they aren't already set.
            # Possibly redundant if all sessions are 'closed.'
            if self.session.firstTime is None:
                self.session.firstTime = block.startTime
            else:
                self.session.firstTime = min(self.session.firstTime, block.startTime)

            if self.session.lastTime is None:
                self.session.lastTime = block.endTime
            else:
                self.session.lastTime = max(self.session.lastTime, block.endTime)

            # Check that the block actually contains at least one sample.
            if block.numSamples < 1:
                # Ignore blocks with empty payload. Could occur in FW <17.
                # TODO: Make sure this doesn't hide too many errors!
                logger.warning("Ignoring block with bad payload size for %r" % self)
                return

            block.cache = self.parent.cache
            oldLength = self._length

            block.blockIndex = len(self._data)
            block.indexRange = (oldLength, oldLength + block.numSamples)

            # _singleSample hint not explicitly set; set it based on this block.
            # There will be problems if the first block has only one sample, but
            # future ones don't. This shouldn't happen, though.
            if self._singleSample is None:
                self._singleSample = block.numSamples == 1
                if self._parentList is not None:
                    self._parentList._singleSample = self._singleSample
                if self.parent.singleSample is None:
                    self.parent.singleSample = self._singleSample
                if self.parent.parent is not None:
                    self.parent.parent.singleSample = self._singleSample

            # HACK (somewhat): Single-sample-per-block channels get min/mean/max
            # which is just the same as the value of the sample. Set the values,
            # but don't set hasMinMeanMax.
            if self._singleSample is True:# and not self.hasMinMeanMax:
                block.minMeanMax = np.tile(block.payload, 3)
                mmmArr = np_recfunctions.structured_to_unstructured(
                        block._minMeanMax.view(self._npType))
                block.min, block.mean, block.max = mmmArr
                self.hasMinMeanMax = False
            elif block.minMeanMax is not None:
                mmmArr = np_recfunctions.structured_to_unstructured(
                    np.frombuffer(block.minMeanMax, self._npType))
                block.min, block.mean, block.max = mmmArr
                self.hasMinMeanMax = True
            else:
                # XXX: Attempt to calculate min/mean/max here instead of
                #  in _computeMinMeanMax(). Causes issues with pressure for some
                #  reason - it starts removing mean and won't plot.
                vals = np_recfunctions.structured_to_unstructured(block.payload.view(self._npType))
                block.min = vals.min(axis=-1)
                block.mean = vals.mean(axis=-1)
                block.max = vals.max(axis=-1)
                self.hasMinMeanMax = True

            # Cache the index range for faster searching
            self._blockIndices.append(oldLength)
            self._blockTimes.append(block.startTime)

            self._hasSubsamples = self._hasSubsamples or block.numSamples > 1

            self._data.append(block)
            self._length += block.numSamples

            block._payload = np.frombuffer(block._payloadEl.dump(), dtype=self._npType)


    @property
    def _firstTime(self):
        return self._data[0].startTime if self._data else None

    @property
    def _lastTime(self):
        return self._data[-1].endTime if self._data else None

    def getInterval(self):
        """ Get the first and last event times in the set.
        """
        if len(self._data) == 0:
            return None

        return self._firstTime, self._lastTime

    #===========================================================================
    # Old utility methods
    #===========================================================================
        
    def _getBlockIndexWithIndex(self, idx, start=0, stop=None):
        """ Get the index of a raw data block that contains the given event
            index.

            :param idx: The event index to find
            :keyword start: The first block index to search
            :keyword stop: The last block index to search
        """
        # TODO: profile & determine if this change is beneficial
        '''
        if stop:
            blockIdx = bisect_right(self._blockIndices, idx, start, stop)
        else:
            blockIdx = bisect_right(self._blockIndices, idx, start)
        if blockIdx:
            return blockIdx-1
        return blockIdx

        '''
        if len(self._blockIndicesArray) != len(self._blockIndices):
            self._blockIndicesArray = np.array(self._blockIndices)

        idxOffset = max(start, 1)
        return idxOffset-1 + np.searchsorted(
            self._blockIndicesArray[idxOffset:stop], idx, side='right'
        )


    def _getBlockIndexWithTime(self, t, start=0, stop=None):
        """ Get the index of a raw data block in which the given time occurs.

            :param t: The time to find
            :keyword start: The first block index to search
            :keyword stop: The last block index to search
        """
        # TODO: profile & determine if this change is beneficial
        '''
        if stop:
            blockIdx = bisect_right(self._blockTimes, t, start, stop)
        else:
            blockIdx = bisect_right(self._blockTimes, t, start)
        if blockIdx:
            return blockIdx-1
        return blockIdx
        '''
        if len(self._blockTimesArray) != len(self._blockTimes):
            self._blockTimesArray = np.array(self._blockTimes)

        idxOffset = max(start, 1)
        return idxOffset-1 + np.searchsorted(
            self._blockTimesArray[idxOffset:stop], t, side='right'
        )


    def _getBlockRollingMean_old(self, blockIdx, force=False):
        """ Get the mean of a block and its neighbors within a given time span.
            Note: Values are taken pre-calibration, and all subchannels are
            returned.
            
            :param blockIdx: The index of the block to check.
            :return: An array containing the mean values of each subchannel. 
        """
        # XXX: I don't remember why I do this.
#         if force is False:
#             if self.removeMean is False or self.allowMeanRemoval is False:
#                 return None
        
        block = self._data[blockIdx]
        span = self.rollingMeanSpan
        
        if (block._rollingMean is not None 
            and block._rollingMeanSpan == span 
            and block._rollingMeanLen == len(self._data)):
            return block._rollingMean

        self._computeMinMeanMax()
        
        if span != -1:
            firstBlock = self._getBlockIndexWithTime(block.startTime - (span/2), 
                                                     stop=blockIdx)
            lastBlock = self._getBlockIndexWithTime(block.startTime + (span/2), 
                                                    start=blockIdx)
            lastBlock = max(lastBlock+1, firstBlock+1)
        else:
            firstBlock = lastBlock = None
        
        try:
            rollingMean = np.median(
                [b.mean for b in self._data[firstBlock:lastBlock]],
                axis=0, overwrite_input=True
            )
            block._rollingMean = rollingMean
            block._rollingMeanSpan = rollingMeanSpan = span
            block._rollingMeanLen = rollingMeanLen = len(self._data)
        
            if span == -1:
                # Set-wide median/mean removal; same across all blocks.
                for b in self._data:
                    b._rollingMean = rollingMean
                    b._rollingMeanSpan = rollingMeanSpan
                    b._rollingMeanLen = rollingMeanLen
            
            return block._rollingMean
        
        except TypeError:
            # XXX: HACK! b.mean can occasionally be a tuple at very start.
            # Occurs very rarely in multithreaded loading. Find and fix cause.
            # May no longer occur with new EBML library.
#             logger.info( "Type error!")
            return None


    def _getBlockRollingMean(self, blockIdx, force=False):
        """ Get the mean of a block and its neighbors within a given time span.
            Note: Values are taken pre-calibration, and all subchannels are
            returned.
            
            :param blockIdx: The index of the block to check.
            :return: An array containing the mean values of each subchannel. 
        """
        if isinstance(blockIdx, Sequence):
            blockIdx = np.array(blockIdx)
        elif not isinstance(blockIdx, np.ndarray):
            return self._getBlockRollingMean_old(blockIdx, force)

        uniqueBlockIndices, blocksPerm = np.unique(blockIdx, return_inverse=True)

        uniqueBlockMeans = np.stack([
            self._getBlockRollingMean_old(idx, force)
            for idx in uniqueBlockIndices
        ], axis=-1)
        return uniqueBlockMeans[:, blocksPerm]


    #===========================================================================
    # Main API methods
    #===========================================================================

    def __getitem__(self, idx, display=False):
        """ Get a specific data point by index.

            :param idx: An integer index or a `slice`
            :return: For single results, a tuple containing (time, value).
                For multiple results, a structured array of (time, value)
                pairs.
        """
        # TODO: Cache this; a Channel's SubChannels will often be used together.
        if not self.useAllTransforms:
            xform = self._comboXform
        elif display:
            xform = self._displayXform or self._fullXform
        else:
            xform = self._fullXform

        if isinstance(idx, (int, np.integer)):


            if idx >= len(self):
                raise IndexError("EventArray index out of range")

            if idx < 0:
                idx = max(0, len(self) + idx)

            return self.arraySlice(idx, idx + 1)[:, 0]

        elif isinstance(idx, slice):
            # vvv Main difference from `EventList.__getitem__` vvv
            return self.arraySlice(idx)

        raise TypeError("EventArray indices must be integers or slices,"
                        " not %s (%r)" % (type(idx), idx))


    def __iter__(self):
        """ Iterator for the EventList. WAY faster than getting individual
            events.
        """
        return self.iterSlice()
                

    def __len__(self):
        """ x.__len__() <==> len(x)
        """
        if self._singleSample:
            return len(self._data)
        if len(self._data) == 0:
            return 0
        # For some reason, the cached self._length wasn't thread-safe.
#         return self._length
        try:
            return self._data[-1].indexRange[-1]
        except (TypeError, IndexError):
            # Can occur early on while asynchronously loading.
            return self._length
    
    
    def __eq__(self, other):
        if other is self:
            return True
        elif not isinstance(other, self.__class__):
            return False
        else:
            return self.parent == other.parent \
               and self.session == other.session \
               and self._data == other._data \
               and self._length == other._length \
               and self.dataset == other.dataset \
               and self.hasSubchannels == other.hasSubchannels \
               and self._firstTime == other._firstTime \
               and self._parentList == other._parentList \
               and self._childLists == other._childLists \
               and self.noBivariates == other.noBivariates \
               and self._singleSample == other._singleSample \
               and self._blockTimes == other._blockTimes \
               and self._blockIndices == other._blockIndices \
               and self.channelId == other.channelId \
               and self.subchannelId == other.subchannelId \
               and self.channelId == other.channelId \
               and self._hasSubsamples == other._hasSubsamples \
               and self.hasDisplayRange == other.hasDisplayRange \
               and self.displayRange == other.displayRange \
               and self.removeMean == other.removeMean \
               and self.hasMinMeanMax == other.hasMinMeanMax \
               and self.rollingMeanSpan == other.rollingMeanSpan \
               and self.transform == other.transform \
               and self.useAllTransforms == other.useAllTransforms \
               and self.allowMeanRemoval == other.allowMeanRemoval 


    def itervalues(self, start=None, end=None, step=1, subchannels=True,
                   display=False):
        """ Iterate all values in the given index range (w/o times).

            :keyword start: The first index in the range, or a slice.
            :keyword end: The last index in the range. Not used if `start` is
                a slice.
            :keyword step: The step increment. Not used if `start` is a slice.
            :keyword subchannels: A list of subchannel IDs or Boolean. `True`
                will return all subchannels in native order.
            :keyword display: If `True`, the `EventArray` transform (i.e. the
                'display' transform) will be applied to the data.
            :return: an iterable of structured array value blocks in the
                specified index range.
        """

        warnings.warn(DeprecationWarning('iter methods should be expected to be '
                                         'removed in future versions of idelib'))

        out = self.arrayValues(start=start, end=end, step=step)

        yield from out.T


    def arrayValues(self, start=None, end=None, step=1, subchannels=True,
                    display=False):
        """ Get all values in the given index range (w/o times).

            :keyword start: The first index in the range, or a slice.
            :keyword end: The last index in the range. Not used if `start` is
                a slice.
            :keyword step: The step increment. Not used if `start` is a slice.
            :keyword subchannels: A list of subchannel IDs or Boolean. `True`
                will return all subchannels in native order.
            :keyword display: If `True`, the `EventArray` transform (i.e. the
                'display' transform) will be applied to the data.
            :return: a structured array of values in the specified index range.
        """

        if not isinstance(start, slice):
            start = slice(start, end, step)
        start, end, step = start.indices(len(self))

        if self.useAllTransforms:
            xform = self._fullXform
            if display:
                xform = self._displayXform or xform
        else:
            xform = self._comboXform

        rawData = self._accessCache(start, end, step)

        if isinstance(self.parent, SubChannel):
            out = np.empty((1, len(rawData)))
        else:
            out = np.empty((len(rawData.dtype), len(rawData)))

        if isinstance(self.parent, SubChannel):
            xform.polys[self.subchannelId].inplace(rawData, out=out)
        else:
            xform.inplace(np_recfunctions.structured_to_unstructured(rawData).T, out=out)

        if self.removeMean:
            out[1:] -= out[1:].mean(axis=1, keepdims=True)

        if isinstance(subchannels, Iterable):
            return out[list(subchannels)]
        else:
            return out


    def iterSlice(self, start=None, end=None, step=1, display=False):
        """ Create an iterator producing events for a range of indices.

            :keyword start: The first index in the range, or a slice.
            :keyword end: The last index in the range. Not used if `start` is
                a slice.
            :keyword step: The step increment. Not used if `start` is a slice.
            :keyword display: If `True`, the `EventArray` transform (i.e. the
                'display' transform) will be applied to the data.
            :return: an iterable of events in the specified index range.
        """

        warnings.warn(DeprecationWarning('iter methods should be expected to be '
                                         'removed in future versions of idelib'))

        out = self.arraySlice(start=start, end=end, step=step, display=display)

        yield from out.T


    def arraySlice(self, start=None, end=None, step=1, display=False):
        """ Create an array of events within a range of indices.

            :keyword start: The first index in the range, or a slice.
            :keyword end: The last index in the range. Not used if `start` is
                a slice.
            :keyword step: The step increment. Not used if `start` is a slice.
            :keyword display: If `True`, the `EventArray` transform (i.e. the
                'display' transform) will be applied to the data.
            :return: a structured array of events in the specified index range.
        """

        if not isinstance(start, slice):
            start = slice(start, end, step)
        start, end, step = start.indices(len(self))

        if self.useAllTransforms:
            xform = self._fullXform
            if display:
                xform = self._displayXform or xform
        else:
            xform = self._comboXform

        rawData = self._accessCache(start, end, step)

        if isinstance(self.parent, SubChannel):
            out = np.empty((2, len(rawData)))
        else:
            out = np.empty((len(rawData.dtype) + 1, len(rawData)))

        self._inplaceTime(start, end, step, out=out[0])

        if isinstance(self.parent, SubChannel):
            xform.polys[self.subchannelId].inplace(rawData, out=out[1], timestamp=out[0])
        else:
            xform.inplace(np_recfunctions.structured_to_unstructured(rawData).T, out=out[1:], timestamp=out[0])

        if self.removeMean:
            out[1:] -= out[1:].mean(axis=1, keepdims=True)

        return out


    def iterJitterySlice(self, start=None, end=None, step=1, jitter=0.5,
                         display=False):
        """ Create an iterator producing events for a range of indices.

            :keyword start: The first index in the range, or a slice.
            :keyword end: The last index in the range. Not used if `start` is
                a slice.
            :keyword step: The step increment. Not used if `start` is a slice.
            :keyword jitter: The amount by which to vary the sample time, as a
                normalized percentage of the regular time between samples.
            :keyword display: If `True`, the `EventArray` transform (i.e. the
                'display' transform) will be applied to the data.
            :return: an iterable of events in the specified index range.
        """

        warnings.warn(DeprecationWarning('iter methods should be expected to be '
                                         'removed in future versions of idelib'))

        self._computeMinMeanMax()

        data = self.arrayJitterySlice(start=start, end=end, step=step, jitter=jitter, display=display)

        yield from data.T
        


    def arrayJitterySlice(self, start=None, end=None, step=1, jitter=0.5,
                          display=False):
        """ Create an array of events within a range of indices.

            :keyword start: The first index in the range, or a slice.
            :keyword end: The last index in the range. Not used if `start` is
                a slice.
            :keyword step: The step increment. Not used if `start` is a slice.
            :keyword jitter: The amount by which to vary the sample time, as a
                normalized percentage of the regular time between samples.
            :keyword display: If `True`, the `EventArray` transform (i.e. the
                'display' transform) will be applied to the data.
            :return: a structured array of events in the specified index range.
        """

        if not isinstance(start, slice):
            start = slice(start, end, step)
        start, end, step = start.indices(len(self))

        # Check for non-jittered cases
        if jitter is True:
            jitter = 0.5
        scaledJitter = jitter * abs(step)

        if scaledJitter <= 0.5:
            return self.arraySlice(start=start, end=end, step=step, display=display)

        # begin as normal
        self._computeMinMeanMax()

        if not isinstance(start, slice):
            start = slice(start, end, step)
        start, end, step = start.indices(len(self))

        if self.useAllTransforms:
            xform = self._fullXform
            if display:
                xform = self._displayXform or xform
        else:
            xform = self._comboXform

        # grab all raw data
        rawData = self._accessCache(None, None, 1)

        # slightly janky way of enforcing output length
        if isinstance(self.parent, SubChannel):
            out = np.empty((2, len(self._accessCache(start, end, step))))
        else:
            out = np.empty((len(rawData.dtype) + 1, len(self._accessCache(start, end, step))))

        # save on space by being really clever and storing indices in timestamps
        indices = out[0].view(np.int64)
        indices[:] = np.arange(start, end, step, dtype=np.int64)
        if len(indices) > 2:
            indices[1:-1] += np.rint(np.random.uniform(
                    -scaledJitter, scaledJitter, (len(indices) - 2,)
                    )).astype(np.int64)

        # now index raw data
        rawData = rawData[indices]

        # now times
        self._inplaceTimeFromIndices(indices, out=out[0])

        if isinstance(self.parent, SubChannel):
            xform.polys[self.subchannelId].inplace(rawData, out=out[1], timestamp=out[0])
        else:
            for i, (k, _) in enumerate(rawData.dtype.descr):
                xform.polys[i].inplace(rawData[k], out=out[i + 1], timestamp=out[0])

        return out


    def getEventIndexBefore(self, t):
        """ Get the index of an event occurring on or immediately before the
            specified time.
        
            :param t: The time (in microseconds)
            :return: The index of the event preceding the given time, -1 if
                the time occurs before the first event.
        """
        if t < self._data[0].startTime:
            return -1

        if t >= self._data[-1].endTime:
            return self._data[-1].indexRange[1]

        blockIdx = self._getBlockIndexWithTime(t)
        try:
            block = self._data[blockIdx]
        except IndexError:
            block = self._data[-1]
        return int(block.indexRange[0] + \
                   ((t - block.startTime) / self._getBlockSampleTime(blockIdx)))
        
 
    def getEventIndexNear(self, t):
        """ The the event occurring closest to a specific time. 
        
            :param t: The time (in microseconds)
            :return: 
        """
        if t <= self._data[0].startTime:
            return 0

        if t >= self._data[-1].endTime:
            return self._data[-1].indexRange[1]

        idx = self.getEventIndexBefore(t)
        events = self[idx:idx+2][0]
        if len(events) == 1:
            return idx

        return idx + abs(events - t).argmin()


    def getRangeIndices(self, startTime, endTime):
        """ Get the first and last event indices that fall within the 
            specified interval.
            
            :keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            :keyword endTime: The second time, or `None` to use the end of
                the session.
        """
        if self.parent.singleSample:
            startIdx = self._getBlockIndexWithTime(startTime)
            if endTime is None:
                endIdx = len(self)
            else:
                endIdx = self._getBlockIndexWithTime(endTime, startIdx) + 1
            return startIdx, endIdx
            
        if startTime is None or startTime <= self._data[0].startTime:
            startIdx = startBlockIdx = 0
            startBlock = self._data[0]
        else:
            startBlockIdx = self._getBlockIndexWithTime(startTime)
            startBlock = self._data[startBlockIdx]
            startIdx = int(startBlock.indexRange[0] + \
                           ((startTime - startBlock.startTime) / \
                            self._getBlockSampleTime(startBlockIdx)) + 1)
            
        if endTime is None:
            endIdx = self._data[-1].indexRange[1]
        elif endTime <= self._data[0].startTime:
            endIdx = 0
        else:
            endIdx = self.getEventIndexBefore(endTime)+1
        return max(0, startIdx), min(endIdx, len(self))
    

    def iterRange(self, startTime=None, endTime=None, step=1, display=False):
        """ Get a set of data occurring in a given interval.
        
            :keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            :keyword endTime: The second time, or `None` to use the end of
                the session.
        """

        warnings.warn(DeprecationWarning('iter methods should be expected to be '
                                         'removed in future versions of idelib'))

        startIdx, endIdx = self.getRangeIndices(startTime, endTime)
        return self.iterSlice(startIdx,endIdx,step,display=display)        


    def arrayRange(self, startTime=None, endTime=None, step=1, display=False):
        """ Get a set of data occurring in a given time interval.

            :keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            :keyword endTime: The second time, or `None` to use the end of
                the session.
            :return: a structured array of events in the specified time
                interval.
        """
        self._computeMinMeanMax()
        startIdx, endIdx = self.getRangeIndices(startTime, endTime)
        return self.arraySlice(startIdx, endIdx, step, display=display)


    def getRange(self, startTime=None, endTime=None, display=False):
        """ Get a set of data occurring in a given time interval. (Currently
            an alias of `arrayRange`.)

            :keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            :keyword endTime: The second time, or `None` to use the end of
                the session.
            :return: a collection of events in the specified time interval.
        """
        return self.arrayRange(startTime, endTime, display=display)


    def iterMinMeanMax(self, startTime=None, endTime=None, padding=0,
                       times=True, display=False):
        """ Get the minimum, mean, and maximum values for blocks within a
            specified interval.

            :todo: Remember what `padding` was for, and either implement or
                remove it completely. Related to plotting; see `plots`.
            
            :keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            :keyword endTime: The second time, or `None` to use the end of
                the session.
            :keyword times: If `True` (default), the results include the 
                block's starting time. 
            :keyword display: If `True`, the final 'display' transform (e.g.
                unit conversion) will be applied to the results. 
            :return: An iterator producing sets of three events (min, mean, 
                and max, respectively).
        """

        warnings.warn(DeprecationWarning('iter methods should be expected to be '
                                         'removed in future versions of idelib'))

        if not self.hasMinMeanMax:
            self._computeMinMeanMax()
            
        startBlockIdx, endBlockIdx = self._getBlockRange(startTime, endTime)
        
        # OPTIMIZATION: Local variables for things used in inner loops
        hasSubchannels = self.hasSubchannels
        session = self.session
        removeMean = self.removeMean and self.allowMeanRemoval
        _getBlockRollingMean = self._getBlockRollingMean
        if not hasSubchannels:
            parent_id = self.subchannelId

        if self.useAllTransforms:
            xform = self._fullXform
            if display:
                xform = self._displayXform or xform
        else:
            xform = self._comboXform

        for block in self._data[startBlockIdx:endBlockIdx]:
            t = block.startTime
            m = _getBlockRollingMean(block.blockIndex)
            
            # HACK: Multithreaded loading can (very rarely) fail at start.
            # The problem is almost instantly resolved, though. Find root cause.
            tries = 0
            if removeMean and m is None:
                sleep(0.01)
                m = _getBlockRollingMean(block.blockIndex)
                tries += 1
                if tries > 10 or not self.dataset.loading:
                    break
            
            if m is not None:
                mx = xform(t, m, session, noBivariates=self.noBivariates)
                if mx is None:
                    sleep(0.005)
                    mx = xform(t, m, session, noBivariates=self.noBivariates)
                    if mx is None:
                        mx = t, m
                m = np.array(mx[1])
                
            result = []
            result_append = result.append
            
            for val in (block.min, block.mean, block.max):
                event=xform(t, val, session, noBivariates=self.noBivariates)
                if event is None:
                    # HACK: No bivariate data (yet), possibly still loading.
                    # Retry once.
                    sleep(0.005)
                    event = xform(t, val, session, noBivariates=self.noBivariates)
                    if event is None:
                        event = t, val
                tx, valx = event
                if removeMean and m is not None:
                    valx = valx - m
                result_append(valx)
            
            # Transformation has negative coefficient for inverted z-axis data
            # -> need to sort mins/maxes to compensate
            if hasSubchannels:
                # 'rotate' the arrays, sort them, 'rotate' back.
                result = list(zip(*list(map(sorted, list(zip(*result))))))
            else:
                result = tuple((v[parent_id],) for v in result)
                if result[0][0] > result[2][0]:
                    result = result[::-1]

            if times:
                yield tuple((tx,)+x for x in result)
            else:
                yield tuple(result)


    def arrayMinMeanMax(self, startTime=None, endTime=None, padding=0,
                        times=True, display=False, iterator=iter):
        """ Get the minimum, mean, and maximum values for blocks within a
            specified interval.

            :todo: Remember what `padding` was for, and either implement or
                remove it completely. Related to plotting; see `plots`.

            :keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            :keyword endTime: The second time, or `None` to use the end of
                the session.
            :keyword times: If `True` (default), the results include the
                block's starting time.
            :keyword display: If `True`, the final 'display' transform (e.g.
                unit conversion) will be applied to the results.
            :return: A structured array of data block statistics (min, mean,
                and max, respectively).
        """

        startBlock, endBlock = self._getBlockRange(startTime, endTime)
        shape = (3, max(1, len(self._npType)) + int(times), endBlock - startBlock)
        scid = self.subchannelId
        isSubchannel = isinstance(self.parent, SubChannel)

        if self.useAllTransforms:
            xform = self._fullXform
            if display:
                xform = self._displayXform or xform
        else:
            xform = self._comboXform

        out = np.empty(shape)

        for i, d in enumerate(self._data[startBlock:endBlock]):
            if isSubchannel:
                if times:
                    out[:, 0, i] = d.startTime
                    out[0, 1, i] = d.min[scid]
                    out[1, 1, i] = d.mean[scid]
                    out[2, 1, i] = d.max[scid]
                else:
                    out[0, 0, i] = d.min[scid]
                    out[1, 0, i] = d.mean[scid]
                    out[2, 0, i] = d.max[scid]
            else:
                if times:
                    out[:, 0, i] = d.startTime
                    out[0, 1:, i] = d.min
                    out[1, 1:, i] = d.mean
                    out[2, 1:, i] = d.max
                else:
                    out[0, :, i] = d.min
                    out[1, :, i] = d.mean
                    out[2, :, i] = d.max

        if isSubchannel:
            xform = xform.polys[self.subchannelId]
            if times:
                for m in range(3):
                    xform.inplace(out[m, 1, :], out=out[m, 1, :])
            else:
                for m in range(3):
                    xform.inplace(out[m, 0, :], out=out[m, 0, :])
        else:
            if times:
                for m in range(3):
                    xform.inplace(out[m, 1:, :], out=out[m, 1:, :])
            else:
                for m in range(3):
                    xform.inplace(out[m, :, :], out=out[m, :, :])

        return out


    def getMinMeanMax(self, startTime=None, endTime=None, padding=0,
                      times=True, display=False, iterator=iter):
        """ Get the minimum, mean, and maximum values for blocks within a
            specified interval. (Currently an alias of `arrayMinMeanMax`.)

            :todo: Remember what `padding` was for, and either implement or
                remove it completely. Related to plotting; see `plots`.

            :keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            :keyword endTime: The second time, or `None` to use the end of
                the session.
            :keyword times: If `True` (default), the results include the
                block's starting time.
            :keyword display: If `True`, the final 'display' transform (e.g.
                unit conversion) will be applied to the results.
            :return: A structured array of data block statistics (min, mean,
                and max, respectively).
        """
        return self.arrayMinMeanMax(startTime, endTime, padding, times,
                                    display, iterator)


    def getRangeMinMeanMax(self, startTime=None, endTime=None, subchannel=None,
                           display=False, iterator=iter):
        """ Get the single minimum, mean, and maximum value for blocks within a
            specified interval. Note: Using this with a parent channel without
            specifying a subchannel number can produce meaningless data if the
            channels use different units or are on different scales.

            :keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            :keyword endTime: The second time, or `None` to use the end of
                the session.
            :keyword subchannel: The subchannel ID to retrieve, if the
                EventArray's parent has subchannels.
            :keyword display: If `True`, the final 'display' transform (e.g.
                unit conversion) will be applied to the results.
            :return: A namedtuple of aggregated event statistics (min, mean,
                and max, respectively).
        """
        stats = self.arrayMinMeanMax(startTime, endTime, times=False,
                                     display=display, iterator=iterator)

        if stats.size == 0:
            return None
        if self.hasSubchannels and subchannel is not None:
            return (
                stats[0, subchannel].min(),
                np.median(stats[1, subchannel]),
                stats[2, subchannel].max(),
            )
        else:
            return (
                stats[0].min(),
                np.mean(np.median(stats[1], axis=-1)),
                stats[2].max(),
            )


    def _getBlockRange(self, startTime=None, endTime=None):
        """ Get blocks falling within a time range. Used internally.
        """
        if startTime is None:
            startBlockIdx = 0
        else:
            startBlockIdx = self._getBlockIndexWithTime(startTime)
            startBlockIdx = max(startBlockIdx-1, 0)
        if endTime is None:
            endBlockIdx = len(self._data)
        else:
            if endTime < 0:
                endTime += self._data[-1].endTime
            endBlockIdx = self._getBlockIndexWithTime(endTime, start=startBlockIdx)
            endBlockIdx = min(len(self._data), max(startBlockIdx+1, endBlockIdx+1))
            
        return startBlockIdx, endBlockIdx


    def getMax(self, startTime=None, endTime=None, display=False, iterator=iter):
        """ Get the event with the maximum value, optionally within a specified
            time range. For Channels, returns the maximum among all
            Subchannels.

            :keyword startTime: The starting time. Defaults to the start.
            :keyword endTime: The ending time. Defaults to the end.
            :keyword display: If `True`, the final 'display' transform (e.g.
                unit conversion) will be applied to the results.
            :return: The event with the maximum value.
        """
        maxs = self.arrayMinMeanMax(startTime, endTime, times=False,
                                    display=display, iterator=iterator)[2].max(axis=0)

        blockIdx = maxs.argmax()  # TODO: is this bug-free? double-check
        sampleIdxRange = self._data[blockIdx].indexRange
        blockData = self.arraySlice(*sampleIdxRange, display=display)
        subIdx = blockData[1:].max(axis=0).argmax()

        return blockData[:, subIdx]


    def getMin(self, startTime=None, endTime=None, display=False, iterator=iter):
        """ Get the event with the minimum value, optionally within a specified
            time range. For Channels, returns the minimum among all
            Subchannels.

            :keyword startTime: The starting time. Defaults to the start.
            :keyword endTime: The ending time. Defaults to the end.
            :keyword display: If `True`, the final 'display' transform (e.g.
                unit conversion) will be applied to the results.
            :return: The event with the minimum value.
        """
        if not self.hasMinMeanMax:
            self._computeMinMeanMax()

        mins = self.arrayMinMeanMax(startTime, endTime, times=False,
                                    display=display, iterator=iterator)[0].min(axis=0)

        blockIdx = mins.argmin()  # TODO: is this bug-free? double-check
        sampleIdxRange = self._data[blockIdx].indexRange
        blockData = self.arraySlice(*sampleIdxRange, display=display)
        subIdx = blockData[1:].min(axis=0).argmin()

        return blockData[:, subIdx]


    def _getBlockSampleTime(self, blockIdx=0):
        """ Get the time between samples within a given data block.
            
            :keyword blockIdx: The index of the block to measure. Times
                within the same block are expected to be consistent, but can
                possibly vary from block to block.
            :return: The sample rate, as samples per second
        """
        if len(self._data) == 0:
            # Channel has no events. Probably shouldn't happen.
            # TODO: Get the sample rate from another session?
            return -1
        
#         if blockIdx < 0:
#             blockIdx += len(self._data)
        
        # See if it's already been computed or provided in the recording
        block = self._data[blockIdx]
        if block.sampleTime is not None:
            return block.sampleTime
        
        startTime = block.startTime
        endTime = block.endTime

        if endTime is None or endTime == startTime:
            # No recorded end time, or a single-sample block.
            if len(self._data) == 1:
                # Only one block; can't compute from that!
                # TODO: Implement getting sample rate in case of single block?
                return -1
            elif blockIdx == len(self._data) - 1:
                # Last block; use previous.
                block.sampleTime = self._getBlockSampleTime(blockIdx-1)
                return block.sampleTime
            else:
                endTime = self._data[blockIdx+1].startTime
            block.endTime = endTime
        
        numSamples = block.getNumSamples(self.parent.parser)
        if numSamples <= 1:
            block.sampleTime = endTime - startTime
            return block.sampleTime

        block.sampleTime = (endTime - startTime) / (numSamples-1.0)
        
        return block.sampleTime


    def _getBlockSampleRate(self, blockIdx=0):
        """ Get the channel's sample rate. This is either supplied as part of
            the channel definition or calculated from the actual data and
            cached.
            
            :keyword blockIdx: The block to check. Optional, because in an
                ideal world, all blocks would be the same.
            :return: The sample rate, as samples per second (float)
        """
        
        if self._data[blockIdx].sampleRate is None:
            sampTime = self._getBlockSampleTime(blockIdx)
            if sampTime > 0:
                self._data[blockIdx].sampleRate = 1000000.0 / sampTime
            else:
                self._data[blockIdx].sampleRate = 0
        return self._data[blockIdx].sampleRate


    def getSampleTime(self, idx=None):
        """ Get the time between samples.
            
            :keyword idx: Because it is possible for sample rates to vary
                within a channel, an event index can be specified; the time
                between samples for that event and its siblings will be 
                returned.
            :return: The time between samples (us)
        """
        sr = self.parent.sampleRate
        if idx is None:
            if sr is not None:
                return 1.0/sr
            else:
                idx = 0
        return self._getBlockSampleTime(self._getBlockIndexWithIndex(idx))
    
    
    def getSampleRate(self, idx=None):
        """ Get the channel's sample rate. This is either supplied as part of
            the channel definition or calculated from the actual data and
            cached.
            
            :keyword idx: Because it is possible for sample rates to vary
                within a channel, an event index can be specified; the sample
                rate for that event and its siblings will be returned.
            :return: The sample rate, as samples per second (float)
        """
        sr = self.parent.sampleRate
        if idx is None and sr is not None:
            return sr
        else:
            idx = 0
        return self._getBlockSampleRate(self._getBlockIndexWithIndex(idx))
    

    def getValueAt(self, at, outOfRange=False, display=False):
        """ Retrieve the value at a specific time, interpolating between
            existing events.
            
            :todo: Optimize. This creates a bottleneck in the calibration.
            
            :param at: The time at which to take the sample.
            :keyword outOfRange: If `False`, times before the first sample
                or after the last will raise an `IndexError`. If `True`, the
                first or last time, respectively, is returned.
        """
        startIdx = self.getEventIndexBefore(at)
        if startIdx < 0:
            first = self.__getitem__(0, display=display)
            if first[0] == at:
                return first
            if outOfRange:
                return first
            raise IndexError("Specified time occurs before first event (%d)" % first[0])
        elif startIdx >= len(self) - 1:
            last = self.__getitem__(-1, display=display)
            if last[0] == at:
                return last
            if outOfRange:
                return last
            raise IndexError("Specified time occurs after last event (%d)" % last[0])
        
        startEvt = self.__getitem__(startIdx, display=display)
        endEvt = self.__getitem__(startIdx+1, display=display)
        relAt = at - startEvt[0]
        endTime = endEvt[0] - startEvt[0] + 0.0
        percent = relAt/endTime
        
        return (at,) + tuple(
            v1 + (percent * (v2-v1))
            for v1, v2 in zip(startEvt[1:], endEvt[1:])
        )


    def getMean(self, startTime=None, endTime=None, display=False, iterator=iter):
        """ Get the mean value of all events, optionally within a specified
            time range. For Channels, returns the mean among all
            Subchannels.

            :keyword startTime: The starting time. Defaults to the start.
            :keyword endTime: The ending time. Defaults to the end.
            :keyword display: If `True`, the final 'display' transform (e.g.
                unit conversion) will be applied to the results.
            :return: The event with the minimum value.
        """
        if not self.hasMinMeanMax:
            self._computeMinMeanMax()

        if startTime is None and endTime is None:
            if self._mean is not None:
                return self._mean

        means = self.arrayMinMeanMax(startTime, endTime, times=False,
                                     display=display, iterator=iterator)[1]

        mean = np.mean(np.average(means, weights=[d.numSamples for d in self._data], axis=-1))

        if startTime is None and endTime is None:
            self._mean = mean

        return mean
    

    def getMeanNear(self, t, outOfRange=False):
        """ Retrieve the mean value near a given time.
        """
        b = self._getBlockIndexWithTime(t)
        _, m = self._comboXform(t, self._getBlockRollingMean(b, force=True))
        if self.hasSubchannels:
            return m
        return m[self.subchannelId]


    def _computeMinMeanMax(self):
        """ Calculate the minimum, mean, and max for files without that data
            recorded. Not recommended for large data sets.
        """
        if self.hasMinMeanMax:
            return
        
        if self.hasSubchannels:
            parseBlock = self.parent.parseBlock
        else:
            parseBlock = self.parent.parent.parseBlock
        
        for block in self._data:
            try:
                if (block.min is None or block.mean is None or block.max is None):
                    vals = parseBlock(block)
                    block.min = vals.min(axis=-1)
                    block.mean = vals.mean(axis=-1)
                    block.max = vals.max(axis=-1)
            
                self.hasMinMeanMax = True
                
            except struct.error:
                logger.warning("_computeMinMeanMax struct error: %r" % (block.indexRange,))
                if __DEBUG__:
                    raise


    def iterResampledRange(self, startTime, stopTime, maxPoints, padding=0,
                           jitter=0, display=False):
        """ Retrieve the events occurring within a given interval,
            undersampled as to not exceed a given length (e.g. the size of
            the data viewer's screen width).
        
            :todo: Optimize iterResampledRange(); not very efficient,
                particularly not with single-sample blocks.
        """

        warnings.warn(DeprecationWarning('iter methods should be expected to be '
                                         'removed in future versions of idelib'))

        startIdx, stopIdx = self.getRangeIndices(startTime, stopTime)
        numPoints = (stopIdx - startIdx)
        startIdx = max(startIdx-padding, 0)
        stopIdx = min(stopIdx+padding, len(self))
        step = max(-int(-numPoints // maxPoints), 1)
        
        if jitter != 0:
            return self.iterJitterySlice(startIdx, stopIdx, step, jitter,
                                         display=display)
        return self.iterSlice(startIdx, stopIdx, step, display=display)


    def arrayResampledRange(self, startTime, stopTime, maxPoints, padding=0,
                            jitter=0, display=False):
        """ Retrieve the events occurring within a given interval,
            undersampled as to not exceed a given length (e.g. the size of
            the data viewer's screen width).

            :todo: Optimize iterResampledRange(); not very efficient,
                particularly not with single-sample blocks.
        """
        from math import ceil

        startIdx, stopIdx = self.getRangeIndices(startTime, stopTime)
        startIdx = max(startIdx-padding, 0)
        stopIdx = min(stopIdx+padding+1, len(self))
        step = max(int(ceil((stopIdx - startIdx) / maxPoints)), 1)

        if jitter != 0:
            return self.arrayJitterySlice(startIdx, stopIdx, step, jitter,
                                          display=display)
        return self.arraySlice(startIdx, stopIdx, step, display=display)


    def exportCsv(self, stream, start=None, stop=None, step=1, subchannels=True,
                  callback=None, callbackInterval=0.01, timeScalar=1,
                  raiseExceptions=False, dataFormat="%.6f", delimiter=", ",
                  useUtcTime=False, useIsoFormat=False, headers=False, 
                  removeMean=None, meanSpan=None, display=False,
                  noBivariates=False):
        """ Export events as CSV to a stream (e.g. a file).
        
            :param stream: The stream object to which to write CSV data.
            :keyword start: The first event index to export.
            :keyword stop: The last event index to export.
            :keyword step: The number of events between exported lines.
            :keyword subchannels: A sequence of individual subchannel numbers
                to export. Only applicable to objects with subchannels.
                `True` (default) exports them all.
            :keyword callback: A function (or function-like object) to notify
                as work is done. It should take four keyword arguments:
                `count` (the current line number), `total` (the total number
                of lines), `error` (an exception, if raised during the
                export), and `done` (will be `True` when the export is
                complete). If the callback object has a `cancelled`
                attribute that is `True`, the CSV export will be aborted.
                The default callback is `None` (nothing will be notified).
            :keyword callbackInterval: The frequency of update, as a
                normalized percent of the total lines to export.
            :keyword timeScalar: A scaling factor for the event times.
                The default is 1 (microseconds).
            :keyword raiseExceptions: 
            :keyword dataFormat: The number of decimal places to use for the
                data. This is the same format as used when formatting floats.
            :keyword useUtcTime: If `True`, times are written as the UTC
                timestamp. If `False`, times are relative to the recording.
            :keyword useIsoFormat: If `True`, the time column is written as
                the standard ISO date/time string. Only applies if `useUtcTime`
                is `True`.
            :keyword headers: If `True`, the first line of the CSV will contain
                the names of each column.
            :keyword removeMean: Overrides the EventArray's mean removal for the
                export.
            :keyword meanSpan: The span of the mean removal for the export. 
                -1 removes the total mean.
            :keyword display: If `True`, export using the EventArray's 'display'
                transform (e.g. unit conversion).
            :return: Tuple: The number of rows exported and the elapsed time.
        """
        noCallback = callback is None
        _self = self.copy()

        # Create a function for formatting the event time.        
        if useUtcTime and _self.session.utcStartTime:
            if useIsoFormat:
                timeFormatter = lambda x: datetime.utcfromtimestamp(x[0] * timeScalar + _self.session.utcStartTime).isoformat()
            else:
                timeFormatter = lambda x: dataFormat % (x[0] * timeScalar + _self.session.utcStartTime)
        else:
            timeFormatter = lambda x: dataFormat % (x[0] * timeScalar)
        
        # Create the function for formatting an entire row.
        if _self.hasSubchannels:
            if isinstance(subchannels, Iterable):
                fstr = '%s' + delimiter + delimiter.join([dataFormat] * len(subchannels))
                formatter = lambda x: fstr % ((timeFormatter(x),) +
                                              tuple(x[1+v] for v in subchannels))
                names = [_self.parent.subchannels[x].name for x in subchannels]
            else:
                fstr = '%s' + delimiter + delimiter.join([dataFormat] * len(_self.parent.types))
                formatter = lambda x: fstr % ((timeFormatter(x),) + tuple(x[1:]))
                names = [x.name for x in _self.parent.subchannels]
        else:
            fstr = "%%s%s%s" % (delimiter, dataFormat)
            formatter = lambda x: fstr % (timeFormatter(x), x[1:])
            names = [_self.parent.name]

        if removeMean is not None:
            _self.removeMean = _self.allowMeanRemoval and removeMean
        if meanSpan is not None:
            _self.rollingMeanSpan = meanSpan
        
        start, stop, step = slice(start, stop, step).indices(len(self))

        totalLines = len(range(start, stop, step))
        numChannels = len(names)
        totalSamples = totalLines * numChannels
        updateInt = int(totalLines * callbackInterval)
        
        t0 = datetime.now()
        if headers:
            stream.write('"Time"%s%s\n' % 
                         (delimiter, delimiter.join(['"%s"' % n for n in names])))

        data = _self.arraySlice(start, stop, step)
        if useUtcTime and _self.session.utcStartTime:
            if useIsoFormat:
                times = data[0]
                data = data.astype([('time', '<U19')] + [(str(i), np.float64) for i in range(1, 4)])

            
        num = 0
        try:
            for num, evt in enumerate(_self.iterSlice(start, stop, step, display=display)):
                stream.write("%s\n" % formatter(evt))
                # print(evt - np.array([float(x) for x in formatter(evt).split(', ')]))
                if callback is not None:
                    if getattr(callback, 'cancelled', False):
                        callback(done=True)
                        break
                    if updateInt == 0 or num % updateInt == 0:
                        callback(num*numChannels, total=totalSamples)
            if callback is not None:
                callback(done=True)
        except Exception as e:
            if raiseExceptions:
                raise
            elif callback is not None:
                callback(error=e)

        return num+1, datetime.now() - t0

    def fillCache(self):
        with self.dataset._channelDataLock:
            self._cacheArray = np.concatenate([d.payload for d in self._data])
            self._cacheBytes = self._cacheArray.view(np.uint8)

            idx = 0
            for d in self._data:
                d._payload = self._cacheArray[idx:idx + len(d._payload)]
                idx += len(d._payload)

    def _accessCache(self, start, end, step):
        """ Access cached data in a thread-safe way.  If data has not fully
            loaded, instead allocate an appropriately large array, fill it with
            data, then return that instead.
        """

        if isinstance(self.parent, SubChannel):
            schId = self.subchannelId
            ch = self.parent.parent
            rawData = ch.getSession(self.session.sessionId)._accessCache(start, end, step)
            schKey = rawData.dtype.names[schId]
            return rawData[schKey]

        with self.dataset._channelDataLock:
            if self.dataset.loading:
                return np.concatenate([d.payload for d in self._data])[start:end:step]
            else:
                return self._cacheArray[start:end:step]

    def _inplaceTime(self, start, end, step, out=None):
        if out is None:
            out = np.empty((int(np.ceil((end - start)/step)),))

        if self._singleSample:
            out[:] = [d.startTime for d in self._data[start:end:step]]
            return out

        vals = np.empty((self._data[-1].indexRange[-1],))

        for d in self._data:
            arrayStart = d.startTime
            arrayEnd = d.endTime
            startIdx, endIdx = d.indexRange
            if d.numSamples > 1:
                samplePeriod = (arrayEnd - arrayStart)/(d.numSamples - 1)
            else:
                samplePeriod = arrayEnd - arrayStart

            # out = samplePeriod*(step*out + start) + arrayStart
            # out = out*(samplePeriod*step) + (samplePeriod*start + arrayStart)
            vals[startIdx:endIdx] = np.arange(d.numSamples)
            vals[startIdx:endIdx] *= samplePeriod
            vals[startIdx:endIdx] += arrayStart

        if out.shape == vals[start:end:step].shape:
            out[:] = vals[start:end:step]
        else:
            out[:] = vals[start:end:step][:out.shape[0]]

        return out

    def _inplaceTimeFromIndices(self, indices, out=None):
        if out is None:
            out = indices.astype(np.float64)

        out[:] = indices

        arrayStart = float(self._data[0].startTime)
        arrayEnd = float(self._data[-1].endTime)
        nSamples = len(self)
        if nSamples > 1:
            samplePeriod = (arrayEnd - arrayStart) / (nSamples - 1)
        else:
            samplePeriod = arrayEnd - arrayStart

        out *= samplePeriod
        out += arrayStart
        return out


#===============================================================================
# 
#===============================================================================


class Plot(Transformable):
    """ A processed set of sensor data. These are typically the final form of
        the data. Transforms applied are intended to be for display purposes
        (e.g. converting data in foot-pounds to pascals).
    """
    
    def __init__(self, source, plotId, name=None, transform=None, units=None,
                 attributes=None):
        self.source = source
        self.id = plotId
        self.session = source.session
        self.dataset = source.dataset
        self.name = source.path() if name is None else name
        self.units = source.units if units is None else units
        self.attributes = attributes
        self.setTransform(transform, update=False)
    
    
    def __len__(self):
        return len(self.source)
    
    
    def __getitem__(self, idx):
        result = self.source[idx]
        if isinstance(result, tuple):
            return self._transform(result, self.session)
        return [self._transform(evt, self.session) for evt in result]
    
    
    def __iter__(self):
        # Note: self._transform is used here instead of self._mapTransform;
        # itertools.imap(None, x) works differently than map(None,x)!
        return map(self._transform, self.source)
            
            
    def getEventIndexBefore(self, t):
        """
        """
        return self.source.getEventIndexBefore(t)
    
    
    def getEventIndexNear(self, t):
        """
        """
        return self.source.getEventIndexNear(t)


    def getRange(self, startTime, endTime):
        return [self._mapTransform(x) for x in self.source.getRange(startTime, endTime)]
    
    
    def getSampleRate(self, idx=0):
        return self.source.getSampleRate(idx)
    
    def getSampleTime(self, idx=0):
        return self.source.getSampleTime(idx)
    
    
    def getValueAt(self, at):
        return self._transform(self.source.getValueAt(at))
    
    
    def iterRange(self, startTime, endTime):
        # Note: self._transform is used here instead of self._mapTransform;
        # itertools.imap(None, x) works differently than map(None,x)!
        return map(self._transform, self.source.iterRange(startTime, endTime))
    
    
    def iterSlice(self, start=None, end=None, step=1):
        # Note: self._transform is used here instead of self._mapTransform;
        # itertools.imap(None, x) works differently than map(None,x)!
        return map(self._transform, self.source.iterSlice(start, end, step))
    

#===============================================================================
# 
#===============================================================================

class WarningRange(object):
    """ An object for indicating when a set of events goes outside of a given
        range. Originally created for flagging periods of extreme temperatures
        that will affect accelerometer readings.
        
        For efficiency, the source data should have relatively few samples
        (e.g. a low sample rate).
    """
    
    def __repr__(self):
        return "<%s %d (%s < %s < %s) at 0x%08x>" % (self.__class__.__name__, 
               self.id, self.low, self.source.name, self.high, id(self))


    @property
    def displayName(self):
        """ A nice, human-readable description of this warning range, for use
            with user interfaces.
        """
        if self._displayName is None:
            try:
                units = self.source.units[1]
                if self.low is None:
                    s = "above %r%s" % (self.high, units)
                elif self.high is None:
                    s = "below %r%s" % (self.low, units)
                else:
                    s = "outside range %r%s to %r%s" % (self.low, units, 
                                                        self.high, units)
                self._displayName = "%s %s" % (self.source.displayName, s)
            except TypeError:
                pass
        return self._displayName
    
    
    def __init__(self, dataset, warningId=None, channelId=None, 
                 subchannelId=None, low=None, high=None, attributes=None):
        """ Constructor.
        """
        self.dataset = dataset
        self.id = warningId
        self.channelId = channelId
        self.subchannelId = subchannelId
        self.high = high
        self.low = low
        self.attributes = attributes
        
        self._sessions = {}
        try:
            self.source = dataset.channels[channelId][subchannelId]
        except (KeyError, IndexError):
            if warningId is not None:
                wid = "0x%02X" % warningId
            else:
                wid = "with no ID"
            logger.warning("WarningRange %s references a non-existent "
                           "subchannel: %s.%s" % (wid, channelId, subchannelId))
            self.source = None
        
        if low is None:
            self.valid = lambda x: x < high
        elif high is None:
            self.valid = lambda x: x > low
        else:
            self.valid = lambda x: x > low and x < high
        
        self._displayName = None
        
        
    def __eq__(self, other):
        if other is self:
            return True
        elif not isinstance(other, self.__class__):
            return False
        else:
            return self.dataset == other.dataset \
               and self.id == other.id \
               and self.channelId == other.channelId \
               and self.subchannelId == other.subchannelId \
               and self.high == other.high \
               and self.low == other.low \
               and self.attributes == other.attributes \
               and self._sessions == other._sessions
    
    
    def getSessionSource(self, sessionId=None):
        """ 
        """
        try:
            return self._sessions[sessionId]
        except KeyError:
            s = self.source.getSession(sessionId)
            self._sessions[sessionId] = s
            return s
        
    
    def getRange(self, start=None, end=None, sessionId=None, iterator=iter):
        """ Retrieve the invalid periods within a given range of events.
            
            :return: A list of invalid periods' [start, end] times.
        """
        if self.source is None:
            return []
        
        source = self.getSessionSource(sessionId)

        if start is None:
            start = source[0][0]
        if end is None:
            end = source[-1][0]
            
        result = []
        v = self.getValueAt(start, source=source)
        if v is None:
            return result
        
        outOfRange =  v[-1] is not True

        if outOfRange:
            result = [[start, start]]
        
        for event in iterator(source.iterRange(start, end)):
            t = event[0]
            if self.valid(event[1:]):
                if outOfRange:
                    result[-1][1] = t
                    outOfRange = False
            else:
                if not outOfRange:
                    result.append([t, t])
                    outOfRange = True
        
        # Close out any open invalid range
        if outOfRange:
            result[-1][1] = -1  # end
        
        return result
    
    
    def getValueAt(self, at, sessionId=None, source=None):
        """ Retrieve the value at a specific time. 
        """
        if self.source is None:
            return at, True
        
        source = self.getSessionSource(sessionId) if source is None else source
        t = min(max(source[0][0], at), source[-1][0])
        val = source.getValueAt(t, outOfRange=True)
        return at, self.valid(val[-1])


#===============================================================================
# 
#===============================================================================

# HACK to work around the fact that the `register` method doesn't show up
# in `dir()`, which creates an error display in PyLint/PyDev/etc. 
getattr(Iterable, 'register')(EventArray)
getattr(Iterable, 'register')(WarningRange)
