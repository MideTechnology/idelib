'''
Created on Aug 5, 2015

@author: dstokes
'''
from ssx import SSXTriggerConfigPanel #, ChannelConfigPanel
from ssx import OptionsPanel, CalibrationPanel, EditableCalibrationPanel, SSXInfoPanel

#===============================================================================
# 
#===============================================================================

class SSCOptionsPanel(OptionsPanel):
    """
    """
    SAMPLE_RATE = (12,3200,400) # Min, max, default

    def getDeviceData(self):
        OptionsPanel.getDeviceData(self)
        
        # Semi-hack: Remove analog accelerometer sample frequency item, and/or
        # replace it with the DC accelerometer's per-channel sample rate
        self.data.pop('SampleFreq', None)
        
        self.accelChannelDC = self.root.device.getAccelChannel(dc=True)
        if self.accelChannelDC is not None: 
            for ch in self.root.deviceConfig.get('SSXChannelConfiguration', []):
                if ch['ConfigChannel'] == self.accelChannelDC.id:
                    self.data['SampleFreq'] = ch.get('ChannelSampleFreq', 400)
        

    def getData(self):
        data = OptionsPanel.getData(self)
        if self.samplingCheck.GetValue():
            sampRate = self.controls[self.samplingCheck][0].GetValue()
            data['SSXChannelConfiguration'] = {'ConfigChannel': self.accelChannelDC.id,
                                               'ChannelSampleFreq': sampRate}
        else:
            data.pop('SSXChannelConfiguration', None)
        return data

#===============================================================================
# 
#===============================================================================

def buildUI_SSC(parent):
    """ Add the Slam Stick X configuration tabs to the configuration dialog.
    """
    usercal = parent.device.getUserCalPolynomials()
    factorycal = parent.device.getFactoryCalPolynomials()
    
    calSerial = parent.device.getCalSerial()
    calDate = parent.device.getCalDate()
    calExpiry = parent.device.getCalExpiration()
    parent.deviceInfo['CalibrationSerialNumber'] = calSerial
    parent.deviceInfo['CalibrationDate'] = calDate
    parent.deviceInfo['CalibrationExpirationDate'] = calExpiry

    parent.options = SSCOptionsPanel(parent.notebook, -1, root=parent)
    parent.notebook.AddPage(parent.options, "General")
    
    parent.triggers = SSXTriggerConfigPanel(parent.notebook, -1, root=parent)
    parent.notebook.AddPage(parent.triggers, "Triggers")

#     if parent.device.firmwareVersion >= 3:
#         parent.channels = ChannelConfigPanel(parent.notebook, -1, root=parent)
#         parent.notebook.AddPage(parent.channels, "Channels")
            
    if factorycal is not None:
        parent.factorycal = CalibrationPanel(parent.notebook, -1, root=parent,
                                          info=factorycal, calSerial=calSerial,
                                          calDate=calDate, calExpiry=calExpiry)
        parent.notebook.AddPage(parent.factorycal, "Factory Calibration")
        
#     if usercal is not None:
        print "usercal:",usercal
        parent.usercal = EditableCalibrationPanel(parent.notebook, -1, root=parent,
                                          info=usercal, factoryCal=factorycal,
                                          editable=True)
        parent.notebook.AddPage(parent.usercal, "User Calibration")

    info = SSXInfoPanel(parent.notebook, -1, root=parent, info=parent.deviceInfo)
    parent.notebook.AddPage(info, "Device Info")

#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    import __init__
#     __init__.testDialog(save=False)
    __init__.testDialog(save=True)