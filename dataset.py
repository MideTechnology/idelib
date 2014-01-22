'''
Created on Sep 26, 2013

@author: dstokes


@todo: Discontinuity handing. This will probably be conveyed as events with
    null values. An attribute/keyword may be needed to suppress this when 
    getting data for processing (FFT, etc.)
@todo: Look at places where lists are returned, consider using `yield` 
    instead (e.g. parseElement(), etc.)
@todo: Have Sensor.addChannel() possibly check the parser to see if the 
    blocks are single-sample, instantiate simpler Channel subclass
@todo: Further optimize EventList._searchBlockRanges() so that the binary
    search only occurs when absolutely necessary, or improve the
    start/end search range limiting hints. Possibly base a reasonable
    guess from the sample rate.
@todo: Decide if dataset.useIndices is worth it, remove it if it isn't.
    Removing it may save a trivial amount of time/memory (one fewer 
    conditional in event-getting methods).

'''


from collections import namedtuple, Iterable
from datetime import datetime
from itertools import imap, izip
import os.path
import sys

from ebml.schema.mide import MideDocument

from parsers import getParserTypes, getParserRanges

#===============================================================================
# 
#===============================================================================

__DEBUG__ = True

if __DEBUG__:
    import ebml
    print "*** Loaded python-ebml from", os.path.abspath(ebml.__file__)
    
#===============================================================================
# 
#===============================================================================

# A 'named tuple' class, mainly for debugging purposes.
Event = namedtuple("Event", ('index','time','value'))


#===============================================================================
# Calibration
#===============================================================================

class Transform(object):
    """ A function-like object representing any processing that an event
        requires, including basic calibration at the low level and 
        adjustments for display at the high level.
    """
    modifiesTime = False
    modifiesValue = False
    
    def __init__(self, *args, **kwargs):
        pass
    
    def __call__(self,  event, channel=None, session=None):
        if session is None:
            return event
        return event[0] + session.startTime, event[1]

    @classmethod
    def null(cls, *args, **kwargs):
        return args[0]



#===============================================================================
# 
#===============================================================================

class ConfidenceThreshold(object):
    """
    """
    def __init__(self, source, validRange):
        self.source = source
        self.range = validRange
        
    def getValueAt(self, t):
        """
        """
        

#===============================================================================
# 
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
        v1 = events[idx1][-1]
        v2 = events[idx2][-1]
        return v1 + percent * (v2 - v1)

    
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
# 
#===============================================================================

class Cascading(object):
    """ A base/mix-in class providing an acquisition chain of attributes; if
        one object doesn't have the attribute, the request is sent to the
        object's parent. 
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
            
            Applicable only to objects derived from `Transformable`.
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


    def setAllAttributes(self, attname, val, last=None):
        """
        """
        if hasattr(self, attname):
            setattr(self, attname, val)
        if self == last or self.parent is None:
            return
        self.parent.setAllAttributes(attname, val, last)
        

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.path())
    
    
#===============================================================================
# 
#===============================================================================

class Transformable(object):
    """ A mix-in class for objects that transform data, making it easy to turn
        it on or off.
        
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
            self._transform = tuple([Transform.null if t is None else t for t in transform])
        else:
            self._transform = Transform.null if self.transform is None else self.transform
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
            self._transform = tuple([Transform.null if t is None else t for t in self.transform])
            self._mapTransform = self.transform


#===============================================================================
# 
#===============================================================================

class Dataset(Cascading):
    """ A collection of sensor data and associated configuration info. 
        Typically represents a single MIDE EMBL file.
        
        Dictionary attributes are all keyed by the relevant ID (sensor ID,
        channel ID, et cetera).
        
        @ivar loading: `True` if a file is loading (or has not yet been
            loaded).
        @type loading: `bool`
        @ivar fileDamaged: `True` if the file ended prematurely.
        @type fileDamaged: `bool`
        @ivar loadCancelled: `True` if the file loading was aborted partway
            through.
        @type loadCancelled: `bool`
        @ivar sessions: A list of individual Session objects in the data set.
            A valid file will have at least one, even if there are no 
            `Session` elements in the data.
        @type sessions: `list`
        @ivar sensors: A dictionary of Sensors.
        @type sensors: `dict`
        @ivar channels: A dictionary of individual Sensor channels.
        @type channels: `dict`
        @ivar plots: A dictionary of individual Plots, the modified output of
            a Channel (or even another plot).
        @type plots: `dict`
        @ivar transforms: A dictionary of functions (or function-like objects)
            for adjusting/calibrating sensor data.
        @type transforms: `dict`
    """
        
    def __init__(self, stream, name=None):
        """
        """
        self.sessions = []
        self.sensors = {}
        self.channels = {}
        self.plots = {}
        self.transforms = {}
        self.parent = None
        self.currentSession = None
        
        self.useIndices = False
        
        self.fileDamaged = False
        self.loadCancelled = False
        self.loading = True
        self.ebmldoc = MideDocument(stream)
        self.filename = self.ebmldoc.stream.file.name

        if name is None:
            self.name = os.path.splitext(os.path.basename(self.filename))[0]
        else:
            self.name = name


    def addSession(self, startTime=None, endTime=None):
        """ Create a new session, add it to the Dataset, and return it.
        """
        self.endSession()
        self.currentSession = Session(self, 
                                      sessionId=len(self.sessions), 
                                      startTime=startTime, 
                                      endTime=endTime)
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
        
    
    def addSensor(self, sensorId, name=None, sensorClass=None):
        """ Create a new Sensor object, and add it to the dataset, and return
            it. To add a sensor object created elsewhere, use 
            `sensors[sensorId]` directly.
            
            @param sensorId: The ID of the new sensor
            @keyword name: The new sensor's name
            @keyword sensorClass: An alternate (sub)class of sensor. Defaults
                to `None`, which creates a `Sensor`.
            @return: The new sensor
        """
        if sensorId in self.sensors:
            return self.sensors[sensorId]
        sensorClass = Sensor if sensorClass is None else sensorClass
        sensor = sensorClass(self,sensorId,name=name)
        self.sensors[sensorId] = sensor
        return sensor


    def path(self):
        """
        """
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
        
    
    def getPlots(self, subchannels=True, plots=True):
        """ Get all plottable data: sensor subchannels and/or Plots.
        
            @keyword subchannels: Include subchannels if `True`.
            @keyword plots: Include Plots if `True`.
        """
        result = []
        if plots:
            result = self.plots.values()
        if subchannels:
            for c in self.channels.itervalues():
                for i in xrange(len(c.subchannels)):
                    result.append(c.getSubChannel(i))
        return result
            
        
#===============================================================================
# 
#===============================================================================

class Session(object):
    """ A collection of data within a dataset, e.g. one test run. A Dataset is
        expected to contain one or more Sessions.
    """
    
    def __init__(self, dataset, sessionId=0, startTime=None, endTime=None):
        self.dataset = dataset
        self.startTime = startTime
        self.endTime = endTime
        self.sessionId = sessionId
        
        # firstTime and lastTime are the actual last event time. These will
        # typically be the same as startTime and endTime, but not necessarily
        # so.
        self.firstTime = self.lastTime = None


#===============================================================================
# 
#===============================================================================

class Sensor(Cascading):
    """ One Sensor object. A Dataset contains at least one.
    """
    
    def __init__(self, dataset, sensorId, name=None):
        self.name = "Sensor%02d" if name is None else name
        self.dataset = dataset
        self.parent = dataset
        self.id = sensorId
        self.channels = {}


    def addChannel(self, channelId, parser, **kwargs):
        """ Add a Channel to a Sensor. 
        
            @param channelId: An unique ID number for the channel.
            @param parser: The Channel's data parser
        """
        if channelId in self.channels:
            return self.channels[channelId]
        channel = Channel(self, channelId, parser, **kwargs)
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
        @ivar possibleRange: The possible ranges of each subchannel, dictated
            by the parser. Not necessarily the same as the range of actual
            values recorded in the file!
    """
    
    def __init__(self, sensor, channelId, parser, name=None, units=('',''), 
                 calibration=None, interpolators=None):
        """ Constructor.
        
            @param sensor: The parent sensor.
            @param channelId: The channel's ID, unique within the file.
            @param parser: The channel's EBML data parser.
            @keyword name: A custom name for this channel.
            @keyword units: The units measured in this channel, used if units
                are not explicitly indicated in the Channel's SubChannels.
            @keyword calibration: A Transform object for adjusting sensor
                readings at the Channel level. 
        """
        self.id = channelId
        self.sensor = sensor
        self.parser = parser
        self.units = units
        self.parent = sensor
        self.dataset = sensor.dataset
        
        if name is None:
            name = "%s:%02d" % (sensor.name, channelId) 
        self.name = name
        
        # Custom parsers will define `types`, otherwise generate it.
        self.types = getParserTypes(parser)
        self.possibleRange = getParserRanges(parser)
        
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

        if calibration is None:
            calibration = (None,) * len(self.subchannels)
            
        self.setTransform(calibration)
        
        # Optimization. Memoization-like cache of the last block parsed.
        self._lastParsed = (None, None)


    @property
    def children(self):
        return list(iter(self))


    def __repr__(self):
        return '<%s 0x%02x: %r>' % (self.__class__.__name__, self.id, self.path())


    def __getitem__(self, idx):
        return self.getSubChannel(idx)


    def __len__(self):
        return len(self.subchannels)

    
    def __iter__(self):
        for i in xrange(len(self)):
            yield self.getSubChannel(i)


    def addSubChannel(self, subchannelId, name=None, units=('',''), 
                 calibration=None):
        """ Create a new SubChannel of the Channel.
        """
#         print subchannelId,name
        if subchannelId > len(self.subchannels):
            raise IndexError("Channel's parser only generates %d subchannels" % \
                             len(self.subchannels))
        else:
            sc = self.subchannels[subchannelId]
            if sc is not None:
                return self.subchannels[subchannelId]
            sc = SubChannel(self, subchannelId, name, units, calibration)
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
    
    
    def parseBlock(self, block, start=0, end=-1, step=1, subchannel=None):
        """ Convert raw data into a set of subchannel values.
            
            @param block: The data block element to parse.
            @keyword start: 
            @keyword end: 
            @keyword step: 
            @keyword subchannel: 
            @return: A list of tuples, one for each subsample.
        """
        # TODO: Cache this; a Channel's SubChannels will often be used together.

        p = (block, start, end, step, subchannel)
        if self._lastParsed[0] == p:
            return self._lastParsed[1]
        result = list(block.parseWith(self.parser, start=start, end=end, 
                                    step=step, subchannel=subchannel))
        self._lastParsed = (p, result)
        return result


#===============================================================================

class SubChannel(Channel):
    """ Output from a sensor, derived from a channel containing multiple
        pieces of data (e.g. the Y from an accelerometer's XYZ). Looks
        like a 'real' channel.
    """
    
    def __init__(self, parent, subChannelId, name=None, units=('',''), calibration=None):
        """ Constructor.
        """
        self.id = subChannelId
        self.parent = parent
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
        
        self.setTransform(calibration)

    @property
    def children(self):
        return []

    @property
    def possibleRange(self):
        """ The range of values *possible* given the type of data recorded. 
            NOT necessarily the range of *actual* values recorded!
        """
        return self.parent.possibleRange[self.id]


    def __repr__(self):
        return '<%s 0x%02x.%x: %r>' % (self.__class__.__name__, self.parent.id, self.id, self.path())


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
    

    def parseBlock(self, block, start=0, end=-1, step=1):
        """
        """
        return self.parent.parseBlock(block, start, end, step=step, subchannel=self.id)
    
        
    def getSession(self, sessionId=None):
        """ Retrieve a session 
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
        
        @todo: Consider a subclass optimized for non-subsampled data.
    """

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
        self._blockIdxTable = ({},{})


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
        return newList
    

    def append(self, block):
        """ Add one data block's contents to the Sensor's list of data.
            Note that this doesn't double-check the channel ID specified in
            the data, but it is inadvisable to include data from different
            channels.
            
            @attention: Added elements should be in chronological order!
        """
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
        tableIdx = block.indexRange[0] / 10000
        self._blockIdxTable[0].setdefault(tableIdx, block.blockIndex)
        self._blockIdxTable[1][tableIdx] = block.blockIndex
        
        
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

            @param idx: 
            @return: 
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
        tableIdx = idx/10000
        if stop == -1:
            stop = self._blockIdxTable[1].get(tableIdx, -2) + 1                
        if start == 0:
            start = max(self._blockIdxTable[0].get(tableIdx, 0)-1, 0)

        return self._searchBlockRanges(idx, self._getBlockIndexRange,
                                       start, stop)


    def _getBlockIndexWithTime(self, t, start=0, stop=-1):
        """ Get the index of a raw data block in which the given time occurs.
        """
        return self._searchBlockRanges(t, self._getBlockTimeRange,
                                       start, stop)
        

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
            idx = min(0, len(self) + idx)
        
        blockIdx = self._getBlockIndexWithIndex(idx)
        subIdx = idx - self._getBlockIndexRange(blockIdx)[0]
        
        block = self._data[blockIdx]
        
        timestamp = block.startTime + self._getBlockSampleTime(blockIdx) * subIdx
        value = self.parent.parseBlock(block, start=subIdx, end=subIdx+1)[0]
        
        if self.hasSubchannels:
            event=tuple((f((timestamp,v)) for f,v in izip(self.parent._transform, value)))
            event=(event[0][0], tuple((e[1] for e in event)))
        else:
            event=self.parent._transform(self.parent.parent._transform[self.parent.id]((timestamp, value)))
        
        if self.dataset.useIndices:
            return Event(idx, event[0], event[1])
        
        return event


    def __iter__(self):
        """ Iterator for the EventList. WAY faster than getting individual
            events.
        """
        for block in self._data:
            indexRange = block.indexRange[0], block.indexRange[1]+1
            sampleTime = self._getBlockSampleTime(block.blockIndex)
            times = iter([block.startTime + sampleTime * t for t in xrange(*indexRange)])            
            for v in self.parent.parseBlock(block):
                yield self.parent._transform((times.next(), v))
                

    def __len__(self):
        """ x.__len__() <==> len(x)
        """
        if len(self._data) == 0:
            return 0
        # For some reason, the cached self._length wasn't thread-safe.
#         return self._length
        return self._data[-1].indexRange[-1]-1


    def iterSlice_old(self, start=0, end=-1, step=1):
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
        
        if start < end and start < len(self):
            step = 1 if step is None else step
    
            startBlockIdx = self._getBlockIndexWithIndex(start) if start > 0 else 0
            startSubIdx = start - self._getBlockIndexRange(startBlockIdx)[0]
            
            endBlockIdx = self._getBlockIndexWithIndex(end, start=startBlockIdx)
            endSubIdx = end - self._getBlockIndexRange(endBlockIdx)[0]
            
            for i in xrange(startBlockIdx, endBlockIdx+1):
                block = self._data[i]
                blockRange = block.indexRange
                sampleTime = self._getBlockSampleTime(i)
                thisStart = startSubIdx if i == startBlockIdx else 0
                thisEnd = endSubIdx if i == endBlockIdx else blockRange[1]-blockRange[0]+1
        
                times = [block.startTime + sampleTime * t for t in xrange(thisStart, thisEnd, step)]
                values = self.parent.parseBlock(block, start=thisStart, end=thisEnd, step=step)
                if self.dataset.useIndices:
                    indices = range(blockRange[0]+thisStart, blockRange[0]+thisEnd, step)
                    for eIdx,eTime,eVal in izip(indices,times,values):
                        if self.hasSubchannels:
                            # TODO: (post Transform fix) Refactor later
                            event=[f((eTime,v)) for f,v in izip(self.parent._transform, eVal)]
                            yield Event(eIdx, event[0][0], tuple((e[1] for e in event)))
                        else:
                            eTime, eVal = self.parent._transform((eTime, eVal))
                            yield Event(eIdx,eTime,eVal)
                else:
                    for event in izip(times,values):
                        if self.hasSubchannels:
                            # TODO: (post Transform fix) Refactor later
                            event=[f((event[-2],v)) for f,v in izip(self.parent._transform, event[-1])]
                            event=(event[0][0], tuple((e[1] for e in event)))
                        else:
                            event = self.parent._transform(self.parent.parent._transform[self.parent.id](event))
                        yield event

      
    def iterSlice(self, start=0, end=-1, step=1):
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
        
        startBlockIdx = self._getBlockIndexWithIndex(start) if start > 0 else 0
        endBlockIdx = self._getBlockIndexWithIndex(end, start=startBlockIdx)

        blockStep = max(1, (step + 0.0) / self._data[startBlockIdx].numSamples)
        numBlocks = int((endBlockIdx - startBlockIdx) / blockStep)+1
        
        subIdx = start - self._getBlockIndexRange(startBlockIdx)[0]
        endSubIdx = end - self._getBlockIndexRange(endBlockIdx)[0]
        
        # in each block, the next subIdx is (step+subIdx)%numSamples
        for i in xrange(numBlocks):
            blockIdx = int(startBlockIdx + (i * blockStep))
            block = self._data[blockIdx]
            blockRange = block.indexRange
            sampleTime = self._getBlockSampleTime(i)
            lastSubIdx = endSubIdx if blockIdx == endBlockIdx else blockRange[1]-blockRange[0]+1
            times = (block.startTime + sampleTime * t for t in xrange(subIdx, block.numSamples, step))
            values = self.parent.parseBlock(block, start=subIdx, end=lastSubIdx, step=step)
            for event in izip(times, values):
                if self.hasSubchannels:
                    # TODO: (post Transform fix) Refactor later
                    event=[f((event[-2],v)) for f,v in izip(self.parent._transform, event[-1])]
                    event=(event[0][0], tuple((e[1] for e in event)))
                else:
                    event = self.parent._transform(self.parent.parent._transform[self.parent.id](event))
                yield event
            subIdx = (subIdx+step) % block.numSamples

      
    def getEventIndexBefore(self, t):
        """ Get the index of an event occurring on or immediately before the
            specified time.
        
            @param t: The time (in microseconds)
            @return: The index of the event preceding the given time, -1 if
                the time occurs before the first event.
        """
        if t <= self._data[0].startTime:
            return -1
        block = self._data[self._getBlockIndexWithTime(t)]
        return int(block.indexRange[0] + ((t - block.startTime) / self._getBlockSampleTime(block.blockIndex)))
        
 
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
        """ Get the first and event indices that fall within the specified
            interval.
            
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
            startIdx = int(startBlock.indexRange[0] + ((startTime - startBlock.startTime) / self._getBlockSampleTime(startBlockIdx)) + 1)
        if endTime is None:
            endIdx = self._data[-1].indexRange[1]
        elif endTime <= self._data[0].startTime:
            endIdx = endBlockIdx = 0
        else:
            endBlockIdx = self._getBlockIndexWithTime(endTime)#, start=startBlockIdx) 
            if endBlockIdx > 0:
                endBlock = self._data[endBlockIdx]
                if endBlockIdx < len(self._data) - 1:
                    endIdx = self._data[endBlockIdx+1].indexRange[0] - 1
                else:
                    endIdx = int(endBlock.indexRange[0] + ((endTime - endBlock.startTime) / self._getBlockSampleTime(endBlockIdx) + 0.0) - 1)
            else:
                endIdx = 0
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

        if len(self._data) == 1:
            # Only one block; can't compute from that!
            raise NotImplementedError("TODO: Implement getting sample rate in case of single block")
        elif blockIdx == len(self._data) - 1:
            # last block. Use previous.
            startTime = self._data[blockIdx-1].startTime
            endTime = block.startTime
        else:
            endTime = self._data[blockIdx+1].startTime
        
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
    

    def getValueAt(self, at):
        """ Retrieve the value at a specific time, interpolating between
            existing events.
        """
        startIdx = self.getEventIndexBefore(at)
        if startIdx < 0:
            if self[0][-2] == at:
                return self[0]
            # TODO: How to handle times before first event?
            raise IndexError("Specified time occurs before first event (%d)" % self[0][-2])
        elif startIdx >= len(self) - 1:
            if self[-1][-2] == at:
                return self[-1]
            # TODO How to handle times after last event?
            raise IndexError("Specified time occurs after last event (%d)" % self[startIdx][-2])
        
        startEvt, endEvt = self[startIdx:startIdx+2]
        relAt = at - startEvt[-2]
        endTime = endEvt[-2] - startEvt[-2] + 0.0
        percent = relAt/endTime
        if self.hasSubchannels:
            print startEvt
            result = startEvt[-1][:]
            for i in xrange(len(self.parent.types)):
                result[i] = self.parent.interpolators[i](startEvt[-1][i], endEvt[-1][i], percent)
                result[i] = self.parent.types[i](result[i])
        else:
            result = self.parent.types[0](self.parent.interpolators[0](startEvt[-1], endEvt[-1], percent))
        if self.dataset.useIndices:
            return None, at, result
        return at, result
        

    def iterStepSlice(self, start, stop, step):
        """ XXX: EXPERIMENTAL!
            Not very efficient, particularly not with single-sample blocks.
            Redo without _getBlockIndexWithIndex
        """
        blockIdx = self._getBlockIndexWithIndex(start)
        lastBlockIdx = self._getBlockIndexWithIndex(stop, blockIdx)+1
        thisRange = self._getBlockIndexRange(blockIdx)
        lastIdx = -1
        for idx in xrange(start, stop, step):
            if idx > thisRange[1]:
                blockIdx = self._getBlockIndexWithIndex(idx, blockIdx+1, lastBlockIdx)
                thisRange = self._getBlockIndexRange(blockIdx)
            if blockIdx > lastIdx:
                lastIdx = blockIdx
                for event in self.iterSlice(idx, min(stop,thisRange[1]+1), step):
                    yield event
    
    
    def iterResampledRange(self, startTime, stopTime, maxPoints, threshold=1.0):
        """ Retrieve the events occurring within a given interval,
            undersampled as to not exceed a given length (e.g. the size of
            the data viewer's screen width).
        
            XXX: EXPERIMENTAL!
            Not very efficient, particularly not with single-sample blocks.
            Redo without _getBlockIndexWithIndex
            
            ALSO: I HAVE NO IDEA HOW THIS WORKS ANYMORE.
        """
        # TODO: Handle possible variations in sample rate.
        blockIdx = self._getBlockIndexWithTime(startTime)
        lastBlockIdx = self._getBlockIndexWithTime(stopTime, start=blockIdx)+1
        startIdx, stopIdx = self.getRangeIndices(startTime, stopTime)
        numPoints = (stopTime - startTime) / (self.getSampleTime(blockIdx) + 0.0)
        step = numPoints / maxPoints
        if step < threshold or blockIdx == lastBlockIdx:
            for p in self.iterSlice(startIdx, stopIdx, max(step,1)):
                yield p
        else:
            step = int(step)
            thisRange = self._getBlockIndexRange(blockIdx)
            lastIdx = -1
            for idx in xrange(startIdx, stopIdx, step):
                if idx > thisRange[1]:
                    blockIdx = self._getBlockIndexWithIndex(idx, start=blockIdx+1, stop=lastBlockIdx)
                    thisRange = self._getBlockIndexRange(blockIdx)
                if blockIdx > lastIdx:
                    lastIdx = blockIdx
                    for event in self.iterSlice(idx, min(stopIdx,thisRange[1]+1), step):
                        yield event
                continue


    def iterResampledRange2(self, startTime, stopTime, maxPoints, threshold=1.0):
        """ Retrieve the events occurring within a given interval,
            undersampled as to not exceed a given length (e.g. the size of
            the data viewer's screen width).
        
            XXX: EXPERIMENTAL!
            Not very efficient, particularly not with single-sample blocks.
            Redo without _getBlockIndexWithIndex
            
            ALSO: I HAVE NO IDEA HOW THIS WORKS ANYMORE.
        """
        # TODO: Handle possible variations in sample rate.
        blockIdx = self._getBlockIndexWithTime(startTime)
        startIdx, stopIdx = self.getRangeIndices(startTime, stopTime)
        numPoints = (stopTime - startTime) / (self.getSampleTime(blockIdx) + 0.0)
        step = int(max(numPoints / maxPoints,1))
        for event in self.iterSlice(startIdx, stopIdx, step):
            yield event
        



    def exportCsv(self, stream, start=0, stop=-1, step=1, subchannels=True,
                  callback=None, callbackInterval=0.01, timeScalar=1,
                  raiseExceptions=False):
        """ Export events as CSV to a stream (e.g. a file).
        
            @param stream: The stream object to which to write CSV data.
            @keyword start: The first event index to export.
            @keyword stop: The last event index to export.
            @keyword step: The number of events between exported lines.
            @keyword subchannels: A sequence of individual subchannel numbers
                to export. Only applicable to objects with subchannels.
                `True` (default) exports them all.
            @keyword timeScalar: A scaling factor for the even times.
                The default is 1 (microseconds).
            @keyword callback: A function (or function-like object) to notify
                as work is done. It should take four keyword arguments:
                `count` (the current line number), `total` (the total number of
                lines), `error` (an exception, if raised during the
                export), and `done` (will be `True` when the export is
                complete). If the callback object has a `cancelled`
                attribute that is `True`, the CSV export will be aborted.
                The default callback is `None` (nothing will be notified).
            @keyword callbackInterval: The frequency of update, as a
                normalized percent of the total lines to export.
            @return: The number of rows exported and the elapsed time.
        """
        def dummyCallback(*args, **kwargs): pass
        def singleVal(x): return ", ".join(map(str,x))
        def multiVal(x): return "%s, %s" % (str(x[-2]*timeScalar), 
                                            str(x[-1]).strip("[({})]"))
        def someVal(x): return "%s, %s" % (str(x[-2]*timeScalar),
                                           str([x[-1][v] for v in subchannels]).strip("[({})]"))
        
        if callback is None:
            noCallback = True
            callback = dummyCallback
        else:
            noCallback = False
        
        if self.hasSubchannels:
            if isinstance(subchannels, Iterable):
                formatter = someVal
            else:
                formatter = multiVal
        else:
            formatter = singleVal
            
        
        totalLines = (stop - start) / (step + 0.0)
        updateInt = int(totalLines * callbackInterval)
        
        start = start + len(self) if start < 0 else start
        stop = stop + len(self) if stop < 0 else stop
        
        t0 = datetime.now()
        try:
#         if True:
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
                
        return num+1, datetime.now() - t0

        
#===============================================================================
# 
#===============================================================================


class Plot(Transformable):
    """ A processed set of sensor data. These are typically the final form of
        the data. Transforms applied are intended to be for display purposes
        (e.g. converting data in centimeters to meters).
    """
    
    def __init__(self, source, name=None, transform=None, units=None):
        self.source = source
        self.dataset = source.dataset
        self.name = source.path() if name is None else name
        self.units = source.units if units is None else units
        self.setTransform(transform)
    
    def __len__(self):
        return len(self.source)
    
    def __getitem__(self, idx):
        result = self.source[idx]
        if isinstance(result, tuple):
            return self._transform(result)
        return map(self._mapTransform, result)
    
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
