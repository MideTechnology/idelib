'''
Created on Dec 16, 2013

@author: dstokes
'''

from collections import OrderedDict
import string
import time

import wx.lib.sized_controls as sc
import wx.lib.masked as mc
import wx; wx = wx

from common import time2int
from mide_ebml import util

#===============================================================================
# 
#===============================================================================

class BaseConfigPanel(sc.SizedPanel):
    """ The base class for the various configuration pages. Defines some
        common methods for adding controls, setting defaults, and reading
        values.
    """

    def addField(self, labelText, name=None, fieldText="", fieldSize=None, 
                 fieldStyle=None, tooltip=None):
        """ Helper method to create and configure a labeled text field. 
        """
        fieldSize = self.fieldSize if fieldSize is None else fieldSize
        txt = unicode(fieldText)
        c = wx.StaticText(self, -1, labelText)
        c.SetSizerProps(valign="center")
        if fieldStyle is None:
            t = wx.TextCtrl(self, -1, txt, size=fieldSize)
        else:
            t = wx.TextCtrl(self, -1, txt, size=fieldSize, style=fieldStyle)

        if tooltip is not None:
            t.SetToolTipString(unicode(tooltip))
            
        if self.fieldSize is None:
            self.fieldSize = t.GetSize()
        
        if name is not None:
            self.fieldMap[name] = t
            
        return t
    
    
    def addCheck(self, checkText, name=None, tooltip=None):
        """ Helper method to create a single checkbox and add it to the set of
            controls. 
        """
        c = wx.CheckBox(self, -1, checkText)
        if name is not None:
            self.fieldMap[name] = c
        sc.SizedPanel(self, -1) # Spacer
        self.controls[c] = [None]
        if name is not None:
            self.fieldMap[name] = c
        return c


    def addCheckField(self, checkText, name=None, fieldText="", fieldSize=None, 
                      fieldStyle=None, tooltip=None):
        """ Helper method to create and configure checkbox/field pairs, and add
            them to the set of controls.
        """
        fieldSize = self.fieldSize if fieldSize is None else fieldSize
        txt = unicode(fieldText)

        c = wx.CheckBox(self, -1, checkText)
        c.SetSizerProps(valign="center")
        if fieldStyle is None:
            t = wx.TextCtrl(self, -1, txt, size=fieldSize)
        else:
            t = wx.TextCtrl(self, -1, txt, size=fieldSize, style=fieldStyle)
        self.controls[c] = [t]
        
        if tooltip is not None:
            c.SetToolTipString(unicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = t.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
            
        return c, t


    def addTimeField(self, checkText, name=None, value=None, tooltip=None):
        """ Helper method to create a checkbox and a time-entry field pair, and
            add them to the set of controls.
        """ 
        check = wx.CheckBox(self, -1, checkText)
        check.SetSizerProps(valign='center')
        timePane = sc.SizedPanel(self, -1)
        timePane.SetSizerType("horizontal")
        ctrl = mc.TimeCtrl(timePane, -1, fmt24hr=True)
        timeSpin = wx.SpinButton(timePane, -1, size=(-1,self.fieldSize.height), 
                                 style=wx.SP_VERTICAL)
        ctrl.BindSpinButton(timeSpin)
        if tooltip is not None:
            check.SetToolTipString(unicode(tooltip))

        self.controls[check] = [ctrl, timeSpin]
        
        if name is not None:
            self.fieldMap[name] = ctrl

        return check, ctrl
    
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard dialog arguments, plus:
        
            @keyword root: The viewer's root window.
            @keyword data: A dictionary of values read from the device.
        """
        self.root = kwargs.pop('root', None)
        self.data = kwargs.pop('data', {})
        super(BaseConfigPanel, self).__init__(*args, **kwargs)
        
        self.fieldSize = (-1,-1)
        self.SetSizerType("form", {'hgap':10, 'vgap':10})
        
        # controls: fields keyed by their corresponding checkbox.
        self.controls = {}
        
        # fieldMap: All fields keyed by their corresponding key in the data.
        self.fieldMap = {}
        
        self.buildUI()
        self.initUI()
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckChanged)


    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        pass


    def initUI(self):
        """ Do any setup work on the page. Most subclasses should override
            this.
        """
        for c in self.controls:
            self.enableAll(c)


    def enableAll(self, checkbox, state=True):
        """ Enable (or disable) all the other controls associated with a
            checkbox.
        """
        for c in self.controls[checkbox]:
            c.Enable(checkbox.GetValue())
        

    def parseTime(self, timeStr):
        """ Turn a string containing a length of time as S.s, M:S.s, or H:M:S.s
            into the corresponding number of seconds. For parsing text fields.
        """
        t = map(lambda x: float(x.strip(string.letters+" ,")), 
                reversed(timeStr.strip().replace(',',':').split(':')))
        if len(t) > 4:
            raise ValueError("Time had too many columns to parse: %r" % timeStr)
        if len(t) == 4:
            total = t.pop() * (24*60*60)
        else:
            total = 0
        for i in xrange(len(t)):
            total += t[i] * (60**i)
        return total


    def setCheckField(self, checkbox, value):
        """ Check a checkbox and set its associated field.
        """
        checkbox.SetValue(True)
        if checkbox in self.controls and self.controls[checkbox]:
            field = self.controls[checkbox][0]
            if field is None:
                return
            if isinstance(field, wx.TextCtrl):
                value = str(value)
            field.SetValue(value)
        
        self.controls[checkbox][0].SetValue(value)
    

    def OnCheckChanged(self, evt):
        cb = evt.EventObject
        if cb in self.controls:
            self.enableAll(cb)


    def addVal(self, check, trig, name, kind=int):
        """ Helper method to add a field's value to a dictionary if its
            corresponding checkbox is checked. For exporting EBML.
         """
        if check not in self.controls:
            return
        
        if check.GetValue() and check.Enabled:
            field = self.controls[check][0]
            if isinstance(field, wx.Choice):
                val = field.GetStrings()[field.GetCurrentSelection()]
            else:
                val = field.GetValue()
            try:
                val = kind(val)
                if val is not None:
                    trig[name] = val
            except ValueError:
                pass
        

#===============================================================================
# 
#===============================================================================

class TriggerConfigPanel(BaseConfigPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """

    def buildUI(self):
        self.delayCheck, self.delayField = self.addCheckField(
            "Wake After Delay:", "PreRecordDelay")

        self.wakeCheck, self.wakeTimeField = self.addTimeField(
            "Wake at specific time:", "WakeTimeUTC")
        
        self.triggerDelayCheck, self.triggerDelayField = self.addCheckField(
            "Delay Trigger Activation:", "PreRecordingDelay",
            tooltip="Enable event-based triggers after a given number of seconds")
        
        self.timeCheck, self.timeField = self.addCheckField(
            "Limit recording time to:", "RecordingTime")
        
        self.rearmCheck = self.addCheck("Re-triggerable", "AutoRearm")
        self.controls[self.timeCheck].append(self.rearmCheck)
        
        self.accelCheck, self.accelField = \
            self.addCheckField("Accelerometer Trigger (High):")
        self.pressLoCheck, self.pressLoField = \
            self.addCheckField("Pressure Trigger (Low)")
        self.pressHiCheck, self.pressHiField = \
            self.addCheckField("Pressure Trigger (High)")
        self.tempLoCheck, self.tempLoField = \
            self.addCheckField("Temperature Trigger (Low)")
        self.tempHiCheck, self.tempHiField = \
            self.addCheckField("Temperature Trigger (High)")

#         self.Bind(wx.EVT_DATE_CHANGED, self.OnDateChanged, self.wakeDateField)
        print self.timeField.GetValue()


    def OnDateChanged(self, evt):
        evt.Skip()


    def OnCheckChanged(self, evt):
        cb = evt.EventObject
        if cb in self.controls:
            self.enableAll(cb)
            if cb == self.delayCheck or cb == self.wakeCheck:
                if cb == self.wakeCheck:
                    other = self.delayCheck
                else:
                    other = self.wakeCheck
                other.SetValue(False)
                self.enableAll(other)


    def initUI(self):
        """
        """
        if not self.data:
            return
        
        for k,v in self.data.iteritems():
            if k == "AutoRearm":
                self.rearmCheck.SetValue(v != 0)
            else:
                self.setCheckField(k, v)
                
            if k == "WakeTimeUTC":
                self.setCheckField(self.wakeCheck, time.gmtime(v))
            elif k == "PreRecordingDelay":
                self.setCheckField(self.triggerDelayCheck, str(v))
            elif k == "RecordingTime":
                self.setCheckField(self.timeCheck, str(v))
            elif k == "AutoRearm":
                self.rearmCheck.SetValue(v != 0)
                
            elif k == "Trigger":
                for trigger in v:
                    channel = trigger['TriggerChannel']
                    subchannel = trigger.get('TriggerSubChannel', None)
                    if channel == 0:
                        # Accelerometer
                        pass
                    elif channel == 1:
                        if subchannel == 0:
                            # Pressure
                            pass
                        elif subchannel == 1:
                            # Temperature
                            pass 
        self.enableAll()


    def getData(self):
        """
        """
        data = OrderedDict()
        triggers = []
        
        self.addVal(self.wakeCheck, data, "WakeTimeUTC", time2int)
        self.addVal(self.delayCheck, data, "PreRecordDelay")
        self.addVal(self.timeCheck, data, "RecordingTime")
        
        if self.rearmCheck.GetValue():
            data['AutoRearm'] = 1 if self.rearmCheck.GetValue() else 0
            
        if self.accelCheck.GetValue():
            trig = OrderedDict(TriggerChannel=0)
            self.addVal(self.accelCheck, trig, "TriggerWindowHi")
            if len(trig) > 1:
                triggers.append(trig)
                
        if self.pressLoCheck.GetValue() or self.pressHiCheck.GetValue():
            trig = OrderedDict(TriggerChannel=1, TriggerSubChannel=0)
            self.addVal(self.pressLoCheck, trig, 'TriggerWindowLo')
            self.addVal(self.pressHiCheck, trig, 'TriggerWindowHi')
            if len(trig) > 2:
                triggers.append(trig)
                    
        if self.tempLoCheck.GetValue() or self.tempHiCheck.GetValue():
            trig = OrderedDict(TriggerChannel=1, TriggerSubChannel=1)
            self.addVal(self.tempLoCheck, trig, 'TriggerWindowLo')
            self.addVal(self.tempHiCheck, trig, 'TriggerWindowHi')
            if len(trig) > 2:
                triggers.append(trig)
        
        if len(triggers) > 0:
            data['Trigger'] = triggers
        
        if data:
            return {'SSXTriggerConfiguration': data}
        
        return {}
        

#===============================================================================
# 
#===============================================================================

class OptionsPanel(BaseConfigPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """
    
    OVERSAMPLING = map(str, [2**x for x in range(4,13)])
    
    def buildUI(self):
        self.nameField = self.addField("Device Name:", "Slam Stick X")
        self.nameField.SetSizerProps(expand=True)

        noteSize = self.nameField.GetSize()
        self.noteField = self.addField("Device Notes:", 
                                       fieldSize=(noteSize[0], noteSize[1]*3),
                                       fieldStyle=wx.TE_MULTILINE)
        self.noteField.SetSizerProps(expand=True)

        wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL)
        sc.SizedPanel(self, -1) # Spacer
      
        self.samplingCheck, self.samplingField = \
            self.addCheckField("Sampling Rate:",)
        
#         self.oversamplingCheck = wx.CheckBox(self, -1, "Oversampling")
#         sc.SizedPanel(self, -1) # Spacer
 
        self.osrCheck = wx.CheckBox(self, -1, "Oversampling")
        self.osrField = wx.Choice(self, -1, size=self.samplingField.GetSize(),
                                  choices=self.OVERSAMPLING)
        self.osrField.Select(len(self.OVERSAMPLING)/2)
        self.controls[self.osrCheck] = [self.osrField]
        
        self.timeBtn = wx.Button(self, -1, "Set Device Time")
        self.timeBtn.SetSizerProps(expand=True)
        timeFieldPane = sc.SizedPanel(self,-1)
        timeFieldPane.SetSizerType("horizontal")
        wx.StaticText(timeFieldPane, -1, "UTC Offset:"
                      ).SetSizerProps(valign='center')
        self.utcOffsetField = wx.TextCtrl(timeFieldPane, -1, 
                                          str(time.timezone / 60 / 60))
        self.localTimeBtn = wx.Button(timeFieldPane, -1, "Get Local TZ")
        self.localTimeBtn.SetToolTipString("Time Zone: %s" % \
                                           time.tzname[time.daylight])
        
        self.Fit()
        
        self.timeBtn.Bind(wx.EVT_BUTTON, self.OnSetTime)
        self.localTimeBtn.Bind(wx.EVT_BUTTON, self.OnSetTZ)


    def OnSetTime(self, event):
        pass
    
    
    def OnSetTZ(self, event):
        val = str(time.timezone / 60 / 60)
        self.utcOffsetField.SetValue(val)


    def getData(self):
        """
        """
        data = OrderedDict()
        
        ssxConfig = OrderedDict()
        self.addVal(self.samplingCheck, ssxConfig, "SampleFreq")
        self.addVal(self.osrCheck, ssxConfig, "OSR")

        userConfig = OrderedDict()
        devName = self.nameField.GetValue().strip()
        devDesc = self.noteField.GetValue().strip()
        if devName:
            userConfig['RecorderName'] = devName
        if devDesc:
            userConfig['RecorderDesc'] = devDesc
            
        if ssxConfig:
            data["SSXBasicRecorderConfiguration"] = ssxConfig
        if userConfig:
            data["RecorderUserData"] = userConfig
            
        return data
    
#===============================================================================
# 
#===============================================================================
        
class InfoPanel(TriggerConfigPanel):
    """ A configuration dialog page showing various read-only properties of
        a recorder.
    """
    
    def buildUI(self):
        infoColor = wx.Colour(60,60,60)
        mono = wx.Font(self.GetFont().GetPointSize()+1, wx.MODERN, wx.NORMAL, 
                       wx.BOLD, False, u'monospace')
        
        sc.SizedPanel(self, -1) # Spacer
        wx.StaticText(self, -1, "All values are read-only"
                      ).SetForegroundColour("RED")
        
        self.text = []
        
        for k,v in self.root.recorderInfo.iteritems():
            if isinstance(v, int) or isinstance(v, long):
                v = "0x%08X" % v
                
            t = self.addField('%s:' % k, k, v, fieldStyle=wx.TE_READONLY)
            t.SetSizerProps(expand=True)
            t.SetFont(mono)
            t.SetForegroundColour(infoColor)
            self.text.append("%s: %s" % (k,v))
    
        sc.SizedPanel(self, -1) # Spacer
        copyBtn = wx.Button(self, -1, "Copy to Clipboard")
        copyBtn.Bind(wx.EVT_BUTTON, self.OnCopy)
        
        self.Fit()


    def OnCopy(self, evt):
        data = wx.TextDataObject()
        data.SetText("\n".join(self.text))
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(data)
            wx.TheClipboard.Close()
        else:
            wx.MessageBox("Unable to open the clipboard", "Error")

        
#===============================================================================
# 
#===============================================================================

class ConfigDialog(sc.SizedDialog):
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | \
            wx.MINIMIZE_BOX | wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
        
        super(ConfigDialog, self).__init__(*args, **kwargs)
        
        # Dummy info
        self.recorderInfo = {"RecorderTypeUID": 0x000DEFEC,
                             "RecorderSerial": 0xD1DAC71C,
                             "SchemaID": 0x01,
                             "ProductName": "Slam Stick X",
                             "HwRev": 0x01,
                             "FwRev": 0x01
                             }
        
        pane = self.GetContentsPane()
        
        self.notebook = wx.Notebook(pane, -1)
        
        self.triggers = TriggerConfigPanel(self.notebook, -1, root=self)
        self.options = OptionsPanel(self.notebook, -1, root=self)
        info = InfoPanel(self.notebook, -1, root=self)

        self.notebook.AddPage(self.options, "General")
        self.notebook.AddPage(self.triggers, "Triggers")
        self.notebook.AddPage(info, "Device Info")
        
        self.notebook.SetSizerProps(expand=True, proportion=-1)

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okButton = self.FindWindowById(wx.ID_OK)
        
        self.SetMinSize((436, 475))
        self.Fit()
        
        
    def getData(self, schema=util.DEFAULT_SCHEMA):
        data = {}
        data.update(self.options.getData())
        data.update(self.triggers.getData())
        
#         return util.encode_container(data, schema=schema)
        return data
        
#===============================================================================
# 
#===============================================================================

def configureRecorder(path):
    """
    """
    dlg = ConfigDialog(None, -1, "Configure Device (%s)" % path)
    dlg.ShowModal()
    
    print "dlg.getData() = %r" %  dlg.getData()
    return dlg


#===============================================================================
# 
#===============================================================================

if True or __name__ == "__main__":
    app = wx.App()
    configureRecorder("e:\\")
