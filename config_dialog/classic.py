'''
The UI for configuring a Slam Stick Classic. Copied from the old configuration
system. This will eventually be retired.
'''

__all__ = ['configureRecorder']

from collections import OrderedDict
from datetime import datetime
import errno
import string
import time

import wx
import wx.lib.sized_controls as SC

# from mide_ebml import util
from common import cleanUnicode
from timeutil import makeWxDateTime
from widgets.shared import DateTimeCtrl
import devices

from special_tabs import InfoPanel

# from base import HtmlWindow

#===============================================================================
# 
#===============================================================================

class BaseConfigPanel(SC.SizedScrolledPanel):
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
    
    
    def setFieldToolTip(self, cb, tooltip):
        """ Helper method to set the tooltip for all a field's widgets.
        """
        if tooltip is None:
            return
        tooltip = cleanUnicode(tooltip)
        cb.SetToolTip(tooltip)
        if cb in self.controls:
            for c in self.controls[cb]:
                try:
                    c.SetToolTip(tooltip)
                except AttributeError:
                    pass
        

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
            col1 = SC.SizedPanel(self, -1)
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
            subpane = SC.SizedPanel(self, -1)
            subpane.SetSizerType("horizontal")
            subpane.SetSizerProps(expand=True)
        else:
            subpane = self
        
        if fieldStyle is None:
            t = wx.TextCtrl(subpane, -1, txt, size=fieldSize)
        else:
            t = wx.TextCtrl(subpane, -1, txt, size=fieldSize, style=fieldStyle)

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

        self.setFieldToolTip(t, tooltip)
            
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
            col1 = SC.SizedPanel(self, -1)
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
        SC.SizedPanel(self, -1) # Spacer
        
        self.controls[b] = []
        if col1 != self:
            self.controls[b].append(pad)

        if tooltip is not None:
            b.SetToolTip(cleanUnicode(tooltip))
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
            col1 = SC.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            pad = wx.StaticText(col1, -1, ' '*indent)
            pad.SetSizerProps(valign="center")
        else:
            col1 = self
        c = wx.CheckBox(col1, -1, checkText)
        SC.SizedPanel(self, -1) # Spacer
        
        if tooltip is not None:
            c.SetToolTip(cleanUnicode(tooltip))
            
        self.controls[c] = [None]
        if col1 != self:
            self.controls[c].append(pad)
        if name is not None:
            self.fieldMap[name] = c
        
        self.setFieldToolTip(c, tooltip)

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
            col1 = SC.SizedPanel(self, -1)
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
 
        col2 = SC.SizedPanel(self, -1)
        col2.SetSizerType("horizontal")
        col2.SetSizerProps(expand=True)
         
        lf = wx.SpinCtrlDouble(col2, -1, value=str(value), inc=precision,
                          min=minmax[0], max=minmax[1], size=fieldSize)
        u = wx.StaticText(col2, -1, units)
        u.SetSizerProps(valign="center")
         
        self.controls[c] = [lf, u]
        if col1 != self:
            self.controls[c].append(pad)
         
        if fieldSize == (-1,-1):
            self.fieldSize = lf.GetSize()
         
        if name is not None:
            self.fieldMap[name] = c
         
        if digits is not None:
            lf.SetDigits(digits)
         
        self.setFieldToolTip(c, tooltip)
 
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
            col1 = SC.SizedPanel(self, -1)
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

        subpane = SC.SizedPanel(self, -1)
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
        
        if fieldSize == (-1,-1):
            self.fieldSize = lf.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
            
        self.setFieldToolTip(c, tooltip)

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
            col1 = SC.SizedPanel(self, -1)
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

        if units is None:
            subpane = col1
        else:
            subpane = SC.SizedPanel(self, -1)
            subpane.SetSizerType("horizontal")
            subpane.SetSizerProps(expand=True)

        if fieldStyle is None:
            field = wx.Choice(subpane, -1, size=fieldSize, choices=choices)
        else:
            field = wx.Choice(subpane, -1, size=fieldSize, choices=choices,
                               style=fieldStyle)
        if units is None:
            self.controls[c] = [field]
        else:
            u = wx.StaticText(subpane, -1, units)
            u.SetSizerProps(valign="center")
            self.controls[c] = [field, u]
            
        if col1 != self:
            self.controls[c].append(pad)
        
        if selected is not None:
            field.SetSelection(int(selected))
        
        if fieldSize == (-1,-1):
            self.fieldSize = field.GetSize()
        
        if name is not None:
            self.fieldMap[name] = c
        
        self.setFieldToolTip(c, tooltip)

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
            col1 = SC.SizedPanel(self, -1)
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

        self.setFieldToolTip(c, tooltip)

        return c


    def addSpacer(self):
#         wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL).SetSizerProps(expand=True)
#         wx.StaticText(self, -1, '')
        SC.SizedPanel(self, -1) # Spacer
        SC.SizedPanel(self, -1) # Spacer


    def startGroup(self, label, indent=0):
        """ Start a visual 'grouping' of controls, starting with a group
            title. Items within the group will be indented.
        """
        indent += self.indent
        if indent > 0:
            col1 = SC.SizedPanel(self, -1)
            col1.SetSizerType('horizontal')
            col1.SetSizerProps(valign="center")
            wx.StaticText(col1, -1, ' '*indent).SetSizerProps(valign="center")
        else:
            col1 = self
            
        t = wx.StaticText(col1, -1, label)
        t.SetFont(self.boldFont)
        SC.SizedPanel(self, -1) # Spacer
        
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
        
        self.tabIcon = -1
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


    def getData(self):
        return {}
    
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
#===============================================================================
# 
#===============================================================================

class ConfigDialog(SC.SizedDialog):
    """ The parent dialog for all the recorder configuration tabs. 
    
        @todo: Choose the tabs dynamically based on the recorder type, once
            there are multiple types of recorders using the MIDE format.
    """
    
    ID_IMPORT = wx.NewIdRef()
    ID_EXPORT = wx.NewIdRef()
    
    ICON_INFO = 0
    ICON_WARN = 1
    ICON_ERROR = 2
    
    FIELD_PAD = 8
    
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
        self.pages = []

        buildUI_Classic(self)
        
        # Tab icon stuff
        images = wx.ImageList(16, 16)
        imageIndices = []
        for n,i in enumerate((wx.ART_INFORMATION, wx.ART_WARNING, wx.ART_ERROR)):
            images.Add(wx.ArtProvider.GetBitmap(i, wx.ART_CMN_DIALOG, (16,16)))
            imageIndices.append(n)
        self.notebook.AssignImageList(images)

        for i in xrange(self.notebook.GetPageCount()):
            icon = self.notebook.GetPage(i).tabIcon
            if icon > -1:
                self.notebook.SetPageImage(i, imageIndices[icon])
        
        self.notebook.SetSizerProps(expand=True, proportion=-1)

        # This stuff is just to create non-standard buttons, right aligned,
        # with a gap. It really should not be this hard to do. This approach is
        # probably not optimal or properly cross-platform.
        SC.SizedPanel(self.GetContentsPane(), -1, size=(8,self.FIELD_PAD))
        
        buttonpane = SC.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
#         wx.Button(buttonpane, self.ID_IMPORT, "Import...").SetSizerProps(halign="left")
#         wx.Button(buttonpane, self.ID_EXPORT, "Export...").SetSizerProps(halign="left")
        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        self.Bind(wx.EVT_BUTTON, self.importConfig, id=self.ID_IMPORT)
        self.Bind(wx.EVT_BUTTON, self.exportConfig, id=self.ID_EXPORT)
        wx.Button(buttonpane, wx.ID_APPLY).SetSizerProps(halign="right")
        wx.Button(buttonpane, wx.ID_CANCEL).SetSizerProps(halign="right")
        
        self.SetAffirmativeId(wx.ID_APPLY)
        self.okButton = self.FindWindowById(wx.ID_APPLY)
        
        self.SetMinSize((400, 500))
        self.Fit()
        self.SetSize((560,560))
        
        
    def getData(self, schema=None):
        """ Retrieve the values entered in the dialog.
        """
        data = OrderedDict()
        for i in range(self.notebook.GetPageCount()):
            try:
                data.update(self.notebook.GetPage(i).getData())
            except AttributeError:
                pass
#         data.update(self.options.getData())
#         data.update(self.triggers.getData())
        return data


    def importConfig(self, evt=None):
        done = False
        dlg = wx.FileDialog(self, 
                            message="Choose an exported configuration file",
                            wildcard=("Exported config file (*.cfx)|*.cfx|"
                                      "All files (*.*)|*.*"),
                            style=wx.FD_OPEN|wx.FD_CHANGE_DIR|wx.FD_FILE_MUST_EXIST)
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
                            style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.device.exportConfig(dlg.GetPath(), data=self.getData())
                    
            except:# NotImplementedError:
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
        msg = getattr(dev, "POST_CONFIG_MSG", None)

        if save:
            try:
                dev.saveConfig(data)
                if hasattr(dlg, "usercal"):
                    if dlg.usercal.info is not None:
                        dev.writeUserCal(dlg.usercal.info)
            except IOError as err:
                msg = ("An error occurred when trying to update the "
                       " recorder's configuration data.")
                if err.errno == errno.ENOENT:
                    msg += "\nThe recorder appears to have been removed."
                wx.MessageBox(msg, "Configuration Error", wx.OK | wx.ICON_ERROR,
                              parent=parent)
        result = data, dlg.setTime, dlg.useUtc, dev, msg
        
    dlg.Destroy()
    return result


#===============================================================================
# 
#===============================================================================


def testDialog(save=True):
    class TestApp(wx.App):
        def getPref(self, name, default=None):
            if name == 'showAdvancedOptions':
                return True
            return default
            
    _app = TestApp()
    recorderPath = devices.getDeviceList()[-1]
    print "configureRecorder() returned %r" % (configureRecorder(recorderPath,
                                                                 save=save,
                                                                 useUtc=True),)

if __name__ == "__main__":
    testDialog()