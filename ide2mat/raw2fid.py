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

def changeFilename(filename, ext=None, path=None):
    """ Modify the path or extension of a filename. 
    """
    if ext is not None:
        ext = ext.lstrip('.')
        filename = "%s.%s" % (os.path.splitext(filename)[0], ext)
    if path is not None:
        filename = os.path.join(path, os.path.basename(filename))
    return os.path.abspath(filename)

#===============================================================================
# 
#===============================================================================

class AccelDumper(object):
    """ Parser replacement that dumps accelerometer data as read. 
    """
    maxTimestamp = ChannelDataBlock.maxTimestamp
    timeScalar = 1000000.0 / 2**15
    
    def __init__(self, source, filename, startTime=0, endTime=None, 
                 interleave=1024):
        
        self.filename = changeFilename(filename, ext=".fid")
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
        
        if isinstance(baseT, Bivariate):
            gain = baseT.coefficients[1]
        elif isinstance(baseT, Univariate):
            gain = baseT.coefficients[0]
        else:
            gain = 1.0
         
        if isinstance(subchannelT, Bivariate):
            gain *= subchannelT.coefficients[1]
        elif isinstance(subchannelT, Univariate):
            gain *= subchannelT.coefficients[0]

        return gain
    
    
    def writeFIH(self):
        """ Write the 'header' file. Done AFTER the main export (or at least
            after it has exported enough to calculate sample rate).
        """
        if issubclass(self.outType, np.signedinteger):
            bits = self.outType(0).itemsize * 8
        else:
            bits = 33
        
        sampRate = (self.lastTime - self.firstTime) / self.numRows
        maxes = np.amax(self.max.reshape((-1, self.numCh)), 
                        axis=0, keepdims=True).flatten()
#         print "%r maxes: %r" % (self.source, maxes)
        
        config = ConfigParser.RawConfigParser()
        config.optionxform = str
        config.add_section('Common')
        config.set('Common', 'Channels', self.numCh)
        config.set('Common', 'Interleave', self.interleave)
        config.set('Common', 'BitsPerSample', bits)
        config.set('Common', 'SampleFrequency', sampRate)
        config.set('Common', 'DataFile', os.path.basename(self.filename))
        
        for c in self.source.subchannels:
            section = 'Channel %d' % (c.id+1)
            config.add_section(section)
            config.set(section, 'Name', c.displayName.encode("ascii", "ignore"))
            config.set(section, 'Unit', c.units[-1].encode("ascii", "ignore"))
            config.set(section, 'Sensitivity', self._getCal(c.id))
            config.set(section, 'CalType', 'mV/EU')
            config.set(section, 'Range', maxes[c.id])
        
        filename = changeFilename(self.filename, ext='.fih')
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
                last = int(len(data)/self.dtype.itemsize)*self.dtype.itemsize
                return np.frombuffer(data[:last]).tolist()
            else:
                raise
        

    def _write(self, vals):
        """ Perform the actual writing of data to the new file.
        """
        len_vals = len(vals)
        if len_vals == 0:
            return
        
        d = np.array(vals, self.outType)
        
        if len_vals % self.interleave != 0:
            # Pad out the end to a full block
            padRows = self.interleave - (len_vals % self.interleave)
            padding = [[0]*len(self.source.subchannels)] * padRows
            d = np.append(vals, padding, axis=0)
        
        maxes = np.amax(d, axis=0, keepdims=True)
        if self.max is None:
            self.max = maxes
        else:
            self.max = np.append(self.max, maxes)
            
        # Convert to flattened string of bytes. 
        # 'order="F"` makes it columns first.
        self.writer.write(d.tostring(order="F"))
        

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
        
        numSamp = len(vals)
        self.numRows += numSamp
        self.numSamp += numSamp * self.numCh
            
        self.numBlocks += 1
        
        if len(self.buffer) >= self.interleave:
            # write a block
            self._write(self.buffer[:self.interleave])
            self.buffer = self.buffer[self.interleave:]

        return True

    
    def close(self):
        """
        """
        self._write(self.buffer)
        self.writer.close()


class OldMPL3115Dumper(AccelDumper):
    """ Parser replacement that dumps the old-style temperature/pressure data.
    """
    
    def __init__(self, source, filename, **kwargs):
        self.parser = MPL3115PressureTempParser()
        super(OldMPL3115Dumper, self).__init__(source, filename, **kwargs)


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
        return np.dtype(','.join(['<f4' for _ in channel.subchannels]))
    
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
#             self.dump(" Done.".ljust(len(self.lastMsg))+'\n')
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
        rec = devices.fromRecording(doc)

        print "Recorder Info"
        print "-" * 40
        print "  Serial Number: %s" % rec.serial
        print "  Recorder Type: %s (%s)" % (rec.productName, rec.partNumber)
        if rec.birthday:
            print "  Date of Manufacture: %s" % datetime.fromtimestamp(rec.birthday)
        print "  Hardware Version: %s" % rec.hardwareVersion
        print "  Firmware Version: %s" % rec.firmwareVersion
        
        print
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

def raw2fid(ideFilename, savepath="", channels=None,
            noTimes=False, startTime=0, endTime=None, interleave=1024, 
            updateInterval=1.5, out=sys.stdout, **kwargs):
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
    
    if savepath:
        if not os.path.isdir(savepath):
            raise ExportError("Save path is a file: %s" % savepath)
    else:
        savepath = os.path.dirname(ideFilename)
    
    basename = os.path.splitext(os.path.basename(ideFilename))[0] + "_Ch%d.fid"
    basename = os.path.join(savepath, basename)
    
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        doc.updateTransforms()

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
        
        dumpArgs = {'startTime': startTime,
                    'endTime': endTime,
                    'interleave': interleave}
        dumpers = {}
        
        try:
            for chId in channels:
                ch = doc.channels[chId]
                filename = basename % chId
                
                if doc.channels[chId].parser.format is None:
                    dumpers[chId] = OldMPL3115Dumper(ch, filename, **dumpArgs)
                else:
                    dumpers[chId] = AccelDumper(ch, filename, **dumpArgs)

            isWriting = False
            offset = 0
            
            try:
                for i, el in enumerate(doc.ebmldoc.iterroots()):
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
                                percent=((stream.tell()-offset)/totalSize))
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
             
            return sum((x.numSamp for x in dumpers.itervalues()))
         
        except Exception as err:
            print "exception: %r" % err
          
        except IOError:
            raise
            pass
              
        finally:
            for d in dumpers.values():
                d.close()
                d.writeFIH()
                

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
    argparser.add_argument('-n', '--interleave', type=int, help="Export block size (in samples)", default=1024)
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
            totalSamples += raw2fid(f, savepath=args.output, 
                                    channels=args.channel,
                                    interleave=args.interleave, 
                                    startTime=args.startTime, endTime=endTime,
                                    updater=updater)
            updater(done=True)
    
        totalTime = datetime.now() - t0
        tstr = str(totalTime).rstrip('0.')
        sampSec = locale.format("%d", totalSamples/totalTime.total_seconds(), grouping=True)
        totSamp = locale.format("%d", totalSamples, grouping=True)
        print "Conversion complete! Exported %s samples in %s (%s samples/sec.)" % (totSamp, tstr, sampSec)
        sys.exit(0)
    except Exception:
        raise
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

