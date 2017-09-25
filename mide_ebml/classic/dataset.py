'''
Created on Mar 5, 2014

@author: dstokes


'''

import abc
from collections import Iterable
import os
import random

import numpy

from mide_ebml import dataset as DS
# from mide_ebml.calibration import Transform, CombinedPoly, PolyPoly

#===============================================================================
# 
#===============================================================================

class Classic(object):
    """ Marker abstract base class for all Slam Stick Classic data objects. """
    __metaclass__ = abc.ABCMeta
    
    
#===============================================================================
# 
#===============================================================================

class Dataset(DS.Dataset):
    """ A Classic dataset.
    """
    schemaVersion = None
    
    def __init__(self, stream, name=None, exitCondition=None, quiet=False):
        """ Constructor.
            @param stream: A file-like stream object containing Slam Stick
                Classic data.
            @keyword name: An optional name for the Dataset. Defaults to the
                base name of the file (if applicable).
            @keyword quiet: If `True`, non-fatal errors (e.g. schema/file
                version mismatches) are suppressed. 
        """
        self.sessions = []
        self.sensors = {}
        self.channels = {}
        self.plots = {}
        self.transforms = {}
        self.parent = None
        self.currentSession = None
        self.recorderInfo = {'ProductName': 'Slam Stick Classic'}
        self.warningRanges = {}
        self.exitCondition = exitCondition
        
        self.useIndices = False
        self.fileDamaged = False
        self.loadCancelled = False
        self.lastUtcTime = None
        if stream is None:
            self.loading = False
            self.file = None
            self.filename = None
        else:
            self.loading = True
            self.file = stream
            self.filename = stream.name

        if name is None and self.filename is not None:
            self.name = os.path.splitext(os.path.basename(self.filename))[0]
        else:
            self.name = name

    def addSession(self, *args, **kwargs):
        """ Create a new session, add it to the Dataset, and return it.
        """
        self.endSession()
        kwargs.setdefault('sessionId', len(self.sessions))
        self.currentSession = Session(self, *args, **kwargs)
        self.sessions.append(self.currentSession)
        return self.currentSession


    def addSensor(self, sensorId=None, name=None, sensorClass=None, 
                  traceData=None, transform=None):
        """
        """
        sensorClass = sensorClass or DS.Sensor
        return super(Dataset, self).addSensor(sensorId=sensorId, 
                                              name=name,
                                              sensorClass=sensorClass, 
                                              traceData=traceData,
                                              transform=transform )


#===============================================================================
# 
#===============================================================================

class Session(DS.Session):
    """
    """
    def __init__(self, dataset, sessionId=0, startTime=0, endTime=None,
                 utcStartTime=None, offset=None, endPos=None, sampleRate=3200):
        """
        """
        self.dataset = dataset
        self._offset = offset
        self._endPos = os.path.getsize(self.dataset.filename) or endPos
        self._sampleRate = sampleRate
        self._sampleTime = 1000000.0 / sampleRate
        
        super(Session, self).__init__(dataset, sessionId, startTime, endTime,
                                      utcStartTime)
        self.firstTime = startTime

#===============================================================================
# 
#===============================================================================


class Channel(DS.Channel):
    """
    """
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


class SubChannel(DS.SubChannel):
    """
    """
    def getSession(self, sessionId=None):
        """ Retrieve a session 
        """
        # NOTE: There's something peculiar here. Not initializing _sessions
        # causes infinite recursion in superclass; there may be a bug there.
        if self._sessions is None:
            self._sessions = {}
            
        if sessionId is None:
            session = self.dataset.lastSession
            sessionId = session.sessionId
        elif self.dataset.hasSession(sessionId):
            session = self.dataset.sessions[sessionId]
        else:
            raise KeyError("Dataset has no Session id=%r" % sessionId)
        
        if sessionId not in self.sessions:
            # This session doesn't exist for the subchannel, so create a new
            # EventList from the parent Channel's data.
            oldList = self.parent.getSession(sessionId)
            newList = EventList(self, session, oldList)
#             newList.setData([(x[-2],x[-1][self.id]) for x in oldList._data],
#                             stamped=True)
            newList.setData(oldList._data, stamped=True)
            self._sessions[sessionId] = newList
        return self._sessions[sessionId]


#===============================================================================
# 
#===============================================================================

class EventList(DS.EventList):
    """ A list-like object containing discrete time/value pairs. The classic
        version does not dynamically load from file; the maximum classic
        recording is 16MB total.
    """

    def __init__(self, parent, session=None, parentList=None):
        self.parent = parent
        self.session = session
        self._parentList = parentList
        self._data = []
        self._length = 0
        self._firstTime = 0
        self._lastTime = None
        self.dataset = parent.dataset
        self.hasSubchannels = len(self.parent.types) > 1

        self._hasSubsamples = False
        
        self.hasDisplayRange = self.parent.hasDisplayRange
        self.displayRange = self.parent.displayRange

        self.removeMean = False
        self.allowMeanRemoval = False
        self.hasMinMeanMax = False
        self.rollingMeanSpan = self.DEFAULT_MEAN_SPAN
        self._mmm = (None, None)
        
        self._comboXform = self._fullXform = self._displayXform = None
#         self.transform = None
        self.setTransform(None)


    def setData(self, data, stamped=False):
        """
        """
        if stamped:
            self._data = data
        else:
            sampleTime = 1000000.0 / self.getSampleRate()
            self._data = [(int(i*sampleTime), d) for i,d in enumerate(data)]


#     def updateTransforms(self, recurse=True):
#         self._comboXform = self._fullXform = Transform.null
#         if self.transform is not None:
#             self._displayXform = self.transform
#         else:
#             self._displayXform = self._comboXform
            

    def copy(self, newParent=None):
        """ Create a shallow copy of the event list.
        """
        parent = self.parent if newParent is None else newParent
        newList = EventList(parent, self.session, self)
        newList._data = self._data
        newList._length = self._length
        newList.dataset = self.dataset
        return newList


    def getInterval(self):
        """ Get the first and last event times in the set.
        """
        if len(self._data) == 0:
            return None
        if self._lastTime is None:
            self._lastTime = self._data[-1][0]
        return self._firstTime, self._lastTime


    def __getitem__(self, idx, display=False):
        """ Get a specific data point by index.
        
            @param idx: An index, a `slice`, or a tuple of one or both
            @return: For single results, a tuple containing (time, value).
                For multiple results, a list of (time, value) tuples.
        """
        xform = self._displayXform if display else self._comboXform
        if isinstance(idx, slice):
            vals = self.iterSlice(idx.start, idx.stop, idx.step, display=display)
            return list(vals)

        result = xform(self._data[idx])
        if self.hasSubchannels:
            return result
        return (result[0], result[1][self.parent.id])
 


    def __iter__(self):
        """ Iterator for the EventList. WAY faster than getting individual
            events.
        """
        return self._data.__iter__()
                

    def __len__(self):
        """ x.__len__() <==> len(x)
        """
        return len(self._data)


    def itervalues(self, start=0, end=-1, step=1, subchannels=True, 
                   display=False):
        """ Iterate all values in the list.
        """
        # TODO: Optimize; times don't need to be computed since they aren't used
        if self.hasSubchannels and subchannels != True:
            # Create a function instead of chewing the subchannels every time
            fun = eval("lambda x: (%s)" % \
                       ",".join([("x[%d]" % c) for c in subchannels]))
            for v in self.iterSlice(start, end, step, display):
                yield fun(v[-1])
        else:
            for v in self.iterSlice(start, end, step, display):
                yield v[-1]
        

    def iterSlice(self, start=0, end=-1, step=1, display=False):
        """ Create an iterator producing events for a range indices.
        """
        xform = self._displayXform if display else self._comboXform
        if isinstance (start, slice):
            s = slice
        else:
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
    
            s = slice(start, end, step)
        
        if self.hasSubchannels:
            for i in iter(self._data[s]):
                yield xform(i)
        else:
            for i in iter(self._data[s]):
                t,v = xform(i)
                yield t,v[self.parent.id]


    def iterJitterySlice(self, start=0, end=-1, step=1, jitter=0.5, 
                         display=False):
        """ Create an iterator producing events for a range indices.
        """
        for evt in self.iterSlice(start, end, step, display=display):
            yield (evt[-2] + (((random.random()*2)-1) * jitter * step), evt[-1])

      
    def getEventIndexBefore(self, t):
        """ Get the index of an event occurring on or immediately before the
            specified time.
        
            @param t: The time (in microseconds)
            @return: The index of the event preceding the given time, -1 if
                the time occurs before the first event.
        """
        if t <= 0:
            return 0
        if t >= self[-1][0]:
            return len(self)-1
        return max(0, int(t / self.getSampleTime()))
        
 
    def getEventIndexNear(self, t):
        """ The the event occurring closest to a specific time. 
        
            @param t: The time (in microseconds)
            @return: 
        """
        if t <= 0:
            return 0
        if t >= self[-1][0]:
            return len(self)-1
        return max(0, int(0.5+(t / self.getSampleTime())))


    def getRangeIndices(self, startTime, endTime):
        """ Get the first and last event indices that fall within the 
            specified interval.
            
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
        """
        return (self.getEventIndexBefore(startTime), 
                self.getEventIndexNear(endTime)+1)
    

    def getRange(self, startTime=None, endTime=None, display=False):
        """ Get a set of data occurring in a given interval.
        
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
        """
        return list(self.iterRange(startTime, endTime, display=display))


    def iterRange(self, startTime=None, endTime=None, step=1, display=False):
        """ Get a set of data occurring in a given interval.
        
            @keyword startTime: The first time (in microseconds by default),
                `None` to start at the beginning of the session.
            @keyword endTime: The second time, or `None` to use the end of
                the session.
        """
        if startTime is None:
            startIdx = 0
        else:
            startIdx = max(0, int(startTime * self.getSampleTime))
        if endTime is None:
            endIdx = None
        else:
            endIdx = min(self._data[-1][0], int(endTime * self.getSampleTime))
        return self.iterSlice(startIdx,endIdx,step,display)


    def getSampleTime(self, idx=0):
        """ Get the time between samples.
            
            @keyword idx: Because it is possible for sample rates to vary
                within a channel, an event index can be specified; the time
                between samples for that event and its siblings will be 
                returned.
            @return: The time between samples (us)
        """
        return self.session._sampleTime
    
    
    def getSampleRate(self, idx=0):
        """ Get the channel's sample rate. This is either supplied as part of
            the channel definition or calculated from the actual data and
            cached.
            
            @keyword idx: Because it is possible for sample rates to vary
                within a channel, an event index can be specified; the sample
                rate for that event and its siblings will be returned.
            @return: The sample rate, as samples per second (float)
        """
        return self.session._sampleRate


    def iterResampledRange(self, startTime, stopTime, maxPoints, padding=0,
                           jitter=0, display=False):
        """ Retrieve the events occurring within a given interval,
            undersampled as to not exceed a given length (e.g. the size of
            the data viewer's screen width).
        """
        startIdx, stopIdx = self.getRangeIndices(startTime, stopTime)
        numPoints = (stopIdx - startIdx)
        startIdx = max(startIdx-padding, 0)
        stopIdx = min(stopIdx+padding, len(self))
        step = max(int(numPoints / maxPoints),1)
        if jitter != 0:
            return self.iterJitterySlice(startIdx, stopIdx, step, jitter, display)
        else:
            return self.iterSlice(startIdx, stopIdx, step, display)


    def getRangeMinMeanMax(self, startTime=None, endTime=None, subchannel=None,
                           display=False):
        """
        """
        xform = self._displayXform if display else self._comboXform
        
        t = (startTime, endTime)
        if t == self._mmm[0]:
            if self.transform is None:
                return self._mmm[1]
            # TODO: transform
            return self._mmm[1]
        
        mmm = numpy.array(list(self.itervalues(startTime, endTime)))
        if self.hasSubchannels and subchannel is not None:
            self._mmm = (t, (mmm[subchannel].min(), 
                    numpy.median(mmm[subchannel]).mean(), 
                    mmm[subchannel].max()))
        else:
            self._mmm = (t, (mmm.min(), numpy.median(mmm), mmm.max()))
        
        return xform(self._mmm)[1]
        

    def getMax(self, startTime=None, endTime=None, display=False):
        """ Get the event with the maximum value, optionally within a specified
            time range. For Channels, the maximum of all Subchannels is
            returned.
            
            @keyword startTime: The starting time. Defaults to the start.
            @keyword endTime: The ending time. Defaults to the end.
            @return: The event with the maximum value.
        """
        vals = self.iterRange(startTime, endTime)
        if self.hasSubchannels:
            return max(vals, key=lambda x: max(x[-1]))
        return max(vals, key=lambda x: x[-1])

    
    def getMin(self, startTime=None, endTime=None, display=False):
        """ Get the event with the minimum value, optionally within a specified
            time range. For Channels, the minimum of all Subchannels is
            returned.
            
            @keyword startTime: The starting time. Defaults to the start.
            @keyword endTime: The ending time. Defaults to the end.
            @return: The event with the minimum value.
        """
        vals = self.iterRange(startTime, endTime)
        if self.hasSubchannels:
            return min(vals, key=lambda x: min(x[-1]))
        return min(vals, key=lambda x: x[-1])

#===============================================================================
# 
#===============================================================================

Classic.register(Dataset)
Classic.register(Channel)
Classic.register(SubChannel)
Classic.register(EventList)
Iterable.register(EventList) #@UndefinedVariable (PyLint doesn't see `register`)
