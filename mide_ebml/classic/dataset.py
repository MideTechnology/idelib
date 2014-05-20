'''
Created on Mar 5, 2014

@author: dstokes

classic header struct: "<IBxIxxBBHH"
    * (uint32-LE) Recording size in bytes, including header
    * (uint8) Sample rate code (contents of ADXL345 BW_RATE register)
    * 1 byte padding/unused (reserved)
    * (uint32-LE) Number of ticks elapsed (32.768KHz)
    * 2 bytes padding/unused
    * (uint8) flags
    * (uint8)1 byte time zone offset
    * (uint16-LE) Date in FAT encoded format (v2+ only)
    * (uint16-LE) Time in FAT encoded format (v2+ only)
    
    
Flags:
    0: Time is set (v2+ only)
    
classic data struct: "<hhh"
    * X/Y/Z, three LSB should be masked (val & 0xFFF8).
'''

import abc
from collections import Iterable
from datetime import datetime
from itertools import izip
import os
import random
import struct

from .. import dataset as DS
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

headerParser = struct.Struct("<IBxIxxBBHH")

class DataParser(struct.Struct):
    ranges = (((-0xFFF8/2), (0xFFF8/2)-1),) * 3
    
    def unpack_from(self, data, offset=0):
        data = super(DataParser, self).unpack_from(data, offset)
        return (data[0] & 0xFFF8, data[1] & 0xFFF8, data[2] & 0xFFF8)


class HeaderParser(struct.Struct):
    def unpack_from(self, data, offset=0):
        data = super(HeaderParser, self).unpack_from(data, offset)
        

class FileHeaderParser(struct.Struct):
    """
    """
    
#===============================================================================
# 
#===============================================================================

class Dataset(DS.Dataset):
    """ A Classic dataset.
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
        self.recorderInfo = None
        
        self.useIndices = False
        self.fileDamaged = False
        self.loadCancelled = False
        self.loading = True
        self.filename = stream.name

        if name is None:
            self.name = os.path.splitext(os.path.basename(self.filename))[0]
        else:
            self.name = name


    def addSensor(self, sensorId=None, name=None, sensorClass=None, 
                  traceData=None, transform=None):
        """
        """
        sensorClass = sensorClass or Sensor
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
    def __init__(self, dataset, sessionId=0, startTime=None, endTime=None,
                 utcStartTime=None, offset=None, endPos=None):
        """
        """
        self._offset = headerParser.size if offset is None else offset
        self._endPos = os.path.getsize(self.dataset.filename) or offset
        
        super(Session, self).__init__(dataset, sessionId, startTime, endTime,
                                      utcStartTime)


#===============================================================================
# 
#===============================================================================

class Sensor(object):
    pass


class Channel(DS.Channel):
    """
    """
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
            sc = self.subchannels[subchannelId]
            if sc is not None:
                return self.subchannels[subchannelId]
            sc = SubChannel(self, subchannelId, **kwargs)
            self.subchannels[subchannelId] = sc
            return sc
        


class SubChannel(DS.SubChannel):
    """
    """
    pass

#===============================================================================
# 
#===============================================================================

class EventList(DS.Cascading):
    """ A list-like object containing discrete time/value pairs. Data is 
        dynamically read from the underlying EBML file. 
        
        @todo: Consider a subclass optimized for non-subsampled data (i.e. 
            one sample per data block).
    """

    def __init__(self, parent, session=None):
        self.parent = parent
        self.session = session
        self.dataset = parent.dataset
        self.hasSubchannels = len(self.parent.types) > 1
        self.hasDisplayRange = self.parent.hasDisplayRange
        self.displayRange = self.parent.displayRange


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
        if self._firstTime is None:
            self._firstTime = self[0][-2]
#             self._firstTime = self._getBlockTimeRange(0)[0]
        if self._lastTime is None:
            self._lastTime = self[-1][-2]
#             self._lastTime = self._getBlockTimeRange(-1)[1]
        return self._firstTime, self._lastTime
    


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
        value = self.parent.parseBlock(block, start=subIdx, end=subIdx+1)[0]
        
        if self.hasSubchannels:
            event=tuple(c._transform(f((timestamp,v),self.session)) for f,c,v in izip(self.parent._transform, self.parent.subchannels, value))
            event=(event[0][0], tuple((e[1] for e in event)))
        else:
            event=self.parent._transform(self.parent.parent._transform[self.parent.id]((timestamp, value),self.session))
        
        if self.dataset.useIndices:
            return DS.Event(idx, event[0], event[1])
        
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
            values = self.parent.parseBlock(block, start=subIdx, end=lastSubIdx, step=step)
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
            values = self.parent.parseBlockByIndex(block, indices)
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
            # Last block; use previous.
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
#         yield stop, self.getValueAt(stop)
    

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
                `count` (the current line number), `total` (the total number
                of lines), `error` (an exception, if raised during the
                export), and `done` (will be `True` when the export is
                complete). If the callback object has a `cancelled`
                attribute that is `True`, the CSV export will be aborted.
                The default callback is `None` (nothing will be notified).
            @keyword callbackInterval: The frequency of update, as a
                normalized percent of the total lines to export.
            @return: The number of rows exported and the elapsed time.
        """
        # Dummy callback to be used if none is supplied
        def dummyCallback(*args, **kwargs): pass
        
        # Functions for formatting the data.
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
        t1 = datetime.now()
        
        return num+1, t1 - t0
    


Classic.register(Dataset)
Classic.register(Channel)