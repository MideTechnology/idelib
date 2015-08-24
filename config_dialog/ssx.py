'''
Created on Jun 25, 2015

@author: dstokes
'''
# import cgi
from collections import OrderedDict
from datetime import datetime
import sys
import time

import wx.lib.sized_controls as SC
# from wx.html import HtmlWindow
import wx; wx = wx

from mide_ebml.parsers import PolynomialParser
# from mide_ebml.ebml.schema.mide import MideDocument
# from common import makeWxDateTime, DateTimeCtrl, cleanUnicode
# import devices


from base import BaseConfigPanel, InfoPanel

#===============================================================================
# 
#===============================================================================

class SSXTriggerConfigPanel(BaseConfigPanel):
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
        
        self.accelTrigCheck = self.addCheck("Acceleration Trigger")
        self.accelLoCheck = self.addFloatField("Accelerometer Trigger, Low:", 
            units="g", tooltip="The lower trigger limit. Less than 0.", 
            value=-5, indent=2, check=False)
        self.accelHiCheck = self.addFloatField("Accelerometer Trigger, High:", 
            units="g", tooltip="The upper trigger limit. Greater than 0.", 
            value=5, indent=2, check=False)
        self.makeChild(self.accelTrigCheck, self.accelLoCheck, self.accelHiCheck)

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
        self.accelTrigCheck.SetValue(False)
        self.setField(self.accelLoCheck, -5, False)
        self.setField(self.accelHiCheck, 5, False)
        
        self.enableAll()
        self.enableField(self.tempTrigCheck)
        self.enableField(self.presTrigCheck)
        self.enableField(self.accelTrigCheck)


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
        super(SSXTriggerConfigPanel, self).initUI()

        accelTransform = self.root.device._unpackAccel
        
        self.controls[self.accelLoCheck][0].SetRange(accelTransform(0), 0)
        self.controls[self.accelHiCheck][0].SetRange(0,accelTransform(65535))

        # Special case for the list of Triggers         
        for trigger in self.data.get("Trigger", []):
            channel = trigger['TriggerChannel']
            subchannel = trigger.get('TriggerSubChannel', None)
            low = trigger.get('TriggerWindowLo', None)
            high = trigger.get('TriggerWindowHi', None)
            if channel == self.accelChannel:
                # Accelerometer. Both or neither must be set.
                low = -5.0 if low is None else accelTransform(low)
                high = 5.0 if high is None else accelTransform(high)
                self.setField(self.accelLoCheck, low)
                self.setField(self.accelHiCheck, high)
                self.accelTrigCheck.SetValue(True)
            elif channel == self.pressTempChannel:
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
        self.enableField(self.accelTrigCheck)


    def getData(self):
        """ Retrieve the values entered in the dialog.
        """
        data = OrderedDict()
        triggers = []
        
        for name,control in self.fieldMap.iteritems():
            self.addVal(control, data, name)
        
        if self.accelTrigCheck.GetValue():
            trig = OrderedDict()
            trig['TriggerChannel']=self.accelChannel
            self.addVal(self.accelLoCheck, trig, "TriggerWindowLo", kind=float,
                        transform=self.root.device._packAccel, 
                        default=self.root.device._packAccel(-5.0))
            self.addVal(self.accelHiCheck, trig, "TriggerWindowHi", kind=float,
                        transform=self.root.device._packAccel, 
                        default=self.root.device._packAccel(5.0))
            if len(trig) > 2:
                triggers.append(trig)
                 
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

class OptionsPanel(BaseConfigPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """
    OVERSAMPLING = map(str, [2**x for x in range(4,13)])
    SAMPLE_RATE = (100,20000,5000) # Min, max, default
    PLUGIN_POLICIES = ['Immediately stop recording and appear as USB drive',
                       'Complete recording before appearing as drive',
                       'Ignore: Stop recording when button is pressed']

    def getDeviceData(self):
        cfg = self.root.device.getConfig()
        self.data = cfg.get('SSXBasicRecorderConfiguration', {}).copy()
        # Hack: flatten RecorderUserData into the rest of the configuration,
        # making things simpler to handle
        self.data.update(cfg.get('RecorderUserData', {}))
        
        if 'UTCOffset' in self.data:
            self.data['UTCOffset'] /= 3600

 
    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.nameField = self.addField("Device Name:", "RecorderName", 
            tooltip="A custom name for the recorder. Not the same as the "
                    "volume label.")
        self.nameField.SetSizerProps(expand=True)

        noteSize = self.nameField.GetSize()
        self.noteField = self.addField("Device Notes:", "RecorderDesc",
            fieldSize=(noteSize[0], noteSize[1]*3), fieldStyle=wx.TE_MULTILINE,
            tooltip="Custom notes about the recorder (position, user ID, etc.)")
        self.noteField.SetSizerProps(expand=True)

        self.addSpacer()
      
        self.samplingCheck = self.addIntField("Sampling Frequency:",
            "SampleFreq", "Hz", minmax=self.SAMPLE_RATE[:2], value=self.SAMPLE_RATE[2],
            tooltip="Checking this field overrides the device's default.")
        
#         self.osrCheck = self.addChoiceField("Oversampling Ratio:", "OSR", 
#             self.OVERSAMPLING, tooltip="Checking this field overrides the "
#             "device's default.")

        self.aaCornerCheck = self.addIntField(
            "Override Antialiasing Filter Cutoff:", "AAFilterCornerFreq", "Hz",
            minmax=(1,20000), value=1000, 
            tooltip="If checked and a value is provided, the input low-pass "
            "filter cutoff will be set to this value.")

        if wx.GetApp().getPref('showAdvancedOptions', False):
            self.aaCheck = self.addCheck("Disable oversampling", "OSR", 
             tooltip="If checked, data recorder will not apply oversampling.")
        
        self.addSpacer()
      
        self.plugPolicy = self.addChoiceField("Plug-in Action", name="PlugPolicy",
            choices=self.PLUGIN_POLICIES, units=None, selected=0,
            tooltip="What a recorder does when attached to USB while recording.")
        self.controls[self.plugPolicy][0].SetSizerProps(expand=True)
         
        self.addSpacer()
      
        self.utcCheck = self.addIntField("Local UTC Offset:", "UTCOffset", 
            "Hours", str(-time.timezone/60/60), minmax=(-24,24), 
            tooltip="The local timezone's offset from UTC time. "
            "Used primarily for file timestamps.")
        
        self.tzBtn = self.addButton("Get Local UTC Offset", -1,  self.OnSetTZ,
            "Fill the UTC Offset field with the offset for the local timezone.")
        self.setTimeCheck = self.addCheck("Set Device Time on Save", 
            tooltip="With this checked, the recorder's clock will be set to "
            "the system time when the configuration is applied.")
        self.setTimeCheck.SetValue(self.root.setTime)
        
        if wx.GetApp().getPref('showAdvancedOptions', False):
            self.addSpacer()
            self.checkDriftBtn = self.addButton("Check Clock Drift", -1, 
                self.OnCheckDrift, tooltip="Read the recorder's clock and "
                "compare to the current system time.")
        
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        self.addButton("Reset to Defaults", wx.ID_DEFAULT, self.OnDefaultsBtn, 
                       "Reset the general configuration to the default values. "
                       "Does not change other tabs.")

        self.Fit()


    def initUI(self):
        BaseConfigPanel.initUI(self)
        self.controls[self.plugPolicy][0].SetSelection(self.data.get('PlugPolicy', 0))


    def OnDefaultsBtn(self, evt):
        """ Reset the device's fields to their factory default.
        """
        # NOTE: This hard-coding is really not very pretty. Revise later.
        self.setField(self.samplingCheck, 5000, False)
        self.setField(self.aaCornerCheck, 1000, False)
        self.aaCheck.SetValue(False)
        self.OnSetTZ(None)

    
    def OnSetTZ(self, event):
        val = int(-time.timezone / 60 / 60) + time.daylight
        self.setField(self.utcCheck, val)


    def OnCheckDrift(self, evt):
        self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
        times = self.root.device.getTime()
        drift = times[0] - times[1]
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        wx.MessageBox("Clock drift: %.4f seconds" % drift, "Check Clock Drift",
                      parent=self, style=wx.OK|wx.ICON_INFORMATION)

    def getData(self):
        """ Retrieve the values entered in the dialog.
        """
        data = OrderedDict()
        
        ssxConfig = OrderedDict()
        userConfig = OrderedDict()
        
        for name,control in self.fieldMap.iteritems():
            if name in ('RecorderName', 'RecorderDesc'):
                self.addVal(control, userConfig, name, self.strOrNone)
            else:
                self.addVal(control, ssxConfig, name)
        
        if 'PlugPolicy' in ssxConfig:
            idx = self.controls[self.plugPolicy][0].GetSelection()
            if idx < 0:
                ssxConfig.pop('PlugPolicy')
            else:
                ssxConfig['PlugPolicy'] = idx
        
        if 'UTCOffset' in ssxConfig:
            ssxConfig['UTCOffset'] *= 3600
        if ssxConfig:
            data["SSXBasicRecorderConfiguration"] = ssxConfig
        if userConfig:
            data["RecorderUserData"] = userConfig
        
       
        if self.setTimeCheck.GetValue():
            try:
                self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
                self.root.device.setTime()
            except IOError:
                wx.MessageBox(
                    "An error occurred when trying to set the recorder's clock.",
                    "Configuration Error", wx.OK | wx.ICON_ERROR, parent=self)
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        self.root.setTime = self.setTimeCheck.GetValue()
        
        return data



#===============================================================================
# 
#===============================================================================

class SSXInfoPanel(InfoPanel):
    """ Specialized InfoPanel that adds special formatting and content based
        on conditions of the recorder.
    """
    
    ICONS = ('../ABOUT/info.png', '../ABOUT/warn.png', '../ABOUT/error.png')

    def getDeviceData(self):
        man = self.root.device.manufacturer
        if man:
            self.data['Manufacturer'] = man
        super(SSXInfoPanel, self).getDeviceData()

    def buildUI(self):
        self.life = self.root.device.getEstLife()
        self.lifeIcon = None
        self.lifeMsg = None
        self.calExp = self.root.device.getCalExpiration()
        self.calIcon = None
        self.calMsg = None
        
        if self.life is not None:
            if self.life < 0:
                self.lifeIcon = self.root.ICON_WARN
                self.lifeMsg = self.ICONS[self.lifeIcon],"This devices is %d days old; battery life may be limited." % self.root.device.getAge()
        
        if self.calExp is not None:
            calExpDate = datetime.fromtimestamp(self.calExp).date()
            if self.calExp < time.time():
                self.calIcon = self.root.ICON_ERROR
                self.calMsg = self.ICONS[self.calIcon],"This device's calibration expired on %s; it may require recalibration." % calExpDate
            elif self.calExp < time.time() - 8035200:
                self.calIcon = self.root.ICON_WARN
                self.calMsg = self.ICONS[self.calIcon],"This device's calibration will expire on %s." % calExpDate

        self.tabIcon = max(self.calIcon, self.lifeIcon, self.tabIcon)
        super(SSXInfoPanel, self).buildUI()


    def addItem(self, k, v, escape=True):
        """ Custom adder that highlights problem items.
        """
        if self.lifeIcon > 0 and k == 'Date of Manufacture':
            k = "<font color='red'>%s</font>" % k
            v = "<font color='red'>%s</font>" % v
            escape = False
        elif self.calIcon > 0 and k == 'Calibration Expiration Date':
            k = "<font color='red'>%s</font>" % k
            v = "<font color='red'>%s</font>" % v
            escape = False

        super(SSXInfoPanel, self).addItem(k, v, escape=escape)
        
    def buildFooter(self):
        warnings = filter(None, (self.lifeMsg, self.calMsg))
        if len(warnings) > 0:
            warnings = ["<tr valign=center><td><img src='%s'></td><td><font color='red'>%s</font></td></tr>" % w for w in warnings]
            warnings.insert(0, "<hr><center><table>")
            warnings.append('</table>')
            if self.root.device.homepage is not None:
                warnings.append("<p>Please visit the <a href='%s'>product's home page</a> for more information.</p>" % self.root.device.homepage)
            warnings.append('</center>')
            self.html.extend(warnings)
        

class SSXExtendedInfoPanel(InfoPanel):
    """
    """
    def getDeviceData(self):
        man = self.root.device.manufacturer
        if man:
            self.data['Manufacturer'] = man
        super(SSXInfoPanel, self).getDeviceData()

    def buildUI(self):
        self.life = self.root.device.getEstLife()
        self.lifeIcon = None
        self.lifeMsg = None
        self.calExp = self.root.device.getCalExpiration()
        self.calIcon = None
        self.calMsg = None
        
        if self.life is not None:
            if self.life < 0:
                self.lifeIcon = self.root.ICON_WARN
                self.lifeMsg = self.ICONS[self.lifeIcon],"This device is %d days old; battery life may be limited." % self.root.device.getAge()
        
        if self.calExp is not None:
            calExpDate = datetime.fromtimestamp(self.calExp).date()
            if self.calExp < time.time():
                self.calIcon = self.root.ICON_ERROR
                self.calMsg = self.ICONS[self.calIcon],"This device's calibration expired on %s; it may require recalibration." % calExpDate
            elif self.calExp < time.time() - 8035200:
                self.calIcon = self.root.ICON_WARN
                self.calMsg = self.ICONS[self.calIcon],"This device's calibration will expire on %s." % calExpDate

        self.tabIcon = max(self.calIcon, self.lifeIcon, self.tabIcon)
        super(SSXInfoPanel, self).buildUI()
    

#===============================================================================
# 
#===============================================================================

class CalibrationPanel(InfoPanel):
    """ Panel for displaying SSX calibration polynomials. Read-only.
    """
    
    def __init__(self, parent, id_, calSerial=None, calDate=None, 
                 calExpiry=None, **kwargs):
        self.calSerial = calSerial
        self.calDate = calDate
        self.calExpiry = calExpiry
        super(CalibrationPanel, self).__init__(parent, id_, **kwargs)
    
    
    def getDeviceData(self):
        if self.info:
            self.info = self.info.values()
        elif hasattr(self.root, 'device'):
            polys = self.root.device.getCalPolynomials()
            if polys is not None:
                self.info = self.root.device.getCalPolynomials().values()
                self.calSerial = self.root.device.getCalExpiration()
                self.calDate = self.root.device.getCalSerial()
            else:
                self.info = []
        else:
            # NOTE: Is this used by anything anymore?
            PP = PolynomialParser(None)
            self.info = [PP.parse(c) for c in self.data.value]
        self.info.sort(key=lambda x: x.id)
        
        
    def cleanFloat(self, f, places=6):
        s = (('%%.%df' % places) % f).rstrip('0')
        if s.endswith('.'):
            return '%s0' % s
        return s
    
    
    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.getDeviceData()
        self.html = [u"<html><body>"]
        
        if self.calSerial:
            self.html.append("<p><b>Calibration Serial: C%03d</b></p>" % self.calSerial)
        if self.calDate or self.calExpiry:
            self.html.append("<p>")
            if self.calDate:
                d = datetime.fromtimestamp(self.calDate).date()
                self.html.append("<b>Calibration Date:</b> %s" % d)
            if self.calDate:
                d = datetime.fromtimestamp(self.calExpiry).date()
                self.html.append("<b>Expires:</b> %s" % d)
            self.html.append("</p>")
        
        if len(self.info) == 0:
            self.html.append("Device has no calibration data.")
        
        for cal in self.info:
            if cal.id is None:
                # HACK: This shouldn't happen.
                continue
            self.html.append("<p><b>Calibration ID %d</b>" % cal.id)
            calType = cal.__class__.__name__
            if hasattr(cal, 'channelId'):
                calType += "; references Channel %d" % cal.channelId
                if hasattr(cal, 'subchannelId'):
                    calType += ", Subchannel %d" % cal.subchannelId
            self.html.append('<ul>')
            self.html.append('<li>%s</li>' % calType)
            if hasattr(cal, 'coefficients'):
                coeffs = ', '.join(map(self.cleanFloat, cal.coefficients))
                refs = ', '.join(map(self.cleanFloat, cal.references))
                self.html.append('<li>Coefficients: <tt>%s</tt></li>' % coeffs)
                self.html.append('<li>Reference(s): <tt>%s</tt></li>' % refs)
            poly = cal.source.split()[-1]
            self.html.append('<li>Polynomial: <tt>%s</tt></li>' % str(cal))
            if str(cal) != poly:
                self.html.append('<li>Polynomial, Reduced: <tt>%s</tt></li>' % poly)
            self.html.append('</ul></p>')

        self.html.append("</body></html>")
        self.SetPage(''.join(self.html))
            

#===============================================================================
# 
#===============================================================================

class ChannelConfigPanel(BaseConfigPanel):
    """ Configuration of channel-specific options.
    """
    
    DC_ACCEL_FREQS = [3200, 1600, 800, 400, 200, 100, 50, 25, 12]
    
    def getDeviceData(self):
        self.accelChannel = self.root.device.getAccelChannel()
        self.accelChannelDC = self.root.device.getAccelChannel(dc=True)
        self.info = self.root.device.getChannels()
    
    
    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.getDeviceData()

        self.startGroup("Channel %d: %s" % (self.accelChannel.id, self.accelChannel.displayName))
        self.indent += 2
        self.accelEnables = [self.addCheck("Enable %s (%d:%d)" % (c.displayName, self.accelChannel.id, c.id)) for c in self.accelChannel.subchannels]
        self.indent -= 2
        self.endGroup()
        
        if self.accelChannelDC is not None:
            # NOTE: Explicit size may not work in future cross-platform versions
            self.fieldSize = (100, 23)
            self.startGroup("Channel %d: %s" % (self.accelChannelDC.id, 
                                                self.accelChannelDC.displayName))
            self.indent += 2
            self.dcEnabled = self.addCheck("Enable (all axes)")
            self.dcSampRate = self.addChoiceField("Sample Rate", units="Hz", 
                                                  choices=self.DC_ACCEL_FREQS, selected=3)
#             self.controls[self.dcSampRate][0].SetSizerProps(expand=True)
            self.indent -= 2
            self.endGroup()
            self.makeChild(self.dcEnabled, self.dcSampRate)
            
#         self.fieldSize = (200, -1)
        self.addSpacer()
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        self.addButton("Reset to Defaults", wx.ID_DEFAULT, self.OnDefaultsBtn, 
                       "Reset the trigger configuration to the default values. "
                       "Does not change other tabs.")
    
    
    def initUI(self):
        """ Populate the dialog's fields.
        """
        super(ChannelConfigPanel, self).initUI()
        self.OnDefaultsBtn()
        
        enableMap = 0xff
        for conf in self.root.deviceConfig.get("SSXChannelConfiguration", []):
            ch = conf.get('ConfigChannel', None)
            if ch == self.accelChannel.id:
                # High-g accelerometer
                enableMap = conf.get("SubChannelEnableMap", enableMap)
                pass
            elif self.accelChannelDC is not None and ch == self.accelChannelDC.id:
                # DC/Low-g accelerometer
                dcEnable = conf.get("SubChannelEnableMap", 0b111) != 0
                self.setField(self.dcEnabled, dcEnable, dcEnable)
                if "ChannelSampleFreq" in conf:
                    self.setField(self.dcSampRate, conf["ChannelSampleFreq"])
        
        for c in self.accelEnables:
            c.SetValue(enableMap & 1 == 1)
            enableMap = enableMap >> 1


    def getData(self):
        """ Retrieve the values entered in the dialog.
        """
        data = []
        accelData = OrderedDict()
        dcData = OrderedDict()
        
        # This is assuming that the default is channel enabled if there is no
        # SubChannelEnableMap element.
        enableMap = 0
        checks = [ch.GetValue() for ch in reversed(self.accelEnables)]
        if not all(checks):
            for en in checks:
                enableMap = (enableMap << 1) | en
            accelData['ConfigChannel'] = self.accelChannel.id
            accelData['SubChannelEnableMap'] = enableMap
            data.append(accelData)
        
        # DC accelerometer doesn't have per-channel enable, so any nonzero
        # value enables the whole thing. Using 0b111 for consistency.
        if self.accelChannelDC is not None:
            dcEnable = 0b111 if self.dcEnabled.GetValue() else 0
            self.addVal(self.dcSampRate, dcData, "ChannelSampleFreq", kind=int)
            if len(dcData) > 0 or dcEnable != 0b111:
                dcData['ConfigChannel'] = self.accelChannelDC.id
                dcData['SubChannelEnableMap'] = dcEnable
                data.append(dcData)

        if len(data) > 0:
            return {"SSXChannelConfiguration": data}
        else:
            return {}


    def OnDefaultsBtn(self, evt=None):
        for c in self.accelEnables:
            c.SetValue(True)
        if self.accelChannelDC is not None:
            self.setField(self.dcEnabled, True, True)
            self.setField(self.dcSampRate, 400, checked=False)
            self.dcSampRate.Enable(True)



#===============================================================================
# 
#===============================================================================

class CalibrationConfigPanel(BaseConfigPanel):
    """
    """
    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.getDeviceData()
        
        self.addSpacer()
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        SC.SizedPanel(self, -1).SetSizerProps(proportion=1)
        self.addButton("Reset to Defaults", wx.ID_DEFAULT, self.OnDefaultsBtn, 
                       "Reset the trigger configuration to the default values. "
                       "Does not change other tabs.")
    
    
    def OnDefaultsBtn(self, evt):
        pass
    

#===============================================================================
# 
#===============================================================================

def buildUI_SSX(parent):
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

    parent.options = OptionsPanel(parent.notebook, -1, root=parent)
    parent.notebook.AddPage(parent.options, "General")
    
    parent.triggers = SSXTriggerConfigPanel(parent.notebook, -1, root=parent)
    parent.notebook.AddPage(parent.triggers, "Triggers")

    if parent.device.firmwareVersion >= 3:
        parent.channels = ChannelConfigPanel(parent.notebook, -1, root=parent)
        parent.notebook.AddPage(parent.channels, "Channels")
            
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