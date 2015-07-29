'''
Created on Jun 25, 2015

@author: dstokes
'''
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
import cgi
from collections import OrderedDict
from datetime import datetime
import string
# import time

import wx.lib.sized_controls as sc
from wx.html import HtmlWindow
import wx; wx = wx

# from mide_ebml import util
# from mide_ebml.parsers import PolynomialParser
# from mide_ebml.ebml.schema.mide import MideDocument
from common import makeWxDateTime, DateTimeCtrl, cleanUnicode
# import devices

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
# 
#===============================================================================
        
class InfoPanel(HtmlWindow):
    """ A generic configuration dialog page showing various read-only properties
        of a recorder. Displays HTML.
        
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
                   'Recorder Serial': lambda x: "SSX%07d" % x,
                    'Calibration Date': datetime.fromtimestamp,
                    'Calibration Expiration Date': datetime.fromtimestamp,
                   'Calibration Serial Number': lambda x: "C%05d" % x
                   }

    column_widths = (50,50)

    def __init__(self, *args, **kwargs):
        self.tabIcon = None
        self.info = kwargs.pop('info', {})
        self.root = kwargs.pop('root', None)
        super(InfoPanel, self).__init__(*args, **kwargs)
        self.data = OrderedDict()
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
            k = self.escape(k).replace(' ','&nbsp;')
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
        return result.replace("UTC", "UTC ").replace(" Of ", " of ")


    def getDeviceData(self):
        for k,v in self.info.iteritems():
            self.data[self.field_names.get(k, self._fromCamelCase(k))] = v

    def buildHeader(self):
        """ Called after the HTML document is started but before the dictionary 
            items are written. Override to add custom stuff.
        """
        return

    def buildFooter(self):
        """ Called after the dictionary items are written but before the HTML 
            document is closed. Override to add custom stuff.
        """
        return

    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        self.getDeviceData()
        self.html = [u"<html><body>"]
        self.buildHeader()
        
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
            except TypeError:
                pass

            self.addItem(k,cleanUnicode(v))
            
        if self._inTable:
            self.html.append(u"</table>")
        
        self.buildFooter()
        
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

            
    def getData(self):
        return {}
    
