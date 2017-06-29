'''
Created on Dec 3, 2014

@author: dstokes
'''

from datetime import datetime
from itertools import izip
import importlib
import locale
import os.path
import platform
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
from mide_ebml import matfile
from mide_ebml import importer
from mide_ebml.matfile import MP
from mide_ebml.parsers import ChannelDataBlock, MPL3115PressureTempParser
from mide_ebml.calibration import CombinedPoly, PolyPoly

from devices import SlamStickX
from common import SimpleUpdater, validateArguments

from build_info import DEBUG, BUILD_NUMBER, VERSION, BUILD_TIME 
__version__ = VERSION


#===============================================================================
# 
#===============================================================================

class MATExportError(Exception):
    pass


#===============================================================================
# 
#===============================================================================

class AccelDumper(object):
    """ Parser replacement that dumps accelerometer data as read. 
    """
    maxTimestamp = ChannelDataBlock.maxTimestamp
    timeScalar = 1000000.0 / 2**15
    
    def __init__(self, source, writer=None, startTime=0, endTime=None, 
                 dtype=MP.miUINT16):
        self.writer = writer
        self.source = source
        self.numCh = len(source.subchannels)
        self.numRows = 0
        self.numSamp = 0
        self.firstTime = None
        self.lastTime = 0
        self.startTime = startTime * 2**15
        self.endTime = None if endTime is None else (endTime * 2**15)
    
        self.timestampOffset = 0
        self.lastStamp = 0
        
        self.dtype = {
            MP.miINT8:   np.int8,
            MP.miUINT8:  np.uint8,
            MP.miINT16:  np.int16,
            MP.miUINT16: np.uint16,
            MP.miINT32:  np.int32,
            MP.miUINT32: np.uint32,
            MP.miINT64:  np.int64,
            MP.miUINT64: np.uint64,
            MP.miUTF8:   np.char,
            MP.miSINGLE: np.single,
            MP.miDOUBLE: np.double}.get(dtype, np.uint16)
    

    def fixOverflow(self, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        timestamp += self.timestampOffset
        while timestamp < self.lastStamp:
            timestamp += self.maxTimestamp
            self.timestampOffset += self.maxTimestamp
        self.lastStamp = timestamp
        return timestamp


    def write(self, el):
        """ Parse the element and write the data.
            @param el: DataBlock element
            @return: `True` if data was written, `False` if not. Data will not
                be written if the block is outside of the specified start
                and end times.
        """
        blockStart = self.fixOverflow(el.value[1].value)
        blockEnd = self.fixOverflow(el.value[2].value)
        if self.firstTime is None:
            self.firstTime = blockStart
        self.lastTime = blockEnd

        if blockStart < self.startTime:
            return False
        
        if self.endTime is not None and blockStart > self.endTime:
            raise StopIteration
        
        data = el.value[-1].value 
        vals= np.frombuffer(data, self.dtype).reshape((-1,self.numCh))
        self.numRows += vals.shape[0]
        self.numSamp += vals.shape[0] * self.numCh
        times = np.linspace(blockStart, blockEnd, vals.shape[0]) * self.timeScalar
        for r in zip(times, vals):
            self.writer(r)
            
        return True


class GenericDumper(AccelDumper):
    """ Parser replacement that dumps temperature/pressure data as read.
        This accumulates data rather than writing it directly.
    """
    
    def __init__(self, *args, **kwargs):
        super(GenericDumper, self).__init__(*args, **kwargs)
        self.unpacker = self.source.parser.unpack_from
        self.data = []
        self.data_append = self.data.append
        
        if self.source.transform is not None or not all([c.transform is None for c in self.source.subchannels]):
            self.source.dataset.updateTransforms()
            self.xform = PolyPoly([CombinedPoly(c.transform, x=self.source.transform) for c in self.source.subchannels])
        else:
            self.xform = None

    def write(self, el):
        self.lastTime = self.fixOverflow(el.value[1].value)
        if self.firstTime is None:
            self.firstTime = self.lastTime
        
        if self.lastTime < self.startTime:
            return False
        
        self.numRows += 1
        self.numSamp += self.numCh
#         if self.xform is not None:
#             self.data_append(self.xform.function(*self.unpacker(el.value[-1].value)))
#         else:
#             self.data_append(self.unpacker(el.value[-1].value))

        self.data_append(self.unpacker(el.value[-1].value))
        return True


#===============================================================================
# 
#===============================================================================

class TempWriter(object):
    """ Thing to write data to a temporary file.
    """
    def __init__(self, stream):
        self.stream = stream
    
    def writerow(self, r):
        self.stream.write('%d, %r\n' % (r[0], list(r[1])))


#===============================================================================
# 
#===============================================================================

def getMatlabType(f, default=MP.miINT16):
    """ Get the largest MATLAB data type for a struct formatting string. Since
        the exported matrix is of a single type, the largest data type is used.
        
        @todo: Raise exception if the formatting string contains incompatible
            types (e.g. strings and numeric values)
    """
    try:
        # ints and longs are the same size in Python structs.
        f = f.replace('l','i').replace('L','I')

        # Float types        
        if 'd' in f:
            return MP.miDOUBLE
        elif 'f' in f:
            # If the struct also has big integers, promote to double.
            if any((c in 'IQq' for c in f)):
                return MP.miDOUBLE
            return MP.miSINGLE
        
        # Combination of signed and unsigned (formatting string is mixed case). 
        # Upgrade smaller unsigned values to larger signed ones.
        if not f.islower() and not f.isupper():
            f = f.replace('I', 'q').replace('H', 'i').replace('B', 'i')
        
        # Lots of tests, starting with the largest integer type.
        if 'q' in f:
            return MP.miINT64
        elif 'Q' in f:
            return MP.miUINT64
        elif 'i' in f:
            return MP.miINT32
        elif 'I' in f:
            return MP.miUINT32
        elif 'h' in f:
            return MP.miINT16
        elif 'H' in f:
            return MP.miUINT16
        elif 'b' in f:
            return MP.miINT8
        elif 'B' in f:
            return MP.miUINT8
        elif 'c' in f:
            return MP.miUTF8
        
    except (TypeError, AttributeError):
        # Not a string. Can occur with old hardcoded parsers.
        pass

    return default
    
    
#===============================================================================
# 
#===============================================================================

def raw2mat(ideFilename, matFilename=None, dtype="double", channels=None,
            noTimes=False, startTime=0, endTime=None, updateInterval=1.5,  
            maxSize=matfile.MatStream.MAX_SIZE, writeCal=True, out=sys.stdout,
            **kwargs):
    """ The main function that handles generating MAT files from an IDE file.
    """
    
    updater = kwargs.get('updater', importer.nullUpdater)
#     maxSize = max(1024**2*16, min(matfile.MatStream.MAX_SIZE, 1024**2*maxSize))
    maxSize =1024*maxSize
    
    def _printStream(*args):
        out.write(" ".join(map(str, args)))
        out.flush()
    
    def _printNone(*args):
        pass
    
    if out is None:
        _print = _printNone
    else:
        _print = _printStream
    
    if matFilename is None:
        matFilename = os.path.splitext(ideFilename)[0] + ".mat"
    elif os.path.isdir(matFilename):
        matFilename = os.path.join(matFilename, os.path.splitext(os.path.basename(ideFilename))[0]+".mat")
        
    with open(ideFilename, 'rb') as stream:
        doc = importer.openFile(stream, **kwargs)
        doc.updateTransforms()

        ssx = SlamStickX.fromRecording(doc)
        
        accelCh = ssx.getAccelChannel()
        if accelCh is not None and len(accelCh.subchannels) > 0:
            accelType = getMatlabType(accelCh.parser.format, MP.miUINT16)
            accelChId = accelCh.id
            numAccelCh = len(accelCh.subchannels)
        else:
            accelCh = accelType = accelChId = numAccelCh = None

        pressTempCh = ssx.getTempChannel().parent
        if pressTempCh is not None and len(pressTempCh.subchannels) > 0:
            pressTempType = getMatlabType(pressTempCh.parser.format, MP.miSINGLE)
            pressTempChId = pressTempCh.id
            numTempCh = len(pressTempCh.subchannels)
        else:
            pressTempCh = pressTempType = pressTempChId = numTempCh = None
        
        dcAccelCh = ssx.getAccelChannel(dc=True)
        if dcAccelCh is not None and len(dcAccelCh.subchannels) > 0:
            dcAccelType = getMatlabType(dcAccelCh.parser.format, MP.miINT16)
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
                raise MATExportError("Unknown channel(s): %s" % (', '.join(missing)))
        
        if "channel" in str(writeCal).lower():
            # Include all channels' calibration, unless it's an old file that
            # uses the special-case pressure/temperature parser, which
            # does the conversion on the fly.
            if pressTempCh is not None and not isinstance(pressTempCh.parser, MPL3115PressureTempParser):
                calChannels = [accelChId, dcAccelChId, pressTempChId]
            else:
                calChannels = [accelChId, dcAccelChId]
        else:
            calChannels = None
        
        mat = matfile.MatStream(matFilename, doc, maxFileSize=maxSize, 
                                writeCal=writeCal, calChannels=calChannels, 
                                writeStart=True, writeInfo=True)
        
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

            try:
                if dcAccelChId in channels:
                    os.remove(tempFile.name)
            except IOError:
                pass
            

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
    
    argparser = argparse.ArgumentParser(description="Mide Raw .IDE to .MAT Converter v%d.%d.%d - Copyright (c) %d Mide Technology" % (VERSION+(datetime.now().year,)))
    argparser.add_argument('-o', '--output', help="The output path to which to save the .MAT files. Defaults to the same as the source file.")
    argparser.add_argument('-c', '--channel', action='append', type=int, help="Export the specific channel. Can be used multiple times. If not used, all channels will export.")
    argparser.add_argument('-a', '--allCal', action='store_const', const=True, default="channel", help="Export all calibration, by ID, instead of only exporting the calibration for each channel.")
    argparser.add_argument('-m', '--maxSize', type=int, default=matfile.MatStream.MAX_SIZE, help="The maximum MAT file size in bytes. Must be less than 2GB.")
    argparser.add_argument('-t', '--startTime', type=float, help="The start of the time span to export (seconds from the beginning of the recording).", default=0)
    argparser.add_argument('-e', '--endTime', type=float, help="The end of the time span to export (seconds from the beginning of the recording).")
    argparser.add_argument('-d', '--duration', type=float, help="The length of time to export, relative to the --startTime. Overrides the specified --endTime")
    argparser.add_argument('-i', '--info', action='store_true', help="Show information about the file and exit.")
    argparser.add_argument('-v', '--version', action='store_true', help="Show detailed version information and exit.")
    argparser.add_argument('source', nargs="+", help="The source .IDE file(s) to convert.")

    args = argparser.parse_args()

    if args.version is True:
        print argparser.description
        print "Converter version %d.%d.%d (build %d) %s, %s" % (VERSION + (BUILD_NUMBER, platform.architecture()[0], datetime.fromtimestamp(BUILD_TIME)))
        print "MIDE EBML library version %d.%d.%d" % ebml_version
        sys.exit(0)
    
    sourceFiles, output, startTime, endTime = validateArguments(args)
    
    try:
        totalSamples = 0
        t0 = datetime.now()
        updater=SimpleUpdater()
        for f in sourceFiles:
            print ('Converting "%s"...' % f)
            updater.precision = max(0, min(2, (len(str(os.path.getsize(f)))/2)-1))
            updater(starting=True)
            totalSamples += raw2mat(f, matFilename=output, 
                                    channels=args.channel, maxSize=args.maxSize,
                                    startTime=startTime, endTime=endTime,
                                    writeCal=args.allCal, updater=updater)
            updater(done=True)
    
        totalTime = datetime.now() - t0
        tstr = str(totalTime).rstrip('0.')
        sampSec = locale.format("%d", totalSamples/totalTime.total_seconds(), grouping=True)
        totSamp = locale.format("%d", totalSamples, grouping=True)
        print "Conversion complete! Exported %s samples in %s (%s samples/sec.)" % (totSamp, tstr, sampSec)
        sys.exit(0)
    except MATExportError as err:
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

