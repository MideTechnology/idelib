'''
Created on Mar 5, 2014

@author: dstokes


'''

import abc
# from collections import Iterable
# from datetime import datetime
# from itertools import izip
import os
# import random
# import struct

from mide_ebml import dataset as DS
# import mide_ebml.dataset as DS

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
    def __init__(self, stream, name=None, quiet=False):
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
        self.recorderInfo = None
        
        self.useIndices = False
        self.fileDamaged = False
        self.loadCancelled = False
        self.loading = True
        self.file = stream
        self.filename = stream.name
        self.lastUtcTime = None

        if name is None:
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
#         print "getSubChannel %r" % subchannelId
        # If there is no SubChannel explicitly defined for a subchannel, 
        # dynamically generate one.
        if self.subchannels[subchannelId] is None:
#             print "new subchannel"
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
            newList = EventList(self, session)
            newList.setData([(x[-2],x[-1][self.id]) for x in oldList._data],
                            stamped=True)
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

    def __init__(self, parent, session=None):
        self.parent = parent
        self.session = session
        self._data = []
        self._length = 0
        self._firstTime = 0
        self.dataset = parent.dataset
        self.hasSubchannels = len(self.parent.types) > 1

        self._hasSubsamples = False
        
        self.hasDisplayRange = self.parent.hasDisplayRange
        self.displayRange = self.parent.displayRange

        self.removeMean = False
        self.hasMinMeanMax = False
        self.rollingMeanSpan = self.DEFAULT_MEAN_SPAN


    def setData(self, data, stamped=False):
        """
        """
        if stamped:
            self._data = data
        else:
            sampleTime = 1000000.0 / self.getSampleRate()
            self._data = [(int(i*sampleTime), d) for i,d in enumerate(data)]


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


    def getInterval(self):
        """ Get the first and last event times in the set.
        """
        if len(self._data) == 0:
            return None
        if self._lastTime is None:
            self._lastTime = self._data[-1][0]
        return self._firstTime, self._lastTime


    def __getitem__(self, idx):
        """ Get a specific data point by index.
        
            @param idx: An index, a `slice`, or a tuple of one or both
            @return: For single results, a tuple containing (time, value).
                For multiple results, a list of (time, value) tuples.
        """
        return self._data[idx]
 


    def __iter__(self):
        """ Iterator for the EventList. WAY faster than getting individual
            events.
        """
        return self._data.__iter__()
                

    def __len__(self):
        """ x.__len__() <==> len(x)
        """
        return len(self._data)


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
            
#         print "iterSlice(%r, %r, %r)" % (start, end, step)

        return iter(self._data[s])
        


    def iterJitterySlice(self, start=0, end=-1, step=1, jitter=0.5):
        """ Create an iterator producing events for a range indices.
        """
        return self.iterSlice(start, end, step)

      
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
#         print "getRangeIndices(%r, %r)" % (startTime, endTime)
        return (self.getEventIndexBefore(startTime), 
                self.getEventIndexNear(endTime)+1)
    

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
        if startTime is None:
            startIdx = 0
        else:
            startIdx = max(0, int(startTime * self.getSampleTime))
        if endTime is None:
            endIdx = None
        else:
            endIdx = min(self._data[-1][0], int(endTime * self.getSampleTime))
        return self.iterSlice(startIdx,endIdx,step)        


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
    
    
#     def getValueAt(self, at, outOfRange=False):
#         """ Retrieve the value at a specific time, interpolating between
#             existing events.
#             
#             @param at: The time at which to take the sample.
#             @keyword outOfRange: If `False`, times before the first sample
#                 or after the last will raise an `IndexError`. If `True`, the
#                 first or last time, respectively, is returned.
#         """
#         startIdx = self.getEventIndexBefore(at)
#         if startIdx < 0:
#             if self[0][-2] == at:
#                 return self[0]
#             # TODO: How best to handle times before first event?
#             if outOfRange:
#                 return self[0]
#             raise IndexError("Specified time occurs before first event (%d)" % self[0][-2])
#         elif startIdx >= len(self) - 1:
#             if self[-1][-2] == at:
#                 return self[-1]
#             if outOfRange:
#                 return self[-1]
#             # TODO How best to handle times after last event?
#             raise IndexError("Specified time occurs after last event (%d)" % self[startIdx][-2])
#         
#         startEvt, endEvt = self[startIdx:startIdx+2]
#         relAt = at - startEvt[-2]
#         endTime = endEvt[-2] - startEvt[-2] + 0.0
#         percent = relAt/endTime
#         if self.hasSubchannels:
#             result = startEvt[-1][:]
#             for i in xrange(len(self.parent.types)):
#                 result[i] = self.parent.interpolators[i](self, startIdx, startIdx+1, percent)
#                 result[i] = self.parent.types[i](result[i])
#         else:
#             result = self.parent.types[0](self.parent.interpolators[0](self, startIdx, startIdx+1, percent))
#         if self.dataset.useIndices:
#             return None, at, result
#         return at, result
#         

    def iterStepSlice(self, start, stop, step):
        """ XXX: EXPERIMENTAL!
            Not very efficient, particularly not with single-sample blocks.
            Redo without _getBlockIndexWithIndex
        """
        return self.iterSlice(start, stop, step)
    

    def iterResampledRange(self, startTime, stopTime, maxPoints, padding=0,
                           jitter=0):
        """ Retrieve the events occurring within a given interval,
            undersampled as to not exceed a given length (e.g. the size of
            the data viewer's screen width).
         
            XXX: EXPERIMENTAL!
            Not very efficient, particularly not with single-sample blocks.
        """
#         print "iterResampledRange(%s, %s, %s, %s, %s)" %(startTime, stopTime, maxPoints, padding, jitter)
        startIdx, stopIdx = self.getRangeIndices(startTime, stopTime)
        numPoints = (stopIdx - startIdx)
        startIdx = max(startIdx-padding, 0)
        stopIdx = min(stopIdx+padding, len(self))
        step = max(int(numPoints / maxPoints),1)
        if jitter != 0:
            return self.iterJitterySlice(startIdx, stopIdx, step, jitter)
        return self.iterSlice(startIdx, stopIdx, step)
        



#     def exportCsv(self, stream, start=0, stop=-1, step=1, subchannels=True,
#                   callback=None, callbackInterval=0.01, timeScalar=1,
#                   raiseExceptions=False):
#         """ Export events as CSV to a stream (e.g. a file).
#         
#             @param stream: The stream object to which to write CSV data.
#             @keyword start: The first event index to export.
#             @keyword stop: The last event index to export.
#             @keyword step: The number of events between exported lines.
#             @keyword subchannels: A sequence of individual subchannel numbers
#                 to export. Only applicable to objects with subchannels.
#                 `True` (default) exports them all.
#             @keyword timeScalar: A scaling factor for the even times.
#                 The default is 1 (microseconds).
#             @keyword callback: A function (or function-like object) to notify
#                 as work is done. It should take four keyword arguments:
#                 `count` (the current line number), `total` (the total number
#                 of lines), `error` (an exception, if raised during the
#                 export), and `done` (will be `True` when the export is
#                 complete). If the callback object has a `cancelled`
#                 attribute that is `True`, the CSV export will be aborted.
#                 The default callback is `None` (nothing will be notified).
#             @keyword callbackInterval: The frequency of update, as a
#                 normalized percent of the total lines to export.
#             @return: The number of rows exported and the elapsed time.
#         """
#         # Dummy callback to be used if none is supplied
#         def dummyCallback(*args, **kwargs): pass
#         
#         # Functions for formatting the data.
#         def singleVal(x): return ", ".join(map(str,x))
#         def multiVal(x): return "%s, %s" % (str(x[-2]*timeScalar), 
#                                             str(x[-1]).strip("[({})]"))
#         def someVal(x): return "%s, %s" % (str(x[-2]*timeScalar),
#                     str([x[-1][v] for v in subchannels]).strip("[({})]"))
#         
#         if callback is None:
#             noCallback = True
#             callback = dummyCallback
#         else:
#             noCallback = False
#         
#         if self.hasSubchannels:
#             if isinstance(subchannels, Iterable):
#                 formatter = someVal
#             else:
#                 formatter = multiVal
#         else:
#             formatter = singleVal
#         
#         totalLines = (stop - start) / (step + 0.0)
#         updateInt = int(totalLines * callbackInterval)
#         
#         start = start + len(self) if start < 0 else start
#         stop = stop + len(self) if stop < 0 else stop
#         
#         t0 = datetime.now()
#         try:
#             for num, evt in enumerate(self.iterSlice(start, stop, step)):
#                 if getattr(callback, 'cancelled', False):
#                     callback(done=True)
#                     break
#                 stream.write("%s\n" % formatter(evt))
#                 if updateInt == 0 or num % updateInt == 0:
#                     callback(num, total=totalLines)
#                 callback(done=True)
#         except Exception as e:
#             if raiseExceptions or noCallback:
#                 raise e
#             else:
#                 callback(error=e)
#         t1 = datetime.now()
#         
#         return num+1, t1 - t0
    


Classic.register(Dataset)
Classic.register(Channel)