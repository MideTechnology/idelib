'''
Configuration UI generation and config data I/O for older recorders. Isolated
to keep the main configuration scripts clean.

Created on Aug 21, 2017
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"


from collections import OrderedDict
import os.path

from mide_ebml.ebmlite import loadSchema, util
from base import SCHEMA, logger

DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), 'defaults')

#===============================================================================
# 
#===============================================================================

def loadConfigUI(device):
    """ Load a default configuration UI from a static XML file. For recorders
        running old firmware that doesn't supply a ``CONFIG.UI`` file.
    """
    partNum = getattr(device, 'partNumber', 'LOG-0002-100G-DC')
    logger.info('Loading default ConfigUI for %s' % partNum)
    filename = os.path.join(DEFAULTS_PATH, partNum + ".xml")
    return util.loadXml(filename, SCHEMA)


#===============================================================================
# 
#===============================================================================

def loadConfigData(device):
    """ Load old configuration data.
    """
    config = device.getConfig()
    newData = {}
    
    basicConfig = config.get('SSXBasicRecorderConfiguration', {})
    basicConfig.update(config.get('RecorderUserData', {}))
    basicConfig.update(config.get('SSXTriggerConfiguration', {}))
    basicConfig.update(config.get('SSXChannelConfiguration', {}))

    for k, cid in (('RecorderName', 0x8ff7f), ('RecorderDesc', 0x9ff7f),
                   ('SampleFreq', 0x2ff08), ('AAFilterCornerFreq', 0x8ff08),
                   ('PlugPolicy', 0xaff7f), ('UTCOffset', 0xbff7f),
                   ('PreRecordDelay', 0xcff7f), ('WakeTimeUTC', 0xfff7f),
                   ('RecordingTime', 0xdff7f), ('AutoRearm', 0xeff7f)):
        val = basicConfig.get(k)
        if val is not None:
            newData[cid] = val
    
    for ch in basicConfig.get('SSXChannelConfiguration', []):
        pass

    return newData


def saveConfigData(configData, device):
    """ Save old configuration data.
    """
    data = OrderedDict()
    basicConfig = OrderedDict()
    userData = OrderedDict()
    channelConfig = []
    
    for k, cid in (('RecorderName', 0x8ff7f), ('RecorderDesc', 0x9ff7f)):
        val = configData.get(cid)
        if val:
            userData[k] = val
    
    for k, cid in (('SampleFreq', 0x2ff08), ('AAFilterCornerFreq', 0x8ff08),
                   ('PlugPolicy', 0xaff7f), ('UTCOffset', 0xbff7f)):
        val = configData.get(cid)
        if val is not None:
            basicConfig[k] = val
                        
    if basicConfig:
        data['SSXBasicRecorderConfiguration'] = basicConfig       
    if userData:
        data['RecorderUserData'] = userData
    if channelConfig:
        data['SSXChannelConfiguration'] = channelConfig

    schema = loadSchema('mide.xml')
 
    

    