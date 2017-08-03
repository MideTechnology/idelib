'''
Utility functions for dealing with recorders, things that probably shouldn't
pollute the recorder classes themselves (e.g. data conversions specific to
a particular hardware or firmware revision).

Created on Jan 25, 2017
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"


import os
import shutil

# from mide_ebml import util
# import mide_ebml.ebml.schema.mide as schema_mide

import mide_ebml
from mide_ebml.ebmlite import loadSchema

SCHEMA_PATH = os.path.join(os.path.dirname(mide_ebml.__file__), 'ebml/schema')
schema_mide = loadSchema(os.path.join(SCHEMA_PATH, 'mide.xml'))
schema_manifest = loadSchema(os.path.join(SCHEMA_PATH, 'manifest.xml'))

#===============================================================================
# 
#===============================================================================
    
def updateConfig(dev, backup=True):
    """ Update an old configuration file (firmware rev 3 or earlier) to
        the current format.
        
        @keyword backup: If `True`, create a backup of the config file
            before saving the modified one.
        @return: The revised config data, or `False` if no changes were
            made.
    """
    if not dev.path or not dev.configFile:
        return False
    elif dev.firmwareVersion <= 3:
        return False
    elif not os.path.exists(dev.configFile):
        return False
    
    config = dev.getConfig(refresh=True)
    
    try:
        trigs = config['SSXTriggerConfiguration']['Trigger']
        if not trigs:
            return False
    except (KeyError, TypeError):
        return False

    changed = False
    for t in trigs:
        # Update trigger channel IDs.
        # TODO: Get channel IDs from the recorder properties.
        ch = t.get('TriggerChannel')
        if ch == 0:
            t['TriggerChannel'] = 8
            changed = True
        elif ch == 1:
            t['TriggerChannel'] = 36
            changed = True

    if not changed:
        return False
    
    if backup:
        # Make backup copy of the config file
        base, ext = os.path.splitext(dev.configFile)
        filename = base + "_old" + ext
        shutil.copy2(dev.configFile, filename)
        
    dev.saveConfig(config)
    dev._config = config
    
    return config


def updateUserCal(dev, backup=True):
    """ Update an user calibration file (firmware rev 3 or earlier) to
        the current format.
        
        @keyword backup: If `True`, create a backup of the file before 
            saving the modified one.
        @return: The revised calibration data, or `False` if no changes were
            made.
    """
    cal = dev.getUserCalibration(refresh=True)
    if not cal:
        return False
    elif dev.firmwareVersion <= 3:
        return False
    
    changed = False
   
    for c in cal.get('BivariatePolynomial', []):
        # TODO: Get channel IDs from the recorder properties.
        if c['BivariateChannelIDRef'] == 1:
            c['BivariateChannelIDRef'] = 36
            changed = True
            
    for c in cal.get('UnivariatePolynomial', []):
        # TODO: Get channel IDs from the recorder properties.
        if c['CalID'] == 0:
            c['CalID'] = 9
            changed = True

    if not changed:
        return False
    
    if backup:
        # Make backup copy of the config file
        base, ext = os.path.splitext(dev.userCalFile)
        filename = base + "_old" + ext
        shutil.copy2(dev.userCalFile, filename)
    
    with open(dev.userCalFile, 'wb') as f:
#         f.write(util.build_ebml('CalibrationList', cal, schema=schema_mide))
        schema_mide.encode(f, {'CalibrationList': cal})
        
    dev._userCalPolys = None
    
    return cal
