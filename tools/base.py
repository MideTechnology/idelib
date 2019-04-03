'''
Created on Aug 25, 2015

@author: dstokes

@todo: Implement common `ToolDialog` and `widgets.export_dialog.ExportDialog`
    base class. They share much of the same functionality, but slightly
    different implementations.

'''

import wx
import wx.lib.sized_controls as SC

#===============================================================================
# 
#===============================================================================

class ToolDialog(SC.SizedDialog):
    """ The base class for all tool dialogs. Implements some useful methods.
    """
    TITLE = None
    
    def addIntField(self, parent, label, units=None, checked=False, 
                    value=0, minmax=None, check=True, tooltip=None,
                    name=None):
        """ Add an integer 'spin' field, with or without a checkbox.
        
            @param parent: The parent `SizedPanel`.
            @param label: The text displayed.
            @keyword units: The name of the units, if any, displayed to the
                right of the field.
            @keyword checked: The checkbox's initial state.
            @keyword value: The initially displayed value.
            @keyword minmax: The allowed range of values.
            @keyword check: If `False`, the field has only a label, not
                a checkbox.
            @keyword tooltip: A string to display as the control's tool tip.
            @return: The checkbox control (or label if `check` is `False`). 
                The associated widgets (the field, and units label if any)
                are referenced by attributes added to the control.
        """
        if name:
            value = self.getPref(name, value)
            
        if check:
            cb = wx.CheckBox(parent, -1, label, name=name or label)
            cb.SetValue(checked)
        else:
            cb = wx.StaticText(parent, -1, label, name=name or label)
            checked = False
        cb.SetSizerProps(valign='center')
        if tooltip is not None:
            cb.SetToolTip(tooltip)
        
        if units is not None:
            parent = SC.SizedPanel(parent, -1)
            parent.SetSizerType("horizontal")
        field = cb._field = wx.SpinCtrl(parent, -1, str(value))
        if minmax is not None:
            field.SetRange(*minmax)
        field.Enable(checked)
        if tooltip is not None:
            field.SetToolTip(tooltip)
        if units is not None:
            units = cb._units = wx.StaticText(parent, -1, units)
            units.SetSizerProps(valign="center")
            units.Enable(checked)
            if tooltip is not None:
                units.SetToolTip(tooltip)
                
        return cb


#     def xaddFloatField(self, checkText, name=None, units="", value="",
#                       precision=0.01, digits=2, minmax=(-100,100), 
#                       fieldSize=None, fieldStyle=None, tooltip=None,
#                       check=True, indent=0):
#         """ Add a numeric field with a 'spinner' control.
# 
#             @param checkText: The checkbox's label text.
#             @keyword name: The name of the key in the config data, if the
#                 field maps directly to a value.
#             @keyword units: The units displayed, if any.
#             @keyword value: The initial value of the field
#             @keyword precision: 
#             @keyword minmax: The minimum and maximum values allowed
#             @keyword fieldSize: The size of the text field
#             @keyword fieldStyle: The text field's wxWindows style flags.
#             @keyword tooltip: A tooltip string for the field.
#         """
#         fieldSize = self.fieldSize if fieldSize is None else fieldSize
#         
#         indent += self.indent
#         if indent > 0:
#             col1 = sc.SizedPanel(self, -1)
#             col1.SetSizerType('horizontal')
#             col1.SetSizerProps(valign="center")
#             pad = wx.StaticText(col1, -1, ' '*indent)
#             pad.SetSizerProps(valign="center")
#         else:
#             col1 = self
#         if check:
#             c = wx.CheckBox(col1, -1, checkText)
#         else:
#             c = wx.StaticText(col1, -1, checkText)
#         c.SetSizerProps(valign="center")
# 
#         col2 = sc.SizedPanel(self, -1)
#         col2.SetSizerType("horizontal")
#         col2.SetSizerProps(expand=True)
#         
#         lf = wx.SpinCtrlDouble(col2, -1, value=str(value), inc=precision,
#                           min=minmax[0], max=minmax[1], size=fieldSize)
#         u = wx.StaticText(col2, -1, units)
#         u.SetSizerProps(valign="center")
#         
#         self.controls[c] = [lf, u]
#         if col1 != self:
#             self.controls[c].append(pad)
#         
#         if fieldSize == (-1,-1):
#             self.fieldSize = lf.GetSize()
#         
#         if name is not None:
#             self.fieldMap[name] = c
#         
#         if digits is not None:
#             lf.SetDigits(digits)
#         
#         self.setFieldToolTip(c, tooltip)
# 
#         return c

    def addFloatField(self, parent, label, units=None, checked=False, 
                    value=0,  precision=0.001, minmax=None, check=True, 
                    tooltip=None, name=None):
        """ Add an integer 'spin' field, with or without a checkbox.
        
            @param parent: The parent `SizedPanel`.
            @param label: The text displayed.
            @keyword units: The name of the units, if any, displayed to the
                right of the field.
            @keyword checked: The checkbox's initial state.
            @keyword value: The initially displayed value.
            @keyword minmax: The allowed range of values.
            @keyword check: If `False`, the field has only a label, not
                a checkbox.
            @keyword tooltip: A string to display as the control's tool tip.
            @return: The checkbox control (or label if `check` is `False`). 
                The associated widgets (the field, and units label if any)
                are referenced by attributes added to the control.
        """
        if name:
            value = self.getPref(name, value)
            
        if check:
            cb = wx.CheckBox(parent, -1, label, name=name or label)
            cb.SetValue(checked)
        else:
            cb = wx.StaticText(parent, -1, label, name=name or label)
            checked = False
        cb.SetSizerProps(valign='center')
        if tooltip is not None:
            cb.SetToolTip(tooltip)
        
        if units is not None:
            parent = SC.SizedPanel(parent, -1)
            parent.SetSizerType("horizontal")
            
        field = cb._field = wx.SpinCtrlDouble(parent, -1, value=str(value), inc=precision)
        if minmax is not None:
            field.SetRange(*minmax)
            
        field.Enable(checked)
        if tooltip is not None:
            field.SetToolTip(tooltip)
        if units is not None:
            units = cb._units = wx.StaticText(parent, -1, units)
            units.SetSizerProps(valign="center")
            units.Enable(checked)
            if tooltip is not None:
                units.SetToolTip(tooltip)
                
        return cb


    def addCheck(self, parent, label, checked=False, indent=False, name=None,
                 tooltip=None):
        """ Add a checkbox without a field. 
        
            @param parent: The parent `SizedPanel`.
            @param label: The text displayed.
            @keyword checked: The checkbox's initial state.
            @keyword indent: If `True` or `False`, the checkbox will appear in 
                either the right or left column of a 'form' SizedPanel. Use
                `None` if the parent does not use the 'form' layout.
            @keyword tooltip: A string to display as the control's tool tip. 
        """
        if name:
            checked = self.getPref(name, checked)
            
        if indent is True:
            SC.SizedPanel(parent, -1)
        cb = wx.CheckBox(parent, -1, label, name=name or label)
        cb.SetSizerProps(valign='center')
        cb.SetValue(checked)
        if tooltip is not None:
            cb.SetToolTip(tooltip)
        if indent is False:
            SC.SizedPanel(parent, -1)
        return cb
        

    def addChoiceField(self, parent, label, choices=[], units=None, 
                       default=wx.NOT_FOUND, check=False, checked=True, 
                       tooltip=None, name=None):
        """ Add a drop down list field, with or without a checkbox.
        
            @param parent: The parent `SizedPanel`.
            @param label: The text displayed.
            @keyword units: The name of the units, if any, displayed to the
                right of the field.
            @keyword checked: The checkbox's initial state.
            @keyword default: The initially displayed value.
            @keyword check: If `False`, the field has only a label, not
                a checkbox.
            @keyword tooltip: A string to display as the control's tool tip.
            @return: The checkbox control (or label if `check` is `False`). 
                The associated widgets (the field, and units label if any)
                are referenced by attributes added to the control.
        """
        if name:
            default = self.getPref(name, default)
            
        enabled = not check or checked
        if check:
            cb = wx.CheckBox(parent, -1, label, name=name or label)
            cb.SetValue(checked)
        else:
            cb = wx.StaticText(parent, -1, label, name=name or label)
            checked = False
        cb.SetSizerProps(valign='center')
        
        if units is not None:
            parent = SC.SizedPanel(parent, -1)
            parent.SetSizerType("horizontal")
            
        field = cb._field = wx.Choice(parent, -1, choices=choices)
        field.SetSelection(default)
        field.Enable(enabled)

        if tooltip is not None:
            cb.SetToolTip(tooltip)
            field.SetToolTip(tooltip)
        
        if units is not None:
            units = cb._units = wx.StaticText(parent, -1, units)
            units.SetSizerProps(valign="center")
            units.Enable(enabled)
            if tooltip is not None:
                units.SetToolTip(tooltip)
        
        return cb


    def getValue(self, control, default=False):
        """ Get the value for a control. If the control is a checkbox that is
            not checked, `False` is returned. If the control has an associated
            field, the field's value is returned. 
        """
        if isinstance(control, wx.CheckBox):
            if not control.IsChecked():
                return default

        try:
            if not hasattr(control, '_field'):
                return control.GetValue()
            elif isinstance(control._field, wx.Choice):
                return control._field.GetSelection()
            else:
                return control._field.GetValue()
        except None:#AttributeError:
            return None


    def setValue(self, control, val, check=True):
        """ 
        """
        if val is None:
            self.setCheck(control, False)
            return val
        if hasattr(control, '_field'):
            if isinstance(control._field, wx.Choice):
                control._field.SetSelection(val)
            else:
                control._field.SetValue(val)
        if check:
            self.setCheck(control)
        return val


    def setCheck(self, obj, checked=True):
        """ Set a checkbox and enable/disable any associated fields.
        """
        if not isinstance(obj, wx.CheckBox):
            return False
        obj.SetValue(checked)
        self.enableField(obj, checked)
        return checked

    
    def enableField(self, obj, enabled=True):
        """ 
        """
        obj.Enable(enabled)
        if hasattr(obj, '_field'):
            obj._field.Enable(enabled)
        if hasattr(obj, '_units'):
            obj._units.Enable(enabled)

    
    def getPref(self, k, default=None):
        return self.app.getPref(k, default=default, section=self.prefSection)
    
    
    def setPref(self, k, v):
        return self.app.setPref(k, v, section=self.prefSection)


    def deletePref(self, name):
        return self.app.deletePref(name, section=self.prefSection)


    def __init__(self, *args, **kwargs):
        style = wx.DEFAULT_DIALOG_STYLE \
            | wx.RESIZE_BORDER \
            | wx.MAXIMIZE_BOX \
            | wx.MINIMIZE_BOX \
            | wx.DIALOG_EX_CONTEXTHELP \
            | wx.SYSTEM_MENU
        
        kwargs.setdefault('style', style)
        super(ToolDialog, self).__init__(*args, **kwargs)
        if self.TITLE and not self.GetTitle():
            self.SetTitle(self.TITLE)
        self.app = wx.GetApp()
        self.prefSection = "tools.%s" % self.__class__.__name__

        self.Bind(wx.EVT_CHECKBOX, self.OnCheck)


    def addBottomButtons(self):
        """
        """
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okBtn = self.FindWindowById(wx.ID_OK)
        self.cancelBtn = self.FindWindowById(wx.ID_CANCEL)

        # Kind of a hack, but the OK/Cancel labels are confusing.
        self.okBtn.SetLabel("Run")
        self.cancelBtn.SetLabel("Close")
        
        self.okBtn.Bind(wx.EVT_BUTTON, self.run)


    def OnCheck(self, evt):
        obj = evt.EventObject
        checked = obj.IsChecked()
        if hasattr(obj, '_field'):
            obj._field.Enable(checked)
        if hasattr(obj, '_units'):
            obj._units.Enable(checked)
    
