'''
MATLAB .MAT file exporting.
'''

from datetime import datetime
from glob import glob
import os.path
import string
import struct

import logging
logger = logging.getLogger('idelib')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")

# NOTE: 64 bit Scipy is unstable; avoid using it for now (v0.13.2, 12/2014).
# from scipy.io.matlab import mio5_params as MP

class MP(object):
    """ MAT data and matrix types. """
    miINT8 =            0x01
    miUINT8 =           0x02
    miINT16 =           0x03
    miUINT16 =          0x04
    miINT32 =           0x05
    miUINT32 =          0x06
    miSINGLE =          0x07
    miDOUBLE =          0x09
    miINT64 =           0x0c
    miUINT64 =          0x0d
    miMATRIX =          0x0e
    miCOMPRESSED =      0x0f
    miUTF8 =            0x10
    miUTF16 =           0x11
    miUTF32 =           0x12
    
    mxCELL_CLASS =      0x01
    mxSTRUCT_CLASS =    0x02
    mxOBJECT_CLASS =    0x03
    mxCHAR_CLASS =      0x04
    mxSPARSE_CLASS =    0x05
    mxDOUBLE_CLASS =    0x06
    mxSINGLE_CLASS =    0x07
    mxINT8_CLASS =      0x08
    mxUINT8_CLASS =     0x09
    mxFUNCTION_CLASS =  0x10
    mxINT16_CLASS =     0x0a
    mxUINT16_CLASS =    0x0b
    mxINT32_CLASS =     0x0c
    mxUINT32_CLASS =    0x0d
    mxINT64_CLASS =     0x0e
    mxUINT64_CLASS =    0x0f
    mxOPAQUE_CLASS =    0x11
    mxOBJECT_CLASS_FROM_MATRIX_H = 0x12


#===============================================================================
# 
#===============================================================================

def splitNum(name, digits=string.digits):
    """ Split a string that ends with a number between the 'body' of the
        string and its numeric suffix. Both parts are returned as strings.
        
        :param name: The string to split.
        :keyword digits: The set of numeric characters. Defaults to 0-9.
        :return: A tuple containing the base name and the numeric suffix.
    """
    base = name.rstrip(digits)
    return base, name[len(base):]
   

def serialFilename(basename, numDigits=2, minNumber=1, inc=1, pad='_'):
    """ Generate a new filename with an incremented numeric suffix.

        :param basename: The name to make unique.
        :keyword numDigits: The minimum number of digits to use when adding a
            new number to a name. Used if there are no existing files.
        :keyword numNumber: The minimum serial number, if no file currently
            exists.
        :keyword inc: The serial number increment.
        :keyword pad: A string to appear between the base name and the number.
        :return: A unique filename.
    """
    base, ext = os.path.splitext(basename)
    existing = glob(base.rstrip(string.digits)+'*'+ext)
    existing = [x for x in existing if os.path.splitext(x)[0][-1].isdigit()]
    if len(existing) > 0:
        existing.sort()
        lastName, lastNum = splitNum(os.path.splitext(existing[-1])[0])
        numDigits = len(existing[-1]) - len(lastName) - len(ext)
        lastNum = int(lastNum)+inc
    else:
        lastNum = minNumber
    return '%s%s%s%s' % (base, pad, str(lastNum).rjust(numDigits, '0'), ext)
    

# def dump8(data, start=0, end=None):
#     """ Debugging tool. Prints data as 8 columns of hex. """
#     end = len(data) if end is None else end
#     for i in range(start,end,8):
#         print '%s:' % (str(i).rjust(4)), 
#         try:
#             for j in range(8):
#                 print "%02x" % (ord(data[i+j])),
#         except IndexError:
#             print "(end)",
#             break
#         print
# 
# def hexdump(data):
#     """ Debugging tool. Dumps a string or a collection of numbers as hex. """
#     if isinstance(data, (str, bytes, bytearray)):
#         a = ["%02x" % ord(c) for c in data]
#     else:
#         a = ["%02x" % c for c in data]
#     return ' '.join(a)

# MATLAB reserved words. 
# TODO: Add standard functions as well
RESERVED_WORDS = ('break', 'case', 'catch','continue', 'else', 'elseif', 'end',
                  'for', 'function', 'global', 'if', 'otherwise', 'persistent',
                  'return', 'switch', 'try', 'while')

def sanitizeName(s, validChars=string.ascii_letters+string.digits+'_',
                 prefix="v", reservedWords=RESERVED_WORDS):
    """ Convert an arbitrary string into a valid MATLAB variable name.
    
        :keyword validChars: A string of all valid characters
    """
    s = s.strip().encode('ascii', 'replace')
    result = [c if c in validChars else '_' for c in (chr(x) for x in s.strip())]
    result = ''.join(result).strip('_ ')
    if result[0].isdigit() or result in reservedWords:
        result = prefix + result.title()
    return result.replace('__', '_').replace('__', '_')


#===============================================================================
# 
#===============================================================================

class MatStream(object):
    """
    """
    MAX_LENGTH = (2**31)-9 # Accounts for data being rounded to the next x8.
    MAX_SIZE = int(MAX_LENGTH * .95) # scale back by 5%, just to be certain
    DEFAULT_HEADER = "MATLAB 5.0 MAT-file MIDE IDE to MAT"
    
    # Map MATLAB types to the struct formatting character
    typeFormatChars = {
        MP.miINT8:   'b',
        MP.miUINT8:  'B',
        MP.miINT16:  'h',
        MP.miUINT16: 'H',
        MP.miINT32:  'i',
        MP.miUINT32: 'I',
        MP.miINT64:  'q',
        MP.miUINT64: 'Q',
        MP.miUTF8:   'c',
        MP.miSINGLE: 'f',
        MP.miDOUBLE: 'd',
    }
    
    # Map data types to matrix types
    classTypes = {
        MP.miINT8:   MP.mxINT8_CLASS,
        MP.miUINT8:  MP.mxUINT8_CLASS,
        MP.miINT16:  MP.mxINT16_CLASS,
        MP.miUINT16: MP.mxUINT16_CLASS,
        MP.miINT32:  MP.mxINT32_CLASS,
        MP.miUINT32: MP.mxUINT32_CLASS,
        MP.miINT64:  MP.mxINT64_CLASS,
        MP.miUINT64: MP.mxUINT64_CLASS,
        MP.miUTF8:   MP.mxCHAR_CLASS,
        MP.miSINGLE: MP.mxSINGLE_CLASS,
        MP.miDOUBLE: MP.mxDOUBLE_CLASS,
    }
    
    intPack = struct.Struct('I')


    def __init__(self, filename, doc=None, msg=None, serialize=True, 
                 maxFileSize=MAX_SIZE, timeScalar=1, writeCal=False,
                 calChannels=None, writeStart=False, writeInfo=False):
        """ Constructor. Create a new .MAT file.
        
            :param filename: The name of the new file, or `None`.
            :keyword doc: The `idelib.dataset.Dataset` from which to export.
            :keyword msg: The message string to appear at the start of the
                MAT file. The first 4 bytes must be non-zero.
            :keyword serialize: If `True`, start the first file with a 
                number. Successive files are always numbered.
            :keyword maxFileSize: The maximum size of each exported file.
                Must not exceed the maximum size allowed for MATs.
            :keyword timeScalar: Timestamp scaling factor.
            :keyword writeCal: If `True`, write calibration data to each
                exported file. If `"channel"`, write calibration by channel
                name, ignoring any transforms not being used.
            :keyword writeStart: If `True`, write the doc's start time.
            :keyword writeInfo: If `True`, write doc/recorder info.
        """
        if msg is None:
            msg = self.DEFAULT_HEADER if doc is None else self.makeHeader(doc)
        self.basename = filename
        self.filename = filename
        self.msg = msg.encode('utf8') or self.DEFAULT_HEADER
        self.stream = None
        self.timeScalar = timeScalar
        self.doc = doc
        if doc is not None:
            self._writeCal = writeCal and len(doc.transforms) > 0
            self._calPerChannel = "channel" in str(writeCal).lower()
            self._writeInfo = writeInfo
            self.startTime = writeStart and doc.sessions[0].utcStartTime
        else:
            self._writeCal = self._writeInfo = self._writeStart = False
        self.calChannels = calChannels

        # MATLAB identifies the file as level 4 if the first byte is 0.
        if b'\x00' in self.msg[:4]:
            self.msg = self.DEFAULT_HEADER
            
        self.maxFileSize = min(self.MAX_SIZE, self.next8(maxFileSize))
        
        # Default array parameters. Typically set by startArray().
        self._inArray = False
        self.arrayName = None
        self.arrayMType = None
        self.arrayDType = MP.miDOUBLE
        self.arrayFlags = 0
        self.arrayNoTimes = False
        self.arrayHasTimes = False
        self.arrayColNames = None
        
        self.exportedFiles = []
        
        if filename is not None:
            self.newFile(serialize)
        else:
            self.stream = None
        

    def newFile(self, serialize=True, offset=None):
        """ Used internally. Wraps file creation.
        """
        if self.stream is not None:
            self.close()
            
        if serialize:
            self.filename = serialFilename(self.basename)
        else:
            self.filename = self.basename
        self.stream = open(self.filename, 'wb')
        self._write = self.stream.write
        self._seek = self.stream.seek

        self._write(struct.pack(b'116s II H 2s', self.msg, 0, 0, 0x0100, b'IM'))
        
        if self._writeInfo:
            self.writeRecorderInfo(self.doc.recorderInfo)
        if self._writeCal:
            if self._calPerChannel:
                self.writeCalPerChannel(self.doc)
            else:
                self.writeCalibration(self.doc.transforms)
        if self.startTime:
            self.writeValue('start_time_utc', self.startTime, MP.miINT64)
        
        self._inArray = False
        self.arrayName = None
        self.arrayColNames = None
        self.arrayStartTime = None
        
        self.exportedFiles.append(self.filename)


    def checkFileSize(self, size, pad=0):
        """ Check if adding data of the given size will exceed the maximum    
            file size; start a new file if it will. Also creates a variable
            for the current array's start time (if provided).
        """
        if self.next8(self.stream.tell() + size + pad) >= self.maxFileSize:
#             print "checkFileSize"
            inArray = self._inArray
            if inArray:
                colNames = self.arrayColNames
                baseName = self.arrayBaseName
                dtype = self.arrayDType
                mtype = self.arrayMType
                noTimes = self.arrayNoTimes
                hasTimes = self.arrayHasTimes
                num = self.arrayNumber + 1
                cols = self.numCols if self.arrayNoTimes else self.numCols - 1
            self.newFile()
            if inArray:
                self.startArray(baseName, cols, arrayNumber=num, 
                                colNames=colNames, mtype=mtype, dtype=dtype, 
                                noTimes=noTimes, hasTimes=hasTimes)


    @property
    def closed(self):
        return True if self.stream is None else self.stream.closed


    @classmethod
    def next8(cls, num):
        """ Return the next multiple of 8; elements within a MAT file must be
            aligned to 64 bits.
        """
        if num % 8 == 0:
            return num
        return 8*(int(num/8)+1)


    def pack(self, fmt, args, dtype=MP.miUINT32):
        """ Write data to the file, proceeded by the type and size (aligned to
            64 bits). Used internally.
            
            :param fmt: A struct formatting string for the data.
            :param args: Arguments for the struct formatting string (i.e. data).
            :keyword dtype: The type for the data size element.
        """
        dataSize = struct.calcsize(fmt)
        result = struct.pack('II'+fmt, dtype, dataSize, *args)
        self._write(result.ljust(self.next8(len(result)), b'\0'))
        return self.next8(dataSize + 8)

    
    def packStr(self, s, maxlen=31):
        """ Write a string to the file, proceeded by type and size info, aligned
            to 64 bits. Used internally.
        """
        s = s[:maxlen].encode('utf8')
        n = self.next8(len(s))
        fmt = 'II %ds' % n
        self._write(struct.pack(fmt, MP.miINT8, len(s), s))

   
    def endArray(self):
        """ End an array, updating all the sizes.
        """
        if not self._inArray:
            return False
        self._inArray = False
        
        dataEndPos = self.stream.tell()
        arrayEndPos = self.next8(dataEndPos)
        
        # Move back and rewrite the actual total size
        self._seek(self.dataStartPos-4)
        self._write(self.intPack.pack(self.next8(dataEndPos-self.dataStartPos)))
        
        # Move back and rewrite the actual number of rows (columns, actually)
        self._seek(self.rowsPos)
        self._write(self.intPack.pack(self.numRows))
            
        # Move back and write the actual payload size (the 'real' portion only)
        self._seek(self.prSize)
        self._write(self.intPack.pack(self.numRows * self.rowFormatter.size))
        
        # Go back to the end.
        self._seek(dataEndPos)
        if dataEndPos < arrayEndPos:
            self._write('\0' * (arrayEndPos-dataEndPos))

        if self.arrayHasTimes and self.arrayNoTimes and self.arrayStartTime is not None:
            self.writeValue('%s_start' % self.arrayBaseName, self.arrayStartTime, MP.miUINT64)
            
        self.arrayMType = None
        self.arrayColNames = None
        self.arrayStartTime = None

        return True


    def startArray(self, name, cols, rows=1, arrayNumber=0, 
                   mtype=None, dtype=MP.miDOUBLE, flags=0, noTimes=True,
                   hasTimes=True, colNames=None):
        """ Begin a 2D array for storing the recorded data.
        
            :param name: The name of the matrix (array).
            :param cols: The number of columns in the data (excluding time).
            :keyword rows: The number of rows in the data (if known).
            :keyword dtype: The Matlab data type in the matrix.
            :keyword mtype: The Matlab matrix type. Defaults to match `dtype`.
            :keyword flags: A set of bit flags for the matrix.
        """
        if self._inArray:
            self.endArray()

        self.arrayBaseName = sanitizeName(name)
        
        # Calculate size of data, plus any applicable 'header' data that needs
        # to be in the same file as the array (column names, start time offset, 
        # etc.)
        headerSize = 0
        if colNames is not None:
            headerSize += self.getNamesSize(colNames, '%s_names' % name, noTimes)
        if noTimes and hasTimes:
            headerSize += self.getValueSize('%s_start' % self.arrayBaseName, self.arrayStartTime, MP.miUINT64)
            
        newSize = 80 + self.next8(len(name)) + headerSize
        self.checkFileSize(newSize)

        self._inArray = True
        self.arrayNumber = arrayNumber
        self.numRows = 0
        self.expectedRows = rows
        self.arrayMType = mtype
        self.arrayDType = dtype
        self.arrayFlags = flags
        self.arrayNoTimes = noTimes
        self.arrayHasTimes = hasTimes
        self.arrayColNames = colNames
        self.arrayStartTime = None
        
        if arrayNumber > 0:
            name = "%s%d" % (self.arrayBaseName, arrayNumber)
            
        if self.arrayColNames:
            self.writeNames(self.arrayColNames, '%s_names' % self.arrayBaseName, self.arrayNoTimes)
        
        if self.arrayMType is None:
            self.arrayMType = self.classTypes[self.arrayDType]
        

        if self.arrayNoTimes:
            self.numCols = cols
        else:
            self.numCols = cols+1
        fchar = self.typeFormatChars.get(self.arrayDType, self.typeFormatChars[MP.miDOUBLE]) * self.numCols
        self.rowFormatter = struct.Struct(fchar)
        
        # Start of matrix element, initial size of 0 (rewritten at end)
        self._write(struct.pack("II", MP.miMATRIX, 0)) # Start
        self.dataStartPos = self.stream.tell()
        
        # Write flags and matrix type
        self.pack('BBBBBBBB', (self.arrayMType, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        
        # Write matrix dimensions. Because the file stores data column first,re
        # the recording data is stored 'sideways': lots of columns. The
        # second dimension is rewritten at the end.
        self.pack('ii', (self.numCols, rows), dtype=MP.miINT32)
        self.rowsPos = self.stream.tell() - 4
        
        # Write the matrix name
        self.packStr(sanitizeName(name))
        
        # Write the start of the 'PR' element; the size will be filled in later.
        self._write(struct.pack('II', self.arrayDType, self.rowFormatter.size * rows))
        self.prSize = self.stream.tell() - 4
        

    def getStringArraySize(self, title, strings):
        """ Get the size of an array of strings before writing it.
        """
        textSize = max([len(s) for s in strings])
        return 40 + self.next8(textSize*len(strings)) + 8 + self.next8(len(title))
        
        
    def writeStringArray(self, title, strings):
        """ Write a set of strings as a MATLAB character array.
        """
        textSize = max([len(s) for s in strings])
        strings = [n.ljust(textSize) for n in strings]
        payload = ''.join([''.join(x) for x in zip(*strings)])
        
        totalSize = self.getStringArraySize(title, strings)
        
        # Ensure that this won't exceed the max file size before writing
        self.checkFileSize(totalSize)
        
        self._write(struct.pack("II", MP.miMATRIX, totalSize)) # Start
        self.pack('BBBBBBBB', (0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        self.pack('II', (len(strings), textSize), dtype=MP.miINT32)
        self.packStr(sanitizeName(title))
        self._write(struct.pack("II", MP.miUTF8, textSize*len(strings)))
        self._write(payload.ljust(self.next8(len(payload)), '\0').encode('utf8'))
        
    
    def getNamesSize(self, names, title="channel_names", noTimes=False):
        if noTimes:
            return self.getStringArraySize(title, names)
        return self.getStringArraySize(title, ['Time']+names)
    
        
    def writeNames(self, names, title="channel_names", noTimes=False):
        """ Write IDE column names to the MAT file, for easy identification
            of rows in MATLAB (IDE data is written in columns in order to
            stream).
        """
        if not noTimes:
            names = names[:]
            names.insert(0, 'Time')
        self.writeStringArray(title, names)


    def writeRow(self, event):
        """ Write a sample to the array.
        
            :param event: The sample, in the format `(time, (v1, v2, ...))`
        """
        if self.arrayStartTime is None:
            self.arrayStartTime = event[0]
        self.checkFileSize(self.rowFormatter.size, pad=96)

        try:
            if self.arrayNoTimes:
                data = self.rowFormatter.pack(*event[:1])
            else:
                data = self.rowFormatter.pack(event[0]*self.timeScalar, *event[1:])
        except struct.error as err:
            logger.exception("ERROR: %s, formatter=%r, event=%r" % (self.arrayBaseName, self.rowFormatter.format, event))
            raise
            
        self._write(data)
        self.numRows += 1


    def getValueSize(self, name, val, dtype=MP.miDOUBLE):
        """ Get the total size of a value as written.
        """
        name = sanitizeName(name)
        fchar = self.typeFormatChars.get(dtype,'d')
        dsize = struct.calcsize(fchar)
        return 40 + self.next8(len(name)) + 8 + self.next8(dsize)
        

    def writeValue(self, name, val, dtype=MP.miDOUBLE):
        """ Write a single numeric value to the MAT file. Don't use for strings.
        """
        name = sanitizeName(name)
        mtype = self.classTypes.get(dtype, MP.mxDOUBLE_CLASS)
        fchar = self.typeFormatChars.get(dtype,'d')
        totalSize = self.getValueSize(name, val, dtype)
        
        self.checkFileSize(totalSize)
        
        self._write(struct.pack("II", MP.miMATRIX, totalSize)) # Start
        self.pack('BBBBBBBB', (mtype, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)) #flags
        self.pack('II', (1, 1), dtype=MP.miINT32) # dimensions
        self.packStr(name)
        self.pack(fchar, (val,), dtype=dtype)

    
    def writeRecorderInfo(self, info):
        """ Write an IDE file's 'RecorderInfo' data to the MAT as a set of
            strings.
        """
        if info:
            s = ['%s:\t%s' % i for i in info.items()]
            self.writeStringArray('recorder_info', s)


    def _writeCalData(self, name, cal, doc=None):
        if isinstance(cal, int):
            cal = doc.transforms.get(cal, None)
        if cal is None:
            return
        vals = cal.references + cal.coefficients
        self.startArray(name, len(vals), dtype=MP.miDOUBLE, noTimes=True, hasTimes=False)
        self.writeRow((0,vals))
        self.endArray()


    def writeCalibration(self, cals):
        """ Write a dictionary of Transform objects (keyed by ID) to the file.
        """
#         print "writeCalibration %s" % self.stream.name
        for calId, cal in cals.items():
            self._writeCalData("calibration%d" % calId, cal)
    
    
    def writeCalPerChannel(self, doc):
        """ Write the calibration used by a document's Channels/Subchannels.
        """
        channels = [c for c in doc.channels.values() if self.calChannels is None or c.id in self.calChannels]
        for c in channels:
            self._writeCalData("%s_calibration" % c.displayName, c.transform, doc)
            for subc in c.subchannels:
                self._writeCalData("%s_calibration" % subc.displayName, subc.transform, doc)

    
    def close(self):
        """ Close the file.
        """
        if self._inArray:
            self.endArray()
        return self.stream.close()



#===============================================================================
# 
#===============================================================================

    @classmethod
    def makeHeader(cls, doc, session=-1, prefix="MATLAB 5.0 MAT-file"):
        """ Generate MAT file header text from a `Dataset` document.
        """
        if not isinstance(prefix, (str, bytes, bytearray)):
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
              raiseExceptions=False, useUtcTime=False, headers=True, 
              removeMean=None, meanSpan=None, display=False, matArgs={},
              noBivariates=False, **kwargs):
    """ Export a `dataset.EventList` as a Matlab .MAT file. Works in a manner
        similar to the standard `EventList.exportCsv()` method.
    
        :param events: an `EventList` from which to export.
        :param filename: The path/name of the .MAT file to write.
        :keyword start: The first event index to export (defaults to first).
        :keyword stop: The last event index to export (defaults to last).
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
            attribute that is `True`, the MAT export will be aborted.
            The default callback is `None` (nothing will be notified).
        :keyword callbackInterval: The frequency of update, as a
            normalized percent of the total lines to export.
        :keyword timeScalar: A scaling factor for the even times.
            The default is 1 (microseconds).
        :keyword raiseExceptions: If `False`, all exceptions will be handled
            quietly, passed along to the callback.
        :keyword useUtcTime: If `True`, times are written as the UTC
            timestamp. If `False`, times are relative to the recording.
        :keyword removeMean: If `True`, remove the mean from the output.
        :keyword meanSpan: The span over which the mean is calculated. -1
            for the total mean.
        :keyword display: If `True`, export using the EventList's 'display'
            transform (e.g. unit conversion).
        :keyword matArgs: A dictionary of keyword arguments supplied to the
            `MatStream` constructor.
        :return: Tuple: The number of rows exported and the elapsed time.
    """
    noCallback = callback is None
    events = events.copy()
    
    events.noBivariates = noBivariates
    if removeMean is not None:
        events.removeMean = removeMean
    if meanSpan is not None:
        events.rollingMeanSpan = meanSpan
    
    start = (1 + start + len(events)) if start < 0 else start
    stop = (1 + stop + len(events)) if stop < 0 else stop
    totalLines = int((stop - start) / (step + 0.0))
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
            
        # Scale to increments used in the source.
        createTime /= timeScalar
   
    # If specific subchannels are specified, export them in order.
    if events.hasSubchannels:
        if subchannels is True:
            numCols = len(events.parent.subchannels)
            formatter = None
            names = [x.name for x in events.parent.subchannels]
        else:
            numCols = len(subchannels)
            # Create a function instead of chewing the subchannels every time
            formatter = eval("lambda x: (%s,)" % \
                       ",".join([("x[%d]" % c) for c in subchannels]))
            names = [events.parent.subchannels[x].name for x in subchannels]
    else:
        numCols = 1
        formatter = lambda x: (x,)
        names = [events.parent.name]

    totalSamples = totalLines * numCols
    if headers is False:
        names = None
    
    comments = MatStream.makeHeader(events.dataset, events.session.sessionId)
    matfile = MatStream(filename, events.dataset, comments, 
                        timeScalar=timeScalar, **matArgs)
    
    matfile.startArray(events.parent.name, numCols, rows=totalLines,
                       colNames=names, noTimes=False)
    
    try:
        for num, evt in enumerate(events.iterSlice(start, stop, step, display)):
            t, v = evt[0], tuple(evt[1:])
            if formatter is not None:
                v = formatter(v)

            matfile.writeRow((createTime + t,)+v)
            
            if callback is not None:
                if getattr(callback, 'cancelled', False):
                    callback(done=True)
                    break
                if updateInt == 0 or num % updateInt == 0:
                    callback(num*numCols, total=totalSamples, 
                             filename=matfile.filename)
                    
        if callback:
            callback(done=True)
            
    except Exception as e:
        if raiseExceptions or noCallback:
            raise
        callback(error=e)
        
    matfile.close()
    
    return num + 1, datetime.now() - t0

#===============================================================================
# 
#===============================================================================

