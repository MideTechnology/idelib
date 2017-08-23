'''
Configuration UI generation and config data I/O for older recorders. Isolated
to keep the main configuration scripts clean.

Created on Aug 21, 2017
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"


from collections import OrderedDict, defaultdict
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

def _copyItems(oldD, newD, *keyPairs):
    for oldK, newK in keyPairs:
        val = oldD.get(oldK)
        if val is not None:
            newD[newK] = val
        

def loadConfigData(device):
    """ Load old configuration data.
    """
    # XXX: REMOVE
#     return {}

    config = device.getConfig()
    newData = {}

    # Combine 'root' dictionaries for easy access
    basicConfig = config.get('SSXBasicRecorderConfiguration', {})
    userConfig = config.get('RecorderUserData', {})
    triggerConfig = config.get('SSXTriggerConfiguration', {})
    channelConfig = config.get('SSXChannelConfiguration', [])

    _copyItems(basicConfig, newData, 
               ('SampleFreq',         0x02ff08),  
               ('AAFilterCornerFreq', 0x08ff08),
               ('PlugPolicy',         0x0aff7f),
               ('UTCOffset',          0x0bff7f))
    
    _copyItems(userConfig, newData, 
               ('RecorderName',       0x08ff7f),
               ('RecorderDesc',       0x09ff7f))
    
    _copyItems(triggerConfig, newData, 
               ('PreRecordDelay',     0x0cff7f),
               ('RecordingTime',      0x0dff7f),
               ('AutoRearm',          0x0eff7f),
               ('WakeTimeUTC',        0x0fff7f))
    
    for ch in channelConfig:
        chId = ch.get('ConfigChannel')
        enables = ch.get('SubChannelEnableMap', 0xFF)
        sampFreq = ch.get('ChannelSampleFreq')
        
        if chId is None:
            continue
        if enables is not None:
            newData[0x01FF00 | (chId & 0xFF)] = enables
        if sampFreq is not None:
            newData[0x82FF00 | (chId & 0xFF)] = sampFreq
    
    dcAccelMap = 0
    
    for trigger in triggerConfig.get('Trigger', []):
        chId = trigger.get('TriggerChannel')
        subchId = trigger.get('TriggerSubChannel', 0xFF) & 0xFF
        trigLo = trigger.get('TriggerWindowLo')
        trigHi = trigger.get('TriggerWindowHi')
        
        if chId is None:
            continue
        
        combinedId = (subchId << 8) | (chId & 0xFF)
        
        if chId == 32:
            dcAccelMap |= (1 << subchId)
        else:
            newData[0x050000 | combinedId] = 1
        
        if trigLo is not None:
            newData[0x030000 | combinedId] = trigLo
        if trigHi is not None:
            newData[0x040000 | combinedId] = trigHi

    if dcAccelMap > 0:
        newData[0x05FF20] = dcAccelMap

    return newData


def saveConfigData(configData, device):
    """ Save old configuration data.
    """
    # XXX: REMOVE
#     return

    configData = configData.copy()
    userData = OrderedDict()
    basicConfig = OrderedDict()
    triggerConfig = OrderedDict()
    channelConfig = OrderedDict()
    
    for k, cid in (('RecorderName', 0x8ff7f), 
                   ('RecorderDesc', 0x9ff7f)):
        val = configData.get(cid, None)
        if val:
            userData[k] = val
    
    for k, cid in (('SampleFreq', 0x2ff08), 
                   ('AAFilterCornerFreq', 0x8ff08),
                   ('PlugPolicy', 0xaff7f), 
                   ('UTCOffset', 0xbff7f)):
        val = configData.get(cid, None)
        if val is not None:
            basicConfig[k] = val
    
    for k, cid in (('PreRecordDelay',     0x0cff7f),
                   ('RecordingTime',      0x0dff7f),
                   ('AutoRearm',          0x0eff7f),
                   ('WakeTimeUTC',        0x0fff7f)):
        val = configData.get(cid, None)
        if val is not None:
            triggerConfig[k] = val
    
    triggers = []
    
    for t in [k for k in configData if (k & 0xFF0000 == 0x050000)]:
        combinedId = t & 0x00FFFF
        trigHi = configData.get(0x030000 | combinedId)
        trigLo = configData.get(0x040000 | combinedId)
        
        trig = OrderedDict(TriggerChannel = combinedId & 0xFF)
        if trigHi is not None:
            trig['TriggerWindowHi'] = trigHi
        if trigLo is not None:
            trig['TriggerWindowLo'] = trigLo
        
        # Special case: DC accelerometer, which uses a 'participation' bitmap
        # instead of having explicit ConfigID items for each subchannel.
        if t == 0x05FF20:
            v = configData[0x05FF20]
            for i in range(3):
                if (v>>i) & 1:
                    d = trig.copy()
                    d['TriggerSubChannel'] = i
                    triggers.append(d)
        else:
            trig['TriggerSubChannel'] = ((combinedId & 0x00FF00) >> 1)
            triggers.append(trig)

    if triggers:
        triggerConfig['Trigger'] = triggers

    legacyConfigData = OrderedDict()
    
    if basicConfig:
        legacyConfigData['SSXBasicRecorderConfiguration'] = basicConfig       
    if userData:
        legacyConfigData['RecorderUserData'] = userData
    if triggerConfig:
        legacyConfigData['SSXTriggerConfiguration'] = triggerConfig
    if channelConfig:
        legacyConfigData['SSXChannelConfiguration'] = channelConfig

    # XXX: remove
    return legacyConfigData
    schema = loadSchema('mide.xml')
 
    

    