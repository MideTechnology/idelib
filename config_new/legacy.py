'''
Configuration UI generation and config data I/O for older recorders. Isolated
to keep the main configuration scripts clean.

Created on Aug 21, 2017
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"


from collections import OrderedDict
from xml.etree import ElementTree as ET
import os.path

from mide_ebml.ebmlite import loadSchema, util

DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), 'defaults')

#===============================================================================
# 
#===============================================================================

def loadConfigUI(device):
    """ Load a default configuration UI from a static XML file. For recorders
        running old firmware that doesn't supply a ``CONFIG.UI`` file.
    """
    # TODO: Modify default with recorder information (accelerometer range, etc.)
    # to reduce the number of individual templates.
    partNum = getattr(device, 'partNumber', 'LOG-0002-100G-DC')
    filename = os.path.join(DEFAULTS_PATH, partNum + ".xml")
    doc = ET.parse(filename)
    
#     accelRange = device.getAccelRange()
#     if accelRange is not None:
#         loEl = doc.find('.//FloatAccelerationField[@id="analogAccelHi"]/FloatMin')
#         hiEl = doc.find('.//FloatAccelerationField[@id="analogAccelHi"]/FloatMax')
#         if loEl is not None:
#             loEl.set('value',str(accelRange[0]))
#         if hiEl is not None:
#             hiEl.set('value',str(accelRange[1]))
            
    return util.loadXml(doc, loadSchema('config_ui.xml'))


#===============================================================================
# 
#===============================================================================

def _copyItems(oldD, newD, *keyPairs):
    """ Utility function to copy existing, non-`None` items from one dictionary
        to another, using different keys.
    """
    for oldK, newK in keyPairs:
        val = oldD.get(oldK)
        if val is not None:
            newD[newK] = val
        

def loadConfigData(device):
    """ Load old configuration data and return it in the new format.
    """
    config = device.getConfig(refresh=True).copy()
    newData = {}

    # Combine 'root' dictionaries for easy access
    basicConfig = config.get('SSXBasicRecorderConfiguration', {})
    userConfig = config.get('RecorderUserData', {})
    triggerConfig = config.get('SSXTriggerConfiguration', {})
    channelConfig = config.get('SSXChannelConfiguration', [])

    # Basic stuff. Items only added if they exist in the old config data.
    _copyItems(basicConfig, newData, 
               ('SampleFreq',         0x02ff08),  
               ('AAFilterCornerFreq', 0x08ff08),
               ('PlugPolicy',         0x0aff7f),
               ('UTCOffset',          0x0bff7f))
    
    _copyItems(userConfig, newData, 
               ('RecorderName',       0x08ff7f),
               ('RecorderDesc',       0x09ff7f))
    
    _copyItems(triggerConfig, newData, 
               ('WakeTimeUTC',        0x0fff7f),
               ('PreRecordDelay',     0x0cff7f),
               ('RecordingTime',      0x0dff7f),
               ('AutoRearm',          0x0eff7f))
    
    # Channel configuration. 
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
    
    # Trigger configuration.
    dcAccelMap = 0 # For building DC accelerometer's 'participation map'.
    
    for trigger in triggerConfig.get('Trigger', []):
        chId = trigger.get('TriggerChannel')
        subchId = trigger.get('TriggerSubChannel', 0) & 0xFF
        trigLo = trigger.get('TriggerWindowLo')
        trigHi = trigger.get('TriggerWindowHi')
        
        if chId is None:
            continue
        
        combinedId = (subchId << 8) | (chId & 0xFF)
        
        if chId == 32:
            # Special case: DC accelerometer (new data uses 'participation map'
            # instead of individual subchannel triggers).
            dcAccelMap |= (1 << subchId)
            combinedId = combinedId | 0x00FF00
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
    """ Save new configuration data in the old format.
    """
    # Copy the data, just in case.
    configData = configData.copy()
    
    # Individual dictionaries/lists for each section of the old config
    userConfig = OrderedDict()
    basicConfig = OrderedDict()
    triggerConfig = OrderedDict()
    channelConfig = []

    # Basic stuff. Items only added if they exist in the new config data.
    _copyItems(configData, userConfig,
               (0x08ff7f, 'RecorderName'), 
               (0x09ff7f, 'RecorderDesc'))

    _copyItems(configData, basicConfig, 
               (0x02ff08, 'SampleFreq'), 
               (0x08ff08, 'AAFilterCornerFreq'),
               (0x0aff7f, 'PlugPolicy'), 
               (0x0bff7f, 'UTCOffset'))
        
    _copyItems(configData, triggerConfig, 
               (0x0fff7f, 'WakeTimeUTC'),
               (0x0cff7f, 'PreRecordDelay'),
               (0x0dff7f, 'RecordingTime'),
               (0x0eff7f, 'AutoRearm'))
    
    # Trigger configuration: separate master elements for each subchannel. 
    triggers = []
    
    # Get all trigger enables/subchannel participation maps
    for t in [k for k in configData if (k & 0xFF0000 == 0x050000)]:
        combinedId = t & 0x00FFFF
        trigLo = configData.get(0x030000 | combinedId)
        trigHi = configData.get(0x040000 | combinedId)
        
        trig = OrderedDict(TriggerChannel = combinedId & 0xFF)
        
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
            trig['TriggerSubChannel'] = ((combinedId & 0x00FF00) >> 8)
            triggers.append(trig)

        if trigLo is not None:
            trig['TriggerWindowLo'] = trigLo
        if trigHi is not None:
            trig['TriggerWindowHi'] = trigHi

    if triggers:
        triggerConfig['Trigger'] = triggers

    # Channel configuration: per-axis enables, sample rate for some.
    for c in device.getChannels():
        combinedId = 0xFF00 | (c & 0xFF)
        d = OrderedDict()
        _copyItems(configData, d, 
                   (0x820000 | combinedId, "ChannelSampleFreq"),
                   (0x010000 | combinedId, "SubChannelEnableMap"))
        
        # Only save if something's been set.
        if d:
            d['ConfigChannel'] = c
            channelConfig.append(d)

    # Build the complete old-style configuration dictionary. Only add stuff
    # with content.
    legacyConfigData = OrderedDict()
    
    if basicConfig:
        legacyConfigData['SSXBasicRecorderConfiguration'] = basicConfig       
    if userConfig:
        legacyConfigData['RecorderUserData'] = userConfig
    if triggerConfig:
        legacyConfigData['SSXTriggerConfiguration'] = triggerConfig
    if channelConfig:
        legacyConfigData['SSXChannelConfiguration'] = channelConfig

    schema = loadSchema('mide.xml')
    ebml = schema.encodes({'RecorderConfiguration':legacyConfigData})

    # This will raise an exception if it fails.
    schema.verify(ebml)
    
    with open(device.configFile, 'wb') as f:
        f.write(ebml)


#===============================================================================
# 
#===============================================================================

def pprint(d, indent=0):
    """ Test function for dumping dictionaries.
        XXX: REMOVE ME.
    """
    if isinstance(d, dict):
        for k,v in d.items():
            print
            print (("    " * indent) + k ),
            pprint(v, indent+1)
    elif isinstance(d, (tuple, list)):
        for i in d:
            print
            print (("    " * indent) + '[')
            pprint(i, indent+1)
            print (("    " * indent) + ']')
    else:
        print d

    