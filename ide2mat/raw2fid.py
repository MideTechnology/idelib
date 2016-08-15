'''
Created on Dec 3, 2014

@author: dstokes
'''

__copyright__=u"Copyright (c) 2016 Mide Technology"


import ConfigParser
from datetime import datetime
from itertools import izip
import importlib
import locale
import os.path
import platform
import struct
import sys
import tempfile
import time

import numpy as np

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    _ = importlib.import_module('mide_ebml')
except ImportError:
    sys.path.append('..')

from mide_ebml import __version__ as ebml_version    
from mide_ebml import importer
from mide_ebml.parsers import ChannelDataBlock, MPL3115PressureTempParser
from mide_ebml.calibration import Univariate, Bivariate


import devices

from build_info import DEBUG, BUILD_NUMBER, VERSION, BUILD_TIME #@UnusedImport
__version__ = VERSION



#===============================================================================
# 
#===============================================================================

class ExportError(Exception):
    pass

#===============================================================================
# 
#===============================================================================

# The output type for each struct formatting character. Because FID/FIH integer
# values are signed, unsigned types are promoted to the next larger signed type. 
SIZES = (
         ('d', np.float64),
         ('f', np.float32),
         ('q', np.int64),
         ('Q', np.int64),
         ('I', np.int64),
         ('L', np.int64),
         ('i', np.int32),
         ('l', np.int32),
         ('H', np.int32),
         ('h', np.int16), 
         ('B', np.int16),
         ('b', np.int8),
)


STRUCT_CHARS = {
 'B': 'u1',
 'H': 'u2',
 'I': 'u4',
 'L': 'u4',
 'Q': 'u8',
 'b': 'i1',
 'h': 'i2',
 'i': 'i4',
 'l': 'i4',
 'q': 'i8',
 'f': 'f4',
 'd': 'f8',
}

#===============================================================================
# 
#===============================================================================

class AccelDumper(object):
    """ Parser replacement that dumps accelerometer data as read. 
    """
    maxTimestamp = ChannelDataBlock.maxTimestamp
    timeScalar = 1000000.0 / 2**15
    
    def __init__(self, source, filename=None, startTime=0, endTime=None, 
                 interleave=1024):
        
        self.filename = filename
        self.writer = open(filename, 'wb')
        
        self.source = source
        self.numCh = len(source.subchannels)
        self.buffer = None
        self.interleave = interleave
        
        self.numRows = 0
        self.numSamp = 0
        self.numBlocks = 0
        self.firstTime = None
        self.lastTime = 0
        self.startTime = startTime * 2**15
        self.endTime = None if endTime is None else (endTime * 2**15)
        self.exportingRange = startTime and endTime is not None
    
        self.timestampOffset = 0
        self.lastStamp = 0
        
        self.calcSampleRate = True
        self.sampleRate = 5000.0
        self.max = None

        self.dtype = makeInputType(source)
        self.outType = getOutputType(source)
    
    
    def _getCal(self, subchannelId):
        """
        """
        baseT = self.source.transform
        subchannelT = self.source[subchannelId].transform
        
        if baseT is None and subchannelT is None:
            if subchannelId == 0:
                return 0.015625
            elif subchannelId ==1:
                return 0.00390625
            return 1.0
        
        if isinstance(baseT, Univariate):
            gain = baseT.coefficients[0]
        elif isinstance(baseT, Bivariate):
            gain = baseT.coefficients[1]
        else:
            gain = 1.0
         
        if isinstance(subchannelT, Univariate):
            gain *= subchannelT.coefficients[0]
        elif isinstance(subchannelT, Bivariate):
            gain *= subchannelT.coefficients[1]

        return gain
    
    
    def writeFIH(self):
        """ Write the 'header' file. Done AFTER the main export (or at least
            after it has exported enough to calculate sample rate).
        """
        if issubclass(self.dtype, np.signedinteger):
            bits = self.outType(0).itemsize
        else:
            bits = 33
        
        sampRate = (self.lastTime - self.firstTime) / self.numRows
        
        config = ConfigParser.RawConfigParser()
        config.add_section('Common')
        config.set('Common', 'Channels', self.numCh)
        config.set('Common', 'Interleave', self.interleave)
        config.set('Common', 'BitsPerSample', bits)
        config.set('Common', 'SampleFrequency', sampRate)
        config.set('Common', 'DataFile', self.filename)
        
        for c in self.source.subchannels:
            section = 'Channel %d' % (c.id+1)
            
            config.add_section(section)
            config.set(section, 'Name', c.name)
            config.set(section, 'Unit', c.units[-1])
            config.set(section, 'Sensitivity', self._getCal(c.id))
            config.set(section, 'CalType', 'mV/EU')
            config.set(section, 'Range', self.max)
        
        filename = os.path.splitext(self.filename)[0] + '.fih'
        with open(filename, 'wb') as f:
            config.write(f)
    

    def fixOverflow(self, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        timestamp += self.timestampOffset
        while timestamp < self.lastStamp:
            timestamp += self.maxTimestamp
            self.timestampOffset += self.maxTimestamp
        self.lastStamp = timestamp
        return timestamp

    
    def readData(self, data):
        """ Parse data from the element payload.
        """
#         return np.frombuffer(data, self.dtype).reshape((-1,self.numCh))

        # TODO: Optimize for channels containing identical subchannels
        try:
            return np.frombuffer(data, self.dtype).tolist()
        except ValueError:
            # Short buffer. 
            if len(data) % self.dtype.itemsize > 0:
                last = (len(data)/self.dtype.itemsize)*self.dtype.itemsize
                return np.frombuffer(data[:last]).tolist()
            else:
                raise
        

    def _write(self, vals):
        """ Perform the actual writing of data to the new file.
        """
        len_vals = len(vals)
        if len_vals == 0:
            return
        
        # Convert to flattened string of bytes. 
        # 'order="F"` makes it columns first.
        d = np.array(vals, self.outType)
        self.max = max(self.max, d.max())
        d = d.tostring(order="F")
        
        if len_vals < self.interleave:
            # Pad out last (presumably) block
            p = vals[0][0].nbytes * self.interleave * self.numCh
            d = d.just(p, '\x00')
        
        self.writer.write(d)
        

    def write(self, el):
        """ Parse the element and write the data.
        
            @param el: DataBlock element
            @return: `True` if data was written, `False` if not. Data will not
                be written if the block is outside of the specified start
                and end times.
        """
        blockStart = self.fixOverflow(el.value[1].value)
        self.lastTime = self.fixOverflow(el.value[2].value)
        
        if blockStart < self.startTime:
            return False
        
        elif self.endTime is not None and blockStart > self.endTime:
            raise StopIteration
                    
        if self.firstTime is None:
            self.firstTime = blockStart

        vals = self.readData(el.value[-1].value)
        
        if self.buffer is None:
            self.buffer = vals
        else:
            self.buffer = np.append(self.buffer, vals, axis=0)
        
        numSamp = vals.shape[0]
        self.numRows += numSamp
        self.numSamp += numSamp * self.numCh
            
        self.numBlocks += 1
        
        if len(self.buffer) > self.interleave:
            # write a block
            self._write(self.buffer[:self.interleave])
            self.buffer = self.buffer[self.interleave:]

        return True

    
    def close(self):
        """
        """
        self._write(self.buffer)
        self.writer.close()
        self.writeFIH()


class OldMPL3115Dumper(AccelDumper):
    """ Parser replacement that dumps the old-style temperature/pressure data.
    """
    
    def __init__(self, source, dtype=np.float32, **kwargs):
        self.parser = MPL3115PressureTempParser()
        super(OldMPL3115Dumper, self).__init__(source, dtype=dtype, **kwargs)


    def readData(self, data):
        return [[self.parser.unpack_from(data)]]



def getOutputType(channel):
    """ Get the smallest supported Numpy data type that will hold all values 
        generated by a Channel.
    """
    if channel.parser is None or not channel.parser.format:
        # Probably an old file using hard-coded parsers.
        if channel.id == 0:
            return np.int32
        else:
            # Presume it is a pressure/temperature channel
            return np.float32
    
    fstr = channel.parser.format.strip(' <>=@!\n\r\t')
    dtype = np.uint16
    dsize = 0
    
    # Floats take priority; FID/FIH only supports 32b floats.
    if 'f' in fstr or 'd' in fstr:
        return np.float32
    
    # Get the largest (signed) integer type
    for fchar in fstr:
        for ch, dt in SIZES:
            if dt(0).nbytes <= dsize:
                break
            if ch == fchar:
                dtype = dt
                dsize = dt(0).nbytes
                break

    return dtype


def makeInputType(channel):
    """ Generate a Numpy structured array from a channel's parser.
    """
    s = channel.parser.format
    if not s:
        # No format: probably an old file with hardcoded parser. Use floats.
        return np.dtype(','.join(['<f4' for _ in s.subchannels]))
    
    endianCode = '<' if sys.byteorder == 'little' else '>'
    s = s.strip().replace('!','>').replace('@', endianCode).replace('=', endianCode)
    
    p = []
    for c in s:
        if c in '<>':
            endianCode = c
        else:
            p.append('%s%s' % (endianCode, STRUCT_CHARS.get(c, 'V1')))
    
    return np.dtype(','.join(p))
    
    

#===============================================================================
# 
#===============================================================================

class SimpleUpdater(object):
    """ A simple text-based progress updater. Simplified version of the one in
        `mide_ebml.importer`
    """
    
    def __init__(self, cancelAt=1.0, quiet=False, out=sys.stdout, precision=0):
        """ Constructor.
            @keyword cancelAt: A percentage at which to abort the import. For
                testing purposes.
        """
        locale.setlocale(0,'English_United States.1252')
        self.out = out
        self.cancelAt = cancelAt
        self.quiet = quiet
        self.precision = precision
        self.reset()


    def reset(self):
        self.startTime = None
        self.cancelled = False
        self.estSum = None
        self.lastMsg = ''
        
        if self.precision == 0:
            self.formatter = " %d%%"
        else:
            self.formatter = " %%.%df%%%%" % self.precision

    def dump(self, s):
        if not self.quiet:
            self.out.write(s)
            self.out.flush()
    
    def __call__(self, count=0, total=None, percent=None, error=None, 
                 starting=False, done=False, **kwargs):
        if starting:
            self.reset()
            return
        if percent >= self.cancelAt:
            self.cancelled=True
        if self.startTime is None:
            self.startTime = time.time()
        if done:
            self.dump(" Done.".ljust(len(self.lastMsg))+'\n')
            self.reset()
        else:
            if percent is not None:
                num = locale.format("%d", count, grouping=True)
                msg = "%s samples read" % num
                if msg != self.lastMsg:
                    self.lastMsg = msg
                    msg = "%s (%s)" % (msg, self.formatter % (percent*100))
                    dt = time.time() - self.startTime
                    if dt > 0:
                        sampSec = count/dt
                        msg = "%s - %s samples/sec." % (msg, locale.format("%d", sampSec, grouping=True))
                    self.dump(msg)
                    self.dump('\x08' * len(msg))
                    self.lastMsg = msg
                if percent >= self.cancelAt:
                    self.cancelled=True
            sys.stdout.flush()


#===============================================================================
# 
#===============================================================================

def showInfo(ideFilename, **kwargs):
    """
    """
    print ideFilename
    print "=" * 70
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        print "Sensors"
        print "-" * 40
        for s in sorted(doc.sensors.values()):
            print "  Sensor %d: %s" % (s.id, s.name)
            if s.traceData:
                for i in s.traceData.items():
                    print "    %s: %s" % i
        print 
        print "Channels"
        print "-" * 40
        for c in sorted(doc.channels.values()):
            print "  Channel %d: %s" % (c.id, c.displayName)
            for sc in c.subchannels:
                print "    Subchannel %d.%d: %s" % (c.id, sc.id, sc.displayName)
    print "=" * 70


#===============================================================================
# 
#===============================================================================

def raw2fid(ideFilename, outFilename=None, channels=None,
            noTimes=False, startTime=0, endTime=None, updateInterval=1.5,  
            out=sys.stdout, **kwargs):
    """ The main function that handles generating MAT files from an IDE file.
    """
    
    updater = kwargs.get('updater', importer.nullUpdater)
    
    def _printStream(*args):
        out.write(" ".join(map(str, args)))
        out.flush()
    
    def _printNone(*args):
        pass
    
    if out is None:
        _print = _printNone
    else:
        _print = _printStream
    
    if outFilename is None:
        outFilename = os.path.splitext(ideFilename)[0] + ".mat"
    elif os.path.isdir(outFilename):
        outFilename = os.path.join(outFilename, os.path.splitext(os.path.basename(ideFilename))[0]+".mat")
        
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        doc.updateTransforms()

        ssx = devices.fromRecording(doc)
        
        accelCh = ssx.getAccelChannel()
        if accelCh is not None and len(accelCh.subchannels) > 0:
            accelChId = accelCh.id
            numAccelCh = len(accelCh.subchannels)
        else:
            accelCh = accelType = accelChId = numAccelCh = None

        pressTempCh = ssx.getTempChannel().parent
        if pressTempCh is not None and len(pressTempCh.subchannels) > 0:
            pressTempChId = pressTempCh.id
            numTempCh = len(pressTempCh.subchannels)
        else:
            pressTempCh = pressTempType = pressTempChId = numTempCh = None
        
        dcAccelCh = ssx.getAccelChannel(dc=True)
        if dcAccelCh is not None and len(dcAccelCh.subchannels) > 0:
            dcAccelChId = dcAccelCh.id
            numDcAccelCh = len(dcAccelCh.subchannels)
        else:
            dcAccelCh = dcAccelType = dcAccelChId = numDcAccelCh = None
        
        totalSize = os.path.getsize(ideFilename) + 0.0
        nextUpdate = time.time() + updateInterval
        
        # Export all channels if no specific IDs were supplied, and bail if an
        # invalid ID was given.
        if channels is None:
            channels = doc.channels.keys()
        else:
            missing = [str(c) for c in channels if c not in doc.channels]
            if missing:
                raise ExportError("Unknown channel(s): %s" % (', '.join(missing)))
        
        # If exporting calibration by channel, exclude the temp/pressure,
        # since it's already converted.
        if "channel" in str(writeCal).lower():
            calChannels = [accelChId, dcAccelChId]
        else:
            calChannels = None

        
        try:
            # The main accelerometer gets dumped first, directly to the MAT.
            # There may not be any analog accelerometer if it was disabled.
            if accelCh is not None:
                colNames = [c.displayName for c in accelCh.subchannels]
                mat.startArray(accelCh.name, numAccelCh, dtype=accelType, 
                               noTimes=True, colNames=colNames)
    
            dumpers = {}

            # TODO: Make this all more generic, to work with any future recorder
            if accelChId in channels:
                # Analog accelerometer data is written directly to the file.
                dumpers[accelChId] = AccelDumper(accelCh, mat.writeRow, 
                                                 startTime, endTime, 
                                                 dtype=accelType)
            if pressTempChId in channels:
                # Pressure/Temperature data is kept in memory and written later.
                dumpers[pressTempChId] = GenericDumper(pressTempCh, None, 
                                                       startTime, endTime)
                
            if dcAccelChId in channels:
                # DC accelerometer data is written to a temporary file and
                # appended to the main MAT file at the end.
                # TODO: If only DC accelerometer, write directly to file.
                tempFile = open(os.path.join(tempfile.gettempdir(), 'ch%d_temp.csv' % dcAccelChId), 'wb')
                tempWriter = TempWriter(tempFile) #csv.writer(tempFile)
                dumpers[dcAccelChId] = AccelDumper(dcAccelCh, tempWriter.writerow, 
                                                   startTime, endTime, 
                                                   dtype=dcAccelType)
            
            lastMat = ''
            writeMsg = '' 
            isWriting = False
            offset = 0
            
            try:
                for i, el in enumerate(doc.ebmldoc.iterroots()):
                    if mat.filename != lastMat:
                        lastMat = mat.filename
                        msgLen = len(writeMsg)
                        writeMsg = "  Writing %s... " % os.path.basename(lastMat)
                        _print("%s%s" % ('\x08'*msgLen, writeMsg))
                        nextUpdate = 0
    
                    if el.name == "ChannelDataBlock":
                        chId = el.value[0].value
                        if chId in dumpers:
                            wroteData = dumpers[chId].write(el)
                            
                            # First block written; base the 
                            if wroteData and not isWriting:
                                offset = stream.tell()
                                totalSize -= offset
                                isWriting = True
                            
                    if i % 250 == 0 or time.time() > nextUpdate:
                        count = sum((x.numSamp for x in dumpers.itervalues()))
                        updater(count=count, total=None, 
                                percent=((stream.tell()-offset)/totalSize), 
                                filename=mat.filename)
                        nextUpdate = time.time() + updateInterval

                    # Remove per-element substreams. Saves memory; a large
                    # file may contain tens of thousands.
                    # NOTE: This may change if the underlying EMBL library does.
                    doc.ebmldoc.stream.substreams.clear()
                    del el
                    
                    if updater.cancelled:
                        break
                    
            except (IOError, StopIteration):
                pass
                
            # Finished dumping the analog accelerometer data.
            mat.endArray()
            
            # Dump temperature/pressure data (if applicable)
            if pressTempChId in channels:
                d = dumpers[pressTempChId]
                colNames = [c.displayName for c in pressTempCh.subchannels]
                mat.startArray(pressTempCh.name, numTempCh, dtype=pressTempType, 
                               noTimes=True, colNames=colNames)
                for r in izip(np.linspace(d.firstTime, d.lastTime, len(d.data)), d.data):
                    mat.writeRow(r)
                mat.endArray()

            # Dump DC accelerometer data (if applicable)
            if dcAccelCh is not None and dcAccelChId in channels:
                tempFile.close()
                d = dumpers[dcAccelChId]
                colNames = [c.displayName for c in dcAccelCh.subchannels]
                mat.startArray(dcAccelCh.name, numDcAccelCh, dtype=dcAccelType, 
                               noTimes=True, colNames=colNames)
                with open(tempFile.name, 'rb') as f:
                    for r in f:
                        mat.writeRow(eval(r))
                mat.endArray()

            # Calculate actual sampling rate based on total count and total time
            # TODO: Write this for each MAT file.
            # TODO: Write the time range in each file (reset parser.firstTime)
            sampRates = [1000000.0/(((d.lastTime-d.firstTime)*ChannelDataBlock.timeScalar)/d.numRows) for d in dumpers.itervalues()]
            mat.startArray("sampling_rates", len(sampRates), dtype=MP.miSINGLE, noTimes=True, hasTimes=False)
            mat.writeRow((0,sampRates))
            mat.endArray()
            
            mat.close()
            return sum((x.numSamp for x in dumpers.itervalues()))
        
        except IOError:
            mat.close()
            
        except KeyboardInterrupt as ex:
            mat.close()
            raise ex

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse
    from glob import glob
    
    argparser = argparse.ArgumentParser(description="Mide Raw IDE to FIH/FID Converter v%d.%d.%d - %s" % (VERSION+(__copyright__,)))
    argparser.add_argument('-o', '--output', help="The output path to which to save the .MAT files. Defaults to the same as the source file.")
    argparser.add_argument('-c', '--channel', action='append', type=int, help="Export the specific channel. Can be used multiple times. If not used, all channels will export.")
    argparser.add_argument('-t', '--startTime', type=float, help="The start of the time span to export (seconds from the beginning of the recording).", default=0)
    argparser.add_argument('-e', '--endTime', type=float, help="The end of the time span to export (seconds from the beginning of the recording).")
    argparser.add_argument('-d', '--duration', type=float, help="The length of time to export, relative to the --startTime. Overrides the specified --endTime")
    argparser.add_argument('-i', '--info', action='store_true', help="Show information about the file and exit.")
    argparser.add_argument('-v', '--version', action='store_true', help="Show detailed version information and exit.")
    argparser.add_argument('source', nargs="*", help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()

    if args.version is True:
        print argparser.description
        print "Converter version %d.%d.%d (build %d) %s, %s" % (VERSION + (BUILD_NUMBER, platform.architecture()[0], datetime.fromtimestamp(BUILD_TIME)))
        print "MIDE EBML library version %d.%d.%d" % ebml_version
        sys.exit(0)
    
    if len(args.source) == 0:
        print "Error: No source file(s) specified!"
        sys.exit(1)
    
    sourceFiles = []
    for f in args.source:
        sourceFiles.extend(glob(f))
    
    if not all(map(os.path.exists, sourceFiles)):
        # Missing a file.
        missing = map(lambda x: not os.path.exists(x), sourceFiles)
        print "Source file(s) could not be found:"
        print "\n\t".join(missing)
        sys.exit(1)

    if args.info is True:
        print "=" * 70
        for f in sourceFiles:
            showInfo(f)
        sys.exit(0)
        
    if args.output is not None:
        if not os.path.exists(args.output):
            print "Output path does not exist: %s" % args.output
            sys.exit(1)
        if not os.path.isdir(args.output):
            print "Specified output is not a directory: %s" % args.output
            sys.exit(1)
    
    if args.duration:
        endTime = args.startTime + args.duration
    else:
        endTime = args.endTime

    if isinstance(endTime, float) and endTime <= args.startTime:
        print "Specified end time (%s) occurs at or before start time (%s). " % (endTime, args.startTime)
        print "(Did you mean to use the --duration argument instead of --endTime?)"
        sys.exit(1)
    
    try:
        totalSamples = 0
        t0 = datetime.now()
        updater=SimpleUpdater()
        for f in sourceFiles:
            print ('Converting "%s"...' % f)
            updater.precision = max(0, min(2, (len(str(os.path.getsize(f)))/2)-1))
            updater(starting=True)
            totalSamples += raw2mat(f, outFilename=args.output, 
                                    channels=args.channel, maxSize=args.maxSize,
                                    startTime=args.startTime, endTime=endTime,
                                    writeCal=args.allCal, updater=updater)
            updater(done=True)
    
        totalTime = datetime.now() - t0
        tstr = str(totalTime).rstrip('0.')
        sampSec = locale.format("%d", totalSamples/totalTime.total_seconds(), grouping=True)
        totSamp = locale.format("%d", totalSamples, grouping=True)
        print "Conversion complete! Exported %s samples in %s (%s samples/sec.)" % (totSamp, tstr, sampSec)
        sys.exit(0)
    except ExportError as err:
        print "*** Export error: %s" % err
        sys.exit(1)
    except KeyboardInterrupt:
        print "\n*** Conversion canceled! MAT version(s) of %s may be incomplete." % f
        sys.exit(0)
    except Exception as err:
        print "*** An unexpected %s occurred. Is source an IDE file?" % err.__class__.__name__
        if DEBUG:
            print "*** Message: %s" % err.message
        sys.exit(1)
#     except IOError as err: #Exception as err:
#         print "\n\x07*** Conversion failed! %r" % err

