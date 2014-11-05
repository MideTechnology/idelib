'''
Created on Oct 17, 2014

@author: dstokes
'''
from scipy.io.matlab import mio5_params as MP

from datetime import datetime
import os.path
import string
import struct

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


def sanitizeName(s, validChars=string.ascii_letters+string.digits+'_'):
    s = s.strip()
    result = [c if c in validChars else '_' for c in s.strip()]
    if result[0].isdigit():
        result.insert(0, '_')
    return ''.join(result).rstrip('_').replace('__','_')
    
#===============================================================================
# 
#===============================================================================

class MatStream(object):
    """
    """
    
    typeFormatChars = {
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
    
    classFormatChars = {
        MP.mxINT8_CLASS:   'b',
        MP.mxUINT8_CLASS:  'B',
        MP.mxINT16_CLASS:  'h',
        MP.mxUINT16_CLASS: 'H',
        MP.mxINT32_CLASS:  'i',
        MP.mxUINT32_CLASS: 'I',
        MP.mxCHAR_CLASS:   'c',
        MP.mxSINGLE_CLASS: 'f',
        MP.mxDOUBLE_CLASS: 'd',
    }
    
    intPack = struct.Struct('I')
    
    def __init__(self, filename, msg="MATLAB 5.0 MAT-file MIDE IDE to MAT"):
        """ Constructor. Create a new .MAT file. 
        """
        if filename is not None:
            if isinstance(filename, basestring):
                self.stream = open(filename, 'wb')
            else:
                self.stream = filename
            msg = msg.encode('utf8')
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

    
    def packStr(self, string, maxlen=31):
        """ Write a string to the file, proceeded by type and size info, aligned
            to 64 bits. Used internally.
        """
        string = string[:maxlen]
        n = self.next8(len(string))
        fmt = 'II %ds' % n
        self.write(struct.pack(fmt, MP.miINT8, len(string), string))

   
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
        fchar = self.typeFormatChars.get(dtype, self.typeFormatChars[MP.miDOUBLE]) * self.numCols
        self.rowFormatter = struct.Struct(fchar)
        
        # Start of matrix element, initial size of 0 (rewritten at end)
        self.write(struct.pack("II", MP.miMATRIX, 0)) # Start
        self.dataStartPos = self.stream.tell()
        
        # Write flags and matrix type
        # NOTE: This didn't work right; hard-coding something that does.
#         self.pack('xxBBxxxx', (flags, mtype))
        self.pack('BBBBBBBB', (0x06, 0x00, 0x00, mtype, 0x00, 0x00, 0x00, 0x00))
        
        # Write matrix dimensions. Because the file stores data column first,re
        # the recording data is stored 'sideways': lots of columns. The
        # second dimension is rewritten at the end.
        self.pack('II', (cols+1, rows), dtype=MP.miINT32)
        self.rowsPos = self.stream.tell() - 4
        
        # Write the matrix name
        self.packStr(sanitizeName(name))
        
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

def makeHeader(doc, session=-1, prefix="MATLAB 5.0 MAT-file"):
    """ Generate MAT file header text from a `Dataset` document.
    """
    if not isinstance(prefix, basestring):
        prefix = ''
    elif not prefix.endswith(' '):
        prefix += ' '
        
    msg = "%sGenerated from %s" % (prefix, os.path.basename(doc.filename))

    s = doc.sessions[session]
    if s.utcStartTime:
        createTime = s.utcStartTime
    else:
        try:
            createTime = os.path.getctime(doc.filename)
        except IOError:
            createTime = None
    
    if createTime is not None:
        msg = "%s recorded %s UTC" % (msg, datetime.utcfromtimestamp(createTime))
    
    return msg


#===============================================================================
# 
#===============================================================================

def exportMat(events, filename, start=0, stop=-1, step=1, subchannels=True,
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
    
    start = (1 + start + len(events)) if start < 0 else start
    stop = (1 + stop + len(events)) if stop < 0 else stop
    totalLines = (stop - start) / (step + 0.0)
    updateInt = int(totalLines * callbackInterval)
    
    # Catch all or no exceptions
    ex = None if raiseExceptions or noCallback else Exception
    
    t0 = datetime.now()
    
    createTime = 0
    if useUtcTime:
        if events.session.utcStartTime:
            createTime = events.session.utcStartTime
        else:
            try:
                createTime = os.path.getctime(events.dataset.filename)
            except IOError:
                pass
   
    # If specific subchannels are specified, export them in order.
    if events.hasSubchannels:
        if subchannels is True:
            numCols = len(events.parent.subchannels)
            formatter = None
        else:
            numCols = len(subchannels)
            # Create a function instead of chewing the subchannels every time
            formatter = eval("lambda x: (%s,)" % \
                       ",".join([("x[%d]" % c) for c in subchannels]))
    else:
        numCols = 1
        formatter = lambda x: (x,)

    comments = makeHeader(events.dataset, events.session.sessionId)
    matfile = MatStream(filename, comments)
    matfile.startArray(events.parent.name, numCols, rows=totalLines)
    
    try:
        for num, evt in enumerate(events.iterSlice(start, stop, step)):
            t, v = evt
            if formatter is not None:
                v = formatter(v)

            matfile.writeRow((createTime + (t * timeScalar), v))
            
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

