'''
The UI for configuring a recorder. Ultimately, the set of tabs will be
determined by the recorder type, and will feature tabs specific to that 
recorder. Since there's only the two SSX variants, this is not urgent.

Created on Dec 16, 2013

@author: dstokes
'''

__all__ = ['configureRecorder']

from collections import OrderedDict
from datetime import datetime
import string
import time

import wx.lib.sized_controls as sc
import wx; wx = wx

from common import datetime2int, DateTimeCtrl
import devices
from mide_ebml import util
from mide_ebml.parsers import PolynomialParser


#===============================================================================
# 
#===============================================================================

class BaseConfigPanel(sc.SizedPanel):
    """ The base class for the various configuration pages. Defines some
        common methods for adding controls, setting defaults, and reading
        values.
    """

    def strOrNone(self, val):
        try:
            val = unicode(val).strip()
            if val == u'':
                return None
        except ValueError:
            return None
        return val
    

    def addField(self, labelText, name=None, units="", fieldText="", 
                 fieldSize=None, fieldStyle=None, tooltip=None):
        """ Helper method to create and configure a labeled text field and
            add it to the set of controls. 
            
            @param labelText: The text proceeding the field.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword fieldText: The default field text.
            @keyword fieldSize: The size of the text field
            @keyword fieldStyle: The text field's wxWindows style flags.
            @keyword tooltip: A tooltip string for the field.
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
            c.SetToolTipString(unicode(tooltip))
            t.SetToolTipString(unicode(tooltip))
            
        if self.fieldSize is None:
            self.fieldSize = t.GetSize()
        
        self.controls[t] = [t]
        if name is not None:
            self.fieldMap[name] = t
            
        return t
    
    
    def addButton(self, label, id_=-1, handler=None, tooltip=None, 
                  size=None, style=None):
        """ Helper method to create a button in the first column.
            
            @param label: The button's label text
            @keyword id_: The ID for the button
            @keyword handler: The `wx.EVT_BUTTON` event handling method
            @keyword tooltip: A tooltip string for the field.
        """
        size = size or (self.fieldSize[0]+20, self.fieldSize[1])
        if style is None:
            b = wx.Button(self, id_, label, size=size)
        else:
            b = wx.Button(self, id_, label, size=size, style=style)
        b.SetSizerProps()
        sc.SizedPanel(self, -1) # Spacer
        
        if tooltip is not None:
            b.SetToolTipString(unicode(tooltip))
        if handler is not None:
            b.Bind(wx.EVT_BUTTON, handler)
        return b
    
    
    def addCheck(self, checkText, name=None, units="", tooltip=None):
        """ Helper method to create a single checkbox and add it to the set of
            controls. 

            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword tooltip: A tooltip string for the field.
        """
        c = wx.CheckBox(self, -1, checkText)
        sc.SizedPanel(self, -1) # Spacer
        if tooltip is not None:
            c.SetToolTipString(unicode(tooltip))
            
        self.controls[c] = [None]
        if name is not None:
            self.fieldMap[name] = c
            
        return c


    def addCheckField(self, checkText, name=None, units="xxx", fieldText="", 
                      fieldSize=None, fieldStyle=None, tooltip=None):
        """ Helper method to create and configure checkbox/field pairs, and add
            them to the set of controls.

            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword fieldText: The default field text.
            @keyword fieldSize: The size of the text field
            @keyword fieldStyle: The text field's wxWindows style flags.
            @keyword tooltip: A tooltip string for the field.
        """
        fieldSize = self.fieldSize if fieldSize is None else fieldSize
        txt = unicode(fieldText)

        c = wx.CheckBox(self, -1, checkText)
        c.SetSizerProps(valign="center")

        subpane = sc.SizedPanel(self, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)
        
        if fieldStyle is None:
            t = wx.TextCtrl(subpane, -1, txt, size=fieldSize)
        else:
            t = wx.TextCtrl(subpane, -1, txt, size=fieldSize, style=fieldStyle)
        self.controls[c] = [t]
        
        u = wx.StaticText(subpane, -1, units)
        u.SetSizerProps(valign="center")
        
        if tooltip is not None:
            c.SetToolTipString(unicode(tooltip))
            t.SetToolTipString(unicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = t.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
            
        return c


    def addChoiceField(self, checkText, name=None, units="", choices=[], 
                       fieldSize=None, fieldStyle=None, tooltip=None):
        """ Helper method to create and configure checkbox/list pairs, and add
            them to the set of controls.
 
            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword choices: The items in the drop-down list.
            @keyword fieldSize: The size of the text field
            @keyword fieldStyle: The text field's wxWindows style flags.
            @keyword tooltip: A tooltip string for the field.
       """
        fieldSize = self.fieldSize if fieldSize is None else fieldSize
        choices = map(str, choices)

        c = wx.CheckBox(self, -1, checkText)
        c.SetSizerProps(valign="center")
        if fieldStyle is None:
            field = wx.Choice(self, -1, size=fieldSize, choices=choices)
        else:
            field = wx.Choice(self, -1, size=fieldSize, choices=choices,
                               style=fieldStyle)
        self.controls[c] = [field]
        
        if tooltip is not None:
            c.SetToolTipString(unicode(tooltip))
            field.SetToolTipString(unicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = field.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
            
        return c


    def addDateTimeField(self, checkText, name=None, tooltip=None):
        """ Helper method to create a checkbox and a time-entry field pair, and
            add them to the set of controls.
 
            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword tooltip: A tooltip string for the field.
        """ 
        check = wx.CheckBox(self, -1, checkText)
        check.SetSizerProps(valign='center')
        ctrl =  DateTimeCtrl(self, -1, size=self.fieldSize)
        ctrl.SetSize(self.fieldSize)
        self.controls[check] = [ctrl]
        ctrl.SetSizerProps(expand=True)
        
        if name is not None:
            self.fieldMap[name] = check

        if tooltip is not None:
            check.SetToolTipString(unicode(tooltip))
            ctrl.SetToolTipString(unicode(tooltip))
            
        return check#, ctrl #ctrl
        

    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard dialog arguments, plus:
        
            @keyword root: The viewer's root window.
            @keyword data: A dictionary of values read from the device.
        """
        self.root = kwargs.pop('root', None)
        super(BaseConfigPanel, self).__init__(*args, **kwargs)
        
        self.data = None
        self.fieldSize = (-1,-1)
        self.SetSizerType("form", {'hgap':10, 'vgap':10})
        
        # controls: fields keyed by their corresponding checkbox.
        self.controls = {}
        
        # fieldMap: All fields keyed by their corresponding key in the data.
        self.fieldMap = OrderedDict()
        
        self.getDeviceData()
        self.buildUI()
        self.initUI()
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckChanged)
        

    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        pass


    def getDeviceData(self):
        pass 


    def initUI(self):
        """ Do any setup work on the page. Most subclasses should override
            this.
        """
        if self.data:
            for k,v in self.data.iteritems():
                c = self.fieldMap.get(k, None)
                if c is None:
                    continue
                self.setField(c, v)
                
        for c in self.controls:
            self.enableField(c)


    def enableField(self, checkbox, state=True):
        """ Enable (or disable) all the other controls associated with a
            checkbox.
        """
        if isinstance(checkbox, wx.CheckBox):
            state = checkbox.GetValue()
        for c in self.controls[checkbox]:
            if c is not None:
                c.Enable(state)
       
            
    def enableAll(self):
        """ Update all fields if the corresponding checkbox is checked.
        """
        map(self.enableField, self.controls.keys())
    

    def parseTime(self, timeStr):
        """ Turn a string containing a length of time as S.s, M:S.s, or H:M:S.s
            into the corresponding number of seconds. For parsing text fields.
        """
        t = map(lambda x: float(x.strip(string.letters+" ,")), 
                reversed(timeStr.strip().replace(',',':').split(':')))
        if len(t) > 4:
            raise ValueError("Time had too many columns to parse: %r" % timeStr)
        if len(t) == 4:
            # Four columns: days, hours, minutes, seconds
            total = t.pop() * (24*60*60)
        else:
            total = 0
        for i in xrange(len(t)):
            total += t[i] * (60**i)
        return total


    def setField(self, checkbox, value):
        """ Check a checkbox and set its associated field.
        """
        if value is None:
            return
        
        if isinstance(checkbox, wx.CheckBox):
            checkbox.SetValue(True)
            
        if checkbox in self.controls and self.controls[checkbox]:
            field = self.controls[checkbox][0]
            if field is None:
                return
            field.Enable()
            if isinstance(field, wx.TextCtrl):
                if isinstance(value, float):
                    value = "%.3f" % value
                else:
                    value = str(value)
            elif isinstance(field, DateTimeCtrl):
                value = wx.DateTimeFromTimeT(float(value))
            elif isinstance(field, wx.Choice):
                strv = unicode(value)
                choices = field.GetItems()
                if strv in choices:
                    field.Select(choices.index(strv))
                else:
                    field.Select(len(choices)/2)
                return
            
            field.SetValue(value)
    

    def OnCheckChanged(self, evt):
        cb = evt.EventObject
        if cb in self.controls:
            self.enableField(cb)


    def addVal(self, control, trig, name, kind=int, transform=None,
               default=None):
        """ Helper method to add a field's value to a dictionary if its
            corresponding checkbox is checked. For exporting EBML.
         """
        if control not in self.controls:
            return
        
        if isinstance(control, wx.CheckBox):
            checked = control.GetValue() and control.Enabled
        else:
            checked = control.Enabled
        if checked or default is not None:
            fields = self.controls[control]
            if isinstance(fields[0], wx.Choice):
                val = fields[0].GetStrings()[fields[0].GetCurrentSelection()]
            elif isinstance(fields[0], DateTimeCtrl):
                val = datetime2int(fields[0].GetValue())
            elif fields[0] is None:
                val = 1
            else:
                val = fields[0].GetValue()
                
            try:
                val = kind(val)
                if val is not None:
                    if transform is not None:
                        val = transform(val)
                    trig[name] = val
                elif default is not None:
                    trig[name] = default
            except ValueError:
                trig[name] = val or default
                
            
        

#===============================================================================
# 
#===============================================================================

class SSXTriggerConfigPanel(BaseConfigPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """

    def getDeviceData(self):
        self.data = self.root.deviceConfig.get('SSXTriggerConfiguration', {})


    def buildUI(self):
        self.delayCheck = self.addCheckField(
            "Wake After Delay:", "PreRecordDelay", "seconds")

        self.wakeCheck = self.addDateTimeField(
            "Wake at specific time:", "WakeTimeUTC")
        
        self.timeCheck = self.addCheckField(
            "Limit recording time to:", "RecordingTime", "seconds")
        
        self.rearmCheck = self.addCheck("Re-triggerable", "AutoRearm")
        self.controls[self.timeCheck].append(self.rearmCheck)
        
        self.pressLoCheck = self.addCheckField("Pressure Trigger (Low):", units="Pa")
        self.pressHiCheck = self.addCheckField("Pressure Trigger (High):", units="Pa")
        self.tempLoCheck = self.addCheckField("Temperature Trigger (Low):", units=u'\xb0C')
        self.tempHiCheck = self.addCheckField("Temperature Trigger (High):", units=u'\xb0C')
        self.accelLoCheck = self.addCheckField("Accelerometer Trigger (Low):", 
           units="G", tooltip="The lower trigger limit. Should be less than 0.")
        self.accelHiCheck = self.addCheckField("Accelerometer Trigger (High):", 
           units="G", tooltip="The upper trigger limit. Should be greater than 0.")


    def OnCheckChanged(self, evt):
        cb = evt.EventObject
        if cb in self.controls:
            self.enableField(cb)
            if cb == self.delayCheck or cb == self.wakeCheck:
                if cb == self.wakeCheck:
                    other = self.delayCheck
                else:
                    other = self.wakeCheck
                other.SetValue(False)
                self.enableField(other)


    def initUI(self):
        """
        """
        super(SSXTriggerConfigPanel, self).initUI()

        accelType = self.root.deviceInfo.get('RecorderTypeUID', 0x12) & 0xff
        if accelType == 0x10:
            # 0x10: 25G accelerometer
            accelTransform = lambda x: (x * 50.0) / 65535 - 25
        else:
            # 0x12: 100G accelerometer
            accelTransform = lambda x: (x * 200.0) / 65535 - 100

        # Special case for the list of Triggers         
        for trigger in self.data.get("Trigger", []):
            channel = trigger['TriggerChannel']
            subchannel = trigger.get('TriggerSubChannel', None)
            low = trigger.get('TriggerWindowLo', None)
            high = trigger.get('TriggerWindowHi', None)
            if channel == 0:
                if low is not None:
                    low = accelTransform(low)
                if high is not None:
                    high = accelTransform(high)
                self.setField(self.accelLoCheck, low)
                self.setField(self.accelHiCheck, high)
            elif channel == 1:
                if subchannel == 0:
                    # Pressure
                    self.setField(self.pressLoCheck, low)
                    self.setField(self.pressHiCheck, high)
                elif subchannel == 1:
                    # Temperature
                    self.setField(self.tempLoCheck, low)
                    self.setField(self.tempHiCheck, high)
                         
        self.enableAll()


    def getData(self):
        """
        """
        data = OrderedDict()
        triggers = []
        
        for name,control in self.fieldMap.iteritems():
            self.addVal(control, data, name)
        
        accelType = self.root.deviceInfo.get('RecorderTypeUID', 0x12) & 0xff
        if accelType == 0x10:
            # 0x10: 25G accelerometer
            accelTransform = lambda x: int(((x + 25)/50.0) * 65535)
        else:
            # 0x12: 100G accelerometer
            accelTransform = lambda x: int(((x + 100)/200.0) * 65535)

        
        if self.accelLoCheck.GetValue() or self.accelHiCheck.GetValue():
            trig = OrderedDict(TriggerChannel=0)
            self.addVal(self.accelLoCheck, trig, "TriggerWindowLo", kind=float,
                        transform=accelTransform, default=0)
            self.addVal(self.accelHiCheck, trig, "TriggerWindowHi", kind=float,
                        transform=accelTransform, default=65535)
            if len(trig) > 2:
                triggers.append(trig)
                 
        if self.pressLoCheck.GetValue() or self.pressHiCheck.GetValue():
            trig = OrderedDict(TriggerChannel=1, TriggerSubChannel=0)
            self.addVal(self.pressLoCheck, trig, 'TriggerWindowLo')
            self.addVal(self.pressHiCheck, trig, 'TriggerWindowHi')
            self.trig.setdefault()
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

    def getDeviceData(self):
        self.data = self.root.deviceConfig.get('SSXBasicRecorderConfiguration', 
                                               {})
        # Hack: flatten RecorderUserData into the rest of the configuration,
        # making things simpler to handle
        self.data.update(self.root.deviceConfig.get('RecorderUserData', {}))
        
        if 'UTCOffset' in self.data:
            self.data['UTCOffset'] /= 3600

 
    def buildUI(self):
        self.nameField = self.addField("Device Name:", "RecorderName", 
            tooltip="A custom name for the recorder. Not the same as the "
                    "volume label.")
        self.nameField.SetSizerProps(expand=True)

        noteSize = self.nameField.GetSize()
        self.noteField = self.addField("Device Notes:", "RecorderDesc",
            fieldSize=(noteSize[0], noteSize[1]*3), fieldStyle=wx.TE_MULTILINE,
            tooltip="Custom notes about the recorder (position, user ID, etc.)")
        self.noteField.SetSizerProps(expand=True)

        wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL)
        sc.SizedPanel(self, -1) # Spacer
      
        self.samplingCheck = self.addCheckField("Sampling Frequency:",
            "SampleFreq", "Hz", tooltip="Checking this field overrides the "
            "device's default.")
        
#         self.osrCheck = self.addChoiceField("Oversampling Ratio:", "OSR", 
#             self.OVERSAMPLING, tooltip="Checking this field overrides the "
#             "device's default.")

        self.aaCornerCheck = self.addCheckField(
            "Override Antialiasing Filter Cutoff:", "AAFilterCornerFreq", "Hz",
            tooltip="If checked and a value is provided, the antialiasing "
                "sample rate will be limited.")
        

        self.aaCheck = self.addCheck("Disable oversampling", "OSR", 
            tooltip="If checked, data recorder will not apply oversampling.")
        
        self.utcCheck = self.addCheckField("UTC Offset:", "UTCOffset", "Hours", 
                                           str(-time.timezone/60/60))
        
        self.tzBtn = self.addButton("Get Local UTC Offset", -1,  self.OnSetTZ,
            "Fill the UTC Offset field with the offset for the local timezone")
        self.timeBtn = self.addButton("Set Device Time", -1, self.OnSetTime, 
            "Set the device's clock. Applied immediately.")
        
        self.Fit()
        


    def OnSetTime(self, event):
        try:
            devices.setDeviceTime(self.root.devPath)
        except IOError:
            wx.MessageBox("An error occurred when trying to access the device.",
                          "Set Device Time", parent=self)
    
    
    def OnSetTZ(self, event):
        val = str(-time.timezone / 60 / 60)
        self.setField(self.utcCheck, val)


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

        if 'UTCOffset' in ssxConfig:
            ssxConfig['UTCOffset'] *= 3600
        if ssxConfig:
            data["SSXBasicRecorderConfiguration"] = ssxConfig
        if userConfig:
            data["RecorderUserData"] = userConfig
            
        return data
    
#===============================================================================
# 
#===============================================================================
        
class InfoPanel(BaseConfigPanel):
    """ A generic configuration dialog page showing various read-only properties
        of a recorder.
        
        @cvar field_types: A dictionary pairing field names with a function to
            prepare the value for display.
    """
    
    field_types = {'DateOfManufacture': datetime.fromtimestamp,
                   'HwRev': str,
                   'FwRev': str,
                   }

    def __init__(self, *args, **kwargs):
        self.info = kwargs.pop('info', {})
        super(InfoPanel, self).__init__(*args, **kwargs)
        
    def getDeviceData(self):
        self.data = self.info


    def buildUI(self):
        infoColor = wx.Colour(60,60,60)
        mono = wx.Font(self.GetFont().GetPointSize()+1, wx.MODERN, 
                            wx.NORMAL, wx.BOLD, False, u'monospace')
        sc.SizedPanel(self, -1) # Spacer
        wx.StaticText(self, -1, "All values are read-only"
                      ).SetForegroundColour("RED")
        
        self.text = []
        
        for k,v in self.data.iteritems():
            if k.startswith('_label'):
                # Treat this like a label
                sc.SizedPanel(self, -1) # Spacer
                wx.StaticText(self, -1, v)
                continue
            
            if k.startswith('_'):
                continue
            elif k in self.field_types:
                v = self.field_types[k](v)
            elif isinstance(v, (int, long)):
                v = "0x%08X" % v
            else:
                v = unicode(v)
            
            t = self.addField('%s:' % k, k, None, v, fieldStyle=wx.TE_READONLY)
            t.SetSizerProps(expand=True)
            t.SetFont(mono)
            t.SetForegroundColour(infoColor)
            self.text.append("%s: %s" % (k,v))
    
        sc.SizedPanel(self, -1) # Spacer
        copyBtn = wx.Button(self, -1, "Copy to Clipboard")
        copyBtn.Bind(wx.EVT_BUTTON, self.OnCopy)
        
        self.Fit()

    def initUI(self):
        pass

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

class CalibrationPanel(InfoPanel):
    """
    """
    
    def getDeviceData(self):
        PP = PolynomialParser(None)
        self.info = [PP.parse(c) for c in self.data.value]
        
        
    def buildUI(self):
        """
        """
        self.text = []
        bold = wx.Font(self.GetFont().GetPointSize(), wx.FONTFAMILY_DEFAULT, 
                            wx.NORMAL, wx.BOLD, False)
        infoColor = wx.Colour(60,60,60)
        mono = wx.Font(self.GetFont().GetPointSize()+1, wx.MODERN, 
                            wx.NORMAL, wx.BOLD, False, u'monospace')
        
        sc.SizedPanel(self, -1) # Spacer
        wx.StaticText(self, -1, "All values are read-only"
                      ).SetForegroundColour("RED")
                      
        for cal in self.info:
            calId = cal.id
            calType = cal.__class__.__name__
            if hasattr(cal, 'channelId'):
                s = "Channel %x" % cal.channelId
                if hasattr(cal, 'subchannelId'):
                    s += ", Subchannel %x" % cal.subchannelId
                calType = "%s; references %s" % (calType, s)
            wx.StaticText(self, -1, "Calibration ID %x:" % calId).SetFont(bold)
            wx.StaticText(self, -1, calType).SetFont(bold)
            
            t = self.addField("Polynomial:", None, '', str(cal), 
                              fieldStyle=wx.TE_READONLY)
            t.SetForegroundColour(infoColor)
            t.SetSizerProps(expand=True)
            t.SetFont(mono)
            
            self.text.append("Calibration ID %x: %s" % (calId, calType))
            self.text.append("Polynomial: %s" % str(cal))

        sc.SizedPanel(self, -1) # Spacer
        copyBtn = wx.Button(self, -1, "Copy to Clipboard")
        copyBtn.Bind(wx.EVT_BUTTON, self.OnCopy)
        
        self.Fit()

                

#===============================================================================
# 
#===============================================================================

class ConfigDialog(sc.SizedDialog):
    """ The parent dialog for all the recorder configuration tabs. 
    
        @todo: Choose the tabs dynamically based on the recorder type, once
            there are multiple types of recorders using the MIDE format.
    """
    
    def __init__(self, *args, **kwargs):
        self.devPath = kwargs.pop('device', None)
        self.root = kwargs.pop('root', None)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | \
            wx.MINIMIZE_BOX | wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
        
        super(ConfigDialog, self).__init__(*args, **kwargs)
        
        self.deviceInfo = devices.getRecorderInfo(self.devPath, {})
        self.deviceConfig = devices.getRecorderConfig(self.devPath, {})
        
        pane = self.GetContentsPane()
        self.notebook = wx.Notebook(pane, -1)
        self.triggers = SSXTriggerConfigPanel(self.notebook, -1, root=self)
        self.options = OptionsPanel(self.notebook, -1, root=self)
        info = InfoPanel(self.notebook, -1, root=self, info=self.deviceInfo)
        
        self.notebook.AddPage(self.options, "General")
        self.notebook.AddPage(self.triggers, "Triggers")
        self.notebook.AddPage(info, "Device Info")
        
        self.notebook.SetSizerProps(expand=True, proportion=-1)

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okButton = self.FindWindowById(wx.ID_OK)
        
        self.SetMinSize((436, 475))
        self.Fit()
        
        
    def getData(self, schema=util.DEFAULT_SCHEMA):
        data = OrderedDict()
        data.update(self.options.getData())
        data.update(self.triggers.getData())
        
#         return util.encode_container(data, schema=schema)
        return data
        
#===============================================================================
# 
#===============================================================================

def configureRecorder(path):
    """ Create the configuration dialog for a recording device. 
    
        @param path: The path to the data recorder (e.g. a mount point under
            *NIX or a drive letter under Windows)
        @return: The data written to the recorder as a nested dictionary, or
            `None` if the configuration is cancelled.
    """
    if not devices.isRecorder(path):
        raise ValueError("Specified path %r does not appear to be a recorder" %\
                         path)
        
    dlg = ConfigDialog(None, -1, "Configure Device (%s)" % path, device=path)
    
    if dlg.ShowModal() == wx.ID_OK:
        data = dlg.getData()
        devices.setRecorderConfig(path, data)
    else:
        data = None
    
    dlg.Destroy()
    return data


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    print configureRecorder("G:\\")


