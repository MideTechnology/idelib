'''
Created on Sep 26, 2013

@author: dstokes


@todo: See where NumPy can be leveraged. The original plan was to make this
    module free of all dependencies (save python_ebml), but NumPy greatly 
    improved the new min/mean/max stuff. Might as well take advantage of it
    elsewhere!  
@todo: Discontinuity handing. This will probably be conveyed as events with
    null values. An attribute/keyword may be needed to suppress this when 
    getting data for processing (FFT, etc.)
@todo: Look at places where lists are returned, consider using `yield` 
    instead (e.g. parseElement(), etc.)
@todo: Have Sensor.addChannel() possibly check the parser to see if the 
    blocks are single-sample, instantiate simpler Channel subclass (possibly
    also a specialized, simpler class of EventList, too)
@todo: Decide if dataset.useIndices is worth it, remove it if it isn't.
    Removing it may save a trivial amount of time/memory (one fewer 
    conditional in event-getting methods).

'''


from collections import namedtuple, Iterable
from datetime import datetime
from itertools import imap, izip
from numbers import Number
import os.path
import random
import sys

import numpy

from ebml.schema.mide import MideDocument
import util

from calibration import Transform
from parsers import getParserTypes, getParserRanges


#===============================================================================
# DEBUGGING: XXX: Remove later!
#===============================================================================

__DEBUG__ = True

# import socket
# __DEBUG__ = socket.gethostname() in ('DEDHAM',)
    
if __DEBUG__:
    import ebml
    print "*** Loaded python-ebml from", os.path.abspath(ebml.__file__)
    
#===============================================================================
# 
#===============================================================================

# A 'named tuple' class, mainly for debugging purposes.
Event = namedtuple("Event", ('index','time','value'))


#===============================================================================
# Interpolation objects, for getting value at a specific time
#===============================================================================

class Interpolation(object):
    """ A function-like class that will produce a value at a specified point
        between two events. Upon instantiation, it can be passed any 
        additional data that a specific interpolation type may need. The
        `__call__()` method also takes a reference to the list-like object
        containing the Events, so any data all the way back to the Dataset
        itself is available.
    """
    def __init__(self, *args, **kwargs):
        pass
    
    def __call__(self, v1, v2, percent):
        raise NotImplementedError("Interpolation is an abstract base class")


class Lerp(Interpolation):
    """ A simple linear interpolation between two values.
    """
    def __call__(self, events, idx1, idx2, percent):
#         print events, idx1, idx2, percent
        percent += 0.0
        v1 = events[idx1][-1]
        v2 = events[idx2][-1]
        return v1 + (percent * (v2 - v1))

    
class MultiLerp(Lerp):
    """ Simple linear interpolation for compound values (e.g. the
        combined axes from an accelerometer).
    """
    def __call__(self, events, idx1, idx2, percent):
        v1 = events[idx1][-1]
        v2 = events[idx2][-1]
        result = v1[:]
        for i in xrange(len(v1)):
            result[i] += percent * (v2[i] - v1[i])
        return result


#===============================================================================
# Mix-In Classes
#===============================================================================

class Cascading(object):
    """ A base/mix-in class for objects in a hierarchy. 
    """

    parent = None
    name = ""

    def getAttribute(self, attname, default=NotImplemented, 
                     last=None, ignore=(None,)):
        """ Retrieve an object's attribute. If it doesn't have the attribute
            (or the attribute is equal to `ignore`), the request is sent to
            the object's parent.
            
            @param attname: The name of the attribute
            @keyword default: A default value to return if the attribute
                isn't found. If a default is not supplied, an 
                `AttributeError` is raised at the end of the chain.
            @keyword last: The final object in the chain, to keep searches
                from crawling too far back.
            @keyword ignore: A set of values that will be treated as if
                the object does not have the attribute.
        """
        if hasattr(self, attname):
            v = getattr(self, attname, default)
            if v not in ignore:
                return self, v
        if self == last or self.parent is None:
            # A bit of a hack; NotImplemented is used as the default for
            # `default`, rather than complicate the method's argument handling.
            # the argument parsing.
            if default is NotImplemented:
                raise AttributeError("%r not found in chain ending with %r" % \
                                     (attname, self))
            return None, default
        
        return self.parent.getAttribute(attname, default, ignore)


    def path(self):
        """ Get the combined names of all the object's parents/grandparents.
        """
        if self.parent is None:
            return self.name
        p = self.parent.path()
        if p is None:
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


    def getTransforms(self, id_=None, _tlist=None):
        """ Get a list of all transforms applied to the data, from first (the
            lowest-level parent) to last (the transform, if any, on the
            object itself).
            
            Applicable only to objects also derived from `Transformable`.
        """
        _tlist = [] if _tlist is None else _tlist
        if getattr(self, "_transform", None) is not None:
            if isinstance(self._transform, Iterable) and id_ is not None:
                x = self._transform[id_]
            else:
                x = self._transform
            if x != Transform.null:
                _tlist.insert(0, x)
        if isinstance(self.parent, Cascading):
            subchannelId = getattr(self, "id", None)
            self.parent.getTransforms(subchannelId, _tlist)
        return _tlist


    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.path())
    
    
class Transformable(object):
    """ A mix-in class for objects that transform data (apply calibration,
        etc.), making it easy to turn the transformation on or off.
        
        @ivar transform: The transformation function/object
        @ivar raw: If `False`, the transform will not be applied to data.  
    """

    # The 'null' transforms applied if displaying raw data. 
    _rawTransforms = Transform.null, None

    def setTransform(self, transform):
        """ Set the transforming function/object. This does not change the
            value of `raw`, however; the new transform will not be applied
            unless it is `True`.
        """
        raw = getattr(self, '_raw', False)
        self.transform = transform
        # `None` can be applied via map, but not directly applied as a function.
        # itertools.imap() also handles None differently than normal map().
        if isinstance(transform, Iterable):
            # Channels have transforms for each subchannel. Build
            # non-transforms for them.
            self._rawTransforms = ((Transform.null,) * len(transform),
                                   (None,) * len(transform))
            self._transform = tuple([Transform.null if t is None \
                                     else t for t in transform])
        else:
            self._transform = Transform.null if self.transform is None \
                                else self.transform
        self._mapTransform = self.transform
        self._raw = raw

    @property
    def raw(self):
        """ If `True`, the transform will not be applied. """
        return getattr(self, '_raw', False)
 
    @raw.setter
    def raw(self, v):
        # Rather than use conditionals in loops, the transform object (or
        # function) gets changed. 
        self._raw = v == True
        if self._raw:
            self._transform, self._mapTransform = self._rawTransforms
        else:
            self._transform = self.transform
            self._mapTransform = self.transform


#===============================================================================
# 
#===============================================================================

class Dataset(Cascading):
    """ A collection of sensor data and associated configuration info. 
        Typically represents a single MIDE EMBL file.
        
        Dictionary attributes are all keyed by the relevant ID (sensor ID,
        channel ID, etc.).
        
        @ivar loading: Boolean; `True` if a file is loading (or has not yet been
            loaded).
        @ivar fileDamaged: Boolean; `True` if the file ended prematurely.
        @ivar loadCancelled: Boolean; `True` if the file loading was aborted 
            part way through.
        @ivar sessions: A list of individual Session objects in the data set.
            A valid file will have at least one, even if there are no 
            `Session` elements in the data.
        @ivar sensors: A dictionary of Sensors.
        @ivar channels: A dictionary of individual Sensor channels.
        @ivar plots: A dictionary of individual Plots, the modified output of
            a Channel (or even another plot).
        @ivar transforms: A dictionary of functions (or function-like objects)
            for adjusting/calibrating sensor data.
    """
        
    def __init__(self, stream, name=None, quiet=False):
        """ Constructor. 
            @param stream: A file-like stream object containing EBML data.
            @keyword name: An optional name for the Dataset. Defaults to the
                base name of the file (if applicable).
            @keyword quiet: If `True`, non-fatal errors (e.g. schema/file
                version mismatches) are suppressed. 
        """
        self.lastUtcTime = None
        self.sessions = []
        self.sensors = {}
        self.channels = {}
        self.plots = {}
        self.transforms = {}
        self.parent = None
        self.currentSession = None
        self.recorderInfo = {}
        
        self.useIndices = False
        
        self.fileDamaged = False
        self.loadCancelled = False
        self.loading = True
        self.ebmldoc = MideDocument(stream)
        self.filename = getattr(stream, "name", None)

        if name is None:
            if self.filename is not None:
                self.name = os.path.splitext(os.path.basename(self.filename))[0]
            else:
                self.name = ""
        else:
            self.name = name

        self.schemaVersion = util.getSchemaDocument().version
        if not quiet:
            if self.schemaVersion != self.ebmldoc.version:
                raise IOError("EBML schema version mismatch: file is %d, "
                              "library is %d" % (self.schemaVersion, 
                                                 self.ebmldoc.version))


    def addSession(self, startTime=None, endTime=None, utcStartTime=None):
        """ Create a new session, add it to the Dataset, and return it.
        """
        self.endSession()
        utcStartTime = self.lastUtcTime if utcStartTime is None else utcStartTime
        self.currentSession = Session(self, 
                                      sessionId=len(self.sessions), 
                                      startTime=startTime, 
                                      endTime=endTime,
                                      utcStartTime=utcStartTime)
        self.sessions.append(self.currentSession)


    def endSession(self):
        """ Set the current session's start/end times.
        """
        cs = self.currentSession
        if cs is not None:
            if cs.startTime is None:
                cs.startTime = cs.firstTime
            if cs.endTime is None:
                cs.endTime = cs.lastTime
                
            self.currentSession = None
        
    
    def addSensor(self, sensorId=None, name=None, sensorClass=None, 
                  traceData=None, transform=None):
        """ Create a new Sensor object, and add it to the dataset, and return
            it. If the given sensor ID already exists, the existing sensor is 
            returned instead. To modify a sensor or add a sensor object created 
            elsewhere, use `Dataset.sensors[sensorId]` directly. 
            
            @param sensorId: The ID of the new sensor.
            @keyword name: The new sensor's name
            @keyword sensorClass: An alternate (sub)class of sensor. Defaults
                to `None`, which creates a `Sensor`.
            @return: The new sensor
        """
        # `sensorId` is mandatory; it's a keyword argument to streamline import.
        if sensorId is None:
            raise TypeError("%s.addSensor() requires a sensorId" %
                            self.__class__.__name__)
            
        if sensorId in self.sensors:
            return self.sensors[sensorId]
        
        sensorClass = Sensor if sensorClass is None else sensorClass
        sensor = sensorClass(self,sensorId,name=name, transform=transform,
                             traceData=traceData)
        self.sensors[sensorId] = sensor
        return sensor


    def addTransform(self, transform):
        """ Add a transform (calibration, etc.) to the dataset. Various child
            objects will reference them by ID.
        """
        if transform.id is None:
            raise ValueError("Added transform did not have an ID")
        
        self.transforms[transform.id] = transform
        

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
        """ Get all plottable data sources: sensor SubChannels and/or Plots.
        
            @keyword subchannels: Include subchannels if `True`.
            @keyword plots: Include Plots if `True`.
            @keyword debug: If `False`, exclude debugging/diagnostic channels.
            @keyword sort: Sort the plots by name if `True`. 
        """
        result = []
        test = lambda x: debug or not x.name.startswith("DEBUG")
        if plots:
            result = [p for p in self.plots.values() if test(p)]
        if subchannels:
            for c in self.channels.itervalues():
                for i in xrange(len(c.subchannels)):
                    subc = c.getSubChannel(i)
                    if test(subc):
                        result.append(subc)
        if sort:
            result.sort(key=lambda x: x.name)
        return result
            
        
#===============================================================================
# 
#===============================================================================

class Session(object):
    """ A collection of data within a dataset, e.g. one test run. A Dataset is
        expected to contain one or more Sessions.
    """
    
    def __init__(self, dataset, sessionId=0, startTime=None, endTime=None,
                 utcStartTime=None):
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

#===============================================================================
# 
#===============================================================================

class Sensor(Cascading):
    """ One Sensor object. A Dataset contains at least one.
    """
    
    def __init__(self, dataset, sensorId, name=None, transform=None,
                  traceData=None):
        self.name = "Sensor%02d" if name is None else name
        self.dataset = dataset
        self.parent = dataset
        self.id = sensorId
        self.channels = {}
        self.traceData = traceData


    def addChannel(self, channelId=None, parser=None, **kwargs):
        """ Add a Channel to a Sensor. 
        
            @param channelId: An unique ID number for the channel.
            @param parser: The Channel's data parser
        """
        if channelId is None or parser is None:
            raise TypeError("addChannel() requires a channel ID")
        if parser is None:
            raise TypeError("addChannel() requires a parser")
        
        channelClass = kwargs.pop('channelClass', Channel)
        
        if channelId in self.channels:
            return self.channels[channelId]
        channel = channelClass(self, channelId, parser, **kwargs)
        self.channels[channelId] = channel
        self.dataset.channels[channelId] = channel
        return channel

    def __getitem__(self, idx):
        return self.channels[idx]

    @property
    def children(self):
        return self.channels.values()

#===============================================================================
# Channels
#===============================================================================

class Channel(Cascading, Transformable):
    """ Output from a Sensor, containing one or more SubChannels. A Sensor
        contains one or more Channels. SubChannels of a Channel can be
        accessed by index like a list or tuple.
        
        @ivar types: A tuple with the type of data in each of the Channel's
            Subchannels.
        @ivar displayRange: The possible ranges of each subchannel, dictated
            by the parser. Not necessarily the same as the range of actual
            values recorded in the file!
    """
    
    def __init__(self, sensor, channelId, parser, name=None, units=('',''), 
                 transform=None, displayRange=None, interpolators=None,
                 cache=False):
        """ Constructor.
        
            @param sensor: The parent sensor.
            @param channelId: The channel's ID, unique within the file.
            @param parser: The channel's EBML data parser.
            @keyword name: A custom name for this channel.
            @keyword units: The units measured in this channel, used if units
                are not explicitly indicated in the Channel's SubChannels.
            @keyword transform: A Transform object for adjusting sensor
                readings at the Channel level. 
        """
        self.id = channelId
        self.sensor = sensor
        self.parser = parser
        self.units = units
        self.parent = sensor
        self.dataset = sensor.dataset
        self.cache = cache
        
        if name is None:
            name = "%s:%02d" % (sensor.name, channelId) 
        self.name = name
        
        # Custom parsers will define `types`, otherwise generate it.
        self.types = getParserTypes(parser)
        self.displayRange = displayRange if displayRange is not None \
                            else getParserRanges(parser)
        
        self.hasDisplayRange = displayRange is not None
        
        # Channels have 1 or more subchannels
        self.subchannels = [None] * len(self.types)
        
        if interpolators is None:
            # Note: all interpolators will reference the same object by
            # default.
            interpolators = tuple([Lerp()] * len(self.types))
        self.interpolators = interpolators
        
        # A set of session EventLists. Populated dynamically with
        # each call to getSession(). 
        self.sessions = {}
        
        self.subsampleCount = [0,sys.maxint]

        if transform is None:
            transform = (None,) * len(self.subchannels)
        else:
            transform = [self.dataset.transforms.get(i, None) if isinstance(i, int) else i for i in transform]
            
        self.setTransform(transform)
        
        # Optimization. Memoization-like cache of the last block parsed.
        self._lastParsed = (None, None)


    @property
    def children(self):
        return list(iter(self))


    def __repr__(self):
        return '<%s 0x%02x: %r>' % (self.__class__.__name__, 
                                    self.id, self.path())


    def __getitem__(self, idx):
        return self.getSubChannel(idx)


    def __len__(self):
        return len(self.subchannels)

    
    def __iter__(self):
        for i in xrange(len(self)):
            yield self.getSubChannel(i)


    def addSubChannel(self, subchannelId=None, **kwargs):
        """ Create a new SubChannel of the Channel.
        """
        if subchannelId is None:
            raise TypeError("addSubChannel() requires a subchannelId")
        
        if subchannelId > len(self.subchannels):
            raise IndexError(
                "Channel's parser only generates %d subchannels" % \
                 len(self.subchannels))
        else:
            channelClass = kwargs.pop('channelClass', SubChannel)
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
            
            @param subchannelId: 
            @return: The SubChannel matching the given ID.
        """
        # If there is no SubChannel explicitly defined for a subchannel, 
        # dynamically generate one.
        if self.subchannels[subchannelId] is None:
            self.subchannels[subchannelId] = SubChannel(self, subchannelId)
        return self.subchannels[subchannelId]


    def getSession(self, sessionId=None):
        """ Retrieve a session 
        """
        if sessionId is None:
            session = self.dataset.lastSession
            sessionId = session.sessionId
        elif self.dataset.hasSession(sessionId):
            session = self.dataset.sessions[sessionId]
        else:
            raise KeyError("Dataset has no Session id=%r" % sessionId)
        return self.sessions.setdefault(sessionId, EventList(self, session))
    
    
    def parseBlock(self, block, start=0, end=-1, step=1, subchannel=None,
                   offset=None):
        """ Parse subsamples out of a data block. Used internally.
        
            @param block: The data block from which to parse subsamples.
            @keyword start: The first block index to retrieve.
            @keyword end: The last block index to retrieve.
            @keyword step: The number of steps between samples.
            @keyword subchannel: If supplied, return only the values for a 
                specific subchannel (i.e. the method is being called by a
                SubChannel).
            @keyword offset: An array of values to subtract from the data or
                `None`. Intended for use with mean removal.
            @return: A list of tuples, one for each subsample.
        """
        # TODO: Cache this; a Channel's SubChannels will often be used together.

        p = (block, start, end, step, subchannel, str(offset))
        if self._lastParsed[0] == p:
            return self._lastParsed[1]
        result = list(block.parseWith(self.parser, start=start, end=end, 
                                    step=step, subchannel=subchannel))
        
        if offset is not None:
            if subchannel is not None:
                offset = offset[subchannel]
            result = [x-offset for x in result]
                
        self._lastParsed = (p, result)
        return result


    def parseBlockByIndex(self, block, indices, subchannel=None, offset=None):
        """ Convert raw data into a set of subchannel values, returning only
             specific items from the result by index.
            
            @param block: The data block element to parse.
            @param indices: A list of sample index numbers to retrieve.
            @keyword subchannel: If supplied, return only the values for a 
                specific subchannel
            @keyword offset: An array of values to subtract from the data or
                `None`. Intended for use with mean removal.
            @return: A list of tuples, one for each subsample.
        """
        if offset is not None:
            if subchannel is not None:
                offset = offset[subchannel]
            return [x-offset for x in block.parseByIndexWith(self.parser, 
                                      indices, subchannel=subchannel)]
        else:
            return list(block.parseByIndexWith(self.parser, indices, 
                                               subchannel=subchannel))

#===============================================================================

class SubChannel(Channel):
    """ Output from a sensor, derived from a channel containing multiple
        pieces of data (e.g. the Y from an accelerometer's XYZ). Looks
        like a 'real' channel.
    """
    
    def __init__(self, parent, subChannelId, name=None, units=('',''), 
                 transform=None, displayRange=None):
        """ Constructor.
        """
        self.id = subChannelId
        self.parent = parent
        self.cache = self.parent.cache
        if name is None:
            self.name = "%s:%02d" % (parent.name, subChannelId)
        else:
            self.name = name
        self.units = units
    
        self.dataset = parent.dataset
        self.sensor = parent.sensor
        self.types = (parent.types[subChannelId], )
        self.interpolators = (parent.interpolators[subChannelId], )
        
        self._sessions = None
        
        transform = self.dataset.transforms.get(transform, None) \
            if isinstance(transform, Number) else transform
        self.setTransform(transform)
        
        if displayRange is None:
            self.displayRange = self.parent.displayRange[self.id]
            self.hasDisplayRange = self.parent.hasDisplayRange
        else:
            self.hasDisplayRange = True
            self.displayRange = displayRange
            
        self.removeMean = False
            

    @property
    def children(self):
        return []


    def __repr__(self):
        return '<%s 0x%02x.%x: %r>' % (self.__class__.__name__, 
                                       self.parent.id, self.id, self.path())


    @property
    def parser(self):
        return self.parent.parser


    @property
    def sessions(self):
        # TODO: Caching the parent's sessions may cause trouble with dynamic loading
        if self._sessions is None:
            for s in self.parent.sessions:
                self._sessions[s] = self.getSession(s)
        return self._sessions
    

    def parseBlock(self, block, start=0, end=-1, step=1, offset=None):
        """ Parse subsamples out of a data block. Used internally.
        
            @param block: The data block from which to parse subsamples.
            @keyword start: The first block index to retrieve.
            @keyword end: The last block index to retrieve.
            @keyword step: The number of steps between samples.
            @keyword offset: An array of values to subtract from the data or
                `None`. Intended for use with mean removal. Note: this is
                always an array of values, not just the offset for a 
                specific subchannel.
        """
        return self.parent.parseBlock(block, start, end, step=step, 
                                      subchannel=self.id, offset=offset)


    def parseBlockByIndex(self, block, indices, offset=None):
        """ Parse specific subsamples out of a data block. Used internally.
        
            @param block: The data block from which to parse subsamples.
            @param indices: A list of individual index numbers to get.
            @keyword offset: An array of values to subtract from the data or
                `None`. Intended for use with mean removal. Note: this is
                always an array of values, not just the offset for a 
                specific subchannel.
        """
        return self.parent.parseBlockByIndex(block, indices, subchannel=self.id,
                                             offset=offset)

    
        
    def getSession(self, sessionId=None):
        """ Retrieve a session by ID. If none is provided, the last session in
            the Dataset is returned.
        """
        if self._sessions is None:
            self._sessions = {}
        elif sessionId in self._sessions:
            return self._sessions[sessionId]
        el = self.parent.getSession(sessionId).copy(self)
        sessionId = el.session.sessionId
        self._sessions[sessionId] = el
        return el
    
    
    def addSubChannel(self, *args, **kwargs):
        raise NotImplementedError("SubChannels have no SubChannels")


    def getSubChannel(self, *args, **kwargs):
        raise NotImplementedError("SubChannels have no SubChannels")


#===============================================================================
# 
#===============================================================================

class EventList(Cascading):
    """ A list-like object containing discrete time/value pairs. Data is 
        dynamically read from the underlying EBML file. 
        
        @todo: Consider a subclass optimized for non-subsampled data (i.e. 
            one sample per data block).
    """

    DEFAULT_MEAN_SPAN = 5000000

    def __init__(self, parent, session=None):
        self.parent = parent
        self.session = session
        self._data = []
        self._length = 0
        self.dataset = parent.dataset
        self.hasSubchannels = len(self.parent.types) > 1
        self._firstTime = self._lastTime = None

        # Optimization: Keep track of indices in blocks (per 10000)
        # The first is the earliest block with the index,
        # The second is the latest block.
        if self.hasSubchannels or not isinstance(parent.parent, Channel):
            self._blockIdxTable = ({},{})
#             self._blockTimeTable = ({},{})
            self._blockIdxTableSize = None
#             self._blockTimeTableSize = None
        else:
            s = self.session.sessionId if session is not None else None
            ps = parent.parent.getSession(s)
            self._blockIdxTable = ps._blockIdxTable
#             self._blockTimeTable = ps._blockTimeTable
            self._blockIdxTableSize = ps._blockIdxTableSize
#             self._blockTimeTableSize = ps._blockTimeTableSize
        
        self._hasSubsamples = False
        
        self.hasDisplayRange = self.parent.hasDisplayRange
        self.displayRange = self.parent.displayRange

        self.removeMean = False
        self.hasMinMeanMax = False
        self.rollingMeanSpan = self.DEFAULT_MEAN_SPAN
        

    @property
    def units(self):
        return self.parent.units


    def path(self):
        return "%s, %s" % (self.parent.path(), self.session.sessionId)


    def copy(self, newParent=None):
        """ Create a shallow copy of the event list.
        """
        parent = self.parent if newParent is None else newParent
        newList = EventList(parent, self.session)
        newList._data = self._data
        newList._length = self._length
        newList.dataset = self.dataset
        newList.hasMinMeanMax = self.hasMinMeanMax
        newList.removeMean = self.removeMean
        return newList
    

    def append(self, block):
        """ Add one data block's contents to the Sensor's list of data.
            Note that this doesn't double-check the channel ID specified in
            the data, but it is inadvisable to include data from different
            channels.
            
            @attention: Added elements should be in chronological order!
        """
        block.cache = self.parent.cache
        oldLength = self._length
        if block.numSamples is None:
            block.numSamples = block.getNumSamples(self.parent.parser)
        block.blockIndex = len(self._data)
        self._data.append(block)
        self._length += block.numSamples
        block.indexRange = (oldLength, self._length - 1)

        # Set the session first/last times if they aren't already set.
        # Possibly redundant if all sessions are 'closed.'
        if self.session.firstTime is None:
            self.session.firstTime = block.startTime
        if self.session.lastTime is None:
            self.session.lastTime = block.endTime
        else:
            self.session.lastTime = max(self.session.lastTime, block.endTime)
            
        # Cache the index range for faster searching
        if self._blockIdxTableSize is None:
            self._blockIdxTableSize = block.numSamples * 10
#             self._blockTimeTableSize = self._blockIdxTableSize * 10
        tableIdx = block.indexRange[0] / self._blockIdxTableSize
#         tableTime = block.startTime / self._blockTimeTableSize
        self._blockIdxTable[0].setdefault(tableIdx, block.blockIndex)
        self._blockIdxTable[1][tableIdx] = block.blockIndex
#         self._blockTimeTable[0].setdefault(tableTime, block.blockIndex)
#         self._blockTimeTable[1][tableTime] = block.blockIndex
        
        self._hasSubsamples = self._hasSubsamples or block.numSamples > 1
        
        if block.minMeanMax is not None:
            block.parseMinMeanMax(self.parent.parser)
            self.hasMinMeanMax = True
        else:
            self.hasMinMeanMax = False
        
    
    def getInterval(self):
        """ Get the first and last event times in the set.
        """
        if len(self._data) == 0:
            return None
        if self._firstTime is None:
            self._firstTime = self[0][-2]
#             self._firstTime = self._getBlockTimeRange(0)[0]
        if self._lastTime is None:
            self._lastTime = self[-1][-2]
#             self._lastTime = self._getBlockTimeRange(-1)[1]
        return self._firstTime, self._lastTime
    

    def _getBlockIndexRange(self, blockIdx):
        """ Get the first and last index of the subsamples within a block,
            as if the channel were just a flat list of subsamples.
        """
        block = self._data[blockIdx]
        # EventList.append() should set block.indexRange. In case it didn't:
        if block.indexRange is None:
            total = 0
            for i in xrange(blockIdx+1):
                if self._data[i].indexRange is None:
                    numSamples = block.getNumSamples(self.parent.parser)
                    self._data[i].indexRange = (total, total+numSamples-1)
                    total += numSamples 
        return block.indexRange
            

    def _getBlockTimeRange(self, blockIdx):
        """ Get the start and end times of an individual data block.
            Note that this takes an index, not a reference to the actual
            element itself!

            @param blockIdx: The index of the block to check.
            @return: A tuple with the blocks start and end times.
        """
        if blockIdx < 0:
            blockIdx += len(self._data)
        block = self._data[blockIdx]
        if block.endTime is None:
            # Probably a SimpleChannelDataBlock, which doesn't record end.
            if len(self._data) == 1:
                # Can't compute without another block's start.
                # Don't cache; another thread may still be loading document
                # TODO: Have sensor description provide nominal sample rate?
                return block.startTime, None
            
            if block.numSamples <= 1:
                block.endTime = block.startTime + self._getBlockSampleTime(blockIdx)
                return block.startTime, block.endTime

            if blockIdx < len(self._data)-1:
                block.endTime = self._data[blockIdx+1].startTime - \
                                self._getBlockSampleTime(blockIdx)
            else:
                block.endTime = block.startTime + \
                                (block.getNumSamples(self.parent.parser)-1) * \
                                self._getBlockSampleTime(blockIdx)
        return block.startTime, block.endTime


    def _searchBlockRanges(self, val, rangeGetter, start=0, stop=-1):
        """ Find the index of a block that (potentially) contains a subsample
            with the given value, computed with the given function. 
            
            @param val: The value to find
            @param rangeGetter: A function that returns a minimum and 
                maximum value for an element (such as `_getBlockTimeRange`)
            @return: The index of the found block.
        """
        # Quick and dirty binary search.
        # TODO: Handle un-found values better (use of `stop` can make these)
        def getIdx(first, last):
            middle = first + ((last-first)/2)
            r = rangeGetter(middle)
            if val >= r[0] and val <= r[1]:
                return middle
            elif middle == first:
                return last
            elif val < r[0]:
                return getIdx(first, middle)
            else:
                return getIdx(middle,last)

        start = len(self._data) + start if start < 0 else start
        stop = len(self._data) + stop if stop < 0 else stop
                
        return getIdx(start, stop)

    
    def _getBlockIndexWithIndex(self, idx, start=0, stop=-1):
        """ Get the index of a raw data block that contains the given event
            index.
            
            @param idx: The event index to find
            @keyword start: The first block index to search
            @keyword stop: The last block index to search
        """
        # Optimization: Set a reasonable start and stop for search
        if self._blockIdxTableSize is not None:
            tableIdx = idx/self._blockIdxTableSize
            if stop == -1:
                stop = self._blockIdxTable[1].get(tableIdx, -2) + 1                
            if start == 0:
                start = max(self._blockIdxTable[0].get(tableIdx, 0)-1, 0)

        return self._searchBlockRanges(idx, self._getBlockIndexRange,
                                       start, stop)


    def _getBlockIndexWithTime(self, t, start=0, stop=-1):
        """ Get the index of a raw data block in which the given time occurs.
        
            @param t: The time to find
            @keyword start: The first block index to search
            @keyword stop: The last block index to search
        """
#         tableTime = t / self._blockTimeTableSize
#         if stop == -1:
#             stop = self._blockTimeTable[1].get(tableTime, -2) + 1                
#         if start == 0:
#             start = max(self._blockTimeTable[0].get(tableTime, 0)-1, 0)
            
        return self._searchBlockRanges(t, self._getBlockTimeRange,
                                       start, stop)
        

    def _getBlockRollingMean(self, blockIdx):
        """ Get the mean of a block and its neighbors within a given time span.
            Note: Values are taken pre-calibration, and all subchannels are
            returned.
            
            @param blockIdx: The index of the block to check.
            @return: An array containing the mean values of each subchannel. 
        """
        if self.removeMean is False:
            return None
        
        block = self._data[blockIdx]
        
        if block.minMeanMax is None:
            return None
        
        span = self.rollingMeanSpan
        
        if block._rollingMean is not None and block._rollingMeanSpan == span and block._rollingMeanLen == len(self._data):
            return block._rollingMean
        
        if span != -1:
            firstBlock = self._getBlockIndexWithTime(block.startTime - (span/2), 
                                                     stop=blockIdx)
            lastBlock = self._getBlockIndexWithTime(block.startTime + (span/2), 
                                                    start=blockIdx)
            lastBlock = max(lastBlock+1, firstBlock+1)
        else:
            firstBlock = lastBlock = None
        
#         block._rollingMean = numpy.mean(
#                         [b.mean for b in self._data[firstBlock:lastBlock]], 0)
        # NOTE: TESTING; CHANGE BACK MAYBE
        block._rollingMean = numpy.median(
                        [b.mean for b in self._data[firstBlock:lastBlock]], 0)
        block._rollingMeanSpan = span
        block._rollingMeanLen = len(self._data)
        return block._rollingMean
    

    def __getitem__(self, idx):
        """ Get a specific data point by index.
        
            @param idx: An index, a `slice`, or a tuple of one or both
            @return: For single results, a tuple containing (time, value).
                For multiple results, a list of (time, value) tuples.
        """
        # TODO: Cache this; a Channel's SubChannels will often be used together.
        if isinstance(idx, Iterable):
            result = []
            for t in idx:
                v = self[t]
                if isinstance(v, list):
                    result.extend(v)
                else:
                    result.append(v)
            return result
        
        if isinstance(idx, slice):
            return list(self.iterSlice(idx.start, idx.stop, idx.step))
        
        if idx >= len(self):
            raise IndexError("EventList index out of range")
        
        if idx < 0:
            idx = max(0, len(self) + idx)
        
        blockIdx = self._getBlockIndexWithIndex(idx)
        subIdx = idx - self._getBlockIndexRange(blockIdx)[0]
        
        block = self._data[blockIdx]
        
        timestamp = block.startTime + self._getBlockSampleTime(blockIdx) * subIdx
        value = self.parent.parseBlock(block, start=subIdx, end=subIdx+1,
                                       offset=self._getBlockRollingMean(blockIdx))[0]
        
        if self.hasSubchannels:
            event=tuple(c._transform(f((timestamp,v),self.session)) for f,c,v in izip(self.parent._transform, self.parent.subchannels, value))
            event=(event[0][0], tuple((e[1] for e in event)))
        else:
            event=self.parent._transform(self.parent.parent._transform[self.parent.id]((timestamp, value),self.session))
        
        if self.dataset.useIndices:
            return Event(idx, event[0], event[1])
        
        return event


    def __iter__(self):
        """ Iterator for the EventList. WAY faster than getting individual
            events.
        """
        return self.iterSlice()
                

    def __len__(self):
        """ x.__len__() <==> len(x)
        """
        if len(self._data) == 0:
            return 0
        # For some reason, the cached self._length wasn't thread-safe.
#         return self._length
        return self._data[-1].indexRange[-1]-1


    def itervalues(self, start=0, end=-1, step=1, subchannels=True):
        """ Iterate all values in the list.
        """
        # TODO: Optimize; times don't need to be computed since they aren't used
        if self.hasSubchannels and subchannels != True:
            # Create a function instead of chewing the subchannels every time
            fun = eval("lambda x: (%s)" % \
                       ",".join([("x[%d]" % c) for c in subchannels]))
            for v in self.iterSlice(start, end, step):
                yield fun(v[-1])
        else:
            for v in self.iterSlice(start, end, step):
                yield v[-1]
        

    def iterSlice(self, start=0, end=-1, step=1):
        """ Create an iterator producing events for a range indices.
        """
        if isinstance (start, slice):
            step = start.step
            end = start.stop
            start = start.start
        
        if start is None:
            start = 0
        elif start < 0:
            start += len(self)
            
        if end is None:
            end = len(self)
        elif end < 0:
            end += len(self) + 1
        else:
            end = min(end, len(self))
        
        if step is None:
            step = 1
        
        startBlockIdx = self._getBlockIndexWithIndex(start) if start > 0 else 0
        endBlockIdx = self._getBlockIndexWithIndex(end-1, start=startBlockIdx)

        blockStep = max(1, (step + 0.0) / self._data[startBlockIdx].numSamples)
        numBlocks = int((endBlockIdx - startBlockIdx) / blockStep)+1
        
        subIdx = start - self._getBlockIndexRange(startBlockIdx)[0]
        endSubIdx = end - self._getBlockIndexRange(endBlockIdx)[0]

        # in each block, the next subIdx is (step+subIdx)%numSamples
        for i in xrange(numBlocks):
            blockIdx = int(startBlockIdx + (i * blockStep))
            block = self._data[blockIdx]
            sampleTime = self._getBlockSampleTime(i)
            lastSubIdx = endSubIdx if blockIdx == endBlockIdx else block.numSamples
            times = (block.startTime + sampleTime * t for t in xrange(subIdx, lastSubIdx, step))
            values = self.parent.parseBlock(block, start=subIdx, end=lastSubIdx, 
                                            step=step, offset=self._getBlockRollingMean(blockIdx))

            for event in izip(times, values):
                if self.hasSubchannels:
                    # TODO: Refactor this ugliness
                    # This is some nasty stuff to apply nested transforms
                    event=[c._transform(f((event[-2],v),self.session), self.session) for f,c,v in izip(self.parent._transform, self.parent.subchannels, event[-1])]
                    event=(event[0][0], tuple((e[1] for e in event)))
                else:
                    event = self.parent._transform(self.parent.parent._transform[self.parent.id](event, self.session))
                yield event
            subIdx = (lastSubIdx-1+step) % block.numSamples


    def iterJitterySlice(self, start=0, end=-1, step=1, jitter=0.5):
        """ Create an iterator producing events for a range indices.
        """
        if start is None:
            start = 0
        elif start < 0:
            start += len(self)
            
        if end is None:
            end = len(self)
        elif end < 0:
            end += len(self) + 1
        else:
            end = min(end, len(self))
        
        if step is None:
            step = 1
        
        startBlockIdx = self._getBlockIndexWithIndex(start) if start > 0 else 0
        endBlockIdx = self._getBlockIndexWithIndex(end-1, start=startBlockIdx)

        blockStep = max(1, (step + 0.0) / self._data[startBlockIdx].numSamples)
        numBlocks = int((endBlockIdx - startBlockIdx) / blockStep)+1
        
        subIdx = start - self._getBlockIndexRange(startBlockIdx)[0]
        endSubIdx = end - self._getBlockIndexRange(endBlockIdx)[0]
        
        # in each block, the next subIdx is (step+subIdx)%numSamples
        for i in xrange(numBlocks):
            blockIdx = int(startBlockIdx + (i * blockStep))
            block = self._data[blockIdx]
            sampleTime = self._getBlockSampleTime(i)
            lastSubIdx = endSubIdx if blockIdx == endBlockIdx else block.numSamples
            
            indices = range(subIdx, lastSubIdx, step)
            if step > 1:
                for x in xrange(2, len(indices)-1):
#                     indices[x] = random.randint(indices[x-1],indices[x+1])
                    indices[x] = int(indices[x] + (((random.random()*2)-1) * jitter * step))
                
            times = (block.startTime + sampleTime * t for t in indices)
            values = self.parent.parseBlockByIndex(block, indices, 
                                                   self._getBlockRollingMean(blockIdx))
            
            for event in izip(times, values):
                if self.hasSubchannels:
                    # TODO: (post Transform fix) Refactor later
                    event=[f((event[-2],v), self.session) for f,v in izip(self.parent._transform, event[-1])]
                    event=(event[0][0], tuple((e[1] for e in event)))
                else:
                    event = self.parent._transform(self.parent.parent._transform[self.parent.id](event, self.session), self.session)
                yield event
            subIdx = (lastSubIdx-1+step) % block.numSamples

      
    def getEventIndexBefore(self, t):
        """ Get the index of an event occurring on or immediately before the
            specified time.
        
            @param t: The time (in microseconds)
            @return: The index of the event preceding the given time, -1 if
                the time occurs before the first event.
        """
        if t <= self._data[0].startTime:
            return -1
        blockIdx = self._getBlockIndexWithTime(t)
        block = self._data[blockIdx]
        return int(block.indexRange[0] + \
                   ((t - block.startTime) / self._getBlockSampleTime(blockIdx)))
        
 
    def getEventIndexNear(self, t):
        """ The the event occurring closest to a specific time. 
        
            @param t: The time (in microseconds)
            @return: 
        """
        if t <= self._data[0].startTime:
            return 0
        idx = self.getEventIndexBefore(t)
        events = self[idx:idx+2]
        if events[0][-2] == t or len(events) == 1:
            return idx
        if t - events[0][-2] < events[1][-2] - t:
            return idx+1
        return idx


    def getRangeIndices(self, startTime, endTime):
        """ Get the first and last event indices that fall within the 
            specified interval.
            
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
        """
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
            endIdx = self.getEventIndexBefore(endTime)
#             endBlockIdx = self._getBlockIndexWithTime(endTime)#, start=startBlockIdx) 
#             if endBlockIdx > 0:
#                 endBlock = self._data[endBlockIdx]
#                 if endBlockIdx < len(self._data) - 1:
#                     endIdx = self._data[endBlockIdx+1].indexRange[0] - 1
#                 else:
#                     endIdx = int(endBlock.indexRange[0] + ((endTime - endBlock.startTime) / self._getBlockSampleTime(endBlockIdx) + 0.0) - 1)
#             else:
#                 endIdx = 0
        return startIdx, endIdx
    

    def getRange(self, startTime=None, endTime=None):
        """ Get a set of data occurring in a given interval.
        
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
        """
        return list(self.iterRange(startTime, endTime))


    def iterRange(self, startTime=None, endTime=None, step=1):
        """ Get a set of data occurring in a given interval.
        
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
        """
        startIdx, endIdx = self.getRangeIndices(startTime, endTime)
        return self.iterSlice(startIdx,endIdx,step)        


    def iterMinMeanMax(self, startTime=None, endTime=None, padding=0,
                       times=True):
        """ Get the minimum, mean, and maximum values for blocks within a
            specified interval.
            
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
            @return: An iterator producing sets of three events (min, mean, 
                and max, respectively).
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
        
        for block in self._data[startBlockIdx:endBlockIdx]:
            if block.minMeanMax is None:
                continue
            t = block.startTime
#             if block.endTime is not None:
#                 t = (t + block.endTime)/2
            m = self._getBlockRollingMean(block.blockIndex)
            result = []
            for val in (block.min, block.mean, block.max):
                if m is not None:
                    val -= m
                if self.hasSubchannels:
                    event=[f((t,v), self.session) for f,v in izip(self.parent._transform, val)]
                    event=(event[0][0], tuple((e[1] for e in event)))
                else:
                    val = val[self.parent.id]
                    event = self.parent._transform(self.parent.parent._transform[self.parent.id]((t,val), self.session), self.session)
                if not times:
                    event = event[-1]
                result.append(event)
            
            yield result
    
    
    def getMinMeanMax(self, startTime=None, endTime=None, padding=0,
                      times=True):
        """ Get the minimum, mean, and maximum values for blocks within a
            specified interval.
            
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
            @return: A list of sets of three events (min, mean, and max, 
                respectively).
        """
        return list(self.iterMinMeanMax(startTime, endTime, padding, times))
    
    
    def getRangeMinMeanMax(self, startTime=None, endTime=None, subchannel=None):
        """ Get the single minimum, mean, and maximum value for blocks within a
            specified interval. Note: Using this with a parent channel without
            specifying a subchannel number can produce meaningless data if the
            channels use different units or are on different scales.
            
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
            @keyword subchannel: The subchannel ID to retrieve, if the
                EventList's parent has subchannels.
            @return: A set of three events (min, mean, and max, respectively).
        """
        mmm = numpy.array(self.getMinMeanMax(startTime, endTime, times=False))
        if self.hasSubchannels and subchannel is not None:
            return (mmm[:,0,subchannel].min(), 
                    mmm[:,1,subchannel].mean(), 
                    mmm[:,1,subchannel].mean(), 
                    mmm[:,2,subchannel].max())
#         return (mmm[:,0].min(), mmm[:,1].mean(), mmm[:,2].max())
        # NOTE: TESTING
        return (mmm[:,0].min(), numpy.median(mmm[:,1]), mmm[:,2].max())
        
        

    def _getBlockSampleTime(self, blockIdx=0):
        """ Get the time between samples within a given data block.
            
            @keyword blockIdx: The index of the block to measure. Times
                within the same block are expected to be consistent, but can
                possibly vary from block to block.
            @return: The sample rate, as samples per second
        """

        if len(self._data) == 0:
            # Channel has no events. Probably shouldn't happen.
            # TODO: Get the sample rate from another session?
            return -1
        
        if blockIdx < 0:
            blockIdx += len(self._data)
        
        # See if it's already been computed
        block = self._data[blockIdx]
        if block.sampleTime is not None:
            return block.sampleTime
        
        # See if the parent has the attribute defined
        sampleTime = self.getAttribute('_sampleTime', None)[1]
        if sampleTime is not None:
            return sampleTime
        
        startTime = block.startTime
        endTime = block.endTime

        if endTime is None:
            if len(self._data) == 1:
                # Only one block; can't compute from that!
                raise NotImplementedError("TODO: Implement getting sample rate in case of single block")
            elif blockIdx == len(self._data) - 1:
                # Last block; use previous.
                startTime = self._data[blockIdx-1].startTime
                endTime = block.startTime
            else:
                endTime = self._data[blockIdx+1].startTime
            block.endTime = endTime
        
        numSamples = block.getNumSamples(self.parent.parser)
        if numSamples == 0:
            # No data in block
            raise NotImplementedError("TODO: Implement getting sample rate in case of empty block")

        block.sampleTime = (endTime - startTime) / (numSamples)
        
        return block.sampleTime


    def _getBlockSampleRate(self, blockIdx=0):
        """ Get the channel's sample rate. This is either supplied as part of
            the channel definition or calculated from the actual data and
            cached.
            
            @keyword blockIdx: The block to check. Optional, because in an
                ideal world, all blocks would be the same.
            @return: The sample rate, as samples per second (float)
        """
        if self._data[blockIdx].sampleRate is None:
            self._data[blockIdx].sampleRate = 1000000.0 / self._getBlockSampleTime(blockIdx)
        return self._data[blockIdx].sampleRate


    def getSampleTime(self, idx=0):
        """ Get the time between samples.
            
            @keyword idx: Because it is possible for sample rates to vary
                within a channel, an event index can be specified; the time
                between samples for that event and its siblings will be 
                returned.
            @return: The time between samples (us)
        """
        return self._getBlockSampleTime(self._getBlockIndexWithIndex(idx))
    
    
    def getSampleRate(self, idx=0):
        """ Get the channel's sample rate. This is either supplied as part of
            the channel definition or calculated from the actual data and
            cached.
            
            @keyword idx: Because it is possible for sample rates to vary
                within a channel, an event index can be specified; the sample
                rate for that event and its siblings will be returned.
            @return: The sample rate, as samples per second (float)
        """
        return self._getBlockSampleRate(self._getBlockIndexWithIndex(idx))
    

    def getValueAt(self, at, outOfRange=False):
        """ Retrieve the value at a specific time, interpolating between
            existing events.
            
            @param at: The time at which to take the sample.
            @keyword outOfRange: If `False`, times before the first sample
                or after the last will raise an `IndexError`. If `True`, the
                first or last time, respectively, is returned.
        """
        startIdx = self.getEventIndexBefore(at)
        if startIdx < 0:
            if self[0][-2] == at:
                return self[0]
            # TODO: How best to handle times before first event?
            if outOfRange:
                return self[0]
            raise IndexError("Specified time occurs before first event (%d)" % self[0][-2])
        elif startIdx >= len(self) - 1:
            if self[-1][-2] == at:
                return self[-1]
            if outOfRange:
                return self[-1]
            # TODO How best to handle times after last event?
            raise IndexError("Specified time occurs after last event (%d)" % self[startIdx][-2])
        
        startEvt, endEvt = self[startIdx:startIdx+2]
        relAt = at - startEvt[-2]
        endTime = endEvt[-2] - startEvt[-2] + 0.0
        percent = relAt/endTime
        if self.hasSubchannels:
            result = startEvt[-1][:]
            for i in xrange(len(self.parent.types)):
                result[i] = self.parent.interpolators[i](self, startIdx, startIdx+1, percent)
                result[i] = self.parent.types[i](result[i])
        else:
            result = self.parent.types[0](self.parent.interpolators[0](self, startIdx, startIdx+1, percent))
        if self.dataset.useIndices:
            return None, at, result
        return at, result
    

    def iterResampledRange(self, startTime, stopTime, maxPoints, padding=0,
                           jitter=0):
        """ Retrieve the events occurring within a given interval,
            undersampled as to not exceed a given length (e.g. the size of
            the data viewer's screen width).
        
            XXX: EXPERIMENTAL!
            Not very efficient, particularly not with single-sample blocks.
        """
        startIdx, stopIdx = self.getRangeIndices(startTime, stopTime)
        numPoints = (stopIdx - startIdx)
        startIdx = max(startIdx-padding, 0)
        stopIdx = min(stopIdx+padding, len(self))
        step = max(int(numPoints / maxPoints),1)
        if jitter != 0:
            return self.iterJitterySlice(startIdx, stopIdx, step, jitter)
        return self.iterSlice(startIdx, stopIdx, step)
        



    def exportCsv(self, stream, start=0, stop=-1, step=1, subchannels=True,
                  callback=None, callbackInterval=0.01, timeScalar=1,
                  raiseExceptions=False, dataFormat="%.6f", useUtcTime=False,
                  useIsoFormat=False, headers=False, removeMean=None,
                  meanSpan=None):
        """ Export events as CSV to a stream (e.g. a file).
        
            @param stream: The stream object to which to write CSV data.
            @keyword start: The first event index to export.
            @keyword stop: The last event index to export.
            @keyword step: The number of events between exported lines.
            @keyword subchannels: A sequence of individual subchannel numbers
                to export. Only applicable to objects with subchannels.
                `True` (default) exports them all.
            @keyword callback: A function (or function-like object) to notify
                as work is done. It should take four keyword arguments:
                `count` (the current line number), `total` (the total number
                of lines), `error` (an exception, if raised during the
                export), and `done` (will be `True` when the export is
                complete). If the callback object has a `cancelled`
                attribute that is `True`, the CSV export will be aborted.
                The default callback is `None` (nothing will be notified).
            @keyword callbackInterval: The frequency of update, as a
                normalized percent of the total lines to export.
            @keyword timeScalar: A scaling factor for the even times.
                The default is 1 (microseconds).
            @keyword raiseExceptions: 
            @keyword dataFormat: The number of decimal places to use for the
                data. This is the same format as used when formatting floats.
            @keyword useUtcTime: If `True`, times are written as the UTC
                timestamp. If `False`, times are relative to the recording.
            @keyword useIsoFormat: If `True`, the time column is written as
                the standard ISO date/time string. Only applies if `useUtcTime`
                is `True`.
            @return: The number of rows exported and the elapsed time.
        """
        # Dummy callback to be used if none is supplied
        def dummyCallback(*args, **kwargs): pass
        
        if callback is None:
            noCallback = True
            callback = dummyCallback
        else:
            noCallback = False
        
        if useUtcTime and self.session.utcStartTime:
            if useIsoFormat:
                timeFormatter = lambda x: datetime.utcfromtimestamp(x[-2] * timeScalar + self.session.utcStartTime).isoformat()
            else:
                timeFormatter = lambda x: dataFormat % (x[-2] * timeScalar + self.session.utcStartTime)
        else:
            timeFormatter = lambda x: dataFormat % (x[-2] * timeScalar)
        
        if self.hasSubchannels:
            if isinstance(subchannels, Iterable):
                fstr = '%s, ' + ', '.join([dataFormat] * len(subchannels))
                formatter = lambda x: fstr % ((timeFormatter(x),) + \
                                              tuple([x[-1][v] for v in subchannels]))
                names = [self.parent.subchannels[x].name for x in subchannels]
            else:
                fstr = '%s, ' + ', '.join([dataFormat] * len(self.parent.types))
                formatter = lambda x: fstr % ((timeFormatter(x),) + x[-1])
                names = [x.name for x in self.parent.subchannels]
        else:
            fstr = "%%s, %s" % dataFormat
            formatter = lambda x: fstr % (timeFormatter(x),x[-1])
            names = [self.parent.name]

        oldRemoveMean = self.removeMean
        oldMeanSpan = self.rollingMeanSpan
        if removeMean is not None:
            self.removeMean = removeMean
        if meanSpan is not None:
            self.rollingMeanSpan = meanSpan
        
        totalLines = (stop - start) / (step + 0.0)
        updateInt = int(totalLines * callbackInterval)
        
        start = start + len(self) if start < 0 else start
        stop = stop + len(self) if stop < 0 else stop
        
        t0 = datetime.now()
        if headers:
            stream.write('"Time",%s\n' % ','.join(['"%s"' % n for n in names]))
        try:
            for num, evt in enumerate(self.iterSlice(start, stop, step)):
                if getattr(callback, 'cancelled', False):
                    callback(done=True)
                    break
                stream.write("%s\n" % formatter(evt))
                if updateInt == 0 or num % updateInt == 0:
                    callback(num, total=totalLines)
                callback(done=True)
        except Exception as e:
            if raiseExceptions or noCallback:
                raise e
            else:
                callback(error=e)

        # Restore old removeMean        
        self.removeMean = oldRemoveMean
        self.rollingMeanSpan = oldMeanSpan
        return num+1, datetime.now() - t0

        
#===============================================================================
# 
#===============================================================================


class Plot(Transformable):
    """ A processed set of sensor data. These are typically the final form of
        the data. Transforms applied are intended to be for display purposes
        (e.g. converting data in foot-pounds to pascals).
    """
    
    def __init__(self, source, plotId, name=None, transform=None, units=None):
        self.source = source
        self.id = plotId
        self.session = source.session
        self.dataset = source.dataset
        self.name = source.path() if name is None else name
        self.units = source.units if units is None else units
        self.setTransform(transform)
    
    
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
        return imap(self._transform, self.source)
            
    def getEventIndexBefore(self, t):
        """
        """
        return self.source.getEventIndexBefore(t)
    
    def getEventIndexNear(self, t):
        """
        """
        return self.source.getEventIndexNear(t)

    def getRange(self, startTime, endTime):
        return map(self._mapTransform, self.source.getRange(startTime, endTime))
    
    def getSampleRate(self, idx=0):
        return self.source.getSampleRate(idx)
    
    def getSampleTime(self, idx=0):
        return self.source.getSampleTime(idx)
    
    def getValueAt(self, at):
        return self._transform(self.source.getValueAt(at))
    
    def iterRange(self, startTime, endTime):
        # Note: self._transform is used here instead of self._mapTransform;
        # itertools.imap(None, x) works differently than map(None,x)!
        return imap(self._transform, self.source.iterRange(startTime, endTime))
    
    def iterSlice(self, start=0, end=-1, step=1):
        # Note: self._transform is used here instead of self._mapTransform;
        # itertools.imap(None, x) works differently than map(None,x)!
        return imap(self._transform, self.source.iterSlice(start, end, step))
    

#===============================================================================

class CompositePlot(Plot):
    """ A set of processed data derived from multiple sources.
    """
    
    # TODO: Implement this!



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
        return "<%s (%s<%s<%s)>" % (self.__class__.__name__, self.low, 
                                    self.source.parent.name, self.high)
    
    def __init__(self, source, low=None, high=None):
        """
        """
        self.high = high
        self.low = low
        self.source = source
        self.valid = lambda x: x > low and x < high
        
        
    def getRange(self, start=None, end=None):
        """ Retrieve the invalid periods within a given range of events.
            
            @return: A list of invalid periods' [start, end] times.
        """
        if start is None:
            start = self.source[0][-2]
        if end is None:
            end = self.source[-1][-2]
            
        result = []
        v = self.getValueAt(start)
        if v is None:
            return result
        
        outOfRange =  v[-1] != True

        if outOfRange:
            result = [[start,start]]
        
        for t,v in self.source.iterRange(start, end):
            if self.valid(v):
                if outOfRange:
                    result[-1][1] = t
                    outOfRange = False
            else:
                if not outOfRange:
                    result.append([t,t])
                    outOfRange = True
        
        # Close out any open invalid range
        if outOfRange:
            result[-1][1] = -1 #end
        
        return result
    
    
    def getValueAt(self, at):
        """ Retrieve the value at a specific time. 
        """
        t = max(min(at, self.source[0][-2]),self.source[1][-2])
#         if at < self.source[0][-2] or at > self.source[-1][-2]:
#             return None
        val = self.source.getValueAt(t)
        return at, self.valid(val[-1])


#===============================================================================
# 
#===============================================================================

Iterable_register = getattr(Iterable, 'register')
Iterable_register(EventList)    
Iterable_register(WarningRange)