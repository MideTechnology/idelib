'''
Created on Aug 5, 2015

@author: dstokes
'''

# from ssx import SSXTriggerConfigPanel, ChannelConfigPanel
from ssx import OptionsPanel, CalibrationPanel, SSXInfoPanel

class SSCOptionsPanel(OptionsPanel):
    """
    """
    SAMPLE_RATE = (12,3200,3200) # Min, max, default
    

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
    
#     parent.triggers = SSXTriggerConfigPanel(parent.notebook, -1, root=parent)
#     parent.notebook.AddPage(parent.triggers, "Triggers")

#     if parent.device.firmwareVersion >= 3:
#         parent.channels = ChannelConfigPanel(parent.notebook, -1, root=parent)
#         parent.notebook.AddPage(parent.channels, "Channels")
            
    if factorycal is not None:
        parent.factorycal = CalibrationPanel(parent.notebook, -1, root=parent,
                                          info=factorycal, calSerial=calSerial,
                                          calDate=calDate, calExpiry=calExpiry)
        parent.notebook.AddPage(parent.factorycal, "Factory Calibration")
        
    if usercal is not None:
        parent.usercal = CalibrationPanel(parent.notebook, -1, root=parent,
                                          info=usercal)
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