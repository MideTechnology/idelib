'''
Created on Sep 30, 2014

@author: dstokes
'''
from collections import Iterable, OrderedDict
from datetime import datetime
import os, os.path
from StringIO import StringIO
import string
import struct
import subprocess
import sys
import time

from xml.etree import ElementTree as ET

import numpy as np
import pylab

VIEWER_PATH = "P:/WVR_RIF/04_Design/Electronic/Software/SSX_Viewer"
INKSCAPE_PATH = r"C:\Program Files (x86)\Inkscape\inkscape.exe"

CWD = os.path.abspath(os.path.dirname(__file__))
sys.path.append(CWD)

try:
    import mide_ebml
except ImportError:
    if os.path.exists('../mide_ebml'):
        sys.path.append(os.path.abspath('..'))
    elif os.path.exists(os.path.join(CWD, '../mide_ebml')):
        sys.path.append(os.path.abspath(os.path.join(CWD, '../mide_ebml')))
    elif os.path.exists(VIEWER_PATH):
        sys.path.append(VIEWER_PATH)
#     import mide_ebml

from mide_ebml import util as ebml_util
from mide_ebml.importer import importFile, SimpleUpdater

from glob import glob
testFiles = glob(r"R:\LOG-Data_Loggers\LOG-0002_Slam_Stick_X\Product_Database\_Calibration\SSX0000039\DATA\20140923\*.IDE")

# NOTE: Make sure devices.py is copied to deployed directory
import devices

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

def changeFilename(filename, ext=None, path=None):
    if ext is not None:
        ext = ext.lstrip('.')
        filename = "%s.%s" % (os.path.splitext(filename)[0], ext)
    if path is not None:
        filename = os.path.join(path, os.path.basename(filename))
    return os.path.abspath(filename)


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


def rms(data, axis=None):
    return np.sqrt(np.mean(data**2, axis=axis))


def window_rms(a, window_size=2):
    a2 = np.power(a,2)
    window = np.ones(window_size)/float(window_size)
    return np.sqrt(np.convolve(a2, window, 'valid'))


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

def flattened(data, rows=None, cols=4):
    """ Given accelerometer data, with each event (time, (z,y,x)), produce an
        array that's (time, z, y, x)
    """
    result = np.zeros(shape=(len(data),cols), dtype=float)
    for i, row in enumerate(data):
        result[i,0] = row[0]
        result[i,1:] = row[1]
    return result

def flattenedIndexed(data, rows=None, cols=4):
    """ Given accelerometer data, with each event (time, (z,y,x)), produce an
        array that's (index, time, z, y, x)
    """
    result = np.zeros(shape=(len(data),cols+1), dtype=float)
    for i, row in enumerate(data):
        result[i,0] = i
        result[i,1] = row[0]
        result[i,2:] = row[1]
    return result

def getFirstIndex(a, fun, col):
    """ Return the index of the first item in the given column that passes the
        given test.
    """
    it = np.nditer(a[:,col], flags=['f_index'])
    while not it.finished:
        if fun(it[0]):
            return it.index
        it.iternext()
    return 0
        
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
    
    def __init__(self, filename, serialNum):
        self.filename = filename
        self.basename = os.path.basename(filename)
        self.name = os.path.splitext(self.basename)[0]
        self.serialNum = serialNum
        self.analyze()
    
    def __str__(self):
        return '%s %2.4f %2.4f %2.4f %2.4f %2.4f %2.4f' % \
            ((self.name,) + tuple(self.rms) + tuple(self.cal))
    
    def analyze(self):
        """ An attempt to port the analysis loop of SSX_Calibration.m to Python.
        
            @return: The calibration constants tuple and the mean temperature.
        """
        thres = 4           # (gs) acceleration detection threshold (trigger for finding which axis is calibrated)
        start= 5000         # Look # data points ahead of first index match after finding point that exceeds threshold
        stop= start + 5000  # Look # of data points ahead of first index match
        cal_value = 7.075   # RMS value of closed loop calibration
        
        _print("importing %s... " % os.path.basename(self.filename))
        self.doc = doc = importFile(self.filename)
        # Turn off existing per-channel calibration (if any)
        for c in doc.channels[0].children:
            c.raw = True
        a = doc.channels[0].getSession()
        a.removeMean = True
        a.rollingMeanSpan = -1
        data = flattened(a, len(a))
        
        _print("%d samples imported. " % len(data)) 
        times = data[:,0] * .000001
    
        gt = lambda(x): x > thres
        
        _print("getting indices... ")
        indices = XYZ(
            getFirstIndex(data, gt, 3),
            getFirstIndex(data, gt, 2),
            getFirstIndex(data, gt, 1)
        )
        
        if indices.x == indices.y == 0:
            indices.x = indices.y = indices.z
        if indices.x == indices.z == 0:
            indices.x = indices.z = indices.y
        if indices.y == indices.z == 0:
            indices.y = indices.z = indices.x
        
    #     _print("slicing...")
        self.accel = XYZ(data[indices.x+start:indices.x+stop,3],
                         data[indices.y+start:indices.y+stop,2],
                         data[indices.z+start:indices.z+stop,1])
        self.times = XYZ(times[indices.x+start:indices.x+stop],
                         times[indices.y+start:indices.y+stop],
                         times[indices.z+start:indices.z+stop])
    
        _print("computing RMS...")
        self.rms = XYZ(rms(self.accel.x), 
                       rms(self.accel.y), 
                       rms(self.accel.z))
        
        self.cal = XYZ(cal_value / self.rms.x, 
                       cal_value / self.rms.y, 
                       cal_value / self.rms.z)
    
        self.cal_temp = np.mean([x[-1] for x in doc.channels[1][1].getSession()])
        
        _println()


    def render(self, imgPath):
        # Generate the plot
        _print("plotting...")
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
        
        imgType = self.imgType.strip('.')
        imgName = 'vibe_test_%s.%s' % (os.path.splitext(os.path.basename(self.filename))[0], imgType)
        pylab.savefig(os.path.join(imgPath, imgName))
#         pylab.show()


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
    
    def __init__(self, files=None,
                 certNum=0,
                 calHumidity=50,
                 calTempComp=-0.30,
                 calRev="A",
                 documentNum="LOG-0002-601", 
                 procedureNum="300-601-502", 
                 refMan="ENDEVCO", 
                 refModel="7251A-10/133", 
                 refSerial="12740/BL33", 
                 refNist="683/283655-13"):
        self.cal_val = files
        self.serialNum = None
        self.certNum = certNum
        
        self.documentNum = documentNum
        self.procedureNum = procedureNum
        
        self.calRev = calRev
        self.calTemp = 21
        self.calTempComp = calTempComp
        self.calHumidity = calHumidity
        
        self.refMan = refMan
        self.refModel = refModel
        self.refSerial = refSerial
        self.refNist = refNist
    
        self.calTime = 0
        
    
    def readManifest(self, devpath):
        """ Read the user page containing the manifest and (possibly)
            calibration data.
            
            Note: Run AFTER calculating calibration constants.
        """
        # Recombine all the 'user page' files
        data = []
        for i in range(4):
            filename = os.path.join(devpath, 'SYSTEM', 'DEV', 'USERPG%d' % i)
            with open(filename, 'rb') as fs:
                data.append(fs.read())
        data = ''.join(data)
        
        manOffset, manSize, calOffset, calSize = struct.unpack_from("<HHHH", data)
        manData = StringIO(data[manOffset:manOffset+manSize])
        calData = StringIO(data[calOffset:calOffset+calSize])
        manifest = ebml_util.read_ebml(manData, schema='mide_ebml.ebml.schema.manifest')
        calibration = ebml_util.read_ebml(calData)

        systemInfo = manifest['DeviceManifest']['SystemInfo']
        self.productSerialNumInt = systemInfo['SerialNumber']
        self.productManTimestamp = systemInfo['DateOfManufacture']
        self.productName = systemInfo['ProductName']
        self.productHwRev = systemInfo['HwRev']
        self.productPartNum = systemInfo['PartNumber']
        
        sensorInfo = manifest['DeviceManifest']['AnalogSensorInfo']
        self.accelSerial = sensorInfo['AnalogSensorSerialNumber']
        
        self.productManDate = datetime.utcfromtimestamp(self.productManTimestamp).strftime("%M/%d/%Y")
        self.productSerialNum = "SSX%07d" % self.productSerialNumInt
        
        # Firmware revision number is in the DEVINFO file
        devInfo = ebml_util.read_ebml(os.path.join(devpath, 'SYSTEM', 'DEV', 'DEVINFO'))
        self.productFwRev = devInfo['RecordingProperties']['FwRev']
        systemInfo['FwRev'] = self.productFwRev
        
        return manifest, calibration

    
    def calculate(self, filenames, prev_cal=(1,1,1), serialNum='', savePath='.'):
        """
        """
        def calc_trans(a, b, c, a_corr, b_corr, c_corr):
            a_cross = a * a_corr
            b_cross = b * b_corr
            c_ampl =  c * c_corr
            Stab = (np.sqrt(((a_cross)**2)+((b_cross)**2)))
            Stb = 100 * (Stab/c_ampl)
            return Stb
        
        self.serialNum = self.serialNum or serialNum
        basenames = map(os.path.basename, filenames)
        if self.cal_val is None:
            self.cal_val = [CalFile(f, serialNum) for f in filenames]
        cal_val = self.cal_val
        
        self.cal = XYZ()
        self.cal_files = XYZ()
        for j in range(3):
            if cal_val[j].cal.x <= 2:
                self.cal.x = cal_val[j].cal.x * prev_cal[0]
                self.cal_files.x = basenames[j]
            if cal_val[j].cal.y <= 2:
                self.cal.y = cal_val[j].cal.y * prev_cal[1]
                self.cal_files.y = basenames[j]
            if cal_val[j].cal.z <= 2:
                self.cal.z = cal_val[j].cal.z * prev_cal[2]
                self.cal_files.z = basenames[j]
        
        for i in range(3):
            x,y,z = cal_val[i].rms
            if x <= 2 and y <= 2:
                self.Sxy = calc_trans(x,y,z,self.cal.x, self.cal.y, self.cal.z)
                self.Sxy_file = basenames[i]
            if y <= 2 and z <= 2:
                self.Syz = calc_trans(y,z,x,self.cal.y,self.cal.z,self.cal.x)
                self.Syz_file = basenames[i]
            if z <= 2 and x <= 2:
                self.Sxz = calc_trans(z,x,y,self.cal.z,self.cal.x,self.cal.y)
                self.Sxz_file = basenames[i]
        
        self.cal_temps = XYZ([cal.cal_temp for cal in self.cal_val])
        self.calTemp = np.mean(self.cal_temps)            

        self.calTimestamp = int(time.mktime(time.gmtime()))

    #===========================================================================
    # 
    #===========================================================================
    
    def createTxt(self, saveTo=None):
        """ Generate the calibration text, optionally saving it to a file.
        """
        result = ['Serial Number: %s' % self.serialNum,
                  'Date: %s' % time.asctime(),
                  '    File  X-rms   Y-rms   Z-rms   X-cal   Y-cal   Z-cal']
        
        result.extend(map(str, self.cal_val))
            
        result.append("%s, X Axis Calibration Constant %.4f" % (self.cal_files.x, self.cal.x))
        result.append("%s, Y Axis Calibration Constant %.4f" % (self.cal_files.y, self.cal.y))
        result.append("%s, Z Axis Calibration Constant %.4f" % (self.cal_files.z, self.cal.z))
    
        result.append("%s, Transverse Sensitivity in XY = %.2f percent" % (self.Sxy_file, self.Sxy))
        result.append("%s, Transverse Sensitivity in YZ = %.2f percent" % (self.Syz_file, self.Syz))
        result.append("%s, Transverse Sensitivity in ZX = %.2f percent" % (self.Sxz_file, self.Sxz))
        
        result = '\n'.join(result)
        
        if isinstance(saveTo, basestring):
            saveTo = open(saveTo, 'wb')
        if hasattr(saveTo, 'write'):
            saveTo.write(result)
            
        return result


    #===========================================================================
    # 
    #===========================================================================
    
    def createCertificate(self, savePath='.', 
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
            ('FIELD_calTemp', self.calTemp),
            ('FIELD_calTempComp', self.calTempComp),
            ('FIELD_cal_x', self.cal.x),
            ('FIELD_cal_y', self.cal.y),
            ('FIELD_cal_z', self.cal.z),
            ('FIELD_certificateNum', certTxt),
            ('FIELD_documentNum', self.documentNum),
            ('FIELD_procedureNum', self.procedureNum),
            ('FIELD_productCalDate', datetime.now().strftime("%M/%d/%Y")),
#             ('FIELD_productMan', 'Mide Technology Corp.'),
            ('FIELD_productManDate', self.productManDate),
            ('FIELD_productName', self.productName),
            ('FIELD_productPartNum', self.productPartNum),
            ('FIELD_productSerial', self.serialNum),
            ('FIELD_refModel', self.refModel),
            ('FIELD_refNist', self.refNist),
            ('FIELD_refSerial', self.refSerial),
            ('FIELD_referenceMan', self.refMan),
        ]
        
        for name, val in fieldIds:
            setText(name, val)
        
        tempFilename = changeFilename(template.replace('template',certTxt), path=savePath)
        certFilename = changeFilename(tempFilename, ext='.pdf')
        xd.write(tempFilename)
    
        subprocess.call('"%s" -f "%s" -A "%s"' % (INKSCAPE_PATH, tempFilename, certFilename), stdout=sys.stdout, stdin=sys.stdin, shell=True)
        os.remove(tempFilename)
        return certFilename


    def createEbml(self):
        """ Create the calibration EBML data, for inclusion in a recorder's
            user page or an external user calibration file.
        """
        g = int(self.productPartNum.rsplit('-',1)[-1])
        baseCoefs = [(g*2.0)/65535.0, -g]
        
        template = OrderedDict([
            ('UnivariatePolynomial', [
                OrderedDict([('CalID', 0), 
                             ('CalReferenceValue', 0.0), 
                             ('PolynomialCoef', baseCoefs)])
                ]
            ), 
            ('BivariatePolynomial', [] ), # filled in below
            ('CalibrationSerialNumber', self.certNum),
            ('CalibrationDate', self.calTimestamp)
         ])
        
        for i in range(3):
            thisCal = OrderedDict([
                ('CalId', i+1),
                ('CalReferenceValue', 0.0), 
                ('BivariateCalReferenceValue', self.cal_temps[i]), 
                ('BivariateChannelIDRef', 1), 
                ('BivariateSubChannelIDRef',1), 
                ('PolynomialCoef', [self.cal[i] * -0.003, self.cal[i], 0.0, 0.0]), 
            ])
            template['BivariatePolynomial'].append(thisCal)
        
        return ebml_util.build_ebml('CalibrationList', template)


