'''
Created on Sep 30, 2014

@author: dstokes
'''
from collections import Iterable, OrderedDict
import csv
from datetime import datetime
import os.path
from xml.sax import saxutils
import shutil
import string
import subprocess
import sys
import tempfile
import time

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO #@UnusedImport

from xml.etree import ElementTree as ET

import numpy as np
import pylab #@UnresolvedImport - doesn't show up for some reason.

from scipy.signal import butter, lfilter #, freqz #@UnresolvedImport

VIEWER_PATH = r"R:\LOG-Data_Loggers\LOG-0002_Slam_Stick_X\Design_Files\Firmware_and_Software\Development\Source\Slam_Stick_Lab"
INKSCAPE_PATH = r"C:\Program Files (x86)\Inkscape\inkscape.exe"

CWD = os.path.abspath(os.path.dirname(__file__))
sys.path.append(CWD)

# Song and dance to make sure the idelib library can be found.
try:
    import idelib
except ImportError:
    if os.path.exists('../idelib'):
        sys.path.append(os.path.abspath('..'))
    elif os.path.exists(os.path.join(CWD, '../idelib')):
        sys.path.append(os.path.abspath(os.path.join(CWD, '../idelib')))
    elif os.path.exists(VIEWER_PATH):
        sys.path.append(VIEWER_PATH)
    import idelib #@UnusedImport

# from idelib import util as ebml_util
# from idelib import xml2ebml
from idelib.importer import importFile, SimpleUpdater

from idelib.ebmlite import loadSchema
from idelib.ebmlite import util as ebmlite_util

from glob import glob
testFiles = glob(r"R:\LOG-Data_Loggers\LOG-0002_Slam_Stick_X\Product_Database\_Calibration\SSX0000039\DATA\20140923\*.IDE")

# NOTE: Make sure devices.py is copied to deployed directory
import devices

from birth_utils import changeFilename, writeFile, writeFileLine, findCalLog

# XXX: REMOVE
import matplotlib.pyplot as plot #@UnresolvedImport @UnusedImport

#===============================================================================
#
#===============================================================================

DEFAULT_HUMIDITY = 22.3

schema_mide = loadSchema('mide.xml')

#===============================================================================
#
#===============================================================================

class CalibrationError(ValueError):
    """ Exception raised when some part of calibration fails.
    """


#===============================================================================
# 
#===============================================================================

class XYZ(list):
    """ Helper for making arrays of XYZ less ugly. A mutable named tuple. """

    def __init__(self, *args, **kwargs):
        if len(args) == 3:
            super(XYZ, self).__init__(args, **kwargs)
        else:
            super(XYZ, self).__init__(*args, **kwargs)
        if len(self) < 3:
            self.extend([0]*(3-len(self)))

    def __repr__(self):
        return "(x: %r, y: %r, z: %r)" % tuple(self)

    @property
    def x(self):
        return self[0]

    @x.setter
    def x(self, val):
        self[0] = val

    @property
    def y(self):
        return self[1]

    @y.setter
    def y(self, val):
        self[1] = val

    @property
    def z(self):
        return self[2]

    @z.setter
    def z(self, val):
        self[2] = val


#===============================================================================
#
#===============================================================================

def lowpassFilter(data, cutoff, fs, order=5):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    y = lfilter(b, a, data)
    return y


def highpassFilter(data, cutoff, fs, order=5):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='high', analog=False)
    y = lfilter(b, a, data)
    return y


#==============================================================================
#
#==============================================================================

def _print(*args, **kwargs):
    msg = ' '.join(map(str, args))
    if kwargs.get('newline', False):
        msg = "%s\n" % msg
    else:
        msg = "%s " % msg
    sys.stdout.write(msg)
    sys.stdout.flush()

def _println(*args):
    _print(*args, newline=True)


#===============================================================================
# Helper functions. Mostly Numpy data manipulation.
#===============================================================================

def ide2csv(filename, savePath=None, importCallback=SimpleUpdater(),
            channel=0, subchannels=(2,1,0)):
    """ Wrapper for quickly dumping IDE data to CSV.
    """
    saveFilename = changeFilename(filename, ".csv", savePath)
    doc = importFile(filename, updater=importCallback)
    a = doc.channels[channel].getSession()
    with open(saveFilename, 'wb') as fp:
        rows, _ = a.exportCsv(fp, subchannels=subchannels)
    doc.ebmldoc.close()
    return saveFilename, rows


def from2diter(data, rows=None, cols=1):
    """ Build a 2D `numpy.ndarray` from an iterator (e.g. what's produced by
        `EventList.itervalues`).

        @todo: This is not the best implementation; even though
            'numpy.fromiter()` doesn't support 2D arrays, there may be
            something else in Numpy for doing this.
    """
    if rows is None:
        if hasattr(data, '__len__'):
            rows = len(data)

    # Build a 2D array. Numpy's `fromiter()` is 1D, but there's probably a
    # better way to do this.
    dataIter = iter(data)
    row1 = dataIter.next()
    if isinstance(row1, Iterable):
        cols = len(row1)

    points = np.zeros(shape=(rows,cols), dtype=float)
    points[0,:] = row1

    for i, row in enumerate(dataIter,1):
        points[i,:] = row

    return points


#===============================================================================
#
#===============================================================================

def dump_csv(data, filename):
    stacked = np.hstack((data[:,0].reshape((-1,1))*.000001,
                         data[:,3].reshape((-1,1)),
                         data[:,2].reshape((-1,1)),
                         data[:,1].reshape((-1,1))))
    np.savetxt(filename, stacked, delimiter=',')


#===============================================================================
# 
#===============================================================================

class CalFile(object):
    """ One analyzed IDE file.
    """
    # RMS value of closed loop calibration
    REFERENCE_RMS = 7.075
#     REFERENCE_RMS = 10*(2**.5)/2
    REFERENCE_OFFSET = 1.0

    def __init__(self, filename, serialNum, dcOnly=False, skipSamples=5000,
                 rms=REFERENCE_RMS):
        """ Constructor.
            @param filename: The IDE file to read.
            @param serialNum: The recorder's serial number (string).
            @keyword skipSamples: The number of samples to skip before the data
                used in the calibration. Used to work around sensor settling
                time.
        """
        self.filename = filename
        self.basename = os.path.basename(filename)
        self.name = os.path.splitext(self.basename)[0]
        self.serialNum = serialNum
        self.skipSamples = skipSamples
        self.dcOnly = dcOnly
        self.referenceRMS = rms
        
        self.sampleRates = {}
        self.analyze()


    def __str__(self):
        try:
            return '%s %8.4f %8.4f %8.4f %8.4f %8.4f %8.4f' % \
                ((self.name,) + tuple(self.rms) + tuple(self.cal))
        except (TypeError, AttributeError):
            return super(self, CalFile).__str__()


    def __repr__(self):
        try:
            return "<%s %s at 0x%08x>" % (self.__class__.__name__,
                                          os.path.basename(self.filename),
                                          id(self))
        except TypeError:
            return super(CalFile, self).__repr__()


    @classmethod
    def flattened(cls, data, rows=None, cols=4):
        """ Given accelerometer data, with each event (time, (z,y,x)), produce an
            array that's (time, z, y, x)
        """
        result = np.zeros(shape=(len(data),cols), dtype=float)
        for i, row in enumerate(data):
            result[i,0] = row[0]
            result[i,1:] = row[1]
        return result


    @classmethod
    def flattenedIndexed(cls, data, rows=None, cols=4):
        """ Given accelerometer data, with each event (time, (z,y,x)), produce
            an array that's (index, time, z, y, x)
        """
        result = np.zeros(shape=(len(data),cols+1), dtype=float)
        for i, row in enumerate(data):
            result[i,0] = i
            result[i,1] = row[0]
            result[i,2:] = row[1]
        return result


    @classmethod
    def getFirstIndex(cls, a, fun, col):
        """ Return the index of the first item in the given column that passes the
            given test.
        """
        it = np.nditer(a[:,col], flags=['f_index'])
        while not it.finished:
            if fun(it[0]):
                return it.index
            it.iternext()
        return 0


    @classmethod
    def calculateRMS(cls, data, axis=None):
        return np.sqrt(np.mean(data**2, axis=axis))


    @classmethod
    def calculateWindowedRMS(cls, a, window_size=2):
        """ Calculate a moving window RMS. Ported from MLeB's MATLAB.
            NOT IN USE.
        """
        a2 = np.power(a,2)
        window = np.ones(window_size)/float(window_size)
        return np.sqrt(np.convolve(a2, window, 'valid'))


    def getHighAccelerometer(self):
        """ Get the high-G accelerometer channel.
        """
        # TODO: Actually check sensor descriptions to get channel ID
        if 0 in self.doc.channels:
            # Old SSX firmware. Probably won't appear again.
            return self.doc.channels[0]
        elif 8 in self.doc.channels:
            # New SSX firmware.
            return self.doc.channels[8]
        elif self.doc.recorderInfo['PartNumber'].startswith('LOG-0003'):
            # Probably a Slam Stick C.
            return None

        raise TypeError("Accelerometer channel not where expected!")


    def getLowAccelerometer(self):
        """ Get the high-G accelerometer channel.
        """
        # TODO: Actually check sensor descriptions to get channel ID
        if 32 in self.doc.channels:
            return self.doc.channels[32]
        if len(self.doc.channels) == 2:
            return None
        else:
            raise TypeError("Low-g accelerometer channel not where expected!")


    def getPressTempChannel(self):
        """ Get the pressure/temperature channel.
        """
        # TODO: Actually check sensor descriptions to get channel ID
        if 1 in self.doc.channels:
            # Old firmware
            return self.doc.channels[1]
        elif 36 in self.doc.channels:
            # New firmware
            return self.doc.channels[36]
        else:
            raise TypeError("Temp/Pressure channel not where expected!")


    def getAxisIds(self, channel):
        """ Get the IDs for the accelerometer X, Y, and Z subchannels. The order
            differs on revisions of SSX.
        """
        ids = XYZ(-1,-1,-1)
        for subc in channel.subchannels:
            errmsg = "Found multiple %%s axes: %%r and %r" % subc.id
            if 'X' in subc.name:
                if ids.x == -1:
                    ids.x = subc.id
                else:
                    raise KeyError(errmsg % ('X', ids.x))
            elif 'Y' in subc.name:
                if ids.y == -1:
                    ids.y = subc.id
                else:
                    raise KeyError(errmsg % ('Y', ids.y))
            elif 'Z' in subc.name:
                if ids.z == -1:
                    ids.z = subc.id
                else:
                    raise KeyError(errmsg % ('Z', ids.z))
        if -1 in ids:
            raise TypeError("Channel did not contain X, Y, and Z subchannels!")
        return ids


    def analyze(self):
        """ An attempt to port the analysis loop of SSX_Calibration.m to Python.

            @return: The calibration constants tuple and the mean temperature.
        """
        # XXX: REMOVE
        self.lowpass = XYZ()

        _print("importing %s... " % os.path.basename(self.filename))
        self.doc = importFile(self.filename)

        if not self.dcOnly:
            accelChannel = self.getHighAccelerometer()
        else:
            accelChannel = None
        if accelChannel:
            self.hasHiAccel = True
            
            # HACK: Is the analog accelerometer piezoresistive?
            self.hasPRAccel = "3255A" in accelChannel[0].sensor.name 
            
            _print("\nAnalyzing high-g data...")

            # HACK: Fix typo in template the hard way
            accelChannel.transform.references = (0,)
            accelChannel.updateTransforms()

            self.accel, self.times, self.rms, self.cal, self.means = self._analyze(accelChannel, skipSamples=self.skipSamples)
        else:
            self.hasHiAccel = False
            self.hasPRAccel = False

        loAccelChannel = self.getLowAccelerometer()
        if loAccelChannel:
            self.hasLoAccel = True
            _print("\nAnalyzing low-g data...")
            self.accelLo, self.timesLo, self.rmsLo, self.calLo, self.meansLo = self._analyze(loAccelChannel, thres=6, start=1000, length=1000)

            if not self.hasHiAccel:
                print "no hi accelerometer"
                self.accel = XYZ(self.accelLo)
                self.times = XYZ(self.timesLo)
                self.rms = XYZ(self.rmsLo)
                self.cal = XYZ(self.calLo)
                self.means = XYZ(self.meansLo)
        else:
            self.hasLoAccel = False

        pressTempChannel = self.getPressTempChannel()
        self.cal_temp = np.mean([x[-1] for x in pressTempChannel[1].getSession()])
        self.cal_press = np.mean([x[-1] for x in pressTempChannel[0].getSession()])


    def getOffsets(self, data, sampRate, lowpass=2.55):
        """ Calculate offsets (means).
        """
        means = XYZ()
        if lowpass:
            _print("Applying low pass filter... ")
            for i in range(1, data.shape[1]):
                filtered = lowpassFilter(data[:,i], lowpass, sampRate)
                self.lowpass[i-1] = filtered
                means[i-1] = np.abs(filtered[int(sampRate*2):int(sampRate*3)]).mean()
        else:
            _print("Calculating means... ")
            for i in range(1, data.shape[1]):
                means[i-1] = np.abs(data[int(sampRate*2):int(sampRate*3),i]).mean()
        return means


    def _analyze(self, accelChannel, thres=4, start=5000, length=5000,
                 skipSamples=0, highpass=10, lowpass=2.55):
        """ Analyze one accelerometer channel.

            An attempt to port the analysis loop of SSX_Calibration.m to Python.

            @param accelChannel:
            @keyword thres: (gs) acceleration detection threshold (trigger for
                finding which axis is calibrated).
            @keyword start: Look # data points ahead of first index match after
                finding point that exceeds threshold.
            @keyword length: The number of samples to use.
        """
        stop = start + length  # Look # of data points ahead of first index match
        axisIds = self.getAxisIds(accelChannel)

        # Turn off existing per-channel calibration (if any)
        for c in accelChannel.children:
            c.setTransform(None)
        accelChannel.updateTransforms()

        a = accelChannel.getSession()
#         a.removeMean = True
#         a.rollingMeanSpan = -1
        a.removeMean = False
        sampRate = self.sampleRates[accelChannel] = a.getSampleRate()
        
        if sampRate < 1000:
            raise CalibrationError("Channel %s (%s) had a low sample rate: %s Hz" 
                                   % (accelChannel.id, accelChannel.name, sampRate))
        
        data = self.flattened(a, len(a))
        _print("%d samples imported. " % len(data))

        means = self.getOffsets(data, sampRate, lowpass)

        times = data[:,0] * .000001

        if highpass:
            _print("Applying high pass filter... ")
            for i in range(1, data.shape[1]):
                data[:,i] = highpassFilter(data[:,i], highpass, sampRate)

        # HACK: Some  devices have a longer delay before Z settles.
        if skipSamples:
            data = data[skipSamples:]

        _print("getting indices... ")
        gt = lambda(x): x > thres
        # Column 0 is the time, so axis columns are offset by 1
        indices = XYZ(
            self.getFirstIndex(data, gt, axisIds.x+1),
            self.getFirstIndex(data, gt, axisIds.y+1),
            self.getFirstIndex(data, gt, axisIds.z+1)
        )

        _print("Indices: %s %s %s" % (indices.x + start + skipSamples,
                                      indices.y + start + skipSamples,
                                      indices.z + start + skipSamples))
        # XXX: What's this actually doing? Do they need the same start?
        if indices.x == indices.y == 0:
            indices.x = indices.y = indices.z
        if indices.x == indices.z == 0:
            indices.x = indices.z = indices.y
        if indices.y == indices.z == 0:
            indices.y = indices.z = indices.x
#         indices.x = indices.y = indices.z = max(indices)

        accel = XYZ(data[(indices.x+start):(indices.x+stop),axisIds.x+1],
                    data[(indices.y+start):(indices.y+stop),axisIds.y+1],
                    data[(indices.z+start):(indices.z+stop),axisIds.z+1])

        times = XYZ(times[(indices.x+start):(indices.x+stop)],
                    times[(indices.y+start):(indices.y+stop)],
                    times[(indices.z+start):(indices.z+stop)])

        _print("computing RMS...")
        rms = XYZ(self.calculateRMS(accel.x),
                  self.calculateRMS(accel.y),
                  self.calculateRMS(accel.z))

        cal = XYZ(self.referenceRMS / rms.x,
                  self.referenceRMS / rms.y,
                  self.referenceRMS / rms.z)

        print
        return accel, times, rms, cal, means


    def render(self, imgPath, baseName='vibe_test_', imgType="png"):
        """ Create a plot of each axis.
        """
        imgName = '%s%s.%s' % (baseName, os.path.splitext(os.path.basename(self.filename))[0], imgType)
        saveName = os.path.join(imgPath, imgName)

        # Generate the plot
#         _print("plotting...")
        plotXMin = min(self.times.x[0], self.times.y[0], self.times.z[0])
        plotXMax = max(self.times.x[-1], self.times.y[-1], self.times.z[-1])
        plotXPad = (plotXMax-plotXMin) * 0.01
        fig = pylab.figure(figsize=(8,6), dpi=80, facecolor="white")
        pylab.suptitle("File: %s, SN: %s" % (os.path.basename(self.filename), self.serialNum), fontsize=24)
        pylab.subplot(1,1,1)
        pylab.xlim(plotXMin-plotXPad, plotXMax+plotXPad)
        pylab.plot(self.times.x, self.accel.x, color="red", linewidth=1.5, linestyle="-", label="X-Axis")
        pylab.plot(self.times.y, self.accel.y, color="green", linewidth=1.5, linestyle="-", label="Y-Axis")
        pylab.plot(self.times.z, self.accel.z, color="blue", linewidth=1.5, linestyle="-", label="Z-Axis")
        pylab.legend(loc='upper right')

        axes = fig.gca()
        axes.set_xlabel('Time (seconds)')
        axes.set_ylabel('Amplitude (g)')

        pylab.savefig(saveName)
#         pylab.show()

        return saveName


#===============================================================================
#
#===============================================================================

class Calibrator(object):
    """
    Example calibration line from Excel document (in 2 columns to save width):
        Cal #:                    3
        Rev:                      A
        Cal Date:                 6/16/2014
        Serial #:                 SSX0000011
        Hardware:                 4
        Firmware:                 1
        Product Name:             Slam Stick X (100g)
        Part Number:              LOG-0002-100G
        Date of Manufacture:      n/a
        Ref Manufacturer:         ENDEVCO
        Ref Model #:              7251A-10/133
        Ref Serial #:             12740/BL33
        NIST #:                   683/287323
        832M1 Serial #:           3951-005
        Temp. (C):                23.5
        Rel. Hum. (%):            45
        Temp Compensation (%/C): -0.30
        X - Axis:                 1.3791
        Y - Axis:                 1.1545
        Z - Axis:                 1.3797

    TODO: check if 'Ref' values are constant.
    """

    # TODO: Get these from the device data (or calibration recordings)
    accelHiCalIds = XYZ(1, 2, 3)
    accelLoCalIds = XYZ(33, 34, 35)


    def __init__(self, devPath=None,
                 certNum=0,
                 calRev="C",
                 isUpdate=False,
                 calHumidity=DEFAULT_HUMIDITY,
                 calTempComp=-0.30,
                 documentNum="LOG-0002-601",
                 procedureNum="300-601-502",
                 refMan="ENDEVCO",
                 refModel="7251A-10/133",
                 refSerial="12740/BL33",
                 refNist="683/287323",
                 skipSamples=5000,
                 productSerialNum=None):
        self.devPath = devPath
        self.productSerialNum = productSerialNum
        self.productSerialInt = None
        self.certNum = certNum
        self.isUpdate=False

        self.documentNum = documentNum
        self.procedureNum = procedureNum

        self.calRev = calRev
        self.meanCalTemp = 21
        self.calTempComp = calTempComp
        self.calHumidity = calHumidity

        self.refMan = refMan
        self.refModel = refModel
        self.refSerial = refSerial
        self.refNist = refNist

        self.calTimestamp = time.time()
        self.productManTimestamp = 0
        self.calFilesUnsorted = self.calFiles = self.filenames = None
        self.hasHiAccel = self.hasLoAccel = self.hasPRAccel = None

        self.skipSamples = skipSamples

        if devPath is not None:
            self.readManifest()

        if self.productSerialInt is None and self.productSerialNum is not None:
            self.productSerialInt = int(self.productSerialNum.strip(string.ascii_letters+string.punctuation))

        self.accelSerial = None
        self.meanCalPress = self.meanCalTemp = None
        self.cal = XYZ(None, None, None)
        self.calLo = XYZ(None, None, None)
        self.offsets = XYZ(None, None, None)
        self.offsetsLo = XYZ(None, None, None)


    def getFiles(self, path=None):
        """ Get the filenames from the first recording directory with 3 IDE
            files. These are presumably the shaker recordings.
        """
        path = self.devPath if path is None else path
        ides = []
        for root, dirs, files in os.walk(os.path.join(path, 'DATA')):
            ides.extend(map(lambda x: os.path.join(root, x), filter(lambda x: x.upper().endswith('.IDE'), files)))
            for d in dirs:
                if d.startswith('.'):
                    dirs.remove(d)
        return ides[-3:]


    def closeFiles(self):
        if self.calFiles:
            for c in self.calFiles:
                try:
                    c.doc.close()
                except Exception:
                    pass


    def readManifest(self):
        """ Read the user page containing the manifest and (possibly)
            calibration data.

        """
        self.device = devices.getDevices([self.devPath])[0]

        manifest = self.device.getManifest()
        calibration = self.device.getCalibration()

        systemInfo = manifest['SystemInfo']
        systemInfo['FwRev'] = self.device.firmwareVersion
        self.productManTimestamp = systemInfo['DateOfManufacture']

        sensorInfo = manifest.get('AnalogSensorInfo', [])
        if len(sensorInfo) > 0:
            self.accelSerial = ' '.join([si.get('AnalogSensorSerialNumber', None) for si in sensorInfo])
        else:
            self.accelSerial = None

        self.productManDate = datetime.utcfromtimestamp(self.productManTimestamp).strftime("%m/%d/%Y")
        self.productSerialNum = self.device.serial
        self.productSerialInt = self.device.serialInt

        return manifest, calibration

    #===========================================================================
    #
    #===========================================================================

    def sortCalFiles(self, calFiles, thresh=2):
        """
        """
        sortedFiles = XYZ()

        try:
            for i in range(3):
                sortedFiles[i] = min(calFiles, key=lambda c: c.cal[i])
        except AttributeError:
            for i in range(3):
                sortedFiles[i] = min(calFiles, key=lambda c: c.calLo[i])

#         for c in calFiles:
#             if c.cal.x <= thresh:
#                 sortedFiles.x = c
#             if c.cal.y <= thresh:
#                 sortedFiles.y = c
#             if c.cal.z <= thresh:
#                 sortedFiles.z = c

        return sortedFiles


    def calculateTrans(self, calFiles, cal, thresh=2, dc=False):
        """ Calculate the transverse sensitivity.
        """
        def calc_trans(a, b, c, a_corr, b_corr, c_corr):
            a_cross = a * a_corr
            b_cross = b * b_corr
            c_ampl =  c * c_corr
            Stab = (np.sqrt(((a_cross)**2)+((b_cross)**2)))
            Stb = 100 * (Stab/c_ampl)
            return Stb

        if dc:
            xRms = calFiles.x.rmsLo
            yRms = calFiles.y.rmsLo
            zRms = calFiles.z.rmsLo
        else:
            xRms = calFiles.x.rms
            yRms = calFiles.y.rms
            zRms = calFiles.z.rms

        Sxy = calc_trans(zRms.x, zRms.y, zRms.z, cal.x, cal.y, cal.z)
        Syz = calc_trans(xRms.y, xRms.z, xRms.x, cal.y, cal.z, cal.x)
        Sxz = calc_trans(yRms.z, yRms.x, yRms.y, cal.z, cal.x, cal.y)

        return (Sxy, Syz, Sxz)


    def calculate(self, filenames=None, prev_cal=(1,1,1), prev_cal_lo=(1,1,1)):
        """ Calculate the high-g accelerometer!
        """
        # TODO: Check for correct number of files?
        self.calDate = datetime.now()
        self.calTimestamp = int(time.mktime(time.gmtime()))

        if filenames is None:
            filenames = self.getFiles()

        self.calFilesUnsorted = [CalFile(f, self.productSerialNum,
                                         skipSamples=self.skipSamples) for f in filenames]

        # All CalFiles will have 'non-Lo' calibration values. For SSC, these
        # will be the same as the DC accelerometer values.
        self.calFiles = self.sortCalFiles(self.calFilesUnsorted)
        self.filenames = XYZ((os.path.basename(c.filename) for c in self.calFiles))
        self.cal = XYZ([self.calFiles[i].cal[i] * prev_cal[i] for i in range(3)])
        self.hasHiAccel = all((c.hasHiAccel for c in self.calFiles))
        self.hasLoAccel = all((c.hasLoAccel for c in self.calFiles))
        self.hasPRAccel = all((c.hasPRAccel for c in self.calFiles))
        
        self.Sxy, self.Syz, self.Sxz = self.calculateTrans(self.calFiles, self.cal)
        self.Syz_file, self.Sxz_file, self.Sxy_file = self.filenames

        self.meanCalTemp = np.mean([cal.cal_temp for cal in self.calFiles])
        self.meanCalPress = np.mean([cal.cal_press for cal in self.calFiles])

        # Invert flipped axes
        if self.hasHiAccel:
            self.cal.z *= -1
            if self.hasPRAccel:
                self.cal.x *= -1

        self.offsets = XYZ()
        for i in range(3):
            self.offsets[i] = 1.0 - (self.cal[i] * self.calFiles[i].means[i])

        self.offsetsLo = XYZ(None, None, None)
        self.calLo = XYZ(None, None, None)
        self.SxyLo = self.SyzLo = self.SxzLo = None

        if self.hasHiAccel and not self.hasLoAccel:
            return

        self.calLo = XYZ([self.calFiles[i].calLo[i] * prev_cal_lo[i] for i in range(3)])
        self.SxyLo, self.SyzLo, self.SxzLo = self.calculateTrans(self.calFiles, self.calLo, dc=True)

        for i in range(3):
            self.offsetsLo[i] = 1.0 - (self.calLo[i] * self.calFiles[i].meansLo[i])


    #===========================================================================
    #
    #===========================================================================

    def createCalLogEntry(self, filename, chipId, mode='at'):
        """ Record this calibration session in the log file.
        """
        l = map(str, (time.asctime(), self.calTimestamp, chipId,
                      self.productSerialInt, self.isUpdate, self.certNum))
        writeFileLine(filename, ','.join(l), mode=mode)


    #===========================================================================
    #
    #===========================================================================


    def createTxt(self, saveTo=None):
        """ Generate the calibration text, optionally saving it to a file.
        """
        if isinstance(saveTo, basestring):
            if self.calTimestamp is None:
                self.calTimestamp = time.time()
            dt = datetime.utcfromtimestamp(self.calTimestamp)
            saveName = 'calibration_%s.txt' % ''.join(filter(lambda x:x not in string.punctuation, dt.isoformat()[:19]))
            saveTo = os.path.join(saveTo, saveName)

        result = ['Serial Number: %s' % self.productSerialNum,
                  'Date: %s' % time.asctime(),
                  '    File    X-rms    Y-rms    Z-rms    X-cal    Y-cal    Z-cal']

        result.extend(map(str, self.calFiles))
        if self.hasHiAccel:
            result.append("Analog Accelerometer:")
            if self.hasPRAccel:
                result.append("%s, X Axis Calibration Constant %.6f, offset %.6f" % (self.filenames.x, self.cal.x, self.offsets.x))
                result.append("%s, Y Axis Calibration Constant %.6f, offset %.6f" % (self.filenames.y, self.cal.y, self.offsets.y))
                result.append("%s, Z Axis Calibration Constant %.6f, offset %.6f" % (self.filenames.z, self.cal.z, self.offsets.z))
            else:
                result.append("%s, X Axis Calibration Constant %.6f" % (self.filenames.x, self.cal.x))
                result.append("%s, Y Axis Calibration Constant %.6f" % (self.filenames.y, self.cal.y))
                result.append("%s, Z Axis Calibration Constant %.6f" % (self.filenames.z, self.cal.z))
            result.append("%s, Transverse Sensitivity in XY = %.6f percent" % (self.Sxy_file, self.Sxy))
            result.append("%s, Transverse Sensitivity in YZ = %.6f percent" % (self.Syz_file, self.Syz))
            result.append("%s, Transverse Sensitivity in ZX = %.6f percent" % (self.Sxz_file, self.Sxz))
            result.append('')

        if self.hasLoAccel:
            result.append('DC Accelerometer:')
            result.append("%s, X Axis Calibration Constant %.6f, offset %.6f" % (self.filenames.x, self.calLo.x, self.offsetsLo.x))
            result.append("%s, Y Axis Calibration Constant %.6f, offset %.6f" % (self.filenames.y, self.calLo.y, self.offsetsLo.y))
            result.append("%s, Z Axis Calibration Constant %.6f, offset %.6f" % (self.filenames.z, self.calLo.z, self.offsetsLo.z))
            result.append("%s, Transverse Sensitivity in XY = %.2f percent" % (self.Sxy_file, self.SxyLo))
            result.append("%s, Transverse Sensitivity in YZ = %.2f percent" % (self.Syz_file, self.SyzLo))
            result.append("%s, Transverse Sensitivity in ZX = %.2f percent" % (self.Sxz_file, self.SxzLo))

        result = '\n'.join(result)

        if isinstance(saveTo, basestring):
            writeFile(saveTo, result)
            return saveTo
        if hasattr(saveTo, 'write'):
            saveTo.write(result)

        return result


    #===========================================================================
    #
    #===========================================================================

    def createPlots(self, savePath='.'):
        """ Render plots of each calibration file.
        """
        if self.calFiles is None:
            return False
        return [c.render(savePath) for c in self.calFiles]


    #===========================================================================
    #
    #===========================================================================

    @classmethod
    def getCertTemplate(cls, device, path=''):
        """ Get the specific certification template SVG for the recording
            device being calibrated.
        """
        if not isinstance(device, devices.SlamStickX):
            raise TypeError("%r is a SlamStick derivative!" % \
                            device.__class__.__name__)
        if isinstance(device, devices.SlamStickS):
            if device.getAccelChannel(dc=True):
                n = "Slam-Stick-S+DC-Calibration-template.svg"
            else:
                n = "Slam-Stick-S-Calibration-template.svg"
        elif isinstance(device, devices.SlamStickC):
            n = "Slam-Stick-C-Calibration-template.svg"
        elif device.getAccelChannel(dc=True):
            n = "Slam-Stick-X+DC-Calibration-template.svg"
        elif device.getAccelChannel(dc=False):
            n = "Slam-Stick-X-Calibration-template.svg"
        else:
            raise TypeError("Can't find a certificate template for %s" % \
                            device.__class__.__name__)

        n = os.path.join(path, n)
        if not os.path.exists(n):
            raise IOError("Could not find template %s" % n)

        return n


    def createCertificate(self, savePath='.', createPdf=True,
                          template="Slam-Stick-X-Calibration-template.svg"):
        """ Create the certificate PDF from the template. The template SVG
            contains `<tspan>` elements with IDs beginning with `FIELD_` which
            get filled in from attributes of this object.

            Fields are:
                'FIELD_calHumidity',
                'FIELD_calTemp',
                'FIELD_calTempComp',
                'FIELD_cal_x',
                'FIELD_cal_y',
                'FIELD_cal_z',
                'FIELD_certificateNum',
                'FIELD_documentNum',
                'FIELD_procedureNum',
                'FIELD_productCalDate',
                'FIELD_productMan',
                'FIELD_productManDate',
                'FIELD_productName',
                'FIELD_productPartNum',
                'FIELD_productSerial',
                'FIELD_refModel',
                'FIELD_refNist',
                'FIELD_refSerial',
                'FIELD_referenceMan'

            For DC accelerometer:
                'FIELD_cal_x_dc',
                'FIELD_cal_y_dc',
                'FIELD_cal_z_dc',
                'FIELD_offset_x_dc',
                'FIELD_offset_y_dc',
                'FIELD_offset_z_dc'
            
            For piezoresistive accelerometer:
                'FIELD_offset_x',
                'FIELD_offset_y',
                'FIELD_offset_z'
            
        """
        xd = ET.parse(template)
        xr = xd.getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}

        # Old version used IDs on the actual `tspan` elements. New versions
        # use the ID on the parent `text` element, which can be set in Inkscape
        # so the SVG files don't require (much) hand-editing.
        # TODO: Get rid of this code debt.
        try:
            oldStyle = xr.find(".//*[@id='FIELD_productSerial']").tag.endswith("tspan")
        except AttributeError:
            oldStyle = False

        def setTextOld(elId, t):
            t = saxutils.escape(str(t).strip())
            el = xr.find(".//*[@id='%s']" % elId)
            if el is not None:
                el.text=t
            else:
                print "could not find field %r in template (probably okay)" % elId

        def setText(elId, t):
            t = saxutils.escape(str(t).strip())
            el = xr.find(".//*[@id='%s']/svg:tspan" % elId, ns)
            if el is not None:
                el.text = t
            else:
                print "could not find field %r in template (probably okay)" % elId

        certTxt = "C%05d" % self.certNum

        if isinstance(self.calTimestamp, basestring):
            caldate = self.calTimestamp
        else:
            caldate = datetime.utcfromtimestamp(self.calTimestamp).strftime("%m/%d/%Y")

        fieldIds = [
            ('FIELD_calHumidity', self.calHumidity),
            ('FIELD_calTemp', "%.2f" % self.meanCalTemp),
            ('FIELD_calTempComp', "%.2f" % self.calTempComp),
            ('FIELD_cal_x', "%.4f" % self.cal.x),
            ('FIELD_cal_y', "%.4f" % self.cal.y),
            ('FIELD_cal_z', "%.4f" % self.cal.z),
            ('FIELD_certificateNum', certTxt),
            ('FIELD_productCalDate', caldate),
            ('FIELD_productManDate', self.productManDate),
            ('FIELD_productName', self.device.productName),
            ('FIELD_productPartNum', self.device.partNumber),
            ('FIELD_productSerial', self.productSerialNum),
#             ('FIELD_documentNum', self.documentNum),
#             ('FIELD_procedureNum', self.procedureNum),
#             ('FIELD_productMan', 'Mide Technology Corp.'),
#             ('FIELD_refModel', self.refModel),
            ('FIELD_refNist', self.refNist),
#             ('FIELD_refSerial', self.refSerial),
#             ('FIELD_referenceMan', self.refMan),
        ]

        if self.hasLoAccel:
            fieldIds.extend([
                ('FIELD_cal_x_dc', "%.4f" % self.calLo.x),
                ('FIELD_cal_y_dc', "%.4f" % self.calLo.y),
                ('FIELD_cal_z_dc', "%.4f" % self.calLo.z),
                ('FIELD_offset_x_dc', "%.4f" % self.offsetsLo.x),
                ('FIELD_offset_y_dc', "%.4f" % self.offsetsLo.y),
                ('FIELD_offset_z_dc', "%.4f" % self.offsetsLo.z)
            ])

        if self.hasPRAccel:
            fieldIds.extend([
                ('FIELD_offset_x', "%.4f" % self.offsets.x),
                ('FIELD_offset_y', "%.4f" % self.offsets.y),
                ('FIELD_offset_z', "%.4f" % self.offsets.z)
            ])


        if oldStyle:
            for name, val in fieldIds:
                setTextOld(name, val)
        else:
            for name, val in fieldIds:
                setText(name, val)

        tempFilename = os.path.realpath(changeFilename(template.replace('template',certTxt), path=savePath))
        if os.path.exists(tempFilename):
            os.remove(tempFilename)
        xd.write(tempFilename)

        if createPdf:
            return self.convertSvg(tempFilename)

        return tempFilename


    @classmethod
    def recreateCertificate(cls, device, logFile, savePath='.', createPdf=True,
                            template="Slam-Stick-X-Calibration-template.svg"):
        """ Recreate a certificate from the calibration log. In case of updated
            templates, or if a failure prevented the certificate from being
            generated during calibration.
        """
        caldata = findCalLog(logFile, val=device.serialNum)
        if not caldata:
            raise KeyError("Could not find device SN %s in log" % device.serialNum)

        c = cls()
        c.device = device
        c.certNum = caldata.get('Cal #', None)
        c.calRev = caldata.get('Rev', None)
        caldate = caldata.get('Cal Date', None)
        mandate = caldata.get('Date of Manufacture', None)
        c.productSerialNum = caldata.get('Serial #', None)
        c.device.hardwareVersion = caldata.get('Hardware', None)
        c.device.firmwareVersion = caldata.get('Firmware', None)
        c.device.productName = caldata.get('Product Name', None)
        c.device.partNumber = caldata.get('Part Number', None)
        c.refMan = caldata.get('Ref Manufacturer', None)
        c.refModel = caldata.get('Ref Model #', None)
        c.refSerial = caldata.get('Ref Serial #', None)
        c.refNist = caldata.get('NIST #', None)
        c.accelSerial = caldata.get('832M1 Serial #', None)
        c.meanCalTemp = caldata.get('Temp. (C)', None)
        c.calHumidity = caldata.get('Rel. Hum. (%)', None)
        c.calTempComp = caldata.get('Temp Comp. (%/C)', None)
        c.cal.x = caldata.get('X-Axis', None)
        c.cal.y = caldata.get('Y-Axis', None)
        c.cal.z = caldata.get('Z-Axis', None)
        c.meanCalPress = caldata.get('Pressure (Pa)', None)
        c.calLo.x = caldata.get('X-Axis (DC)', None)
        c.calLo.y = caldata.get('Y-Axis (DC)', None)
        c.calLo.z = caldata.get('Z-Axis (DC)', None)
        c.offsetsLo.x = caldata.get('X Offset (DC)', None)
        c.offsetsLo.y = caldata.get('Y Offset (DC)', None)
        c.offsetsLo.z = caldata.get('Z Offset (DC)', None)
        c.offsets.x = caldata.get('X Offset', None)
        c.offsets.y = caldata.get('Y Offset', None)
        c.offsets.z = caldata.get('Z Offset', None)

        c.productManDate = mandate.split()[0]
        c.calTimestamp = caldate.split(' ',1)[0]

        if template is None:
            template = cls.getCalTemplate(device)

        c.createCertificate(savePath, createPdf, template)



    @classmethod
    def convertSvg(cls, svgFilename, removeSvg=True):
        """ Helper method to convert SVG to PDF using Inkscape. Separated
            from createCertificate because the conversion will sometimes
            crash hard.
        """
        certFilename = changeFilename(svgFilename, ext='.pdf')
        if os.path.exists(certFilename):
            os.remove(certFilename)

        errfile = os.path.join(tempfile.gettempdir(), 'svg_err.txt')
        with open(errfile,'wb') as f:
            result = subprocess.call('"%s" -f "%s" -A "%s"' % (INKSCAPE_PATH, svgFilename, certFilename),
                                     stdout=sys.stdout, stdin=sys.stdin, shell=True)

        if result != 0:
            with open(errfile, 'rb') as f:
                err = f.read().replace('\n',' ')
            raise IOError(err)

        if removeSvg and result == 0 and os.path.exists(certFilename):
            os.remove(svgFilename)
        return certFilename


    def writeProductLog(self, saveTo=None, err=None):
        """
        """
        caldate = str(datetime.utcfromtimestamp(self.calTimestamp))
        mandate = str(datetime.utcfromtimestamp(self.productManTimestamp))

        if getattr(self, 'device', None) is None:
            hardwareVersion = firmwareVersion = None
            productName = partNumber = None
        else:
            hardwareVersion = self.device.hardwareVersion
            firmwareVersion = self.device.firmwareVersion
            productName = self.device.productName
            partNumber = self.device.partNumber

        data = OrderedDict([
                ("Cal #",                self.certNum),
                ("Rev",                  self.calRev),
                ("Cal Date",             caldate),
                ("Serial #",             self.productSerialNum),
                ("Hardware",             hardwareVersion),
                ("Firmware",             firmwareVersion),
                ("Product Name",         productName),
                ("Part Number",          partNumber),
                ("Date of Manufacture",  mandate),
                ("Ref Manufacturer",     self.refMan),
                ("Ref Model #",          self.refModel),
                ("Ref Serial #",         self.refSerial),
                ("NIST #",               self.refNist),
                ("832M1 Serial #",       self.accelSerial),
                ("Temp. (C)",            self.meanCalTemp),
                ("Rel. Hum. (%)",        self.calHumidity),
                ("Temp Comp. (%/C)",     self.calTempComp),
                ("X-Axis",               self.cal.x),
                ("Y-Axis",               self.cal.y),
                ("Z-Axis",               self.cal.z),
                ("Pressure (Pa)",        self.meanCalPress),
                ("X-Axis (DC)",          self.calLo.x),
                ("Y-Axis (DC)",          self.calLo.y),
                ("Z-Axis (DC)",          self.calLo.z),
                ("X Offset (DC)",        self.offsetsLo.x),
                ("Y Offset (DC)",        self.offsetsLo.y),
                ("Z Offset (DC)",        self.offsetsLo.z),
                ("X Offset",             self.offsets.x),
                ("Y Offset",             self.offsets.y),
                ("Z Offset",             self.offsets.z),
                ])

        if err is not None:
            data['Error Message'] = err
        if saveTo is not None:
            newFile = not os.path.exists(saveTo)
            with open(saveTo, 'ab') as f:
                writer = csv.writer(f)
                if newFile:
                    writer.writerow(data.keys())
                writer.writerow(data.values())

        return data


#     def createEbml(self, xmlTemplate=None, schema="idelib.ebml.schema.mide"):
    def createEbml(self, xmlTemplate=None, schema=schema_mide):
        """ Create the calibration EBML data, for inclusion in a recorder's
            user page or an external user calibration file.
        """
        if xmlTemplate is None:
            # No template; generate from scratch. Generally not used.
            print "No template specified; generating calibration from scratch."
            g = round(self.device.getAccelRange()[1])

            calList = OrderedDict([
                ('UnivariatePolynomial', [
                    OrderedDict([('CalID', 9),
                                 ('CalReferenceValue', 0.0),
                                 ('PolynomialCoef', [(g*2.0)/65535.0, -g])]),
                    OrderedDict([('CalID', 32),
                                 ('CalReferenceValue', 0.0),
                                 ('PolynomialCoef', [0.00048828125, 0.0])])
                    ],
                ),
                ('BivariatePolynomial', [] ), # filled in below
             ])
        else:
            if xmlTemplate.lower().endswith('.xml'):
#                 e = xml2ebml.readXml(xmlTemplate, schema=schema)
#                 doc = ebml_util.read_ebml(StringIO(e), schema=schema)
                doc = ebmlite_util.loadXml(xmlTemplate, schema).dump()
            elif xmlTemplate.lower().endswith('.ebml'):
#                 ebml_util.read_ebml(xmlTemplate, schema=schema)
                doc = schema.load(xmlTemplate).dump()
                
            calList = doc['CalibrationList']

        calList['CalibrationSerialNumber'] = self.certNum
        calList['CalibrationDate'] = self.calTimestamp

        # TODO: Calculate from device calibration data?
        tempSubchannelId = 1
        tempChannelId = 36

        # HIGH-G ANALOG ACCELEROMETER
        #----------------------------

        # Z axis is flipped on the PCB. Negate.
#         self.cal.z *= -1
#         if self.hasPRAccel:
#             # SSS also has X axis flipped.
#             self.cal.x *= -1

        # Remove the default high-g accelerometer polynomials.
        bivars = calList.get('BivariatePolynomial', [])
        bivars = [c for c in bivars if c['CalID'] not in (1,2,3)]
        calList['BivariatePolynomial'] = bivars

        univars = calList.get('UnivariatePolynomial', [])
        univars = [c for c in univars if c['CalID'] not in (1,2,3,33,34,35)]
        calList['UnivariatePolynomial'] = univars

        if self.hasPRAccel:
            for i in range(3):
                thisCal = OrderedDict([
                    ('CalID', i+1),
                    ('CalReferenceValue', 0.0),
                    ('PolynomialCoef', [self.cal[i],self.offsets[i]]),
                ])
                calList['UnivariatePolynomial'].append(thisCal)
        elif self.hasHiAccel:
            for i in range(3):
                thisCal = OrderedDict([
                    ('CalID', i+1),
                    ('CalReferenceValue', 0.0),
                    ('BivariateCalReferenceValue', self.calFiles[i].cal_temp),
                    ('BivariateChannelIDRef', tempChannelId),
                    ('BivariateSubChannelIDRef',tempSubchannelId),
                    ('PolynomialCoef', [self.cal[i] * -0.003, self.cal[i], 0.0, 0.0]),
                ])
                calList['BivariatePolynomial'].append(thisCal)

        # Flip Z (and X, if PR) back, just in case.
#         self.cal.z *= -1
#         if self.hasPRAccel:
#             self.cal.x *= -1

        # DIGITAL DC ACCELEROMETER
        #-------------------------
        if self.hasLoAccel:
            for i in range(3):
                thisCal = OrderedDict([
                    ('CalID', i+33),
                    ('CalReferenceValue', 0.0),
                    ('PolynomialCoef', [self.calLo[i], self.offsetsLo[i]]),
                ])
                calList['UnivariatePolynomial'].append(thisCal)

#         return ebml_util.build_ebml('CalibrationList', calList, schema=schema)
        return schema.encodes({'CalibrationList': calList})


    def createEbmlFromFile(self):
        """ Generate proper calibration EBML data, using the calibration info
            in the calibration recordings as a template.

            @todo: Hook this up!
        """
        ideFile = self.calFiles.x
        accelHi = ideFile.getHighAccelerometer()
        axisIds = ideFile.getAxisIds(accelHi)

        # Z axis is flipped on the PCB. Negate.
#         self.cal.z *= -1

        # High-g accelerometer calibration
        for i in range(3):
            t = accelHi[axisIds[i]].transform
            if t is None:
                raise TypeError("Subchannel %d.%d has no transform!", (accelHi.id, axisIds[i]))
            t.coefficients = (self.cal[i] * -0.003, self.cal[i], 0.0, 0.0)
            t.references = (0.0, self.calFiles[i].cal_temp)

        # Flip Z back, just in case.
#         self.cal.z *= -1

        # Low-g accelerometer calibration
        accelLo = ideFile.getLowAccelerometer()
        if accelLo is not None:
            # TODO: This
            pass

        # Do any other calibration stuff.

        return self.device.generateCalEbml(ideFile.doc.transforms,
                                           date=self.calTimestamp,
                                           calSerial=self.self.certNum)


#===============================================================================
#
#===============================================================================

def makeCalTemplateXml(templatePath, partNum, hwRev, dest):
    """ Generate the generic calibration XML.
    """
    filename = os.path.join(templatePath, partNum, str(hwRev), "cal.template.xml")
    shutil.copy(filename, dest)


#===============================================================================
#
#===============================================================================

def generateUserCal():
    """
    """

#===============================================================================
#
#===============================================================================

if __name__ == "__main__":
    print "This is only a library. Don't try to run it!"
    exit(1)
