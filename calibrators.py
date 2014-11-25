'''
Module for calculating the calibration constants for recording devices. 

Created on Sep 30, 2014

@author: dstokes
'''
from collections import OrderedDict
from datetime import datetime
import os.path
from StringIO import StringIO
import struct
import sys
import time

import numpy as np


from mide_ebml import util as ebml_util
from mide_ebml.importer import importFile

import devices

#===============================================================================
# 
#===============================================================================

class CalibrationError(ValueError):
    """
    """

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
# 
#===============================================================================

class SSXCalFile(object):
    """ One analyzed IDE file.
    """
    ACCEL_THRESH = 4 # (gs) acceleration detection threshold (trigger for finding which axis is calibrated)
    CAL_VALUE = 7.075   # RMS value of closed loop calibration
    
    def __init__(self, filename):
        self.filename = filename
        self.basename = os.path.basename(filename)
        self.name = os.path.splitext(self.basename)[0]
        self.analyze()
    
    def __str__(self):
        return '%s %2.4f %2.4f %2.4f %2.4f %2.4f %2.4f' % \
            ((self.name,) + tuple(self.rms) + tuple(self.cal))
    
    @classmethod
    def flattened(cls, data, rows=None, cols=4):
        """ Given accelerometer data, with each event (time, (z,y,x)), produce 
            an array that's (time, z, y, x)
        """
        result = np.zeros(shape=(len(data),cols), dtype=float)
        for i, row in enumerate(data):
            result[i,0] = row[0]
            result[i,1:] = row[1]
        return result
    
    @classmethod
    def getFirstIndex(cls, a, fun, col):
        """ Return the index of the first item in the given column that passes 
            the given test.
        """
        it = np.nditer(a[:,col], flags=['f_index'])
        while not it.finished:
            if fun(it[0]):
                return it.index
            it.iternext()
        return 0
    
    @classmethod
    def rms(cls, data, axis=None):
        return np.sqrt(np.mean(data**2, axis=axis))
    
    @classmethod
    def window_rms(cls, a, window_size=2):
        a2 = np.power(a,2)
        window = np.ones(window_size)/float(window_size)
        return np.sqrt(np.convolve(a2, window, 'valid'))


    def analyze(self):
        """ An attempt to port the analysis loop of SSX_Calibration.m to Python.
        """
        start= 5000         # Look # data points ahead of first index match after finding point that exceeds threshold
        stop= start + 5000  # Look # of data points ahead of first index match
        
        _print("importing %s... " % os.path.basename(self.filename))
        self.doc = doc = importFile(self.filename)
        # Turn off existing per-channel calibration (if any)
        for c in doc.channels[0].children:
            c.raw = True
        a = doc.channels[0].getSession()
        a.removeMean = True
        a.rollingMeanSpan = -1
        data = self.flattened(a, len(a))
        
        _print("%d samples imported. " % len(data)) 
        times = data[:,0] * .000001
    
        gt = lambda(x): x > self.ACCEL_THRESH
        
        _print("getting indices... ")
        indices = XYZ(
            self.getFirstIndex(data, gt, 3),
            self.getFirstIndex(data, gt, 2),
            self.getFirstIndex(data, gt, 1)
        )
        
        if indices.x == indices.y == 0:
            indices.x = indices.y = indices.z
        if indices.x == indices.z == 0:
            indices.x = indices.z = indices.y
        if indices.y == indices.z == 0:
            indices.y = indices.z = indices.x
        
        self.accel = XYZ(data[indices.x+start:indices.x+stop,3],
                         data[indices.y+start:indices.y+stop,2],
                         data[indices.z+start:indices.z+stop,1])
        self.times = XYZ(times[indices.x+start:indices.x+stop],
                         times[indices.y+start:indices.y+stop],
                         times[indices.z+start:indices.z+stop])
    
        _print("computing RMS...")
        self.rms = XYZ(self.rms(self.accel.x), 
                       self.rms(self.accel.y), 
                       self.rms(self.accel.z))
        
        self.cal = XYZ(self.CAL_VALUE / self.rms.x, 
                       self.CAL_VALUE / self.rms.y, 
                       self.CAL_VALUE / self.rms.z)
    
        self.cal_temp = np.mean([x[-1] for x in doc.channels[1][1].getSession()])
        self.cal_press = np.mean([x[-1] for x in doc.channels[1][0].getSession()])
        
        _println()


#===============================================================================
# 
#===============================================================================

class SSXCalibrator(object):
    """ A class representing and computing a set of calibration constants
        based on a set of shaker recordings.
    """
    
    def __init__(self, devPath=None):
        self.devPath = devPath
        self.productSerialNum = None
        self.certNum = 0
        self.originalCal = None
        
        self.calTimestamp = 0
        self.cal_vals=None
        self.cal_files = None

        if devPath is not None:
            self.device = devices.SlamStickX(devPath)
            _, self.originalCal = self.readManifest()
            

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
        return ides[:3]


    def readManifest(self, devPath=None):
        """ Read the user page containing the manifest and (possibly)
            calibration data.
            
        """
        devPath = self.devPath if devPath is None else self.devPath
        ssx = devices.SlamStickX(devPath)
        
        manifest, calibration = ssx.readManifest()
        systemInfo = manifest['DeviceManifest']['SystemInfo']
        sensorInfo = manifest['DeviceManifest']['AnalogSensorInfo']
        self.accelSerial = sensorInfo['AnalogSensorSerialNumber']
        
        # Firmware revision number is in the DEVINFO file
        devInfo = ssx.getInfo()
        self.productFwRev = devInfo.get('FwRev',1)
        self.productHwRev = devInfo.get('HwRev',1)
        self.productSerialNumInt = devInfo['SerialNumber']
        self.productManTimestamp = devInfo['DateOfManufacture']
        self.productName = devInfo['ProductName']
        self.productPartNum = devInfo['PartNumber']
        systemInfo['FwRev'] = self.productFwRev
        
        self.productManDate = datetime.utcfromtimestamp(self.productManTimestamp).strftime("%m/%d/%Y")
        self.productSerialNum = "SSX%07d" % self.productSerialNumInt
        
        return manifest, calibration

    
    def calculate(self, filenames=None, prev_cal=(1,1,1)):
        """ Compute calibration constants from a set of recording files.
        """
        self.calDate = datetime.now()
        
        def calc_trans(a, b, c, a_corr, b_corr, c_corr):
            a_cross = a * a_corr
            b_cross = b * b_corr
            c_ampl =  c * c_corr
            Stab = (np.sqrt(((a_cross)**2)+((b_cross)**2)))
            Stb = 100 * (Stab/c_ampl)
            return Stb
        
        if filenames is None:
            filenames = self.getFiles()
        
        # TODO: Check for correct number of files?
        
        basenames = map(os.path.basename, filenames)
        if self.cal_vals is None:
            self.cal_vals = [SSXCalFile(f, self.productSerialNum) for f in filenames]
        cal_vals = self.cal_vals
        
        self.cal = XYZ()
        self.cal_files = XYZ()
        for j in range(3):
            if cal_vals[j].cal.x <= 2:
                self.cal.x = cal_vals[j].cal.x * prev_cal[0]
                self.cal_files.x = basenames[j]
            if cal_vals[j].cal.y <= 2:
                self.cal.y = cal_vals[j].cal.y * prev_cal[1]
                self.cal_files.y = basenames[j]
            if cal_vals[j].cal.z <= 2:
                self.cal.z = cal_vals[j].cal.z * prev_cal[2]
                self.cal_files.z = basenames[j]
        
        self.Sxy = self.Sxy_file = None
        self.Syz = self.Syz_file = None
        self.Sxz = self.Sxz_file = None
        
        for i in range(3):
            x,y,z = cal_vals[i].rms
            if x <= 2 and y <= 2:
                self.Sxy = calc_trans(x,y,z,self.cal.x, self.cal.y, self.cal.z)
                self.Sxy_file = basenames[i]
            if y <= 2 and z <= 2:
                self.Syz = calc_trans(y,z,x,self.cal.y,self.cal.z,self.cal.x)
                self.Syz_file = basenames[i]
            if z <= 2 and x <= 2:
                self.Sxz = calc_trans(z,x,y,self.cal.z,self.cal.x,self.cal.y)
                self.Sxz_file = basenames[i]
        
        self.cal_temps = XYZ([cal.cal_temp for cal in self.cal_vals])
        self.calTemp = np.mean(self.cal_temps)
        self.cal_pressures = XYZ([cal.cal_press for cal in self.cal_vals])
        self.calPress = np.mean(self.cal_pressures)          

        self.calTimestamp = int(time.mktime(time.gmtime()))

        if (self.Sxy is None or self.Syz is None or self.Sxz is None):
            # One or more files wasn't identifiable as being an axis recording
            bad = list(basenames)
            for f in (self.Sxy_file, self.Sxy_file, self.Sxz_file):
                if f in bad:
                    bad.remove(f)
            raise CalibrationError("Calibration could not be computed from file(s): %s" % ', '.join(bad))
        

    def createEbml(self, template=None):
        """ Create the calibration EBML data, for inclusion in a recorder's
            user page or an external user calibration file.
        """
        if template is not None:
            doc = ebml_util.read_ebml(template, schema='mide_ebml.ebml.schema.mide')
            calList = doc['CalibrationList']
        else:
            calList = self.originalCal['CalibrationList']
            
        calList['CalibrationSerialNumber'] = self.certNum
        calList['CalibrationDate'] = self.calTimestamp
            
        for i in range(3):
            thisCal = OrderedDict([
                ('CalID', i+1),
                ('CalReferenceValue', 0.0), 
                ('BivariateCalReferenceValue', self.cal_temps[i]), 
                ('BivariateChannelIDRef', 1), 
                ('BivariateSubChannelIDRef',1), 
                ('PolynomialCoef', [self.cal[i] * -0.003, self.cal[i], 0.0, 0.0]), 
            ])
            calList['BivariatePolynomial'].append(thisCal)
        
        return ebml_util.build_ebml('CalibrationList', calList, schema='mide_ebml.ebml.schema.mide')


