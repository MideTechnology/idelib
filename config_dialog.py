'''
The UI for configuring a recorder. Ultimately, the set of tabs will be
determined by the recorder type, and will feature tabs specific to that 
recorder. Since there's only the two SSX variants, this is not urgent.

@todo: I use `info` and `data` for the recorder info at different times;
    if there's no specific reason, unify. It may be vestigial.
    
Created on Dec 16, 2013

@author: dstokes
'''

__all__ = ['configureRecorder']

from collections import OrderedDict
from datetime import datetime
import string
import time

import wx; wx = wx
import wx.lib.sized_controls as sc
import wx.html

from common import datetime2int, makeWxDateTime, DateTimeCtrl
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
        
        Since most fields have two parts -- a checkbox and a field/control of 
        some sort -- the controls are all kept in a dictionary keyed by the
        checkbox. The associated controls get disabled when the checkbox is
        unchecked.
    """

    def strOrNone(self, val):
        try:
            val = unicode(val).strip()
            if val == u'':
                return None
        except ValueError:
            return None
        return val
    

    def addField(self, labelText, name=None, units="", value="", 
                 fieldSize=None, fieldStyle=None, tooltip=None):
        """ Helper method to create and configure a labeled text field and
            add it to the set of controls. 
            
            @param labelText: The text proceeding the field.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword value: The default field text.
            @keyword fieldSize: The size of the text field
            @keyword fieldStyle: The text field's wxWindows style flags.
            @keyword tooltip: A tooltip string for the field.
        """
        fieldSize = self.fieldSize if fieldSize is None else fieldSize
        txt = unicode(value)
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


    def addCheckField(self, checkText, name=None, units="", value="", 
                      fieldSize=None, fieldStyle=None, tooltip=None):
        """ Helper method to create and configure checkbox/field pairs, and add
            them to the set of controls.

            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword value: The default field text.
            @keyword fieldSize: The size of the text field
            @keyword fieldStyle: The text field's wxWindows style flags.
            @keyword tooltip: A tooltip string for the field.
        """
        fieldSize = self.fieldSize if fieldSize is None else fieldSize
        txt = unicode(value)

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


    def addFloatField(self, checkText, name=None, units="", value="",
                      precision=0.01, digits=2, minmax=(-100,100), 
                      fieldSize=None, fieldStyle=None, tooltip=None):
        """ Add a numeric field with a 'spinner' control.

            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword units: The units displayed, if any.
            @keyword value: The initial value of the field
            @keyword precision: 
            @keyword minmax: The minimum and maximum values allowed
            @keyword fieldSize: The size of the text field
            @keyword fieldStyle: The text field's wxWindows style flags.
            @keyword tooltip: A tooltip string for the field.
        """
        fieldSize = self.fieldSize if fieldSize is None else fieldSize

        c = wx.CheckBox(self, -1, checkText)
        c.SetSizerProps(valign="center")

        subpane = sc.SizedPanel(self, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)
        
        lf = wx.SpinCtrlDouble(subpane, -1, value=str(value), inc=precision,
                          min=minmax[0], max=minmax[1], size=fieldSize)
        self.controls[c] = [lf]
        
        u = wx.StaticText(subpane, -1, units)
        u.SetSizerProps(valign="center")
        
        if tooltip is not None:
            c.SetToolTipString(unicode(tooltip))
            lf.SetToolTipString(unicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = lf.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
        
        if digits is not None:
            lf.SetDigits(digits)
        
        return c

    def addIntField(self, checkText, name=None, units="", value=None,
                      minmax=(-100,100), fieldSize=None, fieldStyle=None, 
                      tooltip=None):
        """ Add a numeric field with a 'spinner' control.

            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword units: The units displayed, if any.
            @keyword value: The initial value of the field
            @keyword minmax: The minimum and maximum values allowed
            @keyword fieldSize: The size of the field
            @keyword fieldStyle: The field's wxWindows style flags.
            @keyword tooltip: A tooltip string for the field.
        """
        fieldSize = self.fieldSize if fieldSize is None else fieldSize

        c = wx.CheckBox(self, -1, checkText)
        c.SetSizerProps(valign="center")

        subpane = sc.SizedPanel(self, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)
        
        value = "" if value is None else int(value)
        lf = wx.SpinCtrl(subpane, -1, value=str(value),
                          min=int(minmax[0]), max=int(minmax[1]), size=fieldSize)
        self.controls[c] = [lf]
        
        u = wx.StaticText(subpane, -1, units)
        u.SetSizerProps(valign="center")
        
        if tooltip is not None:
            c.SetToolTipString(unicode(tooltip))
            lf.SetToolTipString(unicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = lf.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
            
        return c


    def addChoiceField(self, checkText, name=None, units="", choices=[], 
                       selected=None, fieldSize=None, fieldStyle=None, 
                       tooltip=None):
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

        subpane = sc.SizedPanel(self, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)

        if fieldStyle is None:
            field = wx.Choice(subpane, -1, size=fieldSize, choices=choices)
        else:
            field = wx.Choice(subpane, -1, size=fieldSize, choices=choices,
                               style=fieldStyle)
        self.controls[c] = [field]
        
        u = wx.StaticText(subpane, -1, units)
        u.SetSizerProps(valign="center")
        
        if selected is not None:
            field.SetSelection(int(selected))
        
        if tooltip is not None:
            c.SetToolTipString(unicode(tooltip))
            field.SetToolTipString(unicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = field.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
        
        return c


    def addDateTimeField(self, checkText, name=None, fieldSize=None, 
                         fieldStyle=None, tooltip=None):
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
        self.device = kwargs.pop('device', None)
        super(BaseConfigPanel, self).__init__(*args, **kwargs)
        
        self.data = None
        self.fieldSize = (-1,-1)
        self.SetSizerType("form", {'hgap':10, 'vgap':10})
        
        # controls: fields keyed by their corresponding checkbox.
        self.controls = {}
        
        # fieldMap: All fields keyed by their corresponding key in the data.
        self.fieldMap = OrderedDict()
        
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
        self.getDeviceData()
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


    def setField(self, checkbox, value, checked=True):
        """ Check a checkbox and set its associated field.
        
            @param checkbox: 
            @param value: 
            @keyword checked: By default, setting a value checks the checkbox.
                This can override that, so the field can be set but the
                checkbox left unchecked.
        """
        if value is None:
            return
        
        if isinstance(checkbox, wx.CheckBox):
            checkbox.SetValue(checked)
            
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
                value = makeWxDateTime(value)
            elif isinstance(field, wx.Choice):
                strv = unicode(value)
                choices = field.GetItems()
                if strv in choices:
                    field.Select(choices.index(strv))
                else:
                    field.Select(len(choices)/2)
                return
            
            field.SetValue(value)
    

    def hideField(self, checkbox, hidden=True):
        """ Helper method to hide or show sets of UI fields.
        """
        if checkbox in self.controls:
            checkbox.Hide(hidden)
            for c in self.controls[checkbox]:
                c.Hide(hidden)
            return True
        return False
    

    def OnCheckChanged(self, evt):
        """ Default check handler to enable/disable associated fields.
        """
        cb = evt.EventObject
        if cb in self.controls:
            self.enableField(cb)


    def addVal(self, control, trig, name, kind=int, transform=None,
               default=None):
        """ Helper method to add a field's value to a dictionary if its
            corresponding checkbox is checked. For exporting EBML.
            
            @param control: The field's controlling checkbox, or the field
                if not a 'check' field.
            @param trig: The dictionary to which to add the value.
            @param name: The associated key in the target dictionary.
            @keyword kind: The data type, for casting from string (or whatever
                is the widget's native type). Not applied to the default.
            @keyword transform: A function to apply to the data before adding
                it to the dictionary. Not applied to the default.
            @keyword default: A default value to use if the field is not
                checked.
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
            
            if not checked and default is not None:
                trig[name] = default
                return
                
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
        cfg= self.root.device.getConfig()
        self.data = cfg.get('SSXTriggerConfiguration', {})
        if not self.root.useUtc and 'WakeTimeUTC' in self.data:
            self.data['WakeTimeUTC'] -= time.timezone
            


    def buildUI(self):
        self.delayCheck = self.addIntField(
            "Wake After Delay:", "PreRecordDelay", "seconds", 0, (0,86400))

        self.wakeCheck = self.addDateTimeField(
            "Wake at specific time:", "WakeTimeUTC")
        
        self.useUtcCheck = self.addCheck("UTC Time", 
            tooltip="If unchecked, the wake time is relative to the current time zone.")
        self.useUtcCheck.SetValue(self.root.useUtc)
        self.controls[self.wakeCheck].append(self.useUtcCheck)
        
        self.timeCheck = self.addIntField(
            "Limit recording time to:", "RecordingTime", "seconds", 0, 
            minmax=(0,86400))
        
        self.rearmCheck = self.addCheck("Re-triggerable", "AutoRearm")
        self.controls[self.timeCheck].append(self.rearmCheck)
        
        self.pressLoCheck = self.addIntField("Pressure Trigger (Low):", 
                                             units="Pa", minmax=(0,120000),
                                             value=0)
        self.pressHiCheck = self.addIntField("Pressure Trigger (High):", 
                                             units="Pa", minmax=(0,120000),
                                             value=120000)
        self.tempLoCheck = self.addFloatField("Temperature Trigger (Low):", 
                                          units=u'\xb0C', minmax=(-40.0,80.0),
                                          value=-40.0)
        self.tempHiCheck = self.addFloatField("Temperature Trigger (High):", 
                                          units=u'\xb0C', minmax=(-40.0,80.0),
                                          value=80.0)
        self.accelLoCheck = self.addFloatField("Accelerometer Trigger (Low):", 
           units="G", tooltip="The lower trigger limit. Less than 0.")
        self.accelHiCheck = self.addFloatField("Accelerometer Trigger (High):", 
           units="G", tooltip="The upper trigger limit. Greater than 0.")


    def OnCheckChanged(self, evt):
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


    def initUI(self):
        """
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
            if channel == 0:
                # Accelerometer. Both or neither must be set.
                low = accelTransform(0 if low is None else low)
                high = accelTransform(65535 if high is None else high)
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
        """ Retrieve the values entered in the dialog.
        """
        data = OrderedDict()
        triggers = []
        
        for name,control in self.fieldMap.iteritems():
            self.addVal(control, data, name)
        
        if self.accelLoCheck.GetValue() or self.accelHiCheck.GetValue():
            trig = OrderedDict(TriggerChannel=0)
            self.addVal(self.accelLoCheck, trig, "TriggerWindowLo", kind=float,
                        transform=self.root.device._packAccel, default=0)
            self.addVal(self.accelHiCheck, trig, "TriggerWindowHi", kind=float,
                        transform=self.root.device._packAccel, default=65535)
            if len(trig) > 2:
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
        
        self.root.useUtc = self.useUtcCheck.GetValue()
        if not self.root.useUtc and 'WakeTimeUTC' in data:
            data['WakeTimeUTC'] += time.timezone
            
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
        cfg = self.root.device.getConfig()
        self.data = cfg.get('SSXBasicRecorderConfiguration', {}).copy()
        # Hack: flatten RecorderUserData into the rest of the configuration,
        # making things simpler to handle
        self.data.update(cfg.get('RecorderUserData', {}))
        
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
      
        self.samplingCheck = self.addIntField("Sampling Frequency:",
            "SampleFreq", "Hz", minmax=(100,20000), value=5000,
            tooltip="Checking this field overrides the device's default.")
        
#         self.osrCheck = self.addChoiceField("Oversampling Ratio:", "OSR", 
#             self.OVERSAMPLING, tooltip="Checking this field overrides the "
#             "device's default.")

        self.aaCornerCheck = self.addIntField(
            "Override Antialiasing Filter Cutoff:", "AAFilterCornerFreq", "Hz",
            minmax=(100,20000), value=1000, 
            tooltip="If checked and a value is provided, the input low-pass "
            "filter cutoff will be set to this value.")

        self.aaCheck = self.addCheck("Disable oversampling", "OSR", 
            tooltip="If checked, data recorder will not apply oversampling.")
        
        self.utcCheck = self.addIntField("Local UTC Offset:", "UTCOffset", "Hours", 
            str(-time.timezone/60/60), minmax=(-24,24), 
            tooltip="The local timezone's offset from UTC time. "
            "Used only for file timestamps.")
        
        self.tzBtn = self.addButton("Get Local UTC Offset", -1,  self.OnSetTZ,
            "Fill the UTC Offset field with the offset for the local timezone.")
        self.setTimeCheck = self.addCheck("Set Device Time on Save", 
            tooltip="With this checked, the recorder's clock will be set to "
            "the system time when the configuration is applied.")
        self.setTimeCheck.SetValue(self.root.setTime)
        
        self.Fit()
        
    
    def OnSetTZ(self, event):
        val = int(-time.timezone / 60 / 60)
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
        
        if self.setTimeCheck.GetValue():
            try:
                self.root.device.setTime()
            except IOError:
                wx.MessageBox(
                    "An error occurred when trying to access the device.",
                    "Set Device Time", parent=self)
                
        self.root.setTime = self.setTimeCheck.GetValue()
        
        return data


#===============================================================================
# 
#===============================================================================
        
class InfoPanel(wx.html.HtmlWindow):
    """ A generic configuration dialog page showing various read-only properties
        of a recorder.
        
        @cvar field_types: A dictionary pairing field names with a function to
            prepare the value for display.
    """
    # Replacement, human-readable field names
    field_names = {'HwRev': 'Hardware Revision',
                   'FwRev': 'Firmware Revision',
                   }

    # Formatters for specific fields. The keys should be the string as
    # displayed (de-camel-cased or replaced by field_names)
    field_types = {'Date of Manufacture': datetime.fromtimestamp,
                   'Hardware Revision': str,
                   'Firmware Revision': str,
                   'Recorder Serial': lambda x: "SSX%07d" % x
                   }

    def __init__(self, *args, **kwargs):
        self.info = kwargs.pop('info', {})
        self.root = kwargs.pop('root', None)
        super(InfoPanel, self).__init__(*args, **kwargs)
        self.html = []
        self._inTable = False
        self.buildUI()
        self.initUI()


    def addItem(self, k, v):
        """ Append a labeled info item.
        """
        # Automatically create new table if not already in one.
        if not self._inTable:
            self.html.append("<table width='100%'>")
            self._inTable = True
        self.html.append("<tr><td width='50%%'>%s</td>" % k)
        self.html.append("<td width='50%%'><b>%s</b></td></tr>" % v)


    def closeTable(self):
        """ Wrap up any open table, if any.
        """
        if self._inTable:
            self.html.append("</table>")
            self._inTable = False


    def addLabel(self, v, warning=False):
        """ Append a label.
        """
        if self._inTable:
            self.html.append("</table>")
            self._inTable = False
        if warning:
            v = "<font color='#FF0000'>%s</font>" % v
        self.html.append("<p>%s</p>" % v)


    def _fromCamelCase(self, s):
        """ break a 'camelCase' string into space-separated words.
        """
        result = []
        lastChar = ''
        for i in range(len(s)):
            c = s[i]
            if c.isupper() and lastChar.islower():
                result.append(' ')
            result.append(c)
            lastChar = c
        # Hack to fix certain acronyms. Should really be done by checking text.
        result = ''.join(result).replace("ID", "ID ").replace("EBML", "EBML ")
        return result.replace(" Of ", " of ")


    def getDeviceData(self):
        self.data = OrderedDict()
        for k,v in self.info.iteritems():
            self.data[self.field_names.get(k, self._fromCamelCase(k))] = v


    def buildUI(self):
        self.getDeviceData()
        self.html = ["<html><body>"]
        for k,v in self.data.iteritems():
            if k.startswith('_label'):
                # Treat this like a label
                self.addLabel(v)
                continue
            
            try:
                if k.startswith('_'):
                    continue
                elif k in self.field_types:
                    v = self.field_types[k](v)
                elif isinstance(v, (int, long)):
                    v = "0x%08X" % v
                else:
                    v = unicode(v)
            except TypeError:
                v = unicode(v)

            self.addItem(k,v)
            
        if self._inTable:
            self.html.append("</table>")
        self.html.append('</body></html>')
        self.SetPage(''.join(self.html))


    def initUI(self):
        pass


    def OnLinkClicked(self, linkinfo):
        """ Handle a link click. Ones starting with "viewer:" link to a
            channel, subchannel and time; ones starting with "http:" link to
            an external web page.
            
            @todo: Implement linking to a viewer position.
        """
        href = linkinfo.GetHref()
        if href.startswith("viewer:"):
            # Link to a channel at a specific time.
            href = href.replace('viewer', '')
            base, t = href.split("@")
            chid, subchid = base.split('.')
            print "Viewer link: %r %s %s" % (chid, subchid, t)
        elif href.startswith("http"):
            # Launch external web browser
            wx.LaunchDefaultBrowser(href)
        else:
            # Show in same window (file, etc.)
            super(InfoPanel, self).OnLinkClicked(linkinfo)
            
    

#===============================================================================
# 
#===============================================================================

class old_InfoPanel(BaseConfigPanel):
    """ A generic configuration dialog page showing various read-only properties
        of a recorder.
        
        @cvar field_types: A dictionary pairing field names with a function to
            prepare the value for display.
            
        @todo: Get rid of this after refactoring CalibrationPanel
    """
    # Replacement, human-readable field names
    field_names = {'HwRev': 'Hardware Revision',
                   'FwRev': 'Firmware Revision',
                   }

    # Formatters for specific fields. The keys should be the string as
    # displayed (de-camel-cased or replaced by field_names)
    field_types = {'Date of Manufacture': datetime.fromtimestamp,
                   'Hardware Revision': str,
                   'Firmware Revision': str,
                   'Recorder Serial': lambda x: "SSX%07d" % x
                   }

    def __init__(self, *args, **kwargs):
        self.info = kwargs.pop('info', {})
        super(old_InfoPanel, self).__init__(*args, **kwargs)


    def _fromCamelCase(self, s):
        """ break a 'camelCase' string into space-separated words.
        """
        result = []
        lastChar = ''
        for i in range(len(s)):
            c = s[i]
            if c.isupper() and lastChar.islower():
                result.append(' ')
            result.append(c)
            lastChar = c
        return ''.join(result).replace(" Of ", " of ")


    def getDeviceData(self):
        self.data = OrderedDict()
        for k,v in self.info.iteritems():
            self.data[self.field_names.get(k, self._fromCamelCase(k))] = v


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
            
            try:
                if k.startswith('_'):
                    continue
                elif k in self.field_types:
                    v = self.field_types[k](v)
                elif isinstance(v, (int, long)):
                    v = "0x%08X" % v
                else:
                    v = unicode(v)
            except TypeError:
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


class CalibrationPanel(old_InfoPanel):
    """ Panel for displaying SSX calibration polynomials. Read-only.
    
        @todo: Refactor this to use the new InfoPanel.
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
# Slam Stick Classic configuration panels
#===============================================================================

class ClassicTriggerConfigPanel(BaseConfigPanel):
    """
    """
    CHIME_TIMES = OrderedDict((
        (0b00000000, '0.5 seconds'),
        (0b00000100, '1 second'),
        (0b00001000, '10 seconds'),
        (0b00001100, '1 minute'),
        (0b00010000, '10 minutes'),
        (0b00010100, '1 Hour'),
        (0b00011000, '1 Day'),
        (0b00011100, '1 Week'),
        (0b00100000, '1 Month'),
        (0b00100100, '1 Year')
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
        
        if not self.root.useUtc:
            self.data['ALARM_TIME'] = datetime2int(self.data['ALARM_TIME'], -time.timezone)

    
    def buildUI(self):
        self.delayCheck = self.addFloatField(
            "Delay Before Recording:", "RECORD_DELAY", "seconds", precision=2, 
            minmax=(0,2**17), tooltip="Seconds to delay before recording. "
            "Note: This will be rounded to the lowest multiple of 2.")

        self.wakeCheck = self.addDateTimeField(
            "Wake at specific time:", "ALARM_TIME", 
            tooltip="The date and time at which to start recording. "
            "Note: the year is ignored.")
        self.useUtcCheck = self.addCheck("Use UTC Time")
        self.useUtcCheck.SetValue(self.root.useUtc)
        self.controls[self.wakeCheck].append(self.useUtcCheck)
        
        self.timeCheck = self.addFloatField(
            "Recording Limit, Time:", "SECONDS_PER_TRIGGER", "seconds", 
            precision=2, minmax=(0,2**17), tooltip="Recording length. "
            "Note: This will be rounded to the lowest multiple of 2.")
        
        self.sampleCountCheck = self.addFloatField(
            "Recording Limit, Samples:", "SAMPLES_PER_TRIGGER", "samples", 
            minmax=(0,2**16))
        
        self.rearmCheck = self.addCheck("Re-triggerable",
            tooltip="Recorder will restart when triggering event re-occurs.")
        
        self.chimeCheck = self.addChoiceField("Trigger at Intervals", 
            choices=self.CHIME_TIMES.values(), tooltip="The frequency at "
            "which to take recordings.")
        self.repeatCheck = self.addIntField("Number of Repeats", 'REPEATS', 
            minmax=(0,255), tooltip="The number of recordings to make, "
            "in addition to the first.")
                
        
        wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL)
        sc.SizedPanel(self, -1) # Spacer
        self.accelTrigCheck = self.addFloatField("Accelerometer Threshold:", 
            'TRIG_THRESH_ACT', units="g", minmax=(0.0,16.0), precision=0.01, 
            tooltip="The minimum acceleration to trigger recording. "
            "Note: due to noise, 0 may cause undesired operation.")
        self.xCheck = self.addCheck("X Axis Acceleration Trigger",
            tooltip="Acceleration on X axis will trigger recording.")
        self.yCheck = self.addCheck("Y Axis Acceleration Trigger",
            tooltip="Acceleration on Y axis will trigger recording.")
        self.zCheck = self.addCheck("Z Axis Acceleration Trigger",
            tooltip="Acceleration on Z axis will trigger recording.")
        self.acCheck = self.addCheck("AC Coupled")
        self.napCheck = self.addChoiceField("Accel. Check Interval",
              choices=self.NAP_TIMES.values())

        self.controls[self.accelTrigCheck].extend((self.xCheck, self.yCheck, 
                                                   self.zCheck, self.acCheck, 
                                                   self.napCheck))


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
        """ Fill out the UI.
        """ 
        self.getDeviceData()
        super(ClassicTriggerConfigPanel, self).initUI()
        trigs = self.info.get('TRIG_ACT_INACT_REG', 0)
        self.acCheck.SetValue((trigs & 0b10000000) and True)
        self.xCheck.SetValue((trigs & 0b01000000) and True)
        self.yCheck.SetValue((trigs & 0b00100000) and True)
        self.zCheck.SetValue((trigs & 0b00010000) and True)
        
        trigs = self.info.get('TRIGGER_FLAGS', 0)
        self.accelTrigCheck.SetValue((trigs[1] & 0b10000000))
        self.wakeCheck.SetValue((trigs[1] & 0b00001000))
        
        conf = self.info.get('CONFIG_FLAGS', 0b10000000)
        self.rearmCheck.SetValue((conf & 0b01000000) and True)
        
        self.setField(self.chimeCheck, 
                      self.CHIME_TIMES.get(self.info.get('ROLLPERIOD',0)),
                      checked=(self.info.get('CHIME_EN',0) & 1) and True)
        
        self.enableAll()
    
    
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
        if self.accelTrigCheck.GetValue(): trigFlags[1] |= 0b10000000
        if self.wakeCheck.GetValue(): trigFlags[1] |= 0b00001000
        data['TRIGGER_FLAGS'] = trigFlags
        
        confFlags = 0b10000000
        if self.rearmCheck.GetValue(): confFlags |= 0b01000000
        data['CONFIG_FLAGS'] = confFlags
        
        if self.chimeCheck.GetValue():
            data['CHIME_EN'] = 1
            data['ROLLPERIOD'] = self.CHIME_TIMES.keys()[self.controls[self.chimeCheck][0].GetSelection()]
        
        self.root.useUtc = self.useUtcCheck.GetValue()
        if self.wakeCheck.GetValue() and not self.root.useUtc:
            data['ALARM_TIME'] += time.timezone

        return data
    
#===============================================================================

class ClassicOptionsPanel(BaseConfigPanel):
    """
    """
    SAMPLE_RATES = OrderedDict(((0x06, '6.25'), 
                                (0x07, '12.5'), 
                                (0x08, '25'), 
                                (0x09, '50'), 
                                (0x0A, '100'), 
                                (0x0B, '200'), 
                                (0x0C, '400'), 
                                (0x0D, '800'), 
                                (0x0E, '1600'), 
                                (0x0F, '3200')))
    
    
    def getDeviceData(self):
        self.info = self.root.device.getConfig().copy()


    def buildUI(self):
        self.nameField = self.addField("Device Name:", "USERUID_RESERVE", 
            tooltip="A custom name for the recorder. Not the same as the "
                    "volume label. 8 characters max.")
        self.nameField.SetSizerProps(expand=True)

        wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL)
        sc.SizedPanel(self, -1) # Spacer
        
        self.samplingCheck = self.addChoiceField("Sampling Frequency:",
                                                 'BW_RATE_PWR',
            units="Hz", choices=self.SAMPLE_RATES.values(), 
            selected=len(self.SAMPLE_RATES)-1,
            tooltip="Checking this field overrides the device's default.")
        
        wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL)
        sc.SizedPanel(self, -1) # Spacer
        
        self.rtccCheck = self.addCheck("Enable Realtime Clock/Cal.")
        self.setTimeCheck = self.addCheck("Set RTCC Time/Date", 
           tooltip="Set the device's realtime clock/calendar to the current "
           "system time on save")
        self.setTimeCheck.SetValue(self.root.setTime)
        self.utcCheck = self.addCheckField("UTC Offset:", "TZ_OFFSET", "Hours", 
            str(-time.timezone/60/60), tooltip="The local timezone's offset "
            "from UTC time. Used only for file timestamps.")
        self.tzBtn = self.addButton("Get UTC", -1,  self.OnSetTZ,
            "Fill the UTC Offset field with the offset for the local timezone")
        self.controls[self.rtccCheck].extend((self.setTimeCheck, self.utcCheck, 
                                              self.tzBtn))
        
        self.Fit()
        

    def initUI(self):
        self.getDeviceData()
        for k,v in self.info.iteritems():
            c = self.fieldMap.get(k, None)
            if c is None:
                continue
            self.setField(c, v)
        
#         self.info['RTCC_ENA'] = self.info['RTCC_ENA']
        self.rtccCheck.SetValue(self.info.get('RTCC_ENA',0) and True)
        
        r = self.info.setdefault('BW_RATE_PWR', 0x0f) & 0xf
        if r in self.SAMPLE_RATES:
            ridx = self.SAMPLE_RATES[r]
        else:
            ridx = self.SAMPLE_RATES.values()[-1]
        self.setField(self.samplingCheck, ridx)


    def OnSetTZ(self, event):
        val = str(-time.timezone / 60 / 60)
        self.setField(self.utcCheck, val)


    def getData(self):
        """ Retrieve the values entered in the dialog.
        """
        data = self.info.copy()
        
        for name,control in self.fieldMap.iteritems():
            self.addVal(control, data, name)
        
        data['BW_RATE_PWR'] = self.SAMPLE_RATES.keys()[self.controls[self.samplingCheck][0].GetSelection()] | 0b1000

        if self.rtccCheck.GetValue():
            data['RTCC_ENA'] = 1
            if self.setTimeCheck.GetValue():
                # Set the 'RTCC write' flag and the time.
                data['WR_RTCC'] = 0x5A
                data['RTCC_TIME'] = datetime.now()
        else:
            data['RTCC_ENA'] = 0

        self.root.setTime = self.setTimeCheck.GetValue()
        return data

#===============================================================================

class ClassicInfoPanel(InfoPanel):
    """ Display read-only attributes of a Slam Stick Classic recorder.
    """
    
    def getDeviceData(self):
        info = self.root.deviceInfo
        self.data = OrderedDict((
            ('Device Type', 'Slam Stick Classic'),
            ('System UID', info['SYSUID_RESERVE']),
            ('Config. Format Version', info['CONFIGFILE_VER']), 
            ('Hardware Revision', info['HWREV']), 
            ('Firmware Revision', info['SWREV']), 
            ('Version String', info['VERSION_STR']), 
         ))


#===============================================================================
# 
#===============================================================================

class ConfigDialog(sc.SizedDialog):
    """ The parent dialog for all the recorder configuration tabs. 
    
        @todo: Choose the tabs dynamically based on the recorder type, once
            there are multiple types of recorders using the MIDE format.
    """
    
    ID_IMPORT = wx.NewId()
    ID_EXPORT = wx.NewId()
    
    def buildUI_SSX(self):
        self.triggers = SSXTriggerConfigPanel(self.notebook, -1, root=self)
        self.options = OptionsPanel(self.notebook, -1, root=self)
        info = InfoPanel(self.notebook, -1, root=self, info=self.deviceInfo)
        self.notebook.AddPage(self.options, "General")
        self.notebook.AddPage(self.triggers, "Triggers")
        self.notebook.AddPage(info, "Device Info")
    
    
    def buildUI_Classic(self):
        self.options = ClassicOptionsPanel(self.notebook, -1, root=self)
        self.triggers = ClassicTriggerConfigPanel(self.notebook, -1, root=self)
        info = ClassicInfoPanel(self.notebook, -1, root=self)
        self.notebook.AddPage(self.options, "General")
        self.notebook.AddPage(self.triggers, "Triggers")
        self.notebook.AddPage(info, "Device Info")


    def __init__(self, *args, **kwargs):
        self.device = kwargs.pop('device', None)
        self.root = kwargs.pop('root', None)
        self.setTime = kwargs.pop('setTime', True)
        self.useUtc = kwargs.pop('useUtc', True)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | \
            wx.MINIMIZE_BOX | wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
        
        super(ConfigDialog, self).__init__(*args, **kwargs)
        
        try:
            self.deviceInfo = self.device.getInfo()
            self.deviceConfig = self.device.getConfig()
            self._doNotShow = False
        except:# NotImplementedError:
            wx.MessageBox( 
                "The device configuration data could not be read.", 
                "Configuration Error", parent=self, style=wx.OK|wx.ICON_ERROR)
            self._doNotShow = True
            return
        
        pane = self.GetContentsPane()
        self.notebook = wx.Notebook(pane, -1)
        
        if isinstance(self.device, devices.SlamStickX):
            self.buildUI_SSX()
        elif isinstance(self.device, devices.SlamStickClassic):
            self.buildUI_Classic()
        else:
            raise TypeError("Unknown recorder type: %r" % self.device)
        
        self.notebook.SetSizerProps(expand=True, proportion=-1)

        buttonpane = sc.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
        wx.Button(buttonpane, self.ID_IMPORT, "Import...")
        wx.Button(buttonpane, self.ID_EXPORT, "Export...")
        self.Bind(wx.EVT_BUTTON, self.importConfig, id=self.ID_IMPORT)
        self.Bind(wx.EVT_BUTTON, self.exportConfig, id=self.ID_EXPORT)
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.APPLY | wx.CANCEL))
        self.SetAffirmativeId(wx.ID_APPLY)
        self.okButton = self.FindWindowById(wx.ID_APPLY)
        
        self.SetMinSize((436, 520))
        self.Fit()
        
        
    def getData(self, schema=util.DEFAULT_SCHEMA):
        """ Retrieve the values entered in the dialog.
        """
        data = OrderedDict()
        data.update(self.options.getData())
        data.update(self.triggers.getData())
        return data


    def importConfig(self, evt=None):
        done = False
        dlg = wx.FileDialog(self, 
                            message="Choose an exported configuration file",
                            wildcard=("Exported config file (*.cfx)|*.cfx|"
                                      "All files (*.*)|*.*"),
                            style=wx.OPEN|wx.CHANGE_DIR|wx.FILE_MUST_EXIST)
        while not done:
            d = dlg.ShowModal()
            if d != wx.ID_OK:
                done = True
            else:
                try:
                    filename = dlg.GetPath()
                    self.device.importConfig(filename)
                    for i in range(self.notebook.GetPageCount()):
                        self.notebook.GetPage(i).initUI()
                    done = True
                except devices.ConfigError:
                    # TODO: More specific error message (wrong device type
                    # vs. not a config file
                    md = wx.MessageBox( 
                        "The selected file does not appear to be a valid "
                        "configuration file for this device.", 
                        "Invalid Configuration", parent=self,
                        style=wx.OK | wx.CANCEL | wx.ICON_EXCLAMATION) 
                    done = md == wx.CANCEL
        dlg.Destroy()

    
    def exportConfig(self, evt=None):
        dlg = wx.FileDialog(self, message="Export Device Configuration", 
                            wildcard=("Exported config file (*.cfx)|*.cfx|"
                                      "All files (*.*)|*.*"),
                            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.device.exportConfig(dlg.GetPath(), data=self.getData())
            except:
                # TODO: More specific error message
                wx.MessageBox( 
                    "The configuration data could not be exported to the "
                    "specified file.", "Config Export Failed", parent=self,
                    style=wx.OK | wx.ICON_EXCLAMATION)
        dlg.Destroy()

#===============================================================================
# 
#===============================================================================

def configureRecorder(path, save=True, setTime=True, useUtc=True, parent=None,
                      showMsg=True):
    """ Create the configuration dialog for a recording device. 
    
        @param path: The path to the data recorder (e.g. a mount point under
            *NIX or a drive letter under Windows)
        @keyword save: If `True` (default), the updated configuration data
            is written to the device when the dialog is closed via the OK
            button.
        @keyword setTime: If `True`, the checkbox to set the device's clock
            on save will be checked by default.
        @keyword useUtc: If `True`, the 'in UTC' checkbox for wake times will
            be checked by default.
        @return: A tuple containing the data written to the recorder (a nested 
            dictionary), whether `setTime` was checked before save, and whether
            `useUTC` was checked before save. `None` is returned if the 
            configuration was cancelled.
    """
    result = None
    
    if isinstance(path, devices.Recorder):
        dev = path
        path = dev.path
    else:
        dev = devices.getRecorder(path)
        
    if not dev:
        raise ValueError("Specified path %r does not appear to be a recorder" %\
                         path)
        
    dlg = ConfigDialog(parent, -1, "Configure %s (%s)" % (dev.baseName, path), 
                       device=dev, setTime=setTime, useUtc=useUtc)
    
    # Sort of a hack to abort the configuration if data couldn't be read
    # (the dialog itself does it)
    
    if dlg._doNotShow:
        return
    if dlg.ShowModal() != wx.ID_CANCEL:
        useUtc = dlg.useUtc
        setTime = dlg.setTime
        data = dlg.getData()
        if save:
            dev.saveConfig(data)
        result = data, dlg.setTime, dlg.useUtc, dev
        
    dlg.Destroy()
    return result


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    recorderPath = devices.getDeviceList()[-1]
    print "configureRecorder() returned %r" % (configureRecorder(recorderPath, 
                                                                 useUtc=False),)
