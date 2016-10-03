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
            cb.SetToolTipString(tooltip)
        
        if units is not None:
            parent = SC.SizedPanel(parent, -1)
            parent.SetSizerType("horizontal")
        field = cb._field = wx.SpinCtrl(parent, -1, str(value))
        if minmax is not None:
            field.SetRange(*minmax)
        field.Enable(checked)
        if tooltip is not None:
            field.SetToolTipString(tooltip)
        if units is not None:
            units = cb._units = wx.StaticText(parent, -1, units)
            units.SetSizerProps(valign="center")
            units.Enable(checked)
            if tooltip is not None:
                units.SetToolTipString(tooltip)
                
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
        cb = wx.CheckBox(parent, -1, label)
        cb.SetSizerProps(valign='center')
        cb.SetValue(checked)
        if tooltip is not None:
            cb.SetToolTipString(tooltip)
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
            cb.SetToolTipString(tooltip)
            field.SetToolTipString(tooltip)
        
        if units is not None:
            units = cb._units = wx.StaticText(parent, -1, units)
            units.SetSizerProps(valign="center")
            units.Enable(enabled)
            if tooltip is not None:
                units.SetToolTipString(tooltip)
        
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


    def OnCheck(self, evt):
        obj = evt.EventObject
        checked = obj.IsChecked()
        if hasattr(obj, '_field'):
            obj._field.Enable(checked)
        if hasattr(obj, '_units'):
            obj._units.Enable(checked)
    
