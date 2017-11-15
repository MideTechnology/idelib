'''
Configuration UI generation and config data I/O for older recorders. Isolated
to keep the main configuration scripts clean.

Created on Aug 21, 2017

@todo: Chunks of this will need to be refactored after `devices` is cleaned up.
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"


from collections import OrderedDict
from glob import glob
import os.path
import shutil
from xml.etree import ElementTree as ET

import wx

from mide_ebml.ebmlite import loadSchema, util

DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), 'defaults')

import logging
logger = logging.getLogger('SlamStickLab.ConfigUI')

#===============================================================================
# 
#===============================================================================

def getUiTemplate(partNum):
    """ Get the default UI template for the given part number.
    """
    # First, look for an exact match to the part number.
    filename = os.path.join(DEFAULTS_PATH, partNum + ".xml")
    if os.path.exists(filename):
        return filename
    
    # Look for templates that match the base part number (for custom units)
    for filename in glob(os.path.join(DEFAULTS_PATH, "*.xml")):
        name = os.path.splitext(os.path.basename(filename))[0]
        if partNum.startswith(name):
            return filename
    
    # Get a more generic template and fill in the details.
    base = partNum[:8]
    filename = os.path.join(DEFAULTS_PATH, "%s-xxxG.xml" % base) 
    if os.path.exists(filename):
        return filename
    
    # Not found! XXX: Should this return a default instead?
    return None
 

def loadConfigUI(device, showAdvanced=False):
    """ Load a default configuration UI from a static XML file. The template 
        gets modified according to specific properties of the recorder that 
        aren't conveyed in the part number. For recorders running old firmware
        that doesn't supply a ``CONFIG.UI`` file. 
    """
    partNum = getattr(device, 'partNumber', 'LOG-0002-100G')
    filename = getUiTemplate(partNum)
    
    if filename is None:
        logger.error("Could not find a template for device %s!", partNum)
        return None
    
    logger.info('Loading legacy UI template %s for device %s' % 
                (os.path.basename(filename), partNum))
    
    doc = ET.parse(filename)
    
    # Double special case: Remove/modify options for old firmware versions.
    if device.firmwareVersion < 6:
        # Old SSX could not trigger on DC accelerometer
        if "Slam Stick X" in device.productName:
            tab = doc.find(".//Tab[@id='TriggersTab']")
            for el in tab.findall("CheckGroup[@id='DCAccelTrigger']"):
                tab.remove(el)
        
        # Recording delay and wake time were mutually exclusive on old SSX.
        # The label and tooltip text on the delay field are also different.
        delayEl = doc.find(".//*[@id='RecordingDelay']/DisableIf")
        wakeEl = doc.find(".//*[@id='WakeTime']/DisableIf")
        delayLabel = doc.find(".//*[@id='RecordingDelay']/Label")
        delayHelp = doc.find(".//*[@id='RecordingDelay']/ToolTip")
        # XXX: Mutual exclusion is creating infinite loop
#         if delayEl is not None and wakeEl is not None:
#             delayEl.set('value', "Config[0x0fff7f]")
#             wakeEl.set('value', "Config[0x0cff7f]")
        if delayLabel is not None:
            delayLabel.set('value', "Wake After Delay:")
        if delayHelp is not None:
            delayHelp.set('value', "Time between the button press and the "
                          "start of the recording, in seconds.")
    
    # Dynamically update the analog accelerometer trigger ranges and gain
    accelRange = None
    analogChannel = device.getAccelChannel(dc=False)
    if analogChannel is not None:
        accelRange = device.getAccelRange(analogChannel.id)
        
    if accelRange is not None:
        analogTrig = doc.find(".//CheckGroup[@id='AnalogAccelTrigger']")
        if analogTrig is not None:
            for lo in analogTrig.findall("FloatAccelerationField/FloatMin"):
                lo.set('value',str(accelRange[0]))
            for hi in analogTrig.findall("FloatAccelerationField/FloatMax"):
                hi.set('value',str(accelRange[1]))
            for gain in analogTrig.findall("FloatAccelerationField/FloatGain"):
                gain.set('value', str((accelRange[1]-accelRange[0])/2**16))
    
    # Dynamically update the DC accelerometer trigger ranges. If there is no
    # DC accelerometer, remove the fields.
    dcChannel = device.getAccelChannel(dc=True)
    if dcChannel is None:
        # No DC accelerometer: just remove all references to it on all tabs.
        for tab in doc.findall('.//Tab'):
            for el in tab.findall("*[@channel='DCAccel']"):
                tab.remove(el)
    else:
        # There is a DC accelerometer. Update the DC accelerometer ranges.
        dcAccelRange = device.getAccelRange(dcChannel.id)
        if dcAccelRange is not None:
            dcTrig = doc.find(".//CheckGroup[@id='DCAccelTrigger']")
            if dcTrig is not None:
                for lo in dcTrig.findall("FloatAccelerationField/FloatMin"):
                    lo.set('value',str(dcAccelRange[0]))
                for hi in dcTrig.findall("FloatAccelerationField/FloatMax"):
                    hi.set('value',str(dcAccelRange[1]))
                # No gain for DC.
    
    # Update the analog channels in the Channels tab
    # The elements are created here, not just updated.
    analogMap = doc.find(".//BitField[@id='AnalogChannelMap']")
    if analogChannel is not None and analogMap is not None:
        ET.SubElement(analogMap, "ConfigID", 
                      {'value': "0x01ff%02x" % analogChannel.id})
        ET.SubElement(analogMap, "Label",
                      {'value': u"Channel %d: %s" % (analogChannel.id, 
                                                     analogChannel.displayName)})
        enables = 0
        for ch in analogChannel.subchannels:
            opt = ET.SubElement(analogMap, "EnumOption")
            label = u"Enable %s" % ch.displayName
            if showAdvanced:
                label += " (Subchannel %d.%d)" % (analogChannel.id, ch.id)
            ET.SubElement(opt, "Label", {'value': label})
            enables = (enables << 1) | 1
        
        ET.SubElement(analogMap, 'UIntValue', {'value': str(enables)})

    # Remove the membrane sensors if the recorder doesn't have them.
    channels = device.getChannels()
    if 59 not in channels:
        tab = doc.find(".//Tab[@id='ChannelsTab']")
        for el in tab.findall("*[@channel='FastPT']"):
            tab.remove(el)
    
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
        if val is not None and val != "":
            newD[newK] = val
        

def loadConfigData(device, data=None):
    """ Load old configuration data and return it in the new format.
    
        @param device: The `Recorder` object from which to read the data.
        @keyword data: An alternate set of configuration data, overriding
            that on the device. For importing configuration data.
    """
    logger.info("Loading legacy configuration format")
    
    newData = {}
    if data is None:
        config = device.getConfig(refresh=True).copy()
    else:
        config = data

    channels = device.getChannels()

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
        
        if chId not in channels:
            # Convert really old firmware channel IDs
            if chId == 0 and 8 in channels:
                chId = 8
            elif chId == 1 and 36 in channels:
                chId = 36
            else:
                logger.warning("Ignoring bad trigger channel ID: %r" % chId)
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

    analogChannel = device.getAccelChannel(dc=False)
    dcChannel = device.getAccelChannel(dc=True)

    if analogChannel is not None:
        enableId = 0x01ff00 | (analogChannel.id & 0xFF)
        if enableId not in newData:
            newData[enableId] = 0
            for ch in analogChannel.subchannels:
                newData[enableId] = (newData[enableId] << 1) | 1
    
    if dcChannel is not None:
        newData[0x01ff00 | (dcChannel.id & 0xFF)] = 1

    return newData


def saveConfigData(configData, device, filename=None):
    """ Save new configuration data in the old format. Note: the `configData`
        should not contain any `None` values; these will be ignored.
        
        @param configData: A dictionary of configuration data, in the new
            style (flat, keyed by ConfigID).
        @param device: The device to which to write.
        @keyword filename: The name of the file to write, instead of the
            device's config file. For exporting config data.
    """
    filename = device.configFile if filename is None else filename
    logger.info("Saving %s in legacy configuration format" % filename)
    
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
    
    with open(filename, 'wb') as f:
        f.write(ebml)


def useLegacyFormatPrompt(parent):
    """ Ask the user if they want to overwrite old format config data with
        the new format. Doesn't actually *do* it, just returns if the user
        answered "Yes" or "No" (`True` or `False`).
        
        @param parent: The parent dialog.
    """
    q = wx.MessageBox("The configuration data loaded from this recorder used "
                      "an older format.\n\nIf saved in the old format, some "
                      "configuration may be lost. If saved in the new format, "
                      "the recorder will no longer be configurable with older "
                      "versions of Slam Stick Lab (version 1.7 or earlier).\n\n"
                      "Save using the new format?", 
                      "Save Configuration", 
                      parent=parent, 
                      style=wx.YES_NO|wx.YES_DEFAULT|wx.ICON_WARNING)
    return q == wx.ID_YES


#===============================================================================
# 
#===============================================================================

def convertConfig(device):
    """ Convert a recorder's configuration file from the old format to the new
        version.
    """
    backupName = "%s_old.%s" % os.path.splitext(device.configFile)
    if not os.path.exists(device.configFile):
        return False
    
    try:
        shutil.copy(device.configFile, backupName)
        saveConfigData(loadConfigData(device), device)
        return True
    except:
        shutil.copy(backupName, device.configFile)
        raise
        
    

#===============================================================================
# 
#===============================================================================

# def pprint(d, indent=0):
#     """ Test function for dumping dictionaries.
#         XXX: REMOVE ME.
#     """
#     if isinstance(d, dict):
#         for k,v in d.items():
#             print
#             print (("    " * indent) + k ),
#             pprint(v, indent+1)
#     elif isinstance(d, (tuple, list)):
#         for i in d:
#             print
#             print (("    " * indent) + '[')
#             pprint(i, indent+1)
#             print (("    " * indent) + ']')
#     else:
#         print d
# 
# 
# if __name__ == "__main__":
#     app = wx.App()
#     print useLegacyFormatPrompt(None)