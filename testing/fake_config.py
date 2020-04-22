
from datetime import datetime
import os.path
import sys
import time

sys.path.insert(0,'..')

import devices
from idelib import util
from assembly.firmware import ssx_bootloadable_device


def setFakeBirthday(path, *args):
    """ Write a fake date of manufacture to a fake device. 
    
        First argument is the device's path, following arguments are datetime 
        parameters (year, month, day, etc.)
    """
    ssx = devices.getRecorder(path)
    t = time.mktime(datetime(*args).timetuple())
    
    info = util.read_ebml(ssx.infoFile)
    info['RecordingProperties']['RecorderInfo']['DateOfManufacture'] = int(t)
    with open(ssx.infoFile, 'wb') as f:
        f.write(util.build_ebml(*info.items()[0]))


def setFakeCalDate(path, *args):
    """ Write a fake date of calibration to a fake device. 
    
        WARNING: This does bad things to the device's USERPG files. Use only
        on a fake recorder.
        
        First argument is the device's path, following arguments are datetime 
        parameters (year, month, day, etc.)
    """
    ssx = devices.getRecorder(path)
    t = time.mktime(datetime(*args).timetuple())

    man = ssx.getManifest()
    cal = ssx.getCalibration()
    cal['CalibrationDate'] = int(t)

    mandata = util.build_ebml('DeviceManifest', man, 'idelib.ebml.schema.manifest')
    caldata = util.build_ebml('CalibrationList', cal)
    fake = ssx_bootloadable_device.makeUserpage(mandata, caldata)
    
    # Kill existing USERPG files. The Lab just concatenates their contents,
    # so only the first really needs any data.
    for i in range(4):
        open(os.path.join(path, 'SYSTEM', 'DEV', 'USERPG%d' % i), 'wb').close()
        
    with open(os.path.join(path, 'SYSTEM', 'DEV', 'USERPG0'), 'wb') as f:
        f.write(fake)