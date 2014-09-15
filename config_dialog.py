'''
The UI for configuring a recorder. Ultimately, the set of tabs will be
determined by the recorder type, and will feature tabs specific to that 
recorder. Since there's only the two SSX variants, this is not urgent.

@author: dstokes

@todo: This has grown organically and should be completely refactored. The
    basic design was based on SSX requirements, with optional fields; making
    it support SSC was a hack.
    
@todo: `BaseConfigPanel` is a bit over-engineered; clean it up.

@todo: I use `info` and `data` for the recorder info at different times;
    if there's no specific reason, unify. It may be vestigial.
    
@todo: Move device-specific components to different modules;
    This could be the start of a sort of extensible architecture.


'''

__all__ = ['configureRecorder']

import cgi
from collections import OrderedDict
from datetime import datetime
import string
import time

import wx.lib.sized_controls as sc
from wx.html import HtmlWindow
import wx; wx = wx

from mide_ebml import util
from mide_ebml.parsers import PolynomialParser
from common import makeWxDateTime, DateTimeCtrl, cleanUnicode
import devices


#===============================================================================
# 
#===============================================================================

class BaseConfigPanel(sc.SizedScrolledPanel):
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
            val = cleanUnicode(val).strip()
            if val == u'':
                return None
        except ValueError:
            return None
        return val
    

    def addField(self, labelText, name=None, units="", value="", 
                 fieldSize=None, fieldStyle=None, tooltip=None, indent=0):
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
        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            pad = wx.StaticText(col1, -1, ' '*indent)
            pad.SetSizerProps(valign="center")
        else:
            col1 = self
        fieldSize = self.fieldSize if fieldSize is None else fieldSize
        txt = cleanUnicode(value)
        c = wx.StaticText(col1, -1, labelText)
        c.SetSizerProps(valign="center")
        
        if units:
            subpane = sc.SizedPanel(self, -1)
            subpane.SetSizerType("horizontal")
            subpane.SetSizerProps(expand=True)
        else:
            subpane = self
        
        if fieldStyle is None:
            t = wx.TextCtrl(subpane, -1, txt, size=fieldSize)
        else:
            t = wx.TextCtrl(subpane, -1, txt, size=fieldSize, style=fieldStyle)

        if tooltip is not None:
            c.SetToolTipString(cleanUnicode(tooltip))
            t.SetToolTipString(cleanUnicode(tooltip))
            
        if self.fieldSize is None:
            self.fieldSize = t.GetSize()
        
        self.controls[t] = [t, c]
        
        if units:
            u = wx.StaticText(subpane, -1, units)
            u.SetSizerProps(valign="center")
            self.controls[t].append(u)
        
        if col1 != self:
            self.controls[t].append(pad)
        if name is not None:
            self.fieldMap[name] = t
            
        return t
    
    
    def addButton(self, label, id_=-1, handler=None, tooltip=None, 
                  size=None, style=None, indent=0):
        """ Helper method to create a button in the first column.
            
            @param label: The button's label text
            @keyword id_: The ID for the button
            @keyword handler: The `wx.EVT_BUTTON` event handling method
            @keyword tooltip: A tooltip string for the field.
        """
        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            pad = wx.StaticText(col1, -1, ' '*indent)
            pad.SetSizerProps(valign="center")
        else:
            col1 = self
        size = size or (self.fieldSize[0]+20, self.fieldSize[1])
        if style is None:
            b = wx.Button(col1, id_, label, size=size)
        else:
            b = wx.Button(col1, id_, label, size=size, style=style)
        b.SetSizerProps()
        sc.SizedPanel(self, -1) # Spacer
        
        self.controls[b] = []
        if col1 != self:
            self.controls[b].append(pad)

        if tooltip is not None:
            b.SetToolTipString(cleanUnicode(tooltip))
        if handler is not None:
            b.Bind(wx.EVT_BUTTON, handler)
        return b
    
    
    def addCheck(self, checkText, name=None, units="", tooltip=None, indent=0):
        """ Helper method to create a single checkbox and add it to the set of
            controls. 

            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword tooltip: A tooltip string for the field.
        """
        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            pad = wx.StaticText(col1, -1, ' '*indent)
            pad.SetSizerProps(valign="center")
        else:
            col1 = self
        c = wx.CheckBox(col1, -1, checkText)
        sc.SizedPanel(self, -1) # Spacer
        
        if tooltip is not None:
            c.SetToolTipString(cleanUnicode(tooltip))
            
        self.controls[c] = [None]
        if col1 != self:
            self.controls[c].append(pad)
        if name is not None:
            self.fieldMap[name] = c
            
        return c


    def addCheckField(self, checkText, name=None, units="", value="", 
                      fieldSize=None, fieldStyle=None, tooltip=None, indent=0):
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
        txt = cleanUnicode(value)

        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType("horizontal")
            pad = wx.StaticText(col1, -1, ' '*indent)
            c = wx.CheckBox(col1, -1, checkText)
        else:
            c = wx.CheckBox(self, -1, checkText)
        c.SetSizerProps(valign="center")

        subpane = sc.SizedPanel(self, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)
        
        if fieldStyle is None:
            t = wx.TextCtrl(subpane, -1, txt, size=fieldSize)
        else:
            t = wx.TextCtrl(subpane, -1, txt, size=fieldSize, style=fieldStyle)
        u = wx.StaticText(subpane, -1, units)
        u.SetSizerProps(valign="center")
        
        self.controls[c] = [t, u]
        if col1 != self:
            self.controls[c].append(pad)
        
        if tooltip is not None:
            c.SetToolTipString(cleanUnicode(tooltip))
            t.SetToolTipString(cleanUnicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = t.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
            
        return c


    def addFloatField(self, checkText, name=None, units="", value="",
                      precision=0.01, digits=2, minmax=(-100,100), 
                      fieldSize=None, fieldStyle=None, tooltip=None,
                      check=True, indent=0):
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
        
        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            pad = wx.StaticText(col1, -1, ' '*indent)
            pad.SetSizerProps(valign="center")
        else:
            col1 = self
        if check:
            c = wx.CheckBox(col1, -1, checkText)
        else:
            c = wx.StaticText(col1, -1, checkText)
        c.SetSizerProps(valign="center")

        col2 = sc.SizedPanel(self, -1)
        col2.SetSizerType("horizontal")
        col2.SetSizerProps(expand=True)
        
        lf = wx.SpinCtrlDouble(col2, -1, value=str(value), inc=precision,
                          min=minmax[0], max=minmax[1], size=fieldSize)
        u = wx.StaticText(col2, -1, units)
        u.SetSizerProps(valign="center")
        
        self.controls[c] = [lf, u]
        if col1 != self:
            self.controls[c].append(pad)
        
        if tooltip is not None:
            c.SetToolTipString(cleanUnicode(tooltip))
            lf.SetToolTipString(cleanUnicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = lf.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
        
        if digits is not None:
            lf.SetDigits(digits)
        
        return c

    def addIntField(self, checkText, name=None, units="", value=None,
                      minmax=(-100,100), fieldSize=None, fieldStyle=None, 
                      tooltip=None, check=True, indent=0):
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

        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            pad = wx.StaticText(col1, -1, ' '*indent)
            pad.SetSizerProps(valign="center")
        else:
            col1 = self
        if check:
            c = wx.CheckBox(col1, -1, checkText)
        else:
            c = wx.StaticText(col1, -1, checkText)
        c.SetSizerProps(valign="center")

        subpane = sc.SizedPanel(self, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)
        
        value = "" if value is None else int(value)
        lf = wx.SpinCtrl(subpane, -1, value=str(value),
                          min=int(minmax[0]), max=int(minmax[1]), size=fieldSize)
        u = wx.StaticText(subpane, -1, units)
        u.SetSizerProps(valign="center")
        
        self.controls[c] = [lf, u]
        if col1 != self:
            self.controls[c].append(pad)
        
        if tooltip is not None:
            c.SetToolTipString(cleanUnicode(tooltip))
            lf.SetToolTipString(cleanUnicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = lf.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
            
        return c


    def addChoiceField(self, checkText, name=None, units="", choices=[], 
                       selected=None, fieldSize=None, fieldStyle=None, 
                       tooltip=None, check=True, indent=0):
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

        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            pad = wx.StaticText(col1, -1, ' '*indent)
            pad.SetSizerProps(valign="center")
        else:
            col1 = self
        if check:
            c = wx.CheckBox(col1, -1, checkText)
        else:
            c = wx.StaticText(col1, -1, checkText)
        c.SetSizerProps(valign="center")

        subpane = sc.SizedPanel(self, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)

        if fieldStyle is None:
            field = wx.Choice(subpane, -1, size=fieldSize, choices=choices)
        else:
            field = wx.Choice(subpane, -1, size=fieldSize, choices=choices,
                               style=fieldStyle)
        u = wx.StaticText(subpane, -1, units)
        u.SetSizerProps(valign="center")
        
        self.controls[c] = [field, u]
        if col1 != self:
            self.controls[c].append(pad)
        
        if selected is not None:
            field.SetSelection(int(selected))
        
        if tooltip is not None:
            c.SetToolTipString(cleanUnicode(tooltip))
            field.SetToolTipString(cleanUnicode(tooltip))
        
        if fieldSize == (-1,-1):
            self.fieldSize = field.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
        
        return c


    def addDateTimeField(self, checkText, name=None, fieldSize=None, 
                         fieldStyle=None, tooltip=None, check=True, indent=0):
        """ Helper method to create a checkbox and a time-entry field pair, and
            add them to the set of controls.
 
            @param checkText: The checkbox's label text.
            @keyword name: The name of the key in the config data, if the
                field maps directly to a value.
            @keyword tooltip: A tooltip string for the field.
        """ 
        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            pad = wx.StaticText(col1, -1, ' '*indent)
            pad.SetSizerProps(valign="center")
        else:
            col1 = self
        if check:
            c = wx.CheckBox(col1, -1, checkText)
        else:
            c = wx.StaticText(col1, -1, checkText)
        c.SetSizerProps(valign='center')
        ctrl =  DateTimeCtrl(self, -1, size=self.fieldSize)
        ctrl.SetSize(self.fieldSize)
        ctrl.SetSizerProps(expand=True)
        
        self.controls[c] = [ctrl]
        if col1 != self:
            self.controls[c].append(pad)
            
        if name is not None:
            self.fieldMap[name] = c

        if tooltip is not None:
            c.SetToolTipString(cleanUnicode(tooltip))
            ctrl.SetToolTipString(cleanUnicode(tooltip))

        return c


    def addSpacer(self):
#         wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL).SetSizerProps(expand=True)
#         wx.StaticText(self, -1, '')
        sc.SizedPanel(self, -1) # Spacer
        sc.SizedPanel(self, -1) # Spacer


    def startGroup(self, label, indent=0):
        """ Start a visual 'grouping' of controls, starting with a group
            title. Items within the group will be indented.
        """
        indent += self.indent
        if indent > 0:
            col1 = sc.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            wx.StaticText(col1, -1, ' '*indent).SetSizerProps(valign="center")
        else:
            col1 = self
            
        t = wx.StaticText(col1, -1, label)
        t.SetFont(self.boldFont)
        sc.SizedPanel(self, -1) # Spacer
        
        self.controls[t] = []
        if col1 != self:
            self.controls[t].append(col1)
            
        self.indent += 1
        return t
     
    def endGroup(self):
        self.indent -= 1
    
    
    def makeChild(self, parent, *children):
        """ Set one or more fields as the 'children' of another field
            (e.g. individual trigger parameters that should be disabled when
            a main 'use triggers' checkbox is unchecked).
        """
        for child in children:
            if child in self.controls:
                self.controls[parent].extend(self.controls[child])
            self.controls[parent].append(child)


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
        
        self.boldFont = self.GetFont().Bold()
        self.indent = 0
        
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
        # Stub. Subclasses should implement this.
        pass


    def getDeviceData(self):
        """ Retrieve the device's configuration data (or other info) and 
            put it in the `data` attribute.
        """
        # Stub. Subclasses should implement this.
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
        else:
            checkbox.Enable(state)
        if checkbox not in self.controls:
            return
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
            field.Enable(checked)
            if isinstance(field, wx.TextCtrl):
                if isinstance(value, float):
                    value = "%.3f" % value
                elif not isinstance(value, basestring):
                    value = str(value)
            elif isinstance(field, DateTimeCtrl):
                value = makeWxDateTime(value)
            elif isinstance(field, wx.Choice):
                strv = cleanUnicode(value)
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
            checkbox.Show(not hidden)
            for c in self.controls[checkbox]:
                if c is not None:
                    c.Show(not hidden)
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
                val = fields[0].GetValue().GetTicks()
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
        """ Retrieve the device's configuration data (or other info) and 
            put it in the `data` attribute.
        """
        cfg= self.root.device.getConfig()
        self.data = cfg.get('SSXTriggerConfiguration', {})


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
            "RecordingTime", "seconds", 0, minmax=(0,86400))
        
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
            units="G", tooltip="The lower trigger limit. Less than 0.", 
            value=-5, indent=2, check=False)
        self.accelHiCheck = self.addFloatField("Accelerometer Trigger, High:", 
            units="G", tooltip="The upper trigger limit. Greater than 0.", 
            value=5, indent=2, check=False)
        self.makeChild(self.accelTrigCheck, self.accelLoCheck, self.accelHiCheck)

        sc.SizedPanel(self, -1).SetSizerProps(proportion=1)
        sc.SizedPanel(self, -1).SetSizerProps(proportion=1)
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
                low = -5.0 if low is None else accelTransform(low)
                high = 5.0 if high is None else accelTransform(high)
                self.setField(self.accelLoCheck, low)
                self.setField(self.accelHiCheck, high)
                self.accelTrigCheck.SetValue(True)
            elif channel == 1:
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
            trig = OrderedDict(TriggerChannel=0)
            self.addVal(self.accelLoCheck, trig, "TriggerWindowLo", kind=float,
                        transform=self.root.device._packAccel, 
                        default=self.root.device._packAccel(-5.0))
            self.addVal(self.accelHiCheck, trig, "TriggerWindowHi", kind=float,
                        transform=self.root.device._packAccel, 
                        default=self.root.device._packAccel(5.0))
            if len(trig) > 2:
                triggers.append(trig)
                 
        if self.presTrigCheck.GetValue():
            trig = OrderedDict(TriggerChannel=1, TriggerSubChannel=0)
            self.addVal(self.pressLoCheck, trig, 'TriggerWindowLo')
            self.addVal(self.pressHiCheck, trig, 'TriggerWindowHi')
            if len(trig) > 2:
                triggers.append(trig)
                     
        if self.tempTrigCheck.GetValue():
            trig = OrderedDict(TriggerChannel=1, TriggerSubChannel=1)
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
        
        sc.SizedPanel(self, -1).SetSizerProps(proportion=1)
        sc.SizedPanel(self, -1).SetSizerProps(proportion=1)
        self.addButton("Reset to Defaults", wx.ID_DEFAULT, self.OnDefaultsBtn, 
                       "Reset the general configuration to the default values. "
                       "Does not change other tabs.")

        self.Fit()

        
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
                    "An error occurred when trying to set the recorder's clock.",
                    "Configuration Error", wx.OK | wx.ICON_ERROR, parent=self)
                
        self.root.setTime = self.setTimeCheck.GetValue()
        
        return data


#===============================================================================
# 
#===============================================================================
        
class InfoPanel(HtmlWindow):
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
                   'Config. Format Version': str,
                   'Recorder Serial': lambda x: "SSX%07d" % x
                   }

    column_widths = (50,50)

    def __init__(self, *args, **kwargs):
        self.info = kwargs.pop('info', {})
        self.root = kwargs.pop('root', None)
        super(InfoPanel, self).__init__(*args, **kwargs)
        self.html = []
        self._inTable = False
        self.buildUI()
        self.initUI()

    def escape(self, s):
        return cgi.escape(cleanUnicode(s))

    def addItem(self, k, v, escape=True):
        """ Append a labeled info item.
        """
        # Automatically create new table if not already in one.
        if not self._inTable:
            self.html.append(u"<table width='100%'>")
            self._inTable = True
        if escape:
            k = self.escape(k)
            v = self.escape(v)
        else:
            k = cleanUnicode(k)
            v = cleanUnicode(v)
        
        self.html.append(u"<tr><td width='%d%%'>%s</td>" % 
                         (self.column_widths[0],k))
        self.html.append(u"<td width='%d%%'><b>%s</b></td></tr>" % 
                         (self.column_widths[1],v))


    def closeTable(self):
        """ Wrap up any open table, if any.
        """
        if self._inTable:
            self.html.append(u"</table>")
            self._inTable = False


    def addLabel(self, v, warning=False, escape=True):
        """ Append a label.
        """
        if escape:
            v = self.escape(v)
        else:
            v = cleanUnicode(v)
        if self._inTable:
            self.html.append(u"</table>")
            self._inTable = False
        if warning:
            v = u"<font color='#FF0000'>%s</font>" % v
        self.html.append(u"<p>%s</p>" % v)


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
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.getDeviceData()
        self.html = [u"<html><body>"]
        if isinstance(self.data, dict):
            items = self.data.iteritems()
        else:
            items = iter(self.data)
        for k,v in items:
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
                    v = u"0x%08X" % v
                else:
                    v = cleanUnicode(v)
            except TypeError:
                v = cleanUnicode(v)

            self.addItem(k,v)
            
        if self._inTable:
            self.html.append(u"</table>")
        self.html.append(u'</body></html>')
        self.SetPage(u''.join(self.html))


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

class CalibrationPanel(InfoPanel):
    """ Panel for displaying SSX calibration polynomials. Read-only.
    """
    
    def getDeviceData(self):
        PP = PolynomialParser(None)
        self.info = [PP.parse(c) for c in self.data.value]
        
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
        
        for cal in self.info:
            self.html.append("<p><b>Calibration ID %d</b>" % cal.id)
            calType = cal.__class__.__name__
            if hasattr(cal, 'channelId'):
                calType += "; references Channel %x" % cal.channelId
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
            "RECORD_DELAY", "seconds", minmax=(0,2**17), check=False,
            tooltip="Seconds to delay between pressing the 'record' button "
            "and the start of recording. Note: This will be rounded to the "
            "lowest multiple of 2.")
        self.timeCheck = self.addIntField(
            "Recording Length Limit:", "SECONDS_PER_TRIGGER", "seconds", 
            minmax=(0,2**17), check=False, tooltip="Recording length. "
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
        
        self.intGroup = self.startGroup("Interval Trigger")
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
            'REPEATS', minmax=(0,255), tooltip="The number of interval-based "
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
        
        sc.SizedPanel(self, -1).SetSizerProps(proportion=1)
        sc.SizedPanel(self, -1).SetSizerProps(proportion=1)
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
            self.hideField(self.intGroup)
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
        
        sc.SizedPanel(self, -1).SetSizerProps(proportion=1)
        sc.SizedPanel(self, -1).SetSizerProps(proportion=1)
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
        wx.Button(buttonpane, self.ID_IMPORT, "Import...").SetSizerProps(halign="left")
        wx.Button(buttonpane, self.ID_EXPORT, "Export...").SetSizerProps(halign="left")
        sc.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        self.Bind(wx.EVT_BUTTON, self.importConfig, id=self.ID_IMPORT)
        self.Bind(wx.EVT_BUTTON, self.exportConfig, id=self.ID_EXPORT)
        wx.Button(buttonpane, wx.ID_APPLY).SetSizerProps(halign="right")
        wx.Button(buttonpane, wx.ID_CANCEL).SetSizerProps(halign="right")
        
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
            try:
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
                    except devices.ConfigVersionError as err:
                        # TODO: More specific error message (wrong device type
                        # vs. not a config file
                        cname, cvers, dname, dvers = err.args[1]
                        if cname != dname:
                            md = wx.MessageBox( 
                                "The selected file does not appear to be a  "
                                "valid configuration file for this device.", 
                                "Invalid Configuration", parent=self,
                                style=wx.OK | wx.CANCEL | wx.ICON_EXCLAMATION) 
                            done = md == wx.CANCEL
                        else:
                            s = "older" if cvers < dvers else "newer"
                            md = wx.MessageBox(
                                 "The selected file was exported from a %s "
                                 "version of %s.\nImporting it may cause "
                                 "problems.\n\nImport anyway?" % (s, cname), 
                                 "Configuration Version Mismatch", parent=self, 
                                 style=wx.YES_NO|wx.NO_DEFAULT|wx.ICON_EXCLAMATION)
                            if md == wx.YES:
                                self.device.importConfig(filename, 
                                                         allowOlder=True, 
                                                         allowNewer=True)
                                done = True
    
            except ValueError:
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
            except NotImplementedError:
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
            try:
                dev.saveConfig(data)
            except IOError as err:
                msg = ("An error occurred when trying to update the "
                       " recorder's configuration data.")
                if err.errno == 2:
                    msg += "\nThe recorder appears to have been removed."
                wx.MessageBox(msg, "Configuration Error", wx.OK | wx.ICON_ERROR,
                              parent=parent)
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
                                                                 useUtc=True),)
