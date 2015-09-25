'''
Created on Sep 30, 2014

@author: dstokes
'''
from collections import Iterable, OrderedDict
import csv
from datetime import datetime
import os.path
import shutil
import string
import subprocess
import sys
import tempfile
import time

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from xml.etree import ElementTree as ET

import numpy as np
import pylab #@UnresolvedImport - doesn't show up for some reason.

from scipy.signal import butter, lfilter, freqz #@UnresolvedImport

VIEWER_PATH = r"R:\LOG-Data_Loggers\LOG-0002_Slam_Stick_X\Design_Files\Firmware_and_Software\Development\Source\Slam_Stick_Lab"
INKSCAPE_PATH = r"C:\Program Files (x86)\Inkscape\inkscape.exe"

CWD = os.path.abspath(os.path.dirname(__file__))
sys.path.append(CWD)

# Song and dance to make sure the mide_ebml library can be found.
try:
    import mide_ebml
except ImportError:
    if os.path.exists('../mide_ebml'):
        sys.path.append(os.path.abspath('..'))
    elif os.path.exists(os.path.join(CWD, '../mide_ebml')):
        sys.path.append(os.path.abspath(os.path.join(CWD, '../mide_ebml')))
    elif os.path.exists(VIEWER_PATH):
        sys.path.append(VIEWER_PATH)
    import mide_ebml #@UnusedImport

from mide_ebml import util as ebml_util
from mide_ebml import xml2ebml
from mide_ebml.importer import importFile, SimpleUpdater

from glob import glob
testFiles = glob(r"R:\LOG-Data_Loggers\LOG-0002_Slam_Stick_X\Product_Database\_Calibration\SSX0000039\DATA\20140923\*.IDE")

# NOTE: Make sure devices.py is copied to deployed directory
import devices
# from devices.ssx import SlamStickX

from birth_utils import changeFilename, writeFile, writeFileLine

#===============================================================================
# 
#===============================================================================

class XYZ(list):
    """ Helper for making arrays of XYZ less ugly. A mutable named tuple. """
    
    names = ('x','y','z')
    
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
    doc.ebmldoc.stream.file.close()
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
        self.analyze()
    
    
    def __str__(self):
        return '%s %8.4f %8.4f %8.4f %8.4f %8.4f %8.4f' % \
            ((self.name,) + tuple(self.rms) + tuple(self.cal))
    
    
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
        elif len(self.doc.channels) == 2:
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
        _print("importing %s... " % os.path.basename(self.filename))
        self.doc = importFile(self.filename)

        if not self.dcOnly:
            accelChannel = self.getHighAccelerometer()
        else:
            accelChannel = None
        if accelChannel:
            self.hasHiAccel = True
            _print("Analyzing high-g accelerometer data...")
            
            # HACK: Fix typo in template the hard way
            accelChannel.transform.references = (0,)
            accelChannel.updateTransforms()
                
            self.accel, self.times, self.rms, self.cal, self.means = self._analyze(accelChannel, skipSamples=self.skipSamples)
        else:
            self.hasHiAccel = False

        loAccelChannel = self.getLowAccelerometer()
        if loAccelChannel:
            self.hasLoAccel = True
            _print("Analyzing low-g accelerometer data...")
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
        means = XYZ()
        if lowpass:
            _print("Applying low pass filter... ")
            for i in range(1, data.shape[1]):
                means[i-1] = lowpassFilter(data[:,i], lowpass, sampRate)[int(sampRate*2):int(sampRate*3)].mean()
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

        accelChannel.removeMean = False
        self.rawMeans = XYZ([accelChannel[c].getSession().getRangeMinMeanMax(1000000)[1] for c in axisIds])
                    
        a = accelChannel.getSession()
        sampRate = a.getSampleRate()
#         a.removeMean = True
#         a.rollingMeanSpan = -1
        a.removeMean = False
        data = self.flattened(a, len(a))
        
        means = self.getOffsets(data, sampRate, lowpass)
        
        # HACK: Some  devices have a longer delay before Z settles.
        if skipSamples:
            data = data[skipSamples:]

        self.rawMeans = XYZ((data[:sampRate,i].mean() for i in range(1,data.shape[1])))
        
        _print("%d samples imported. " % len(data)) 
        times = data[:,0] * .000001
        
#         if not a.allowMeanRemoval:
#             _print("Doing 'manual' mean removal.")
#             data = data - ([0] + means)
        
        if highpass:
            _print("Applying high pass filter... ")
            for i in range(1, data.shape[1]):
                data[:,i] = highpassFilter(data[:,i], highpass, sampRate)
    
        gt = lambda(x): x > thres
        
        _print("getting indices... ")
        # Column 0 is the time, so axis columns are offset by 1
        indices = XYZ(
            self.getFirstIndex(data, gt, axisIds.x+1),
            self.getFirstIndex(data, gt, axisIds.y+1),
            self.getFirstIndex(data, gt, axisIds.z+1)
        )
        
        if indices.x == indices.y == 0:
            indices.x = indices.y = indices.z
        if indices.x == indices.z == 0:
            indices.x = indices.z = indices.y
        if indices.y == indices.z == 0:
            indices.y = indices.z = indices.x
        
        # Column 0 is the time, so axis columns are offset by 1
        accel = XYZ(data[indices.x+start:indices.x+stop,axisIds.x+1],
                         data[indices.y+start:indices.y+stop,axisIds.y+1],
                         data[indices.z+start:indices.z+stop,axisIds.z+1])
        times = XYZ(times[indices.x+start:indices.x+stop],
                         times[indices.y+start:indices.y+stop],
                         times[indices.z+start:indices.z+stop])
    
        _print("computing RMS...")
        rms = XYZ(self.calculateRMS(accel.x), 
                  self.calculateRMS(accel.y), 
                  self.calculateRMS(accel.z))
        
        cal = XYZ(self.referenceRMS / rms.x, 
                  self.referenceRMS / rms.y, 
                  self.referenceRMS / rms.z)
        
        return accel, times, rms, cal, means
        

    def render(self, imgPath, baseName='vibe_test_', imgType="png"):
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
        NIST #:                   683/283655-13
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
                 calHumidity=50,
                 calTempComp=-0.30,
                 documentNum="LOG-0002-601", 
                 procedureNum="300-601-502", 
                 refMan="ENDEVCO", 
                 refModel="7251A-10/133", 
                 refSerial="12740/BL33", 
                 refNist="683/283655-13",
                 skipSamples=5000):
        self.devPath = devPath
        self.productSerialNum = None
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
    
        self.calTimestamp = 0
        self.calFilesUnsorted = self.calFiles = self.filenames = None
        self.hasHiAccel = self.hasLoAccel = None

        self.skipSamples = skipSamples

        if devPath is not None:
            self.readManifest()
        
        if self.productSerialInt is None and self.productSerialNum is not None:
            self.productSerialInt = int(self.productSerialNum.strip(string.ascii_letters+string.punctuation))
            

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
        
        sensorInfo = manifest.get('AnalogSensorInfo', {})
        self.accelSerial = sensorInfo.get('AnalogSensorSerialNumber', None)
        
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
        
        for i in range(3):
            sortedFiles[i] = min(calFiles, key=lambda c: c.cal[i])
        
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
        
        self.Sxy, self.Syz, self.Sxz = self.calculateTrans(self.calFiles, self.cal)
        self.Syz_file, self.Sxz_file, self.Sxy_file = self.filenames
        
        self.meanCalTemp = np.mean([cal.cal_temp for cal in self.calFiles])
        self.meanCalPress = np.mean([cal.cal_press for cal in self.calFiles])

        if self.hasHiAccel and not self.hasLoAccel:
            return
        
        self.calLo = XYZ([self.calFiles[i].calLo[i] * prev_cal_lo[i] for i in range(3)])
        self.SxyLo, self.SyzLo, self.SxzLo = self.calculateTrans(self.calFiles, self.calLo, dc=True)


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
        result.append("%s, X Axis Calibration Constant %.4f" % (self.filenames.x, self.cal.x))
        result.append("%s, Y Axis Calibration Constant %.4f" % (self.filenames.y, self.cal.y))
        result.append("%s, Z Axis Calibration Constant %.4f" % (self.filenames.z, self.cal.z))
        result.append("%s, Transverse Sensitivity in XY = %.2f percent" % (self.Sxy_file, self.Sxy))
        result.append("%s, Transverse Sensitivity in YZ = %.2f percent" % (self.Syz_file, self.Syz))
        result.append("%s, Transverse Sensitivity in ZX = %.2f percent" % (self.Sxz_file, self.Sxz))
        
        if self.hasLoAccel and not self.hasHiAccel:
            result.append('')
            result.append('DC Accelerometer:')
            result.append("%s, X Axis Calibration Constant %.4f" % (self.filenames.x, self.calLo.x))
            result.append("%s, Y Axis Calibration Constant %.4f" % (self.filenames.y, self.calLo.y))
            result.append("%s, Z Axis Calibration Constant %.4f" % (self.filenames.z, self.calLo.z))
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
         """
        xd = ET.parse(template)
        xr = xd.getroot()
        
        def setText(elId, t):
            xr.find(".//*[@id='%s']" % elId).text=str(t).strip()
        
        certTxt = "C%05d" % self.certNum
        
        fieldIds = [
            ('FIELD_calHumidity', self.calHumidity),
            ('FIELD_calTemp', "%.2f" % self.meanCalTemp),
            ('FIELD_calTempComp', "%.2f" % self.calTempComp),
            ('FIELD_cal_x', "%.4f" % self.cal.x),
            ('FIELD_cal_y', "%.4f" % self.cal.y),
            ('FIELD_cal_z', "%.4f" % self.cal.z),
            ('FIELD_certificateNum', certTxt),
            ('FIELD_productCalDate', datetime.utcfromtimestamp(self.calTimestamp).strftime("%m/%d/%Y")),
            ('FIELD_productManDate', self.productManDate),
            ('FIELD_productName', self.device.productName),
            ('FIELD_productPartNum', self.device.partNumber),
            ('FIELD_productSerial', self.productSerialNum),
#             ('FIELD_documentNum', self.documentNum),
#             ('FIELD_procedureNum', self.procedureNum),
#             ('FIELD_productMan', 'Mide Technology Corp.'),
#             ('FIELD_refModel', self.refModel),
#             ('FIELD_refNist', self.refNist),
#             ('FIELD_refSerial', self.refSerial),
#             ('FIELD_referenceMan', self.refMan),
        ]
        
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


    def writeProductLog(self, saveTo=None):
        """
        """
        caldate = str(datetime.utcfromtimestamp(self.calTimestamp))
        mandate = str(datetime.utcfromtimestamp(self.productManTimestamp))
        
        data = OrderedDict([
                ("Cal #",                self.certNum),
                ("Rev",                  self.calRev),
                ("Cal Date",             caldate),
                ("Serial #",             self.productSerialNum),
                ("Hardware",             self.device.hardwareVersion),
                ("Firmware",             self.device.firmwareVersion),
                ("Product Name",         self.device.productName),
                ("Part Number",          self.device.partNumber),
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
                ("Pressure (Pa)",        self.meanCalPress)])
        
        if saveTo is not None:
            newFile = not os.path.exists(saveTo)
            with open(saveTo, 'ab') as f:
                writer = csv.writer(f)
                if newFile:
                    writer.writerow(data.keys())
                writer.writerow(data.values())
                
        return data


    def createEbml(self, xmlTemplate=None):
        """ Create the calibration EBML data, for inclusion in a recorder's
            user page or an external user calibration file.
        """
        if xmlTemplate is None:
            # No template; generate from scratch. Generally not used.
            g = round(self.device.getAccelRange()[1])
            baseCoefs = [(g*2.0)/65535.0, -g]
             
            calList = OrderedDict([
                ('UnivariatePolynomial', [
                    OrderedDict([('CalID', 9), 
                                 ('CalReferenceValue', 0.0), 
                                 ('PolynomialCoef', baseCoefs)])
                    ]
                ), 
                ('BivariatePolynomial', [] ), # filled in below
             ])
        else:
            if xmlTemplate.lower().endswith('.xml'):
                e = xml2ebml.readXml(xmlTemplate, schema="mide_ebml.ebml.schema.mide")
                doc = ebml_util.read_ebml(StringIO(e), schema='mide_ebml.ebml.schema.mide')
            elif xmlTemplate.lower().endswith('.ebml'):
                ebml_util.read_ebml(xmlTemplate, schema='mide_ebml.ebml.schema.mide')
            calList = doc['CalibrationList']
            
        calList['CalibrationSerialNumber'] = self.certNum
        calList['CalibrationDate'] = self.calTimestamp
        
        # TODO: Calculate from device calibration data?
        channels = self.device.getChannels()
        if 36 in channels:
            tempChannelId = 36
        else:
            tempChannelId = 1
        tempSubchannelId = 1
        
        # HIGH-G ANALOG ACCELEROMETER
        #----------------------------
        
        # Z axis is flipped on the PCB. Negate.
        self.cal.z *= -1

        # Remove the default high-g accelerometer polynomials.
        bivars = calList['BivariatePolynomial']
        bivars = [c for c in bivars if c['CalID'] not in (1,2,3)]
        calList['BivariatePolynomial'] = bivars
        
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

        # Flip Z back, just in case.
        self.cal.z *= -1
        
        # DIGITAL DC ACCELEROMETER
        #-------------------------
        
        # TODO: Handle DC accelerometer calibration.
        
        return ebml_util.build_ebml('CalibrationList', calList, schema='mide_ebml.ebml.schema.mide')


    def createEbmlFromFile(self):
        """ Generate proper calibration EBML data, using the calibration info
            in the calibration recordings as a template. 
            
            @todo: Hook this up!
        """
        ideFile = self.calFiles.x
        accelHi = ideFile.getHighAccelerometer()
        axisIds = ideFile.getAxisIds(accelHi)

        # Z axis is flipped on the PCB. Negate.
        self.cal.z *= -1
                
        # High-g accelerometer calibration
        for i in range(3):
            t = accelHi[axisIds[i]].transform
            if t is None:
                raise TypeError("Subchannel %d.%d has no transform!", (accelHi.id, axisIds[i]))
            t.coefficients = (self.cal[i] * -0.003, self.cal[i], 0.0, 0.0)
            t.references = (0.0, self.calFiles[i].cal_temp)

        # Flip Z back, just in case.
        self.cal.z *= -1
                
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