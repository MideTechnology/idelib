'''
Created on Sep 30, 2014

@author: dstokes
'''
from collections import Iterable
import os.path
import sys
import time

import numpy as np
import pylab
VIEWER_PATH = "P:/WVR_RIF/04_Design/Electronic/Software/SSX_Viewer"

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

from mide_ebml.importer import importFile, SimpleUpdater

from glob import glob
testFiles = glob(r"R:\LOG-Data_Loggers\LOG-0002_Slam_Stick_X\Product_Database\_Calibration\SSX0000039\DATA\20140923\*.IDE")

#===============================================================================
# 
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

def analyze(filename, serialNum='xxxxxxxxx', imgPath=None, imgType=".jpg"):
    """ An attempt to port the analysis loop of SSX_Calibration.m to Python.
    """
    thres = 4           # (gs) acceleration detection threshold (trigger for finding which axis is calibrated)
    start= 5000         # Look # data points ahead of first index match after finding point that exceeds threshold
    stop= start + 5000  # Look # of data points ahead of first index match
    cal_value = 7.075   # RMS value of closed loop calibration
    
    print "importing %s..." % os.path.basename(filename),
    doc = importFile(filename)
    a = doc.channels[0].getSession()
    a.removeMean = True
    a.rollingMeanSpan = -1
    data = flattened(a, len(a))
    
    print "%d samples imported. " % len(data), 
    times = data[:,0] * .000001

    gt = lambda(x): x > thres
    
    print "getting indices...",
    index1 = getFirstIndex(data, gt, 3)
    index2 = getFirstIndex(data, gt, 2)
    index3 = getFirstIndex(data, gt, 1)
    
    if index1 == index2 == 0:
        index1 = index2 = index3
    if index1 == index3 == 0:
        index1 = index3 = index2
    if index2 == index3 == 0:
        index2 = index3 = index1
    
#     print "slicing..."
    x_accel = data[index1+start:index1+stop,3]
    x_times = times[index1+start:index1+stop]
    y_accel = data[index2+start:index2+stop,2]
    y_times = times[index2+start:index2+stop]
    z_accel = data[index3+start:index3+stop,1]
    z_times = times[index3+start:index3+stop]

    print "computing RMS...",
    x_rms = rms(x_accel)
#     x_rms = window_rms(x_accel)
    y_rms = rms(y_accel)
#     y_rms = window_rms(y_accel)
    z_rms = rms(z_accel)
#     z_rms = window_rms(z_accel)
    
    x_cal = cal_value / x_rms
    y_cal = cal_value / y_rms
    z_cal = cal_value / z_rms

    cal_val = [x_rms, y_rms, z_rms, x_cal, y_cal, z_cal]
        
    # Generate the plot
    if imgPath:
        print "plotting...",
        plotXMin = min(x_times[0], y_times[0], z_times[0])
        plotXMax = max(x_times[-1], y_times[-1], z_times[-1])
        plotXPad = (plotXMax-plotXMin) * 0.01
        fig = pylab.figure(figsize=(8,6), dpi=80, facecolor="white")
        pylab.suptitle("File: %s, SN: %s" % (os.path.basename(filename), serialNum), fontsize=24)
        pylab.subplot(1,1,1)
        pylab.xlim(plotXMin-plotXPad, plotXMax+plotXPad)
        pylab.plot(x_times, x_accel, color="red", linewidth=1.5, linestyle="-", label="X-Axis")
        pylab.plot(y_times, y_accel, color="green", linewidth=1.5, linestyle="-", label="Y-Axis")
        pylab.plot(z_times, z_accel, color="blue", linewidth=1.5, linestyle="-", label="Z-Axis")
        pylab.legend(loc='upper right')
        
        axes = fig.gca()
        axes.set_xlabel('Time (seconds)')
        axes.set_ylabel('Amplitude (g)')
        
        imgName = os.path.splitext(os.path.basename(filename))[0]+imgType
        pylab.savefig(imgName)
#         pylab.show()
    
    # Done
    print ''
    return cal_val


def calConstant(filenames, prev_cal=(1,1,1), serialNum='', savePath='.'):
    """
    """
    def calc_trans(a, b, c, a_corr, b_corr, c_corr):
        a_cross = a * a_corr
        b_cross = b * b_corr
        c_ampl =  c * c_corr
        Stab = (np.sqrt(((a_cross)**2)+((b_cross)**2)))
        Stb = 100 * (Stab/c_ampl)
        return Stb
    
    basenames = map(os.path.basename, filenames)
    cal_val = [analyze(f, imgPath=savePath) for f in filenames]

    calib = ['']*3
    for j in range(3):
        if cal_val[j][3] <= 2:
            x_corr = cal_val[j][3] * prev_cal[0]
            calib[0] = "%s, X Axis Calibration Constant %.4f" % (basenames[j], x_corr)
        if cal_val[j][4] <= 2:
            y_corr = cal_val[j][4] * prev_cal[1]
            calib[1] = "%s, Y Axis Calibration Constant %.4f" % (basenames[j], y_corr)
        if cal_val[j][5] <= 2:
            z_corr = cal_val[j][5] * prev_cal[2]
            calib[2] = "%s, Z Axis Calibration Constant %.4f" % (basenames[j], z_corr)
    
    trans = [''] * 3
    for i in range(3):
        x,y,z = cal_val[i][:3]
        if x <= 2 and y <= 2:
            Sxy = calc_trans(x,y,z,x_corr,y_corr,z_corr)
            trans[0] = "%s, Transverse Sensitivity in XY = %.2f percent" % (basenames[i], Sxy)
        if y <= 2 and z <= 2:
            Syz = calc_trans(y,z,x,y_corr,z_corr,x_corr)
            trans[1] = "%s, Transverse Sensitivity in YZ = %.2f percent" % (basenames[i], Syz)
        if z <= 2 and x <= 2:
            Sxz = calc_trans(z,x,y,z_corr,x_corr,y_corr)
            trans[2] = "%s, Transverse Sensitivity in ZX = %.2f percent" % (basenames[i], Sxz)

    names = [os.path.splitext(f)[0] for f in basenames]
    result = ['Serial Number: %s' % serialNum,
              'Date: %s' % time.asctime(),
              '    File X-rms  Y-rms  Z-rms  X-cal  Y-cal  Z-cal']
    for name, cal in zip(names, cal_val):
        result.append('%s %2.4f %2.4f %2.4f %2.4f %2.4f %2.4f' % ((name,)+tuple(cal)))
    result.extend(calib)
    result.extend(trans)
    
    return '\n'.join(result)
