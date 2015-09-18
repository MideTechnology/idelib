'''
Created on Aug 5, 2015

@author: dstokes
'''
from collections import OrderedDict
import sys

import wx
import wx.lib.sized_controls as SC

# from ssx import SSXTriggerConfigPanel, ChannelConfigPanel
from base import BaseConfigPanel
from ssx import OptionsPanel, CalibrationPanel, SSXInfoPanel


#===============================================================================
# 
#===============================================================================

class SSCTriggerConfigPanel(BaseConfigPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """

    def getDeviceData(self):
        """ Retrieve the device's configuration data (or other info) and 
            put it in the `data` attribute.
        """
        cfg = self.root.device.getConfig()
        self.data = cfg.get('SSXTriggerConfiguration', {})
        
        self.accelChannel = self.root.device.getAccelChannel().id
        self.pressTempChannel = self.root.device.getTempChannel().parent.id


    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.delayCheck = self.addIntField("Wake After Delay:", 
            "PreRecordDelay", "seconds", 0, (0,86400))

        self.wakeCheck = self.addDateTimeField("Wake at specific time:", 
                                               "WakeTimeUTC")
        self.indent += 1
        self.useUtcCheck = self.addCheck("UTC Time", tooltip=\
            "If unchecked, the wake time is relative to the current time zone.")
        self.indent -= 1
        self.useUtcCheck.SetValue(self.root.useUtc)
        self.makeChild(self.wakeCheck, self.useUtcCheck)
        
        self.timeCheck = self.addIntField("Limit recording time to:", 
            "RecordingTime", "seconds", 0, minmax=(0,sys.maxint))
        
        self.rearmCheck = self.addCheck("Re-triggerable", "AutoRearm")
        self.makeChild(self.timeCheck, self.rearmCheck)
        
        self.presTrigCheck = self.addCheck("Pressure Trigger")
        self.pressLoCheck = self.addIntField("Pressure Trigger, Low:", 
            units="Pa", minmax=(0,120000), value=90000, indent=2, check=False)
        self.pressHiCheck = self.addIntField("Pressure Trigger, High:", 
            units="Pa", minmax=(0,120000), value=110000, indent=2, check=False)
        self.makeChild(self.presTrigCheck, self.pressLoCheck, self.pressHiCheck)
         
        self.tempTrigCheck = self.addCheck("Temperature Trigger")
        self.tempLoCheck = self.addFloatField("Temperature Trigger, Low:", 
            units=u'\xb0C', minmax=(-40.0,80.0), value=-15.0, indent=2, check=False)
        self.tempHiCheck = self.addFloatField("Temperature Trigger, High:", 
            units=u'\xb0C', minmax=(-40.0,80.0), value=35.0, indent=2, check=False)
        self.makeChild(self.tempTrigCheck, self.tempLoCheck, self.tempHiCheck)
#         
#         self.accelTrigCheck = self.addCheck("Acceleration Trigger")
#         self.accelLoCheck = self.addFloatField("Accelerometer Trigger, Low:", 
#             units="g", tooltip="The lower trigger limit. Less than 0.", 
#             value=-5, indent=2, check=False)
#         self.accelHiCheck = self.addFloatField("Accelerometer Trigger, High:", 
#             units="g", tooltip="The upper trigger limit. Greater than 0.", 
#             value=5, indent=2, check=False)
#         self.makeChild(self.accelTrigCheck, self.accelLoCheck, self.accelHiCheck)

        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        self.addButton("Reset to Defaults", wx.ID_DEFAULT, self.OnDefaultsBtn, 
                       "Reset the trigger configuration to the default values. "
                       "Does not change other tabs.")

        self.useUtcCheck.Bind(wx.EVT_CHECKBOX, self.OnUtcCheck)

        self.Fit()

    
    def OnDefaultsBtn(self, evt):
        """ Apply the factory defaults, both in the field values and whether the
            field is checked.
        """
        # NOTE: This hard-coding is really not very pretty. Revise later.
        self.setField(self.delayCheck, 0, False)
        self.setField(self.timeCheck, 0, False)
        self.setField(self.wakeCheck, wx.DateTime_Now().GetTicks(), False)
        self.useUtcCheck.SetValue(False)
        self.useUtcCheck.Enable(False)
        self.rearmCheck.SetValue(False)

        self.tempTrigCheck.SetValue(False)
        self.setField(self.pressLoCheck, 90000, False)
        self.setField(self.pressHiCheck, 110000, False)
        self.presTrigCheck.SetValue(False)
        self.setField(self.tempLoCheck, -15, False)
        self.setField(self.tempHiCheck, 35, False)
#         self.accelTrigCheck.SetValue(False)
#         self.setField(self.accelLoCheck, -5, False)
#         self.setField(self.accelHiCheck, 5, False)
        
        self.enableAll()
        self.enableField(self.tempTrigCheck)
        self.enableField(self.presTrigCheck)
#         self.enableField(self.accelTrigCheck)


    def OnCheckChanged(self, evt):
        """ General checkbox event handler.
        """
        cb = evt.EventObject
        if cb in self.controls:
            self.enableField(cb)
            if cb == self.delayCheck or cb == self.wakeCheck:
                # Recording delay and wake time are mutually exclusive options
                if cb == self.wakeCheck:
                    other = self.delayCheck
                else:
                    other = self.wakeCheck
                other.SetValue(False)
                self.enableField(other)


    def OnUtcCheck(self, evt):
        """ Update the displayed time with or without the local UTC offset.
        """
        if not self.wakeCheck.GetValue():
            # wake time field unchecked; skip changing. Can occur on startup.
            return
        dt = self.controls[self.wakeCheck][0].GetValue()
        if evt is True or evt.IsChecked():
            t = dt.ToTimezone(dt.UTC).GetTicks()
        else:
            t = dt.FromTimezone(dt.UTC).GetTicks()
        self.setField(self.wakeCheck, t)

    
    def initUI(self):
        """ Populate the UI.
        """
        super(SSCTriggerConfigPanel, self).initUI()

#         accelTransform = self.root.device._unpackAccel
#         
#         self.controls[self.accelLoCheck][0].SetRange(accelTransform(0), 0)
#         self.controls[self.accelHiCheck][0].SetRange(0,accelTransform(65535))
# 
#         # Special case for the list of Triggers         
        for trigger in self.data.get("Trigger", []):
            channel = trigger['TriggerChannel']
            subchannel = trigger.get('TriggerSubChannel', None)
            low = trigger.get('TriggerWindowLo', None)
            high = trigger.get('TriggerWindowHi', None)
#             if channel == self.accelChannel:
#                 # Accelerometer. Both or neither must be set.
#                 low = -5.0 if low is None else accelTransform(low)
#                 high = 5.0 if high is None else accelTransform(high)
#                 self.setField(self.accelLoCheck, low)
#                 self.setField(self.accelHiCheck, high)
#                 self.accelTrigCheck.SetValue(True)
#             elif channel == self.pressTempChannel:
            if channel == self.pressTempChannel:
                if subchannel == 0:
                    # Pressure
                    self.presTrigCheck.SetValue(True)
                    self.setField(self.pressLoCheck, low)
                    self.setField(self.pressHiCheck, high)
                elif subchannel == 1:
                    # Temperature
                    self.tempTrigCheck.SetValue(True)
                    self.setField(self.tempLoCheck, low)
                    self.setField(self.tempHiCheck, high)
        
        if self.root.useUtc:
            self.OnUtcCheck(True)
        
        self.enableAll()

        # HACK: Fields and parent check both in controls, so enableAll doesn't
        # always work. Refactor later.
        self.enableField(self.presTrigCheck)
        self.enableField(self.tempTrigCheck)
#         self.enableField(self.accelTrigCheck)


    def getData(self):
        """ Retrieve the values entered in the dialog.
        """
        data = OrderedDict()
        triggers = []
        
        for name,control in self.fieldMap.iteritems():
            self.addVal(control, data, name)
        
#         if self.accelTrigCheck.GetValue():
#             trig = OrderedDict()
#             trig['TriggerChannel']=self.accelChannel
#             self.addVal(self.accelLoCheck, trig, "TriggerWindowLo", kind=float,
#                         transform=self.root.device._packAccel, 
#                         default=self.root.device._packAccel(-5.0))
#             self.addVal(self.accelHiCheck, trig, "TriggerWindowHi", kind=float,
#                         transform=self.root.device._packAccel, 
#                         default=self.root.device._packAccel(5.0))
#             if len(trig) > 2:
#                 triggers.append(trig)
                  
        if self.presTrigCheck.GetValue():
            trig = OrderedDict()
            trig['TriggerChannel'] = self.pressTempChannel
            trig['TriggerSubChannel'] = 0
            self.addVal(self.pressLoCheck, trig, 'TriggerWindowLo')
            self.addVal(self.pressHiCheck, trig, 'TriggerWindowHi')
            if len(trig) > 2:
                triggers.append(trig)
                      
        if self.tempTrigCheck.GetValue():
            trig = OrderedDict()
            trig['TriggerChannel'] = self.pressTempChannel
            trig['TriggerSubChannel'] = 1
            self.addVal(self.tempLoCheck, trig, 'TriggerWindowLo')
            self.addVal(self.tempHiCheck, trig, 'TriggerWindowHi')
            if len(trig) > 2:
                triggers.append(trig)
         
        if len(triggers) > 0:
            data['Trigger'] = triggers
        
        self.root.useUtc = self.useUtcCheck.GetValue()
        if self.root.useUtc and 'WakeTimeUTC' in data:
            t = self.controls[self.wakeCheck][0].GetValue()
            data['WakeTimeUTC'] = t.FromUTC().GetTicks()
        
        if data:
            return OrderedDict(SSXTriggerConfiguration=data)
        
        return data


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
    
    parent.triggers = SSCTriggerConfigPanel(parent.notebook, -1, root=parent)
    parent.notebook.AddPage(parent.triggers, "Triggers")

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