'''
Created on Oct 17, 2014

@author: dstokes
'''
from scipy.io.matlab import mio5_params as MP

import dataset
import multi_importer as importer

from datetime import datetime
from itertools import imap, izip
import os.path
import struct
import time

#===============================================================================
# 
#===============================================================================

def dump8(data, start=0, end=None):
    """ Debugging tool. Prints data as 8 columns of hex. """
    end = len(data) if end is None else end
    for i in range(start,end,8):
        print '%s:' % (str(i).rjust(4)), 
        try:
            for j in range(8):
                print "%02x" % (ord(data[i+j])),
        except IndexError:
            print "(end)",
            break
        print

def hexdump(data):
    """ Debugging tool. Dumps a string or a collection of numbers as hex. """
    if isinstance(data, basestring):
        a = ["%02x" % ord(c) for c in data]
    else:
        a = ["%02x" % c for c in data]
    return ' '.join(a)

    
#===============================================================================
# 
#===============================================================================

class MatStream(object):
    formatChars = {
        MP.miINT8:   'b',
        MP.miUINT8:  'B',
        MP.miINT16:  'h',
        MP.miUINT16: 'H',
        MP.miINT32:  'i',
        MP.miUINT32: 'I',
        MP.miUTF8:   'c',
        MP.miSINGLE: 'f',
        MP.miDOUBLE: 'd',
    }
    
    intPack = struct.Struct('I')
    
    def __init__(self, filename, msg="MIDE IDE to MAT"):
        """ Constructor. Create a new .MAT file. 
        """
        if filename is not None:
            if isinstance(filename, basestring):
                self.stream = open(filename, 'wb')
            else:
                self.stream = filename
            self.write(struct.pack('116s II H 2s', msg, 0, 0, 0x0100, 'IM'))
        else:
            self.stream = None
            
        self._inArray = False


    @property
    def closed(self):
        return True if self.stream is None else self.stream.closed


    @classmethod
    def appendTo(cls, filename):
        """ Open an existing .MAT file for appending. """
        matfile = cls(None)
        matfile.stream = open(filename, 'ab')
        return matfile
        

    @classmethod
    def next8(cls, num):
        """ Return the next multiple of 8; elements within a MAT file must be
            aligned to 64 bits.
        """
        if num % 8 == 0:
            return num
        return 8*(int(num/8)+1)


    def write(self, data):
        """ Used internally. Wrapper for writing raw data to the file.
        """
#         print "pos=%d writing %d bytes: %s" % (self.stream.tell(), len(data), hexdump(data))
        self.stream.write(data)


    def pack(self, fmt, args, dtype=MP.miUINT32):
        """ Write data to the file, proceeded by the type and size (aligned to
            64 bits). Used internally.
            
            @param fmt: A struct formatting string for the data.
            @param args: Arguments for the struct formatting string (i.e. data).
            @keyword dtype: The type for the data size element.
        """
        dataSize = self.next8(struct.calcsize(fmt))
        result = struct.pack('II'+fmt, dtype, dataSize, *args)
        self.write(result.ljust(self.next8(len(result)),'\0'))
        return dataSize + 8

    
    def packStr(self, string):
        """ Write a string to the file, proceeded by type and size info, aligned
            to 64 bits. Used internally.
        """
        n = self.next8(len(string))
        fmt = 'II %ds' % n
        self.write(struct.pack(fmt, MP.miINT8, n, string))

   
    def endArray(self):
        """ End an array, updating all the sizes.
        """
        if not self._inArray:
            return False
        
        endPos = self.stream.tell()
        
        # Move back and rewrite the actual total size
        self.stream.seek(self.dataStartPos-4)
        self.write(self.intPack.pack(endPos-self.dataStartPos))
        
        if self.numRows != self.expectedRows:
            # Move back and rewrite the actual number of rows (columns, actually)
            self.stream.seek(self.rowsPos)
            self.write(self.intPack.pack(self.numRows))
            
            # Move back and write the actual payload size (the 'real' portion only)
            self.stream.seek(self.prSize)
            self.write(self.intPack.pack(self.numRows * self.rowFormatter.size))
            
        # Go back to the end.
        self.stream.seek(endPos)
        return True


    def startArray(self, name, cols, rows=1, mtype=MP.mxDOUBLE_CLASS, dtype=MP.miDOUBLE, flags=0):
        """ Begin a 2D array for storing the recorded data.
        
            @param name: The name of the matrix (array).
            @param cols: The number of columns in the data (excluding time).
            @keyword rows: The number of rows in the data (if known).
            @keyword mtype: The Matlab matrix type.
            @keyword dtype: The Matlab data type in the matrix (usually matches
                the matrix's type).
            @keyword flags: A set of bit flags for the matrix.
        """
        if self._inArray:
            self.endArray()
            
        self._inArray = True
        self.numRows = 0
        self.expectedRows = rows

        self.numCols = cols+1
        fchar = self.formatChars.get(dtype, self.formatChars[MP.miDOUBLE]) * self.numCols
        self.rowFormatter = struct.Struct(fchar)
        
        # Start of matrix element, initial size of 0 (rewritten at end)
        self.write(struct.pack("II", MP.miMATRIX, 0)) # Start
        self.dataStartPos = self.stream.tell()
        
        # Write flags and matrix type
        # NOTE: This didn't work right; hard-coding something that does.
#         self.pack('xxBBxxxx', (flags, mtype))
        self.pack('BBBBBBBB', (0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        
        # Write matrix dimensions. Because the file stores data column first,
        # the recording data is stored 'sideways': lots of columns. The
        # second dimension is rewritten at the end.
        self.pack('II', (cols+1, rows), dtype=MP.miINT32)
        self.rowsPos = self.stream.tell() - 4
        
        # Write the matrix name
        self.packStr(name)
        
        # Write the start of the 'PR' element; the size will be filled in later.
        self.write(struct.pack('II', dtype, self.rowFormatter.size * rows))
        self.prSize = self.stream.tell() - 4
        

    def writeRow(self, event):
        """
        """
        self.write(self.rowFormatter.pack(event[-2], *event[-1]))
        self.numRows += 1
    

    def close(self):
        """ Close the file.
        """
        if self._inArray:
            self.endArray()
        return self.stream.close()


#===============================================================================
# 
#===============================================================================

def exportCsv(events, filename, start=0, stop=-1, step=1, subchannels=True,
              callback=None, callbackInterval=0.01, timeScalar=1,
              raiseExceptions=False, useUtcTime=False, removeMean=None,
              meanSpan=None):
    """ Export a `dataset.EventList` as a Matlab .MAT file.
    
        @param events: an `EventList` from which to export.
        @param filename: The path/name of the .MAT file to write.
        @keyword start: The first event index to export (defaults to first).
        @keyword stop: The last event index to export (defaults to last).
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
        @keyword raiseExceptions: If `False`, all exceptions will be handled
            quietly, passed along to the callback.
        @keyword useUtcTime: If `True`, times are written as the UTC
            timestamp. If `False`, times are relative to the recording.
        @keyword removeMean: If `True`, remove the mean from the output.
        @keyword meanSpan: The span over which the mean is calculated. -1
            for the total mean.
        @return: Tuple: The number of rows exported and the elapsed time.
    """
    noCallback = callback is None
    
    # Save current mean removal settings, apply ones for export.
    oldRemoveMean = events.removeMean
    oldMeanSpan = events.rollingMeanSpan
    if removeMean is not None:
        events.removeMean = removeMean
    if meanSpan is not None:
        events.rollingMeanSpan = meanSpan
    
    totalLines = (stop - start) / (step + 0.0)
    updateInt = int(totalLines * callbackInterval)
    
    start = start + len(events) if start < 0 else start
    stop = stop + len(events) if stop < 0 else stop
    
    # Catch all or no exceptions
    ex = None if raiseExceptions or noCallback else Exception
    
    t0 = datetime.now()
    
    if events.session.utcStartTime:
        createTime = events.session.utcStartTime
    else:
        createTime = os.path.getctime(events.dataset.filename)
    
    comments = "%s, recorded %s" % (os.path.basename(events.dataset.filename), 
                                    datetime.utcfromtimestamp(createTime))
    matfile = MatStream(filename, comments)
    
    try:
        for num, evt in enumerate(events.iterSlice(start, stop, step)):
            if useUtcTime:
                evt = (createTime + (evt[0] * timeScalar), evt[1])
            else:
                evt = (evt[0] * timeScalar, evt[1])

            matfile.writeRow(evt)
            
            if callback is not None:
                if getattr(callback, 'cancelled', False):
                    callback(done=True)
                    break
                if updateInt == 0 or num % updateInt == 0:
                    callback(num, total=totalLines)
                    
        if callback:
            callback(done=True)
            
    except ex as e:
        callback(error=e)

        
    matfile.close()
    
    # Restore old removeMean        
    events.removeMean = oldRemoveMean
    events.rollingMeanSpan = oldMeanSpan
    return num+1, datetime.now() - t0

#===============================================================================
# 
#===============================================================================

class StreamedDataset(dataset.Dataset):
    """ A stand-in for the normal `dataset.Dataset` object, tuned for
        streaming calibrated data into another file, as opposed to importing
        everything.
    """
    def __init__(self, *args, **kwargs):
        self.outStream = self.kwargs.pop('outStream')
        self.channelId = self.kwargs.pop('exportChannelId', 0)
        self.subchannelId = self.kwargs.pop('exportSubchannelId', None)
        self._loading = True
        super(StreamedDataset, self).__init__(*args, **kwargs)
    
    @property
    def loading(self):
        return self._loading
    
    @loading.setter
    def loading(self, val):
        if val is False and self._loading is True:
            self.outStream.close()
        self._loading = val


    def writeToStream(self, event, channelId=0, subchannelId=None):
        # This is what writes an event to the stream. Maybe different
        # streams based on channel and subchannel ID.
        pass
    
    

class StreamedChannel(dataset.Channel):
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
            self.subchannels[subchannelId] = StreamedSubChannel(self, subchannelId)
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
        return self.sessions.setdefault(sessionId, StreamedEventList(self, session))


class StreamedSubChannel(StreamedChannel, dataset.SubChannel):
    """
    """

class StreamedEventList(dataset.EventList):
    """
    """
    
    def __init__(self, *args, **kwargs):
        self.lastEvent = None
        super(StreamedEventList, self).__init__(*args, **kwargs)
    
    def copy(self, *args, **kwargs):
        c = super(StreamedEventList, self).copy(*args, **kwargs)
        c.lastEvent = self.lastEvent
        return c
    
    def append(self, block):
        # `append()` doesn't really append; it writes the data to a file.
        values = self.parent.parseBlock(block)
        sampleTime = (block.endTime - block.startTime) / len(values)
        times = (block.startTime + (i * sampleTime) for i in xrange(len(values)))
        if self.hasSubchannels:
            for event in izip(times, values):
                # TODO: Refactor this ugliness
                # This is some nasty stuff to apply nested transforms
                event=[c._transform(f((event[-2],v),self.session), self.session) for f,c,v in izip(self.parent._transform, self.parent.subchannels, event[-1])]
                event=(event[0][0], tuple((e[1] for e in event)))
                self.dataset.writeToStream(event, self.parent.id)
        else:
            for event in izip(times, values):
                event = self.parent._transform(self.parent.parent._transform[self.parent.id](event, self.session))
                self.dataset.writeToStream(event, self.parent.parent.id, self.parent.id)
                
        self.lastEvent = event


    def getValueAt(self, at, outOfRange=True):
        # Always gets the last value.
        if self.hasSubchannels:
            return self.lastEvent
        else:
            return self.lastEvent[-1][self.parent.id]
    


def ideIterator(filename, **kwargs):
    """
    """
    with open(filename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        
