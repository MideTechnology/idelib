"""

"""

from collections import Counter
from datetime import datetime
import os.path
import sys
from time import time as time_time
from time import sleep
import warnings

import struct
try:
    import tqdm.auto
except ModuleNotFoundError:
    tqdm = None

from . import transforms
from .dataset import Dataset
from . import parsers


#===============================================================================
# 
#===============================================================================

# from dataset import __DEBUG__

import logging
logger = logging.getLogger('idelib')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")


#===============================================================================
# Defaults
#===============================================================================

# from parsers import AccelerometerParser

# Legacy hard-coded sensor/channel mapping. Used when importing files recorded 
# on SSX running old firmware, which does not contain self-description data.
DEFAULTS = {
    "sensors": {
        0x00: {"name": "832M1 Accelerometer"},
        0x01: {"name": "MPL3115 Temperature/Pressure"}
    },
    
    "channels": {
            0x00: {"name": "Accelerometer XYZ",
    #                 "parser": struct.Struct("<HHH"), 
    #                 "transform": 0, #calibration.AccelTransform(),
                    "parser": struct.Struct("<HHH"),
                    "transform": 0,
                    "subchannels":{0: {"name": "Accelerometer Z", 
                                       "axisName": "Z",
                                       "units":('Acceleration','g'),
                                       "displayRange": (-100.0,100.0),
                                       "transform": 3,
                                       "warningId": [0],
                                       "sensorId": 0,
                                     },
                                  1: {"name": "Accelerometer Y", 
                                      "axisName": "Y",
                                      "units":('Acceleration','g'),
                                      "displayRange": (-100.0,100.0),
                                      "transform": 2,
                                      "warningId": [0],
                                      "sensorId": 0,
                                      },
                                  2: {"name": "Accelerometer X", 
                                      "axisName": "X",
                                      "units":('Acceleration','g'),
                                      "displayRange": (-100.0,100.0),
                                      "transform": 1,
                                      "warningId": [0],
                                      "sensorId": 0,
                                      },
                                },
                   },
            0x01: {"name": "Pressure/Temperature",
                   "parser": parsers.MPL3115PressureTempParser(),
                   "subchannels": {0: {"name": "Pressure", 
                                       "units":('Pressure','Pa'),
                                       "displayRange": (0.0,120000.0),
                                      "sensorId": 1,
                                       },
                                   1: {"name": "Temperature", 
                                       "units":('Temperature','\xb0C'),
                                       "displayRange": (-40.0,80.0),
                                      "sensorId": 1,
                                       }
                                   },
                   "cache": True,
                   "singleSample": True,
                   },
    },
    
    "warnings": [{"warningId": 0,
                   "channelId": 1,
                   "subchannelId": 1,
                   "low": -20.0,
                   "high": 60.0
                   }]
}


def createDefaultSensors(doc, defaults=None):
    """ Given a nested set of dictionaries containing the definition of one or
        more sensors, instantiate those sensors and add them to the dataset
        document.
    """
#     logger.info("creating default sensors")
    defaults = defaults or DEFAULTS
    sensors = defaults['sensors'].copy()
    channels = defaults['channels'].copy()
    warnings = defaults['warnings']
    
    if doc.recorderInfo:
        # TODO: Move device-specific stuff out of the main importer
        rtype = doc.recorderInfo.get('RecorderTypeUID', 0x10)
        if rtype | 0xff == 0xff:
            # SSX recorders have UIDs that are zero except the least byte.
            SSX_ACCEL_RANGES = {
               0x10: (-25,25),
               0x12: (-100,100),
               0x13: (-200,200),
               0x14: (-500, 500),
               0x15: (-2000, 2000),
               0x16: (-6000, 6000)
            }
            rrange = SSX_ACCEL_RANGES.get(rtype & 0xff, (-25,25))
            transform = transforms.AccelTransform(*rrange)
            ch0 = channels[0x00]
            ch0['transform'] = transform
            for i in range(3):
                ch0['subchannels'][i]['displayRange'] = rrange

    for sensorId, sensorInfo in sensors.items():
        doc.addSensor(sensorId, sensorInfo.get("name", None))
        
    for chId, chInfo in channels.items():
        chArgs = chInfo.copy()
#         chArgs['sensor'] = sensor
        subchannels = chArgs.pop('subchannels', None)
        channel = doc.addChannel(chId, **chArgs)
        if subchannels is None:
            continue
        for subChId, subChInfo in subchannels.items():
            channel.addSubChannel(subChId, **subChInfo)
    
    for warn in warnings:
        doc.addWarning(**warn)
    

#===============================================================================
# Parsers/Element Handlers
#===============================================================================

# Parser importer. These are taken from the module by type. We may want to 
# create the list of parser types 'manually' prior to release; it's marginally 
# safer.
ELEMENT_PARSER_TYPES = parsers.getElementHandlers()


def instantiateParsers(doc, parserTypes=None):
    """ Create a dictionary of element parser objects keyed by the name of the
        element they handle. Handlers that handle multiple elements have
        individual keys for each element name.
    """
    parserTypes = parserTypes or ELEMENT_PARSER_TYPES
    elementParsers = {}
    for t in parserTypes:
        p = t(doc)
        if isinstance(t.elementName, str):
            elementParsers[t.elementName] = p
        else:
            for name in t.elementName:
                elementParsers[name] = p
    return elementParsers


#===============================================================================
# Updater callbacks
#===============================================================================


def nullUpdater(*args, **kwargs):
    """ A progress updater stand-in that does nothing. """
    if kwargs.get('error',None) is not None:
        raise kwargs['error']
nullUpdater.cancelled = False
nullUpdater.paused = False


class SimpleUpdater(object):
    """ A simple text-based progress updater.
        :ivar cancelled: If set to `True`, the job using the updater will abort. 
        :ivar paused: If set to `True`, the job using the updater will pause.
    """
    
    def __init__(self, cancelAt=1.0, quiet=False):
        """ Constructor.
            :keyword cancelAt: A percentage at which to abort the import. For
                testing purposes.
        """
        self.cancelled = False
        self.paused = False
        self.startTime = None
        self.cancelAt = cancelAt
        self.estSum = None
        self.quiet = quiet
    
    def dump(self, s):
        if not self.quiet:
            sys.stdout.write(s)
    
    def __call__(self, count=0, total=None, percent=None, error=None, 
                 starting=False, done=False):
        if percent >= self.cancelAt:
            self.cancelled=True
        if self.startTime is None:
            self.startTime = datetime.now()
        if starting:
            logger.info("Import started at %s" % self.startTime)
            return
        if done:
            logger.info("Import completed in %s" % (datetime.now() - self.startTime))
            logger.info("Original estimate was %s" % self.estSum)
        else:
            self.dump('\x0d%s samples read' % count)
            if percent is not None:
                p = int(percent*100)
                self.dump(' (%d%%)' % p)
                if p > 0 and p < 100:
                    d = ((datetime.now() - self.startTime) / p) * (100-p)
                    self.dump(' - est. completion in %s' % d)
                    if self.estSum is None:
                        self.estSum = d
                else:
                    self.dump(' '*25)
            sys.stdout.flush()


if tqdm is not None:
    class TQDMUpdater:

        paused = False
        cancelled = False

        _size = 100

        def __init__(self, fileLength=None):
            self.fileLength = fileLength
            pbarKwargs = {
                # 'ncols': 150,
                'unit_scale': 1,
                }
            if fileLength is None:
                self.pbar = tqdm.auto.tqdm(total=self._size, unit='%', **pbarKwargs)
            else:
                self.pbar = tqdm.auto.tqdm(total=fileLength, unit='B', **pbarKwargs)
            self._lastUpdate = 0

        def __call__(self, percent=0, done=False, **kwargs):
            if done:
                self.pbar.update(self.pbar.total - self.pbar.n)
                return

            if self.fileLength is None:
                self.pbar.update(int(percent*self._size) - self._lastUpdate)
                self._lastUpdate = int(percent*self._size)
            else:
                filepos = kwargs.get('filepos', 1)
                self.pbar.update(filepos - self._lastUpdate)
                self._lastUpdate = kwargs.get('filepos')

        def __del__(self):
            self.pbar.close()


else:
    def TQDMUpdater():
        warnings.warn('TQDM was not imported properly')
        return nullUpdater()
    

#===============================================================================
#
#===============================================================================

def _getSize(stream, chunkSize=512 * 1024):
    """
    Get the length of a stream from its data.

    :param stream: A file stream or file-like object (must implement `tell()`
        and `seek()`).
    :returns: The total length of the file.
    """
    if not (hasattr(stream, 'seek') and hasattr(stream, 'tell')):
        raise TypeError('Cannot get size of non-stream {}'.format(type(stream)))

    # If it's a real file, no problem!
    if hasattr(stream, 'name'):
        if os.path.isfile(stream.name):
            return os.path.getsize(stream.name)

    originalPos = stream.tell()

    # Grab chunks until less is read than requested.
    thisRead = chunkSize
    while thisRead == chunkSize:
        thisRead = len(stream.read(chunkSize))

    eof = stream.tell()
    stream.seek(originalPos)
    return eof


#===============================================================================
# ACTUAL FILE READING HAPPENS BELOW
#===============================================================================

def importFile(filename='', startTime=None, endTime=None, channels=None,
               updater=None, parserTypes=None, defaults=None, name=None,
               quiet=False, **kwargs):
    """ Create a new Dataset object and import the data from a MIDE file. 
        Primarily for testing purposes. The GUI does the file creation and 
        data loading in two discrete steps, as it will need a reference to 
        the new document before the loading starts.
        :see: `readData()`
    """
    # FUTURE: Remove `kwargs` and this conditional warning.
    if kwargs:
        warnings.warn(
            'Some importFile() updater-related arguments have been deprecated.'
            ' Ignored arguments: {}'.format(', '.join(kwargs)),
            DeprecationWarning,
            stacklevel=2,
        )

    defaults = defaults or DEFAULTS

    stream = open(filename, "rb")
    doc = openFile(stream, updater=updater, name=name, parserTypes=parserTypes,
                   defaults=defaults, quiet=quiet)
    readData(doc, startTime=startTime, endTime=endTime, channels=channels,
             updater=updater, parserTypes=parserTypes)
    return doc


def openFile(stream, updater=None, parserTypes=None, defaults=None, name=None,
             quiet=False):
    """ Create a `Dataset` instance and read the header data (i.e. non-sample-
        data). When called by a GUI, this function should be considered 'modal,' 
        in that it shouldn't run in a background thread, unlike `readData()`. 
        
        :param stream: The file or file-like object containing the EBML data.
        :param updater: A function (or function-like object) to notify as
            work is done. It should take four keyword arguments: `count`
            (the current line number), `total` (the total number of samples),
            `error` (an unexpected exception, if raised during the import),
            and `done` (will be `True` when the export is complete). If the
            updater object has a `cancelled` attribute that is `True`, the
            import will be aborted. The default callback is `None` (nothing
            will be notified).
        :param parserTypes: A collection of `parsers.ElementHandler` classes.
        :param defaults: A nested dictionary containing a default set of
            sensors, channels, and subchannels. These will only be used if
            the dataset contains no sensor/channel/subchannel definitions. 
        :param name: An optional name for the Dataset. Defaults to the
            base name of the file (if applicable).
        :param quiet: If `True`, non-fatal errors (e.g. schema/file version
            mismatches) are suppressed.
        :return: The opened (but still 'empty') `dataset.Dataset`
    """
    defaults = defaults or DEFAULTS
    parserTypes = parserTypes or ELEMENT_PARSER_TYPES

    if isinstance(stream, str):
        stream = open(stream, 'rb')
    
    doc = Dataset(stream, name=name, quiet=quiet)
    doc.addSession()

    if doc._parsers is None:
        doc._parsers = instantiateParsers(doc, parserTypes)
    
    elementParsers = doc._parsers
    
    try:
        for r in doc.ebmldoc:
            if getattr(updater, "cancelled", False):
                doc.loadCancelled = True
                break
            if r.name not in elementParsers:
                continue
            parser = elementParsers[r.name]
            if parser.makesData():
                break
            parser.parse(r) 
            
    except IOError as e:
        if e.errno is None:
            # The EBML library raises an empty IOError if it hits EOF.
            # TODO: Handle other cases of empty IOError (lots in python-ebml)
            doc.fileDamaged = True
        elif updater:
            updater(error=e)

    except TypeError as e:
        logger.exception(e)
        # This can occur if there is a bad element in the data
        # (typically the last)
        doc.fileDamaged = True

    if not doc.sensors:
        # Got data before the recording props; use defaults.
        if defaults is not None:
            createDefaultSensors(doc, defaults)
            
    doc.updateTransforms()
    return doc


def filterTime(doc, startTime=0, endTime=None, channels=None):
    """ Efficiently read data within a certain interval from an IDE file.
        Note that due to the way data is stored in an IDE, the exported
        interval will be slightly wider than the specified start and end
        times; this ensures the data is copied verbatim and without loss.

        :param doc: An opened (but not yet fully imported) `Dataset`.
        :param startTime: The start of the extraction range, relative to the
            recording's start.
        :param endTime: The end of the extraction range, relative to the
            recording's end.
        :param channels: A list of channel IDs to process. If `None` (the
            default), all channels are processed.
        :yields: Elements from the `Dataset`'s EBML file, excluding
            `ChannelDataBlock`s outside of the specified time range, or
            `None`.
    """
    if startTime == endTime and startTime is not None:
        raise ValueError('startTime and endTime must differ')

    startTime, endTime = sorted((startTime or 0,
                                 endTime or float('infinity')))

    # Dictionaries (and similar) for tracking progress of each ChannelDataBlock
    # element handled. All keyed by channel ID (ChannelIDRef).
    lastBlocks = {}  # Previous element w/ its start and end times
    channelsWritten = Counter()  # Number of elements extracted per channel
    finished = {}  # Channels that have completed extraction

    try:
        timeScalars = doc._parsers['ChannelDataBlock'].timeScalars

        for el in doc.ebmldoc:
            if el.name == 'ChannelDataBlock':
                # Get ChannelIDRef, StartTimeCodeAbs, and EndTimeCodeAbs;
                # usually the 1st three, in order, but don't assume!
                chId = blockStart = blockEnd = None
                for subEl in el:
                    if subEl.name == "ChannelIDRef":
                        chId = subEl.value
                    elif subEl.name == "StartTimeCodeAbs":
                        blockStart = subEl.value
                    elif subEl.name == "EndTimeCodeAbs":
                        blockEnd = subEl.value

                blockEnd = blockEnd or blockStart
                if chId is None:
                    logger.warning("Extractor: {} missing <ChannelIDRef> subelement, skipping.".format(el))
                    continue
                if blockStart is None:
                    logger.warning("Extractor: {} missing <StartTimeCodeAbs> subelement, skipping.".format(el))
                    continue

                if finished.setdefault(chId, False):
                    yield None
                    continue

                if channels and chId not in channels:
                    yield None
                    continue

                # TODO: Modulus correction, if still needed.
                scalar = timeScalars.get(chId, 1)
                blockStart *= scalar
                blockEnd *= scalar

                writeCurrent = True
                writePrev = False  # write previous block, if current one starts late

                if blockEnd < startTime:
                    # Entirely before extraction interval. Yield nothing.
                    writeCurrent = False
                elif blockStart <= startTime:
                    # Block overlaps start of interval. Yield block.
                    # Mark channel finished if block also includes end of interval.
                    writePrev = False
                    finished[chId] = blockEnd >= endTime
                elif blockEnd <= endTime:
                    # Block within interval. Write block (w/ prev. if needed).
                    writePrev = channelsWritten[chId] == 0
                else:
                    # Block overlaps end of interval. Yield block (w/ prev. if needed).
                    # Mark channel finished.
                    finished[chId] = True
                    writePrev = channelsWritten[chId] == 0

                if writePrev:
                    # Yield the previous block, which is before the extraction interval.
                    # This is to ensure that initial data is not left out.
                    prev = lastBlocks.get(chId, None)
                    if prev:
                        channelsWritten[chId] += 1
                        yield prev[0]

                lastBlocks[chId] = (el, blockStart, blockEnd)

                if writeCurrent:
                    channelsWritten[chId] += 1
                    yield el
                else:
                    yield None

            else:
                # FUTURE: Omit `<Sync>` elements outside the interval and
                #  'manually' create ones immediately before and after? Omit
                #  certain time-specific `<Attribute>` elements as well
                #  (if any)?
                yield el

    except (StopIteration, KeyboardInterrupt):
        pass


def readData(doc, source=None, startTime=None, endTime=None, channels=None,
             updater=None, total=None, bytesRead=0, samplesRead=0,
             parserTypes=None, **kwargs):
    """ Import the data from a file into a Dataset.
    
        :param doc: The Dataset document into which to import the data.
        :param source: An alternate Dataset to merge into the main one.
        :param startTime: The start of the extraction range, relative to the
            recording's start.
        :param endTime: The end of the extraction range, relative to the
            recording's end.
        :param channels: A list of channel IDs to import. If `None` (the
            default), all channels are imported.
        :param updater: A function (or function-like object) to notify as
            work is done. It should take four keyword arguments: `count` (the 
            current line number), `total` (the total number of samples), `error` 
            (an unexpected exception, if raised during the import), and `done` 
            (will be `True` when the export is complete). If the updater object 
            has a `cancelled` attribute that is `True`, the import will be 
            aborted. The default callback is `None` (nothing will be notified).
        :param total: The total number of bytes in the file(s) being imported.
            Defaults to the size of the current file, but can be used to
            display an overall progress when merging multiple recordings. For
            display purposes.
        :param bytesRead: The number of bytes already imported. Mainly for
            merging multiple recordings. For display purposes.
        :param samplesRead: The total number of samples imported. Mainly for
            merging multiple recordings.
        :param parserTypes: A collection of `parsers.ElementHandler` classes.
        :return: The total number of samples read.
    """
    kwargs.pop('sessionId', None)  # Unused; for Classic compatibility.

    # FUTURE: Remove `kwargs` and this conditional warning.
    if kwargs:
        warnings.warn(
            'Some importFile() updater-related arguments have been deprecated.'
            ' Ignored arguments: {}'.format(', '.join(kwargs)),
            DeprecationWarning,
            stacklevel=2,
        )

    parserTypes = parserTypes or ELEMENT_PARSER_TYPES
    if doc._parsers is None:
        # Possibly redundant; is `doc._parsers` ever `None` at this point?
        doc._parsers = instantiateParsers(doc, parserTypes)
    
    elementParsers = doc._parsers

    elementCount = 0
    numSamples = 0  # Number of samples imported from this file

    # Progress display setup
    if updater and total is None:
        total = _getSize(doc.ebmldoc.stream) + bytesRead

    increment = 50  # Number of elements per updater. FUTURE: Base this on total size?
    timeOffset = 0

    # Actual importing ---------------------------------------------------------
    if source is None:
        source = doc

    try:
        if startTime is not None or endTime is not None or channels:
            iterator = filterTime(doc, startTime, endTime, channels=channels)
        else:
            iterator = iter(source.ebmldoc)

        for n, el in enumerate(iterator):
            # Progress display stuff -------------------------------------
            if updater:
                loadCancelled = getattr(updater, "cancelled", False)
                if loadCancelled:
                    doc.loadCancelled = loadCancelled
                    break

                thisOffset = el.offset + bytesRead
                if n % increment == 0:
                    updater(count=numSamples + samplesRead,
                            percent=thisOffset / total)

            if el is None:
                continue

            el_name = el.name

            if el_name not in elementParsers:
                # Unknown block type; probably okay to skip.
                logger.info("unknown block {!r} (ID 0x{:02x}) @{}".format(
                        el_name, el.id, el.offset))
                continue

            if source != doc and el_name == "TimeBaseUTC":
                timeOffset = (el.value - doc.lastSession.utcStartTime) * 1000000.0
                continue
                
            try:
                parser = elementParsers[el_name]

                # "Header" elements were loaded by `openFile()`; don't duplicate.
                if not parser.isHeader or el_name == "Attribute":
                    added = parser.parse(el, timeOffset=timeOffset)
                    if isinstance(added, int):
                        numSamples += added
                    
            except parsers.ParsingError as err:
                # TODO: Error messages?
                logger.error("Parsing error during import: %s" % err)
                continue

            elementCount += 1

    except IOError as e:
        if e.errno is None:
            # The EBML library raises an empty IOError if it hits EOF.
            # TODO: Verify that this still does anything (leftover from old EBML library)
            doc.fileDamaged = True
        elif updater:
            updater(error=e, done=True)
        
    except TypeError:
        # This can occur if there is a bad element in the data
        # (typically the last)
        doc.fileDamaged = True

    doc.fillCaches()
    doc.loading = False

    if updater:
        updater(done=True)

    return numSamples

