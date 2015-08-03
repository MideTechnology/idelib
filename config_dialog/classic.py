'''
Created on Jun 25, 2015

@author: dstokes
'''
import cgi
from collections import OrderedDict
from datetime import datetime
import string
import time

import wx.lib.sized_controls as SC
from wx.html import HtmlWindow
import wx; wx = wx

from mide_ebml import util
from mide_ebml.parsers import PolynomialParser
# from mide_ebml.ebml.schema.mide import MideDocument
from common import makeWxDateTime, DateTimeCtrl, cleanUnicode
import devices

from base import BaseConfigPanel, InfoPanel

#===============================================================================
# Slam Stick Classic configuration panels
#===============================================================================

class ClassicTriggerConfigPanel(BaseConfigPanel):
    """
    """
    CHIME_TIMES = OrderedDict((
        (0b00000000, 'Every 0.5 seconds'),
        (0b00000100, 'Every 1 second'),
        (0b00001000, 'Every 10 seconds'),
        (0b00001100, 'Every 1 minute'),
        (0b00010000, 'Every 10 minutes'),
        (0b00010100, 'Every 1 Hour'),
        (0b00011000, 'Every 1 Day'),
        (0b00011100, 'Every 1 Week'),
        (0b00100000, 'Every 1 Month'),
        (0b00100100, 'At specified time only')
    ))
    
    NAP_TIMES = OrderedDict((
        (0, "Continuous"),
        (7, "1 Hz"),
        (6, "2 Hz"),
        (5, "4 Hz"),
        (4, "8 Hz"),
    ))

    
    def getDeviceData(self):
        self.data = self.info = self.root.device.getConfig().copy()
        if self.data['ALARM_TIME'] == 0:
            self.data['ALARM_TIME'] = datetime.now()
        
#         if not self.root.useUtc:
#             self.data['ALARM_TIME'] = datetime2int(self.data['ALARM_TIME'], 
#                                                    -time.timezone+time.daylight)

    
    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.delayCheck = self.addIntField("Delay After Button Press:", 
            "RECORD_DELAY", "seconds", minmax=(0,2**17-4), check=False,
            tooltip="Seconds to delay between pressing the 'record' button "
            "and the start of recording. Note: This will be rounded to the "
            "lowest multiple of 2.")
        self.timeCheck = self.addIntField(
            "Recording Length Limit:", "SECONDS_PER_TRIGGER", "seconds", 
            minmax=(0,2**17-4), check=False, tooltip="Recording length. "
            "Note: This will be rounded to the lowest multiple of 2. "
            "Zero is no limit.")
        
#         self.sampleCountCheck = self.addIntField(
#             "Recording Limit, Samples:", "SAMPLES_PER_TRIGGER", "samples", 
#             minmax=(0,2**16))
        
        self.indent += 1
        self.rearmCheck = self.addCheck("Re-triggerable",
            tooltip="Recorder will restart when triggering event re-occurs. "
            "Only applicable when the recording length is limited.")
        self.indent -= 1
        
        self.wakeCheck = self.addDateTimeField("Alarm Time:", "ALARM_TIME", 
            tooltip="The date and time used for all interval triggers. "
            "Note: the year is ignored.")
        self.indent += 2
        self.useUtcCheck = self.addCheck("Use UTC Time")
        self.indent -= 2
        self.useUtcCheck.SetValue(self.root.useUtc)
        
        self.intervalField = self.addChoiceField("Trigger at Intervals", 
            choices=self.CHIME_TIMES.values(), check=False, 
            selected=len(self.CHIME_TIMES)-1, 
            tooltip="The frequency at which to take recordings, based on "
            "the Alarm Time.")
        self.chimeCheck = self.addIntField("Limit Number of Triggers:", 
            'REPEATS', minmax=(0,254), tooltip="The number of interval-based "
            "triggers to record, in addition to the first. Does not include "
            "recordings started by the accelerometer trigger.")
        self.makeChild(self.wakeCheck, self.useUtcCheck, self.intervalField, self.chimeCheck)
        # Keep track of wakeCheck apart from the group so enabling works,
        # so the next line should remain commented out. 
#         self.makeChild(self.intGroup, self.wakeCheck)
        self.endGroup()
        
        self.startGroup('Accelerometer Triggers')
        self.accelTrigCheck = self.addFloatField("Accelerometer Threshold:", 
            'TRIG_THRESH_ACT', units="g", minmax=(0.0,16.0), precision=0.01, 
            tooltip="The minimum acceleration to trigger recording. "
            "Note: due to noise, 0 may cause undesired operation.")
        self.indent += 1
        self.xCheck = self.addCheck("X Axis Trigger",
            tooltip="Acceleration on X axis will trigger recording.")
        self.yCheck = self.addCheck("Y Axis Trigger",
            tooltip="Acceleration on Y axis will trigger recording.")
        self.zCheck = self.addCheck("Z Axis Trigger",
            tooltip="Acceleration on Z axis will trigger recording.")
        self.acCheck = self.addCheck("Ignore Gravity", 
             tooltip="AC couple the input to trigger on accelerometer changes, "
             "ignoring the constant 1 G acceleration of Earth's gravity.")
        self.napCheck = self.addChoiceField("Accel. Check Interval",
             choices=self.NAP_TIMES.values(), selected=0, check=False,
             tooltip="The frequency at which the recorder will check the "
             "accelerometer trigger. Lower values use less power.")
        
        self.makeChild(self.accelTrigCheck, self.xCheck, self.yCheck, 
                       self.zCheck, self.acCheck, self.napCheck)
        self.indent -= 1
        self.endGroup()
        
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        self.addButton("Reset to Defaults", wx.ID_DEFAULT, self.OnDefaultsBtn, 
                       "Reset the trigger configuration to the default values. "
                       "Does not change other tabs.")

        self.useUtcCheck.Bind(wx.EVT_CHECKBOX, self.OnUtcCheck)
        self.Fit()

        
    def OnDefaultsBtn(self, evt):
        self.setField(self.chimeCheck, 0, checked=False)
        self.setField(self.accelTrigCheck, 8.0, checked=False)
        self.xCheck.SetValue(True)
        self.xCheck.Enable(False)
        self.yCheck.SetValue(True)
        self.yCheck.Enable(False)
        self.zCheck.SetValue(True)
        self.zCheck.Enable(False)
        self.acCheck.SetValue(True)
        self.acCheck.Enable(False)
        self.setField(self.napCheck, self.NAP_TIMES.values()[0])
        self.enableField(self.napCheck, False)
        

    def OnCheckChanged(self, evt):
        cb = evt.EventObject
        if cb in self.controls:
            self.enableField(cb)
            if cb == self.delayCheck or cb == self.wakeCheck:
                if cb == self.wakeCheck:
                    other = self.delayCheck
                else:
                    other = self.wakeCheck
                    
                if hasattr(other, 'SetValue'):
                    other.SetValue(False)
                self.enableField(other)


    def OnUtcCheck(self, evt):
        """ Update the displayed time with or without the local UTC offset.
        """
        dt = self.controls[self.wakeCheck][0].GetValue()
        if evt is True or evt.IsChecked():
            t = dt.ToTimezone(dt.UTC).GetTicks()
        else:
            t = dt.FromTimezone(dt.UTC).GetTicks()
        self.setField(self.wakeCheck, t)


    def initUI(self):
        """ Fill out the UI.
        """ 
        self.getDeviceData()
        super(ClassicTriggerConfigPanel, self).initUI()
        
        # Hide fields not supported by earlier versions of the firmware
        if self.info.get('SWREV', 0) < 2:
#             self.hideField(self.intGroup)
            self.hideField(self.wakeCheck)
        
        trigs = self.info.get('TRIG_ACT_INACT_REG', 0)
        self.acCheck.SetValue((trigs & 0b10000000) != 0)
        self.xCheck.SetValue((trigs & 0b01000000) != 0)
        self.yCheck.SetValue((trigs & 0b00100000) != 0)
        self.zCheck.SetValue((trigs & 0b00010000) != 0)
        
        if self.root.useUtc:
            self.OnUtcCheck(True)
            
        trigs = self.info.get('TRIGGER_FLAGS', 0)
        self.accelTrigCheck.SetValue((trigs[1] & 0b10000000) != 0)
        self.wakeCheck.SetValue((trigs[1] & 0b00001000) != 0)
        
        conf = self.info.get('CONFIG_FLAGS', 0b10000000)
        self.rearmCheck.SetValue((conf & 0b01000000) and True)
        
        self.setField(self.chimeCheck, self.info.get('REPEATS', 0),
                      checked=(not self.info.get('CHIME_EN',0) & 1))
        self.setField(self.intervalField, 
                      self.CHIME_TIMES.get(self.info.get('ROLLPERIOD',0)))
        
        self.enableAll()
        self.enableField(self.napCheck, self.accelTrigCheck.GetValue())
        self.enableField(self.intervalField, self.wakeCheck.GetValue())
        
        if self.info['SWREV'] > 1 and self.info['CONFIGFILE_VER'] == 1:
            self.setField(self.chimeCheck, 0, checked=False)
    
    
    def getData(self):
        """ Retrieve the values entered in the dialog.
        """
        data = OrderedDict()
        
        for name,control in self.fieldMap.iteritems():
            self.addVal(control, data, name)

        trigAxes = 0
        if self.acCheck.GetValue(): trigAxes |= 0b10000000
        if self.xCheck.GetValue(): trigAxes |=  0b01000000
        if self.yCheck.GetValue(): trigAxes |=  0b00100000
        if self.zCheck.GetValue(): trigAxes |=  0b00010000
        data['TRIG_ACT_INACT_REG'] = trigAxes
        
        trigFlags = self.info['TRIGGER_FLAGS'][:]
        trigFlags[1] = 0
        if self.accelTrigCheck.GetValue(): trigFlags[1] |= 0b10000000
        if self.wakeCheck.GetValue(): trigFlags[1] |= 0b00001000
        data['TRIGGER_FLAGS'] = trigFlags
        
        confFlags = 0b10000000
        if self.rearmCheck.GetValue(): confFlags |= 0b01000000
        data['CONFIG_FLAGS'] = confFlags
        
        if self.chimeCheck.GetValue():
            # CHIME is enabled when recording count NOT limited!
            data['CHIME_EN'] = 0
        else:
            data['CHIME_EN'] = 1
            
        data['ROLLPERIOD'] = self.CHIME_TIMES.keys()[self.controls[self.intervalField][0].GetSelection()]
        
        self.root.useUtc = self.useUtcCheck.GetValue()
        if self.root.useUtc and self.wakeCheck.GetValue():
            t = self.controls[self.wakeCheck][0].GetValue()
            data['ALARM_TIME'] = t.FromUTC().GetTicks()

        return data
    
#===============================================================================

class ClassicOptionsPanel(BaseConfigPanel):
    """
    """
    SAMPLE_RATES = OrderedDict((#(0x06, '6.25'), 
                                #(0x07, '12.5'), 
                                #(0x08, '25'), 
                                #(0x09, '50'), 
                                (0x0A, '100'), 
                                (0x0B, '200'), 
                                (0x0C, '400'), 
                                (0x0D, '800'), 
                                (0x0E, '1600'), 
                                (0x0F, '3200')))
    
    
    def getDeviceData(self):
        self.info = self.root.device.getConfig().copy()


    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.nameField = self.addField("Device Name:", "USER_NAME", 
            tooltip="A custom name for the recorder. Not the same as the "
                    "volume label. 64 characters maximum.")
        self.nameField.SetSizerProps(expand=True)

        noteSize = self.nameField.GetSize()
        self.noteField = self.addField("Device Notes:", "USER_NOTES",
            fieldSize=(noteSize[0], noteSize[1]*3), fieldStyle=wx.TE_MULTILINE,
            tooltip="Custom notes about the recorder (position, user ID, etc.)."
            " 256 characters maximum.")
        self.noteField.SetSizerProps(expand=True)

        self.addSpacer()
        
        self.samplingCheck = self.addChoiceField("Sampling Frequency:",
            'BW_RATE_PWR', "Hz", choices=self.SAMPLE_RATES.values(), 
            selected=len(self.SAMPLE_RATES)-1, check=False)
        
        self.addSpacer()
        
        self.rtccCheck = self.addCheck("Enable Realtime Clock/Cal.")
        self.indent += 1
        self.setTimeCheck = self.addCheck("Set RTCC Time/Date", 
           tooltip="Set the device's realtime clock/calendar to the current "
           "system time on save")
        self.setTimeCheck.SetValue(self.root.setTime)
        self.utcCheck = self.addField("UTC Offset:", "TZ_OFFSET", "Hours", 
            str(-time.timezone/60/60), tooltip="The local timezone's offset "
            "from UTC time. Used only for file timestamps.")
        self.tzBtn = self.addButton("Get UTC", -1,  self.OnSetTZ,
            "Fill the UTC Offset field with the offset for the local timezone")
        self.makeChild(self.rtccCheck, self.setTimeCheck, self.utcCheck, self.tzBtn)
        self.indent -= 1
        
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        self.addButton("Reset to Defaults", wx.ID_DEFAULT, self.OnDefaultsBtn, 
                       "Reset the general configuration to the default values. "
                       "Does not change other tabs.", size=(-1,-1))

        self.Fit()


    def OnDefaultsBtn(self, evt):
        self.rtccCheck.SetValue(True)
        self.enableField(self.rtccCheck)
        self.setTimeCheck.SetValue(True)
        self.setTimeCheck.Enable(True)
        self.setField(self.samplingCheck, self.SAMPLE_RATES.values()[-1])
        self.enableField(self.samplingCheck, True)


    def initUI(self):
        self.getDeviceData()
        
        if self.info.get('SWREV', 0) < 2:
            self.hideField(self.rtccCheck)
            self.hideField(self.samplingCheck)
        
        for k,v in self.info.iteritems():
            c = self.fieldMap.get(k, None)
            if c is None:
                continue
            self.setField(c, v)
        
        self.rtccCheck.SetValue(self.info.get('RTCC_ENA',0) and True)
        
        r = self.info.setdefault('BW_RATE_PWR', 0x0f) & 0xf
        if r in self.SAMPLE_RATES:
            ridx = self.SAMPLE_RATES[r]
        else:
            ridx = self.SAMPLE_RATES.values()[-1]
        self.setField(self.samplingCheck, ridx)


    def OnSetTZ(self, event):
        val = str((-time.timezone / 60 / 60) + time.daylight)
        self.setField(self.utcCheck, val)


    def getData(self):
        """ Retrieve the values entered in the dialog.
        """
        data = self.info.copy()
        
        for name,control in self.fieldMap.iteritems():
            self.addVal(control, data, name)
        
        samplingIdx = self.controls[self.samplingCheck][0].GetSelection()
        data['BW_RATE_PWR'] = self.SAMPLE_RATES.keys()[samplingIdx]

        if self.rtccCheck.GetValue():
            data['RTCC_ENA'] = 1
            if self.setTimeCheck.GetValue():
                # Set the 'RTCC write' flag and the time.
                data['WR_RTCC'] = 0x5A
                data['RTCC_TIME'] = datetime.now()
        else:
            data['RTCC_ENA'] = 0
        
        # Simple test to update config file version. 
        if data['SWREV'] > 1:
            data['CONFIGFILE_VER'] = max(2, data['CONFIGFILE_VER'])
            
        self.root.setTime = self.setTimeCheck.GetValue()
        return data

#===============================================================================

class ClassicInfoPanel(InfoPanel):
    """ Display read-only attributes of a Slam Stick Classic recorder.
    """
    
    def getDeviceData(self):
        info = self.root.deviceInfo
        vers = info['VERSION_STR']
        uid = cleanUnicode(info['SYSUID_RESERVE'] or "None")
        self.data = OrderedDict((
            ('Device Type', 'Slam Stick Classic'),
            ('System UID', uid),
            ('Version String', vers),
            ('Hardware Revision', info['HWREV']), 
            ('Firmware Revision', info['SWREV']), 
            ('Config. Format Version', info['CONFIGFILE_VER']), 
         ))
        if 'U' in vers:
            # Unlikely to ever be missing, but just in case...
            self.data['Capacity'] = "%s MB" % vers[vers.index('U')+1:]

#===============================================================================
# 
#===============================================================================

def buildUI_Classic(parent):
    parent.options = ClassicOptionsPanel(parent.notebook, -1, root=parent)
    parent.triggers = ClassicTriggerConfigPanel(parent.notebook, -1, root=parent)
    info = ClassicInfoPanel(parent.notebook, -1, root=parent)
    parent.notebook.AddPage(parent.options, "General")
    parent.notebook.AddPage(parent.triggers, "Triggers")
    parent.notebook.AddPage(info, "Device Info")


#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    import __init__
    __init__.testDialog(save=False)
#     __init__.testDialog(save=True)