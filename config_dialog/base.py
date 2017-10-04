'''
New, modular configuration system. Dynamically creates the UI based on the new 
"UI Hints" data. The UI is described in EBML; UI widget classes have the same
names as the elements. The crucial details of the widget type are also encoded
into the EBML ID; if there is not a specialized subclass for a particular 
element, this is used to find a generic widget for the data type. 

Basic theory of operation: 

* Configuration items with values of `None` do not get written to the config 
    file. 
* Fields with checkboxes have a value of `None` if unchecked. 
* Disabled fields also have a value of `None`. 
* Children of disabled fields have a value of `None`, as do children of fields 
    with checkboxes (i.e. `CheckGroup`) if their parent is unchecked. 
* The default value for a field is in the native units/data type as in the 
    config file. Setting a field to the default uses the same mechanism as 
    setting it according to the config file.
* Fields with values that aren't in the config file get the default; if they
    have checkboxes, the checkbox is left unchecked.

@todo: Clean up (maybe replace) the old calibration and info tabs.
@todo: Implement configuration import/export (refactor in `devices` module).
@todo: There are some redundant calls to update enabled and checkbox states.
    They don't cause a problem, but they should be cleaned up.
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

#===============================================================================
# 
#===============================================================================

import logging
logger = logging.getLogger('SlamStickLab.ConfigUI')
logger.setLevel(logging.INFO)
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")

#===============================================================================
# 
#===============================================================================

import errno
from fnmatch import fnmatch
import os.path
import string
import time

# XXX: For testing.
import sys
sys.path.insert(0, '..')

import wx
import wx.lib.filebrowsebutton as FB
import wx.lib.scrolledpanel as SP
import wx.lib.sized_controls as SC

from widgets.shared import DateTimeCtrl
from common import makeWxDateTime, makeBackup, restoreBackup

import legacy
from mide_ebml.ebmlite import loadSchema

import devices

# Temporary?
from special_tabs import CalibrationPanel, EditableCalibrationPanel, SSXInfoPanel
import classic

#===============================================================================
# 
#===============================================================================

SCHEMA = loadSchema('config_ui.xml')

#===============================================================================
#--- Utility functions
#===============================================================================

# Dictionaries of all known field and tab types. The `@registerField` and 
# `@registerTab` decorators add classes to them, respectively. See 
# `registerField()` and `registerTab()` functions, below.
FIELD_TYPES = {}
TAB_TYPES = {}

def registerField(cls):
    """ Class decorator for registering configuration field types. Class names
        should match the element names in the ``CONFIG.UI`` EBML.
    """
    global FIELD_TYPES
    FIELD_TYPES[cls.__name__] = cls
    return cls


def registerTab(cls):
    """ Class decorator for registering configuration tab types. Class names
        should match the element names in the ``CONFIG.UI`` EBML.
    """
    global TAB_TYPES
    TAB_TYPES[cls.__name__] = cls
    return cls


#===============================================================================
# 
#===============================================================================

def getClipboardText():
    """ Retrieve text from the clipboard.
    """
    if not wx.TheClipboard.IsOpened(): 
        wx.TheClipboard.Open()
    
    obj = wx.TextDataObject()
    if (wx.TheClipboard.GetData(obj)):
        return obj.GetText()
    
    return ""


#===============================================================================
# 
#===============================================================================

class TextValidator(wx.PyValidator):
    """ Validator for TextField and ASCIIField text widgets.
    """
    
    VALID_KEYS = (wx.WXK_LEFT, wx.WXK_UP, wx.WXK_RIGHT, wx.WXK_DOWN,
                  wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN,
                  wx.WXK_INSERT, wx.WXK_DELETE)
    
    def __init__(self, validator=None, maxLen=None):
        """ Instantiate a text field validator.
        
            @keyword validChars: A string of chars 
        """
        self.maxLen = maxLen
        self.isValid = validator 
        wx.PyValidator.__init__(self)
        self.Bind(wx.EVT_CHAR, self.OnChar)
        self.Bind(wx.EVT_TEXT_PASTE, self.OnPaste)
        

    def Clone(self):
        return TextValidator(self.isValid, self.maxLen)
    
    
    def TransferToWindow(self):
        """ Required in wx.PyValidator subclasses. """
        return True
    
    
    def TransferFromWindow(self):
        """ Required in wx.PyValidator subclasses. """
        return True
    
    
    def Validate(self, win):
        txt = self.GetWindow().GetValue()
        return self.isValid(txt)


    def OnChar(self, evt):
        """ Validate a character that has been typed.
        """
        key = evt.GetKeyCode()

        if key < wx.WXK_SPACE or key in self.VALID_KEYS:
            evt.Skip()
            return
        
        val = self.GetWindow().GetValue()

        if self.isValid(unichr(key)) and len(val) < self.maxLen:
            evt.Skip()
            return

        if not wx.Validator_IsSilent():
            wx.Bell()

        return
    
    
    def OnPaste(self, evt):
        """ Validate text pasted into the field.
        """
        txt = getClipboardText()
        current = self.GetWindow().GetValue()
        if self.isValid(current + txt):
            evt.Skip()
        elif not wx.Validator_IsSilent():
            wx.Bell()
    
    
#===============================================================================
# 
#===============================================================================

class DisplayContainer(object):
    """ A wrapper for the dialog's dictionary of configuration items, which
        dynamically gets the displayed values from the corresponding widget. It
        simplifies the field's ``DisplayFormat``, ``ValueFormat``, and 
        ``DisableIf`` expressions. Iterating over it is performed in the order
        of the keys (i.e. config IDs), low to high; dependencies can be avoided
        by giving dependent values higher config IDs than the fields they
        depend upon.
    """
    
    def __init__(self, root):
        self.root = root
    
    
    def get(self, k, default=None):
        if k in self.root.configItems:
            return self[k]
        return default


    def __getitem__(self, k):
        if k not in self.root.configItems:
            return None
        return self.root.configItems[k].getDisplayValue()


    def __contains__(self, k):
        return k in self.root.configItems

    
    def __iter__(self):
        return iter(self.keys())


    def iterkeys(self):
        return self.__iter__()
    
    
    def itervalues(self):
        for k in self.iterkeys():
            yield self[k]

    
    def iteritems(self):
        for k in self.iterkeys():
            yield (k, self[k])


    def keys(self):
        return sorted(self.root.configItems.keys())


    def values(self):
        return list(self.itervalues())

    
    def items(self):
        return list(self.iteritems())


    def toDict(self):
        """ Create a real dictionary of field values keyed by config IDs.
            Items with values of `None` are excluded.
        """
        return {k:v for k,v in self.iteritems() if v is not None}


class ConfigContainer(DisplayContainer):
    """ A wrapper for the dialog's dictionary of configuration items, which
        dynamically gets the converted configuration values (as written to the
        config file) from the corresponding widget. It simplifies saving the
        configuration data. Iterating over it is performed in the order of the
        keys (i.e. config IDs), low to high; dependencies can be avoided by
        giving dependent values higher config IDs than the fields they depend
        upon.
    """

    def __getitem__(self, k):
        return self.root.configItems[k].getConfigValue()


#===============================================================================
#--- Base classes
#===============================================================================

class ConfigBase(object):
    """ Base/mix-in class for configuration items. Handles parsing attributes
        from EBML. Doesn't do any of the GUI-specific widget work, as some 
        components don't correspond directly to a UI widget.
        
        @cvar ARGS: A dictionary mapping EBML element names to object attribute
            names. Wildcards are allowed in the element names.
        @cvar CLASS_ARGS: A dictionary mapping additional EBML element names
            to object attribute names. Subclasses can add their own unique
            attributes to this dictionary.
        @cvar DEFAULT_TYPE: The name of the EBML ``*Value`` element type used
            when writing this item's value to the config file. Used if the
            defining EBML element does not contain a ``*Value`` sub-element.
    """

    # Mapping of element names to object attributes. May contain glob-style
    # wildcards.
    ARGS = {"Label": "label",
            "ConfigID": "configId",
            "ToolTip": "tooltip",
            "Units": "units",
            "DisableIf": "disableIf",
            "DisplayFormat": "displayFormat",
            "ValueFormat": "valueFormat",
            "MaxLength": "maxLength",
            "*Min": "min",
            "*Max": "max",
            "*Value": "default",
            "*Gain": "gain",
            "*Offset": "offset"
    }

    
    # Class-specific element/attribute mapping. Subclasses can use this for
    # their unique attributes without clobbering the common ones in ARGS.
    CLASS_ARGS = {}
    
    # The name of the default *Value EBML element type used when writing this 
    # item's value to the config file. Used if the definition does not include
    # a *Value element.
    DEFAULT_TYPE = None
    
    # Default expression code objects for DisableIf, ValueFormat, DisplayFormat.
    # `noEffect` always returns the field's value unmodified (supplied as the
    # variable ``x``). `noValue` always returns `None`.
    noEffect = compile("x", "<ConfigBase.noEffect>", "eval")
    noValue = compile("None", "<ConfigBase.noValue>", "eval")
    
    
    def makeExpression(self, exp, name):
        """ Helper method for compiling an expression in a string into a code
            object that can later be used with `eval()`. Used internally.
        """
        if exp is None:
            # No expression defined: value is returned unmodified (it matches 
            # the config item's type)
            return self.noEffect
        elif exp is '':
            # Empty string expression: always returns `None` (e.g. the field is
            # used to calculate another config item, not a config item itself)
            return self.noValue
        elif not isinstance(exp, basestring):
            # Probably won't occur, but just in case...
            logger.debug("Bad value for %s: %r (%s)" % (name, exp, exp.__class__))
            return
        
        # Create a nicely formatted, informative string for the compiled 
        # expression's "filename" and for display if the expression is bad.
        idstr = ("(ID 0x%0X) " % self.configId) if self.configId else ""
        msg = "%r %s%s" % (self.label, idstr, name)
        
        try:
            return compile(exp, "<%s>" % msg, "eval")
        except SyntaxError as err:
            logger.error("Ignoring bad expression (%s) for %s %s: %r" % 
                         (err.msg, self.__class__.__name__, msg, err.text))
            return self.noValue


    def makeGainOffsetFormat(self):
        """ Helper method for generating `displayFormat` and `valueFormat`
            expressions using the field's `gain` and `offset`. Used internally.
        """
        # Create a nicely formatted, informative string for the compiled 
        # expression's "filename" and for display if the expression is bad.
        idstr = (" (ID 0x%0X)" % self.configId) if self.configId else ""
        msg = "%r%s" % (self.label, idstr)
        
        gain = 1.0 if self.gain is None else self.gain
        offset = 0.0 if self.offset is None else self.offset
        
        self.displayFormat = compile("(x+%.8f)*%.8f" % (offset, gain), 
                                     "%s displayFormat" % msg, "eval")
        self.valueFormat = compile("(x/%.8f)-%.8f" % (gain, offset), 
                                   "%s valueFormat" % msg, "eval")
        
    
    def setAttribDefault(self, att, val):
        """ Sets an attribute, if the attribute has not yet been set, similar to
            `dict.setdefault()`. Allows subclasses to set defaults that differ 
            from their superclass.
        """
        if not hasattr(self, att):
            setattr(self, att, val)
            return val
        return getattr(self, att)

    
    def __init__(self, element, root):
        """ Constructor. Instantiates a `ConfigBase` and parses parameters out
            of the supplied EBML element.
        
            @param element: The EBML element from which to build the object.
            @param root: The main dialog.
        """
        self.root = root
        self.element = element
        
        # Convert element children to object attributes.
        # First, set any previously undefined attributes to None.
        args = self.ARGS.copy()
        args.update(self.CLASS_ARGS)
        for v in args.values():
            self.setAttribDefault(v, None)
        
        self.valueType = self.DEFAULT_TYPE
        
        for el in self.element.value:
            if el.name in FIELD_TYPES:
                # Child field: skip now, handle later (if applicable)
                continue
            
            if el.name.endswith('Value'):
                # If the field has a '*Value' element, the field will use that
                # type when saving to the config file.
                self.valueType = el.__class__.name
                
            if el.name in args:
                # Known element name (verbatim): set attribute
                setattr(self, args[el.name], el.value)
            else:
                # Match wildcards and set attribute
                for k,v in args.items():
                    if fnmatch(el.name, k):
                        setattr(self, v, el.value)

        # Compile expressions for converting to/from raw and display values.
        if self.gain is None and self.offset is None:
            # No gain and/or offset: use displayFormat/valueFormat if defined.
            self.displayFormat = self.makeExpression(self.displayFormat, 'displayFormat')
            self.valueFormat = self.makeExpression(self.valueFormat, 'valueFormat')
        else:
            # Generate expressions using the field's gain and offset.
            self.makeGainOffsetFormat()
        
        if self.disableIf is not None:
            self.disableIf = self.makeExpression(self.disableIf, 'disableIf')
        
        if self.configId is not None and self.root is not None:
            self.root.configItems[self.configId] = self
        
        self.expressionVariables = self.root.expresionVariables.copy()


    def __repr__(self):
        """
        """
        name = self.__class__.__name__
        if not self.label:
            return "<%s at 0x%x>" % (name, id(self))
        return "<%s %r at 0x%x>" % (name, self.label, id(self))
        

    def isDisabled(self):
        """ Check the Field's `disableIf` expression (if any) to determine if
            the Field should be enabled.
        """
        if self.disableIf is None:
            return False
            
        return eval(self.disableIf, self.expressionVariables)
        
    
    def getDisplayValue(self):
        """ Get the object's displayed value. 
        """
        if self.isDisabled():
            return None
        try:
            return self.value
        except AttributeError:
            return self.default
    
    
    def getConfigValue(self):
        """ Get the widget's value, as written to the config file.
        """
        if self.configId is None:
            return
        try:
            val = self.getDisplayValue()
            if val is None:
                return None
            self.expressionVariables['x'] = val
            return eval(self.valueFormat, self.expressionVariables)
        except (KeyError, ValueError, TypeError):
            return None
    
    
    def setDisplayValue(self, val, **kwargs):
        """ Set the object's value, in the data type and units it displays
            (if applicable).
        """
        # This is overridden by ConfigWidget subclasses; they have no `value`.
        self.value = val


    def setConfigValue(self, val, **kwargs):
        """ Set the Field's value, using the data type native to the config
            file. 
        """
        self.expressionVariables['x'] = val
        val = eval(self.displayFormat, self.expressionVariables)
        self.setDisplayValue(val, **kwargs)


    def setToDefault(self, **kwargs):
        """ Set the configuration item to its default value.
        """
        self.setConfigValue(self.default, **kwargs)


class ConfigWidget(wx.Panel, ConfigBase):
    """ Base class for a configuration field.
    
        @cvar CHECK: Does this field have a checkbox?
        @cvar UNITS: Should this widget always leave space for the 'units'
            label, even when its EBML description doesn't contain a ``Label``?
        @cvar ARGS: A dictionary mapping EBML element names to object attribute
            names. Wildcards are allowed in the element names. Inherited from
            `ConfigBase`.
        @cvar CLASS_ARGS: A dictionary mapping additional EBML element names
            to object attribute names. Subclasses can add their own unique
            attributes to this dictionary. Inherited from `ConfigBase`.
        @cvar DEFAULT_TYPE: The name of the EBML ``*Value`` element type used
            when writing this item's value to the config file. Used if the
            defining EBML element does not contain a ``*Value`` sub-element.
            Inherited from `ConfigBase`.
    """
    
    # Does this widget subclass have a checkbox?
    CHECK = False
    
    # Should this widget subclass always leave space for 'units' label?
    UNITS = True

    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated. The element's name typically matches that of
                the class.
            @keyword root: The main dialog.
            @keyword group: The parent group containing the Field (if any).
        """
        element = kwargs.pop('element', None)
        root = kwargs.pop('root', None)
        self.group = kwargs.pop('group', None)
        
        ConfigBase.__init__(self, element, root)
        wx.Panel.__init__(self, *args, **kwargs)

        self.initUI()
    
    
    def __repr__(self):
        return ConfigBase.__repr__(self)
    
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
            Separated from `initUI()` for subclassing. This method should be 
            overridden in subclasses.
        """
        self.field = None
        p = wx.Panel(self, -1)
        self.sizer.Add(p, 3)
        return p

    
    def initUI(self):
        """ Build the user interface, adding the item label and/or checkbox,
            the appropriate UI control(s) and a 'units' label (if applicable). 
            Separated from `__init__()` for the sake of subclassing.
        """
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        if self.CHECK:
            self.checkbox = wx.CheckBox(self, -1, self.label or '')
            self.labelWidget = self.checkbox
            self.sizer.Add(self.checkbox, 2, wx.ALIGN_CENTER_VERTICAL)
        else:
            self.checkbox = None
            self.labelWidget = wx.StaticText(self, -1, self.label or '')
            self.sizer.Add(self.labelWidget, 2, wx.ALIGN_CENTER_VERTICAL)
        
        self.addField()
        
        if self.UNITS or self.units:
            self.unitLabel = wx.StaticText(self, -1, self.units or '')
            self.sizer.Add(self.unitLabel, 1, wx.WEST|wx.ALIGN_CENTER_VERTICAL, 
                           border=8)
        else:
            self.unitLabel = None

        if self.tooltip:
            self.SetToolTipString(self.tooltip)
            self.labelWidget.SetToolTipString(self.tooltip)
            if self.units:
                self.unitLabel.SetToolTipString(self.tooltip)
            if self.field is not None:
                self.field.SetToolTipString(self.tooltip)
        
        if self.checkbox is not None:
            self.Bind(wx.EVT_CHECKBOX, self.OnCheck)
            self.setCheck(False)
        
        self.SetSizer(self.sizer)
        
        self.setToDefault()
        
        if self.field is not None:
            self.field.Bind(wx.EVT_KILL_FOCUS, self.OnLoseFocus)


    def isDisabled(self):
        """ Check the Field's `disableIf` expression (if any) to determine if
            the Field should be enabled.
        """
        if self.group is not None:
            if self.group.checkbox is not None and not self.group.checkbox.GetValue():
                return True
            if self.group.isDisabled():
                return True
        
        return super(ConfigWidget, self).isDisabled()
    
    
    def enableChildren(self, enabled=True):
        """ Enable/Disable the Field's children.
        """
        if self.field is not None:
            self.field.Enable(enabled)
        if self.unitLabel is not None:
            self.unitLabel.Enable(enabled)


    def setCheck(self, checked=True):
        """ Set the Field's checkbox, if applicable.
        """
        if self.checkbox is not None:
            self.checkbox.SetValue(checked)
            self.enableChildren(checked)
            

    def setConfigValue(self, val, check=True):
        """ Set the Field's value, using the data type native to the config
            file. 
        """
        super(ConfigWidget, self).setConfigValue(val, check=check)
        try:
            if val is not None and self.group.checkbox is not None:
                self.group.setCheck(check)
        except AttributeError:
            pass
        
    
    def setDisplayValue(self, val, check=True):
        """ Set the Field's value, using the data type native to the widget. 
        """
        if val is not None:
            if self.field is not None:
                self.field.SetValue(val)
            else:
                check = bool(val)
        self.setCheck(check)
        

    def setToDefault(self, check=False):
        """ Reset the Field to its default value.
        """
        super(ConfigWidget, self).setToDefault()
        self.setCheck(check)


    def getDisplayValue(self):
        """ Get the field's displayed value. 
        """
        if self.isDisabled():
            return None
        elif self.checkbox is not None and not self.checkbox.GetValue():
            return None
        
        if self.field is not None:
            return self.field.GetValue()
        
        return self.default

    
    def updateDisabled(self):
        """ Automatically enable or disable this field according to its 
            `isDisabled` expression (if any).
        """
        enabled = not self.isDisabled()
        self.Enable(enabled)

    
    #===========================================================================
    # Event handlers
    #===========================================================================
        
    def OnCheck(self, evt):
        """ Handle checkbox changing.
        """
        self.root.updateDisabledItems()
        evt.Skip()


    def OnLoseFocus(self, evt):
        """ Handle focus leaving the field; update other, potentially dependent
            fields.
        """
        self.root.updateDisabledItems()
        evt.Skip()
        
        
#===============================================================================
#--- Non-check fields 
# Container fields excluded (see below).
# Note: BooleanField is technically non-check. 
#===============================================================================

@registerField
class BooleanField(ConfigWidget):
    """ UI widget for editing a Boolean value. This is a special case; although
        it is a checkbox, it is not considered a 'check' field
    """
    CHECK = True

    DEFAULT_TYPE = "BooleanValue"

    def setDisplayValue(self, val, check=False):
        """ Set the Field's value, using the data type native to the widget. 
        """
        self.checkbox.SetValue(bool(val))
    
    
    def getDisplayValue(self):
        """ Get the field's displayed value. 
        """
        if self.isDisabled():
            return None
        
        return int(self.checkbox.GetValue())


#===============================================================================

@registerField
class TextField(ConfigWidget):
    """ UI widget for editing Unicode text.
    """
    CLASS_ARGS = {'MaxLength': 'maxLength',
                  'TextLines': 'textLines'}

    UNITS = False

    DEFAULT_TYPE = "TextValue"
    
    # String of valid characters. 'None' means all are valid.
    VALID_CHARS = None

    def __init__(self, *args, **kwargs):
        self.setAttribDefault('default', '')
        self.setAttribDefault('textLines', 1)
        super(TextField, self).__init__(*args, **kwargs)

    
    def isValid(self, s):
        """ Filter for characters valid in the text field. """
        # All characters are permitted in UTF-8 fields.
        if self.maxLength is not None and len(s) > self.maxLength:
            return False
        if self.VALID_CHARS is None:
            return True
        return all(c in self.VALID_CHARS for c in s)


    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        validator = TextValidator(self.isValid, self.maxLength)
        if self.textLines > 1:
            self.field = wx.TextCtrl(self, -1, str(self.default or ''),
                                     style=wx.TE_MULTILINE|wx.TE_PROCESS_ENTER,
                                     validator=validator)
            # XXX: This is supposed to set multi-line field height, doesn't work
            s = self.field.GetSize()[1]
            self.field.SetSizeWH(-1, s * self.textLines)
        else:
            self.field = wx.TextCtrl(self, -1, str(self.default or ''),
                                     validator=validator)
            
        self.sizer.Add(self.field, 3, wx.EXPAND)
        return self.field
    
    
    def getDisplayValue(self):
        v = super(TextField, self).getDisplayValue()
        if not v:
            return None
        return v
    

#===============================================================================

@registerField
class ASCIIField(TextField):
    """ UI widget for editing ASCII text.
    """
    DEFAULT_TYPE = "ASCIIValue"    
    
    # String of valid characters, limited to the printable part of 7b ASCII.
    VALID_CHARS = string.printable


#===============================================================================

@registerField
class IntField(ConfigWidget):
    """ UI widget for editing a signed integer.
    """
    DEFAULT_TYPE = "IntValue"

    # Min/max integers supported by wxPython SpinCtrl
    MAX_SIGNED_INT = 2**31 - 1
    MIN_SIGNED_INT = -2**31
    
        
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated.
            @keyword root: The main dialog.
            @keyword group: The parent group containing the Field.
        """
        # Set some default values
        self.setAttribDefault('default', 0)
        super(IntField, self).__init__(*args, **kwargs)
    
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        # wxPython SpinCtrl values limited to 32b signed integer range
        self.min = int(max(self.min, self.MIN_SIGNED_INT))
        self.max = int(min(self.max, self.MAX_SIGNED_INT))
        self.default = max(min(self.default, self.max), self.min)
        
        self.field = wx.SpinCtrl(self, -1, size=(40,-1), 
                                 style=wx.SP_VERTICAL|wx.TE_RIGHT,
                                 min=self.min, max=self.max, 
                                 initial=self.default)
        self.sizer.Add(self.field, 2)
        return self.field

    
    def Enable(self, enabled=True):
        # Fields nested within groups look different when their parent is
        # disabled; disable explicitly to make it look right.
        if self.checkbox is not None:
            self.enableChildren(self.checkbox.GetValue())
        else:
            self.field.Enable(enabled)
        wx.Panel.Enable(self, enabled)


#===============================================================================

@registerField
class UIntField(IntField):
    """ UI widget for editing an unsigned integer.
    """
    DEFAULT_TYPE = "UIntValue"
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated.
            @keyword root: The main dialog.
            @keyword group: The parent group containing the Field.
        """
        self.setAttribDefault('min', 0)
        super(UIntField, self).__init__(*args, **kwargs)
        

#===============================================================================

@registerField
class FloatField(IntField):
    """ UI widget for editing a floating-point value.
    """
    DEFAULT_TYPE = "FloatValue"
    
    CLASS_ARGS = {'FloatIncrement': 'increment'}
        
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated.
            @keyword root: The main dialog.
            @keyword group: The parent group containing the Field.
        """
        self.setAttribDefault('increment', 0.25)
        self.setAttribDefault("floatDigits", 2)
        super(FloatField, self).__init__(*args, **kwargs)

        
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = wx.SpinCtrlDouble(self, -1, 
                                       inc=self.increment,
                                       min=self.min, max=self.max, 
                                       value=str(self.default))
        self.field.SetDigits(self.floatDigits)
        self.sizer.Add(self.field)
        return self.field


#===============================================================================

@registerField
class EnumField(ConfigWidget):
    """ UI widget for selecting one of several items from a list.
    """
    DEFAULT_TYPE = "UIntValue"
    
    UNITS = False

    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated. The element's name typically matches that of
                the class.
            @keyword root: The main dialog.
            @keyword group: The parent group containing the Field (if any).
        """
        
        self.setAttribDefault('default', 0) 
        super(EnumField, self).__init__(*args, **kwargs)

    
    def initUI(self):
        optionEls = [el for el in self.element.value if el.name=="EnumOption"]
        self.options = [EnumOption(el, self, n) for n,el in enumerate(optionEls)]
        super(EnumField, self).initUI()

    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        choices = [u"%s" % o.label for o in self.options]
        
        self.field = wx.Choice(self, -1, choices=choices)
        self.sizer.Add(self.field, 3)
        
        self.Bind(wx.EVT_CHOICE, self.OnChoice)
        return self.field


    def updateToolTips(self):
        """ Update the tool tips on the option list to show the text for the
            selected item (if any). Options without tool tips default to that
            of their parent.
        """
        tt = self.tooltip or ''
        index = self.field.GetSelection()
        if index != wx.NOT_FOUND and index < len(self.options):
            tt = self.options[index].tooltip or tt
            
        self.field.SetToolTipString(tt)


    def OnChoice(self, evt):
        """ Handle option selected.
        """
        self.updateToolTips()
        self.root.updateDisabledItems()
        evt.Skip()
        

    def setDisplayValue(self, val, check=True):
        """ Select the appropriate item in the drop-down list.
        """
        index = wx.NOT_FOUND
        for i,o in enumerate(self.options):
            if o.value == val:
                index = i
                break
        self.field.Select(index)
        self.setCheck(check)
        self.updateToolTips()
    

    def getDisplayValue(self):
        """ Get the field's displayed value. 
        """
        if self.isDisabled():
            return None
        elif self.checkbox is not None and not self.checkbox.GetValue():
            return None
        
        index = self.field.GetSelection()
        if index != wx.NOT_FOUND and index < len(self.options):
            return self.options[index].getDisplayValue()
        return self.default


    def Enable(self, enabled=True):
        # XXX: I'm not sure why I have to do this explicitly now, and just
        # for EnumField. 
        if self.checkbox is not None:
            self.enableChildren(self.checkbox.GetValue())
        elif self.field is not None:
            self.field.Enable(enabled)
        wx.Panel.Enable(self, enabled)


    
    
#===============================================================================
    
class EnumOption(ConfigBase):
    """ One choice in an enumeration (e.g. an item in a drop-down list). Note:
        unlike the other classes, this is not itself a UI field.
    """
    DEFAULT_TYPE = "UIntValue"
    
    def __init__(self, element, parent, index, **kwargs):
        """ Constructor.
            @keyword element: The EBML element for which the enumeration option
                is being generated.
            @param parent: The parent `EnumField`. 
        """
        super(EnumOption, self).__init__(element, parent.root, **kwargs)
        self.parent = parent

        if self.default is None:
            self.value = index
        else:
            self.value = self.default
        
        if self.label is None:
            self.label = u"%s" % self.value

    
#===============================================================================

@registerField
class BitField(EnumField):
    """ A widget representing a set of bits in an unsigned integer, with 
        individual checkboxes for each bit. A subclass of `EnumField`, each
        `EnumOption` creates a checkbox; its value indicates the index of the
        corresponding bit (0 is the first bit, 1 is the second, 2 is the third,
        etc.). 
    """
    DEFAULT_TYPE = "UIntValue"

    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        if self.labelWidget is None:
            # No label or checkbox; add checks directly to main sizer.
            childSizer = self.sizer
        else:
            # the field has a label or a checkbox; indent child checkboxes.
            childSizer = wx.BoxSizer(wx.VERTICAL)
            self.sizer.Add(childSizer, 1, wx.WEST, 24)
        
        for o in self.options:
            o.checkbox = wx.CheckBox(self, -1, o.label)
            childSizer.Add(o.checkbox, 0, 
                           wx.ALIGN_LEFT|wx.EXPAND|wx.NORTH|wx.SOUTH, 4)
            
            tooltip = o.tooltip or self.tooltip
            if tooltip:
                o.checkbox.SetToolTipString(tooltip)
        
        self.field = None
        return childSizer
        

    def setDisplayValue(self, val, check=True):
        """ Check the items according to the bits of the supplied value. 
        """
        for o in self.options:
            o.checkbox.SetValue(bool(val & (1 << o.value)))
        self.setCheck(check)
    

    def initUI(self):
        """ Build the user interface, adding the item label and/or checkbox,
            the appropriate UI control(s) and a 'units' label (if applicable). 
            Separated from `__init__()` for the sake of subclassing.
        """
        optionEls = [el for el in self.element.value if el.name=="EnumOption"]
        self.options = [EnumOption(el, self, n) for n,el in enumerate(optionEls)]
        
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        if self.label:
            if self.CHECK:
                self.checkbox = wx.CheckBox(self, -1, self.label or '')
                self.labelWidget = self.checkbox
                self.sizer.Add(self.checkbox, 0, wx.ALIGN_CENTER_VERTICAL)
                self.Bind(wx.EVT_CHECKBOX, self.OnCheck)
                self.setCheck(False)
            else:
                self.checkbox = None
                self.labelWidget = wx.StaticText(self, -1, self.label or '')
                self.sizer.Add(self.labelWidget, 0, wx.ALIGN_CENTER_VERTICAL)
        
            self.labelWidget.SetFont(self.labelWidget.GetFont().Bold())
        else:
            self.checkbox = self.labelWidget = None

        self.addField() 
        self.unitLabel = None

        if self.tooltip:
            self.SetToolTipString(self.tooltip)
            if self.labelWidget is not None:
                self.labelWidget.SetToolTipString(self.tooltip)
        
        self.SetSizer(self.sizer)
        
        self.setToDefault()
        
        # Child checks should also fire the 'on check' handler.
        self.Bind(wx.EVT_CHECKBOX, self.OnCheck)


    def getDisplayValue(self):
        """ Get the field's displayed value. 
        """
        if self.isDisabled():
            return None
        elif self.checkbox is not None and not self.checkbox.GetValue():
            return None
        
        val = 0
        for o in self.options:
            if o.checkbox.GetValue():
                val = val | (1 << o.value)
        
        return val
    

#===============================================================================
    
@registerField
class DateTimeField(IntField):
    """ UI widget for editing a date/time value.
    """
    DEFAULT_TYPE = "IntValue"
    LABEL = False
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        h = int(1.6*self.labelWidget.GetSizeTuple()[1])
        self.field = DateTimeCtrl(self, -1, size=(-1,h))
        self.utcCheck = wx.CheckBox(self, -1, "UTC")
        self.sizer.Add(self.field, 3)
        self.sizer.Add(self.utcCheck, 0, wx.WEST|wx.ALIGN_CENTER_VERTICAL, 
                           border=8)
        
        self.utcCheck.SetValue(self.root.useUtc)
        self.utcCheck.Bind(wx.EVT_CHECKBOX, self.OnUtcCheck)
        return self.field

    
    def enableChildren(self, enabled=True):
        super(DateTimeField, self).enableChildren(enabled=enabled)
        self.utcCheck.Enable(enabled)
    
    
    def setDisplayValue(self, val, check=True):
        """ Set the Field's value, in epoch seconds UTC.
        """
        if not val:
            val = wx.DateTimeFromTimeT(time.time())
        else:
            val = makeWxDateTime(val)
        
        if not self.utcCheck.GetValue():
            val = val.FromUTC()
        
        super(DateTimeField, self).setDisplayValue(val, check)
    
    
    def getDisplayValue(self):
        """ Get the field's displayed value (epoch seconds UTC). 
        """
        val = super(DateTimeField, self).getDisplayValue()
        if val is None:
            return None
        if not self.utcCheck.GetValue():
            val = val.ToUTC()
        return val.GetTicks()
    
    
    def OnUtcCheck(self, evt):
        # NOTE: This changes the main dialog's useUtc attribute, but it will
        # not update other DateTimeFields. Will need revision if/when we use
        # more than one.
        self.root.useUtc = evt.Checked()
        evt.Skip()


#===============================================================================

@registerField
class UTCOffsetField(FloatField):
    """ Special-case UI widget for entering the local UTC offset, with the
        ability to get the value from the computer.
    """
    DEFAULT_TYPE = "IntValue"

    def __init__(self, *args, **kwargs):
        self.setAttribDefault('min', -23.0)
        self.setAttribDefault('max', 23.0)
        self.setAttribDefault('units', "Hours")
        self.setAttribDefault('increment', 0.5)
        self.setAttribDefault('displayFormat', "x/3600.0")
        self.setAttribDefault('valueFormat', "x*3600")
        self.setAttribDefault("label", "Local UTC Offset")
        super(UTCOffsetField, self).__init__(*args, **kwargs)
        

    def initUI(self):
        """ Build the user interface, adding the item label and/or checkbox,
            the appropriate UI control(s) and a 'units' label (if applicable). 
            The UTC Offset fields have an extra button to the right of the
            units label.
        """
        super(UTCOffsetField, self).initUI()

        self.getOffsetBtn = wx.Button(self, -1, "Get Local Offset")
        self.getOffsetBtn.SetSizeWH(-1, self.field.GetSizeTuple()[1])
        self.getOffsetBtn.Bind(wx.EVT_BUTTON, self.OnSetTZ)
        self.sizer.Add(self.getOffsetBtn, 0)

        if self.tooltip:
            self.getOffsetBtn.SetToolTipString(self.tooltip)

    
    def OnSetTZ(self, event):
        """ Handle the 'Get Local Offset' button press by getting the local
            time zone offset.
        """
#         val = int(-time.timezone / 60 / 60) + time.daylight
        # `time.timezone` and `time.daylight` not reliable under Windows.
        gt = time.gmtime()
        lt = time.localtime()
        val = (time.mktime(lt) - time.mktime(gt)) / 60.0 / 60.0
        self.setDisplayValue(val)


#===============================================================================

@registerField
class BinaryField(ConfigWidget):
    """ Special-case UI widget for selecting binary data.
        FOR FUTURE IMPLEMENTATION.
    """
    DEFAULT_TYPE = "BinaryValue"
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = FB.FileBrowseButton(self, -1)
        self.sizer.Add(self.field, 3)
        return self.field


#===============================================================================
#--- Check fields 
# Container fields excluded (see below).
#===============================================================================

@registerField
class CheckTextField(TextField):
    """ UI widget (with a checkbox) for editing Unicode text.
    """
    CHECK = True


@registerField
class CheckASCIIField(ASCIIField):
    """ UI widget (with a checkbox) for editing ASCII text.
    """
    CHECK = True
    

@registerField
class CheckIntField(IntField):
    """ UI widget (with a checkbox) for editing a signed integer.
    """
    CHECK = True


@registerField
class CheckUIntField(UIntField):
    """ UI widget (with a checkbox) for editing an unsigned integer.
    """
    CHECK = True


@registerField
class CheckFloatField(FloatField):
    """ UI widget (with a checkbox) for editing a floating-point value.
    """
    CHECK = True


@registerField
class CheckEnumField(EnumField):
    """ UI widget (with a checkbox) for selecting one of several items from a 
        list.
    """
    CHECK = True


@registerField
class CheckBitField(BitField):
    """ A widget (with a checkbox) representing a set of bits in an unsigned 
        integer, with individual checkboxes for each bit. A subclass of 
        `EnumField`, each `EnumOption` creates a checkbox; its value indicates
        the index of the corresponding bit (0 is the first bit, 1 is the 
        second, 2 is the third, etc.). 
    """
    CHECK = True


@registerField
class CheckDateTimeField(DateTimeField):
    """ UI widget (with a checkbox) for editing a date/time value.
    """
    CHECK = True


@registerField
class CheckUTCOffsetField(UTCOffsetField):
    """ Special-case UI widget (with a checkbox) for entering the local UTC 
        offset, with the ability to get the value from the computer.
    """
    CHECK = True


@registerField
class CheckBinaryField(BinaryField):
    """ Special-case UI widget (with a checkbox) for selecting binary data.
        FOR FUTURE IMPLEMENTATION.
    """
    CHECK = True
 

#===============================================================================
#--- Type-specific fields/widgets
# These few are mostly proof-of-concept and don't provide additional features. 
# Future ones may offer special handling (selectable units, etc).
#===============================================================================

@registerField
class FloatTemperatureField(FloatField):
    """ `FloatField` variant with appropriate defaults for temperature display.
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault("units", u"\u00b0C")
        self.setAttribDefault("label", "Temperature")
        self.setAttribDefault("min", -40.0)
        self.setAttribDefault("max", 80.0)
        super(FloatTemperatureField, self).__init__(*args, **kwargs)


@registerField
class CheckFloatTemperatureField(FloatTemperatureField):
    """ `CheckFloatField` variant with appropriate defaults for temperature 
        display.
    """
    CHECK = True
        

@registerField
class FloatAccelerationField(FloatField):
    """ `FloatField` variant with appropriate defaults for acceleration display.
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault("units", u"g")
        self.setAttribDefault("label", "Acceleration")
        self.setAttribDefault("min", -100.0)
        self.setAttribDefault("max", 100.0)
        self.setAttribDefault("default", 5.0)
        super(FloatAccelerationField, self).__init__(*args, **kwargs)
    

@registerField
class CheckFloatAccelerationField(FloatAccelerationField):
    """ `CheckFloatField` variant with appropriate defaults for acceleration 
        display.
    """
    CHECK = True
    

#===============================================================================
#--- Special-case fields/widgets
#===============================================================================

@registerField
class CheckDriftButton(ConfigWidget):
    """ Special-case "field" consisting of a button that checks the recorder's
        clock versus the host computer's time. It does not affect the config
        data.
    """
    UNITS = False
    DEFAULT_TYPE = None

    def __init__(self, *args, **kwargs):
        self.setAttribDefault("label", "Check Clock Drift")
        self.setAttribDefault("tooltip", "Read the recorder's clock and "
                                         "compare to the current system time.")
        super(CheckDriftButton, self).__init__(*args, **kwargs)
        

    def initUI(self):
        """ Build the user interface, adding the item label and/or checkbox,
            the appropriate UI control(s) and a 'units' label (if applicable). 
            Separated from `__init__()` for the sake of subclassing.
        """
        self.checkbox = None
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.field = wx.Button(self, -1, self.label)
        self.sizer.Add(self.field, 0)

        if self.tooltip:
            self.SetToolTipString(self.tooltip)
            self.field.SetToolTipString(self.tooltip)
        
        self.SetSizer(self.sizer)

        self.Bind(wx.EVT_BUTTON, self.OnButtonPress)


    def OnButtonPress(self, evt):
        """ Handle button press: perform the clock drift test.
        """
        self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
        try:
            times = self.root.device.getTime()
        except Exception:
            if __DEBUG__:
                raise
            wx.MessageBox("Could not read the recorder's clock!", self.label,
                          parent=self, style=wx.OK|wx.ICON_ERROR)
            return
        
        drift = times[0] - times[1]
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        wx.MessageBox("Clock drift: %.4f seconds" % drift, self.label,
                      parent=self, style=wx.OK|wx.ICON_INFORMATION)


@registerField
class VerticalPadding(ConfigWidget):
    """ Special-case "field" that simply provides resizeable vertical padding, 
        so the  fields following it appear at the bottom of the dialog. Note
        that this is handled as a special case by `Group.addChild()`.
    """

    def initUI(self):
        self.checkbox = self.field = None


@registerField
class ResetButton(CheckDriftButton):
    """ Special-case "field" that consists of a button that resets all its
        sibling fields in its group or tab.
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault("label", "Reset to Defaults")
        self.setAttribDefault("tooltip", "Reset this set of fields to their "
                                         "default values")
        super(ResetButton, self).__init__(*args, **kwargs)
    
    
    def OnButtonPress(self, evt):
        """ Handle button press: reset sibling fields to the factory defaults.
        """
        if self.group is not None:
            self.group.setToDefault()


#===============================================================================
#--- Container fields 
#===============================================================================

@registerField
class Group(ConfigWidget):
    """ A labeled group of configuration items. Children appear indented.
    """
    # Should this group get a heading label?
    LABEL = True
    
    # Default types for Fields in the EBML schema with no specialized 
    # subclasses. The low byte of a Field's EBML ID denotes its type.
    # Note: The Field must appear in the EBML schema, so it will be identified
    # as a CONTAINER ('master') type.
    DEFAULT_FIELDS = {
        0x00: BooleanField,
        0x01: UIntField,
        0x02: IntField,
        0x03: FloatField,
        0x04: ASCIIField,
        0x05: TextField,
        0x06: BinaryField,
        0x07: EnumField,
        
        0x10: BooleanField,
        0x11: CheckUIntField,
        0x12: CheckIntField,
        0x13: CheckFloatField,
        0x14: CheckASCIIField,
        0x15: CheckTextField,
        0x16: CheckBinaryField,
        0x17: CheckEnumField,

        0x22: DateTimeField,
        0x32: CheckDateTimeField
    }
    
    DEFAULT_TYPE = None
    
    
    @classmethod
    def getWidgetClass(cls, el):
        """ Get the appropriate class for an EBML *Field element. Elements
            without a specialized subclass will get a generic widget for their
            basic data type.
            
            Note: does not handle IDs not present in the schema!
        """
        if el.name in FIELD_TYPES:
            return FIELD_TYPES[el.name]
        
        if el.id & 0xFF00 == 0x4000:
            # All field EBML IDs have 0x40 as their 2nd byte. Bits 0-3 denote
            # the 'base' type; bit 4 denotes if the field has a checkbox.
            baseId = el.id & 0x001F
            if baseId in cls.DEFAULT_FIELDS:
                return cls.DEFAULT_FIELDS[baseId]
            else:
                raise NameError("Unknown field type: %s" % el.name)
        
        return None
    
    
    def addChild(self, el, flags=wx.ALIGN_LEFT|wx.EXPAND|wx.NORTH, border=4):
        """ Add a child field to the Group.
        """
        cls = self.getWidgetClass(el)
        if cls is None:
            return
        
        widget = cls(self, -1, element=el, root=self.root, group=self)
        self.fields.append(widget)
        
        # Special case: PaddingField is expandable. 
        if cls == VerticalPadding:
            self.sizer.Add(widget, 1, wx.EXPAND)
        else:
            self.sizer.Add(widget, 0, flags, border=border)

            
    def initUI(self):
        """ Build the user interface, adding the item label and/or checkbox
            (if applicable) and all the child Fields.
        """
        self.fields = []
        outerSizer = wx.BoxSizer(wx.VERTICAL)
        
        if self.LABEL and self.label is not None:
            if self.CHECK:
                self.checkbox = wx.CheckBox(self, -1, self.label or '')
                label = self.checkbox
                self.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.checkbox)
            else:
                self.checkbox = None
                label = wx.StaticText(self, -1, self.label or '')
        
            outerSizer.Add(label, 0, wx.NORTH, 4)
            label.SetFont(label.GetFont().Bold())
            
        else:
            self.checkbox = label = None

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        for el in self.element.value:
            self.addChild(el)
            
        outerSizer.Add(self.sizer, 1, wx.WEST|wx.EXPAND, 24)
        
        if self.checkbox is not None:
            self.setCheck(False)

        self.SetSizer(outerSizer)
        

    def enableChildren(self, enabled=True):
        """ Enable/Disable the Field's children.
        """
        for f in self.fields:
            if hasattr(f, 'Enable'):
                f.Enable(enabled)


    def setToDefault(self, check=False):
        """ Reset the Field to the default values. Calls `setToDefault()` 
            method of each of its children.
        """
        for f in self.fields:
            if hasattr(f, 'setToDefault'):
                if f.configId in (0x8ff7f, 0x9ff7f):
                    # Special case: don't reset name or notes text fields.
                    continue
                f.setToDefault(check)
        
        
    def getDisplayValue(self):
        """ Get the groups's value (if applicable). 
        """
        if self.isDisabled():
            return None
        elif self.checkbox is not None:
            return self.checkbox.GetValue() or None
        
        return None

        
@registerField
class CheckGroup(Group):
    """ A labeled group of configuration items with a checkbox to enable or 
        disable them all. Children appear indented.
    """
    CHECK = True


#===============================================================================

@registerTab
class Tab(SP.ScrolledPanel, Group):
    """ One tab of configuration items. All configuration dialogs contain at 
        least one. The Tab's label is used as the name shown on the tab. 
    """
    LABEL = False
    CHECK = False

    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.lib.scrolledpanel.ScrolledPanel`
            arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated. The element's name typically matches that of
                the class.
            @keyword root: The main dialog.
        """
        element = kwargs.pop('element', None)
        root = kwargs.pop('root', self)
        self.group = None
        
        # Explicitly call __init__ of base classes to avoid ConfigWidget stuff
        ConfigBase.__init__(self, element, root)
        SP.ScrolledPanel.__init__(self, *args, **kwargs)

        self.SetupScrolling()

        self.initUI()


    def initUI(self):
        """ Build the contents of the tab.
        """
        self.checkbox = None
        self.fields = []
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        for el in self.element.value:
            self.addChild(el, flags=wx.ALIGN_LEFT|wx.EXPAND|wx.ALL, border=4)
        self.SetSizer(self.sizer)


    def save(self):
        """ Perform any special operations related to saving the Tab's contents.
            Regular tabs don't have any special features; this is primarily for
            the special-case subclasses.
        """
        pass


#===============================================================================
#--- Special-case tabs 
#===============================================================================

@registerTab
class DeviceInfoTab(Tab):
    """ Special-case Tab for showing device info. The tab's default behavior
        shows the appropriate info for Slam Stick recorders, no child fields
        required.
        
        TODO: Refactor and clean up DeviceInfoTab, removing dependency on old 
            system.
    """
    
    def __init__(self, *args, **kwargs):
        self.setAttribDefault("label", "Recorder Info")
        super(DeviceInfoTab, self).__init__(*args, **kwargs)


    def initUI(self):
        dev = self.root.device
        info = dev.getInfo()

        info['CalibrationSerialNumber'] = dev.getCalSerial()
        info['CalibrationDate'] = dev.getCalDate()
        info['CalibrationExpirationDate'] = dev.getCalExpiration()
    
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.field = SSXInfoPanel(self, -1, 
                                  root=self.root,
                                  info=dev.getInfo())
        self.sizer.Add(self.field, 1, wx.EXPAND)
        self.SetSizer(self.sizer)


@registerTab
class FactoryCalibrationTab(DeviceInfoTab):
    """ Special-case Tab for showing recorder's factory-set calibration 
        polynomials. The tab's default behavior shows the appropriate info for 
        Slam Stick recorders, no child fields required.
        
        TODO: Refactor and clean up FactoryCalibrationTab, removing dependency 
            on old system.
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault('label', 'Factory Calibration')
        super(FactoryCalibrationTab, self).__init__(*args, **kwargs)


    def initUI(self):
        dev = self.root.device
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.field = CalibrationPanel(self, -1, 
                                      root=self.root,
                                      info=dev.getFactoryCalPolynomials(),
                                      calSerial=dev.getCalSerial(), 
                                      calDate=dev.getCalDate(), 
                                      calExpiry=dev.getCalExpiration())
        self.sizer.Add(self.field, 1, wx.EXPAND)
        self.SetSizer(self.sizer)


@registerTab
class UserCalibrationTab(FactoryCalibrationTab):
    """ Special-case Tab for showing recorder's user-defined calibration 
        polynomials. The tab's default behavior shows the appropriate info for 
        Slam Stick recorders, no child fields required.
        
        TODO: Refactor and clean up UserCalibrationTab, removing dependency on
            old system.
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault('label', 'User Calibration')
        super(UserCalibrationTab, self).__init__(*args, **kwargs)


    def initUI(self):
        dev = self.root.device
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.field = EditableCalibrationPanel(self, -1, 
                                      root=self.root,
                                      info=dev.getUserCalPolynomials(),
                                      factoryCal=dev.getFactoryCalPolynomials(),
                                      editable=True)
        self.sizer.Add(self.field, 1, wx.EXPAND)
        self.SetSizer(self.sizer)
    

    def save(self):
        """ Save the user calibration, if any. Called when main dialog saves
            prior to closing.
        """
        if self.field.info:
            self.root.device.writeUserCal(self.field.info)


#===============================================================================
# 
#===============================================================================

class ConfigDialog(SC.SizedDialog):
    """ Root window for recorder configuration.
    """
    
    # Used by the Info tab. Remove after refactoring the legacy tabs.
    ICON_INFO = 0
    ICON_WARN = 1
    ICON_ERROR = 2
    

    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `SizedDialog` arguments, plus:
        
            @keyword device: The recorder to configure (an instance of a 
                `devices.Recorder` subclass)
            @keyword setTime: If `True`, the 'Set device clock on exit' 
                checkbox will be checked by default.
            @keyword keepUnknownItems: If `True`, the new config file will 
                retain any items from the original that don't map to a UI field
                (e.g. parameters for hidden/future features).
            @keyword saveOnOk: If `False`, exiting the dialog with OK will not
                save to the recorder. Primarily for debugging.
        """
        self.setTime = kwargs.pop('setTime', True)
        self.device = kwargs.pop('device', None)
        self.keepUnknown = kwargs.pop('keepUnknownItems', False)
        self.saveOnOk = kwargs.pop('saveOnOk', True)
        self.useUtc = kwargs.pop('useUtc', True)
        
        try:
            devName = self.device.productName
            if self.device.path:
                devName += (" (%s)" % self.device.path) 
        except AttributeError:
            # Typically, this won't happen outside of testing.
            devName = "Recorder"
        
        # Having 'hints' argument is a temporary hack!
        self.hints = kwargs.pop('hints', None)
        if self.hints is None:
            self.loadConfigUI()
        
        kwargs.setdefault("title", "Configure %s" % devName)
        kwargs.setdefault("style", wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        super(ConfigDialog, self).__init__(*args, **kwargs)

        pane = self.GetContentsPane()
        self.notebook = wx.Notebook(pane, -1)
        self.notebook.SetSizerProps(expand=True, proportion=-1)
        
        self.configItems = {}
        self.configValues = ConfigContainer(self)
        self.displayValues = DisplayContainer(self)
        
        # Variables to be accessible by field expressions. Includes mapping
        # None to ``null``, making the expressions less specific to Python. 
        self.expresionVariables = {'Config': self.displayValues,
                                   'null': None}
        
        self.tabs = []
        self.useLegacyConfig = False
        
        self.buildUI()
        self.loadConfigData()

        # Restore the following if/when import and export are fixed.
#         self.setClockCheck = wx.CheckBox(pane, -1, "Set device clock on exit")
#         self.setClockCheck.SetSizerProps(expand=True, border=(['top', 'bottom'], 8))
        
        buttonpane = SC.SizedPanel(pane,-1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)#, border=(['top'], 8))

        # Restore the following if/when import and export are fixed.
#         self.importBtn = wx.Button(buttonpane, -1, "Import...")
#         self.exportBtn = wx.Button(buttonpane, -1, "Export...")

        # Remove the following if/when import and export are fixed.
        # This puts the 'set clock' checkbox in line with the OK/Cancel
        # buttons, where Import/Export used to be.
        self.setClockCheck = wx.CheckBox(buttonpane, -1, "Set device clock on exit")
        self.setClockCheck.SetSizerProps(expand=True, border=(['top', 'bottom'], 8))

        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        wx.Button(buttonpane, wx.ID_OK)
        wx.Button(buttonpane, wx.ID_CANCEL)
        buttonpane.SetSizerProps(halign='right')

        self.setClockCheck.SetValue(self.setTime)
        self.setClockCheck.Enable(hasattr(self.device, 'setTime'))
        
        self.SetAffirmativeId(wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnOK, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
        
        # Restore the following if/when import and export are fixed.
#         self.importBtn.Bind(wx.EVT_BUTTON, self.OnImportButton)
#         self.exportBtn.Bind(wx.EVT_BUTTON, self.OnExportButton)
        
        self.Fit()
        self.SetMinSize((500, 480))
        self.SetSize((570, 680))


    def buildUI(self):
        """ Construct and populate the UI based on the ConfigUI element.
        """
        for el in self.hints.roots[0]:
            if el.name in TAB_TYPES:
                tabType = TAB_TYPES[el.name]
                tab = tabType(self.notebook, -1, element=el, root=self)
                self.notebook.AddPage(tab, str(tab.label))
                self.tabs.append(tab)


    def loadConfigUI(self, defaults=None):
        """ Read the UI definition from the device. For recorders with old
            firmware that doesn't generate a UI description, an appropriate
            generic version is created.
        """
        self.hints = defaults
        
        filename = getattr(self.device, 'configUIFile', None)
        if filename is None or not os.path.exists(filename):
            # Load default ConfigUI for the device from static XML.
            self.hints = legacy.loadConfigUI(self.device)
        else:
            logger.info('Loading ConfigUI from %s' % filename)
            self.hints = SCHEMA.load(filename)
        

    def applyConfigData(self, data, reset=False):
        """ Apply a dictionary of configuration data. 
        
            @param data: The dictionary of config values, keyed by ConfigID.
            @keyword reset: If `True`, reset all the fields to their defaults
                before applying the configuration data.
        """
        if reset:
            for c in self.configItems.itervalues():
                c.setToDefault()

        for k,v in data.iteritems():
            try:
                self.configItems[k].setConfigValue(v)
            except (KeyError, AttributeError):
                pass
            
        self.updateDisabledItems()
                    

    def loadConfigData(self):
        """ Load config data from the recorder.
        """
        # Mostly for testing. Will probably be removed.
        if self.device is None:
            self.configData = self.origConfigData = {}
            return self.configData
        
        # First, try to get the new config ID/value data.
        self.configData = self.device.getConfigItems()
        if not self.configData:
            # Try to get the legacy config data.
            if self.device.getConfig():
                self.configData = legacy.loadConfigData(self.device)
                self.useLegacyConfig = True
            else:
                # No config data. Use version appropriate for FW version.
                self.useLegacyConfig = self.device.firmwareVersion < 13
                self.configData = {}
            
                
        self.origConfigData = self.configData.copy()
        
        self.applyConfigData(self.configData)
        return self.configData 
    
    
    def updateConfigData(self):
        """ Update the dictionary of configuration data.
        """
        self.configData = {}
        
        if self.keepUnknown:
            # Preserve items in the existing config data without a UI element
            # (configuration for hidden features, etc.)
            for k,v in self.origConfigData.items():
                if k not in self.configItems:
                    self.configData[k] = v
       
        self.configData.update(self.configValues.toDict())
        
        
    
    def saveConfigData(self, filename=None):
        """ Save edited config data to the recorder (or another file).
            
            @keyword filename: A file to which to save the configuration data,
                if not the device's specified `configFile`.
        """
        if self.device is None and filename is None:
            return
       
        self.updateConfigData()
        
        filename = filename or self.device.configFile 
        makeBackup(filename)

        try:
            if self.useLegacyConfig:
                return legacy.saveConfigData(self.configData, self.device)
            
            values = []
            for k,v in self.configData.items():
                elType = self.configItems[k]
                values.append({'ConfigID': k,
                               elType.valueType: v})
            
            data = {'RecorderConfigurationList': 
                        {'RecorderConfigurationItem': values}}
            
            schema = loadSchema('mide.xml')
            encoded = schema.encodes(data)
            
            with open(filename, 'wb') as f:
                f.write(encoded)
        
        except Exception:
            restoreBackup(filename)
            raise
    
    
    def configChanged(self):
        """ Check if the configuration data has been changed.
        """
        self.updateConfigData()
        
        oldKeys = sorted(self.origConfigData.keys())
        newKeys = sorted(self.configData.keys())
        
        if oldKeys != newKeys:
            return True

        # Chew through the dictionaries manually, to handle items that are the
        # same but have different data types (e.g. `True` and ``1``).
        for k in newKeys:
            if self.configData.get(k) != self.origConfigData.get(k):
                return True

        return False
        
    
    def updateDisabledItems(self):
        """ Enable or disable config items according to their `disableIf`
            expressions and/or their parent group/tab's check or enabled state.
        """
        for item in self.configItems.itervalues():
            item.updateDisabled()
            
    
    def OnImportButton(self, evt):
        """ Handle the "Import..." button.
         
            @todo: Refactor to support new config format (means modifying 
                things in the `devices` module).
        """ 
        dlg = wx.FileDialog(self, 
                            message="Choose an exported configuration file",
                            style=wx.OPEN|wx.CHANGE_DIR|wx.FILE_MUST_EXIST,
                            wildcard=("Exported config file (*.cfx)|*.cfx|"
                                      "All files (*.*)|*.*"))
        try:
            d = dlg.ShowModal()
            if d == wx.ID_OK:
                try:
                    filename = dlg.GetPath()
                    self.device.importConfig(filename)
                    for i in range(self.notebook.GetPageCount()):
                        self.notebook.GetPage(i).initUI()
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
                    else:
                        s = "an older" if cvers < dvers else "a newer"
                        md = wx.MessageBox(
                             "The selected file was exported from %s "
                             "version of %s.\nImporting it may cause "
                             "problems.\n\nImport anyway?" % (s, cname), 
                             "Configuration Version Mismatch", parent=self, 
                             style=wx.YES_NO|wx.NO_DEFAULT|wx.ICON_EXCLAMATION)
                        if md == wx.YES:
                            self.device.importConfig(filename, 
                                                     allowOlder=True, 
                                                     allowNewer=True)

        except ValueError:
            # TODO: More specific error message (wrong device type
            # vs. not a config file
            md = wx.MessageBox( 
                "The selected file does not appear to be a valid "
                "configuration file for this device.", 
                "Invalid Configuration", parent=self,
                style=wx.OK | wx.ICON_EXCLAMATION) 
            
        dlg.Destroy()

    
    def OnExportButton(self, evt):
        """ Handle the "Import..." button.
         
            @todo: Refactor to support new config format (means modifying 
                things in the `devices` module).
        """ 
        dlg = wx.FileDialog(self, message="Export Device Configuration", 
                            style=wx.SAVE|wx.OVERWRITE_PROMPT, 
                            wildcard=("Exported config file (*.cfx)|*.cfx|"
                                      "All files (*.*)|*.*"))
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.device.exportConfig(dlg.GetPath(), data=self.getData())
                    
            except Exception as err:
                # TODO: More specific error message
                logger.error('Could not export configuration (%s: %s)' % 
                             (err.__class__.__name__, err))
                wx.MessageBox( 
                    "The configuration data could not be exported to the "
                    "specified file.", "Config Export Failed", parent=self,
                    style=wx.OK | wx.ICON_EXCLAMATION)
                
        dlg.Destroy()    


    def OnOK(self, evt):
        """ Handle dialog OK, saving changes.
        """
        if not self.saveOnOk:
            self.updateConfigData()
            evt.Skip()
            return
        
        try:
            self.saveConfigData()
        except IOError as err:
            msg = ("An error occurred when trying to update the recorder's "
                   "configuration data.")
            if err.errno == errno.ENOENT:
                msg += "\nThe recorder appears to have been removed."
            wx.MessageBox(msg, "Configuration Error", 
                          wx.OK|wx.OK_DEFAULT| wx.ICON_ERROR,
                          parent=self)
            evt.Skip()
            return
        
        # Handle other exceptions here if need be.
        
        for tab in self.tabs:
            tab.save()
        
        if self.setClockCheck.IsEnabled() and self.setClockCheck.GetValue():
            logger.info("Setting clock...")
            try:
                self.device.setTime()
            except Exception as err:
                logger.error("Error setting clock: %r" % err)
                wx.MessageBox("The recorder's clock could not be set.", 
                              "Configure Device", parent=self,
                              style=wx.OK|wx.OK_DEFAULT|wx.ICON_WARNING)
                
        evt.Skip()


    def OnCancel(self, evt):
        """ Handle dialog cancel, prompting the user to save any changes.
        """
        if self.configChanged():
            q = wx.MessageBox("Save configuration changes before exiting?",
                              "Configure Device", parent=self,
                              style=wx.YES_NO|wx.CANCEL|wx.CANCEL_DEFAULT)
            if q == wx.CANCEL:
                return
            elif q == wx.YES:
                self.saveConfigData()
                evt.Skip()
                return
        
        # If cancelled, the returned configuration data is `None`
        self.configData = None
        evt.Skip()
        

#===============================================================================
# 
#===============================================================================

def configureRecorder(path, setTime=True, useUtc=True, parent=None,
                      keepUnknownItems=True, hints=None, saveOnOk=True, 
                      modal=True):
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
        @keyword parent: The parent window, or `None`.
        @keyword keepUnknownItems: If `True`, the new config file will retain 
            any items from the original that don't map to a UI field (e.g. 
            parameters for hidden/future features).
        @keyword saveOnOk: If `False`, exiting the dialog with OK will not save
            to the recorder. Primarily for debugging.
        @keyword modal: If `True`, the dialog will display modally. If `False`,
            the dialog will be non-modal, and the function will return the
            dialog itself. For debugging.
        @return: A tuple containing the data written to the recorder (a nested 
            dictionary), whether `setTime` was checked before save, and whether
            `useUTC` was checked before save. `None` is returned if the 
            configuration was cancelled.
    """
    if isinstance(path, devices.Recorder):
        dev = path
        path = dev.path
    else:
        dev = devices.getRecorder(path)
        
    if not dev and hints is None:
        raise ValueError("Path '%s' does not appear to be a recorder" % path)
    
    if isinstance(dev, devices.SlamStickClassic):
        return classic.configureRecorder(path, saveOnOk, setTime, useUtc, parent)

    # remove
    global dlg
    dlg = ConfigDialog(parent, hints=hints, device=dev, setTime=setTime,
                       useUtc=useUtc, keepUnknownItems=keepUnknownItems,
                       saveOnOk=saveOnOk)
    
    if modal:
        dlg.ShowModal()
    else:
        dlg.Show()
    
    result = dlg.configData
    setTime = dlg.setClockCheck.GetValue()
    
    if not modal:
        return dlg
    
    dlg.Destroy()
    
    if result is None:
        return None
    
    return result, setTime, useUtc, dev


#===============================================================================
# 
#===============================================================================

# XXX: Remove all this debugging stuff
__DEBUG__ = not True
dlg = None

if __name__ == "__main__":
    from mide_ebml.ebmlite import util
    
    # XXX: TEST CODE, loads the UI from a file (XML or EBML), specified as a 
    # command line argument. If no file is specified, the first recorder found 
    # is used.
#     sys.argv = ['',  'CONFIG.UI']
    if len(sys.argv) > 1:
        device = None
        if sys.argv[-1].endswith('.xml'):
            hints = util.loadXml(sys.argv[-1], SCHEMA)
        else:
            hints = SCHEMA.load(sys.argv[-1])
    else:
        hints = None
        from devices import getDevices
        device = getDevices()[0]
    
    app = wx.App()

    d = configureRecorder(device, hints=hints, modal=not __DEBUG__, 
                          useUtc=False, saveOnOk=True)
    
    if __DEBUG__:
        # Show the Python shell. NOTE: dialog is non-modal; closing the windows
        # won't stop the app.
        print "Dialog shown non-modally; result will not be printed."
        import wx.py.shell
        con = wx.py.shell.ShellFrame()
        con.Show()
        app.MainLoop()
    else:
        print "Dialog (modal) returned {}".format(d)
