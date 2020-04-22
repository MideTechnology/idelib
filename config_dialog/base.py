'''
Widgets used to dynamically populate a configuration dialog, as specified by
a device's "UI Hints" data (a/k/a CONFIG_UI). 

The dialog itself was split off to allow a more modular approach.
'''

from __future__ import absolute_import, print_function

__author__ = "dstokes"
__copyright__ = "Copyright 2020 Mide Technology Corporation"

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

from fnmatch import fnmatch
import string
import time

import wx
import wx.lib.filebrowsebutton as FB
import wx.lib.scrolledpanel as SP

from widgets.shared import DateTimeCtrl
from timeutil import getUtcOffset


#===============================================================================
# 
#===============================================================================

# XXX: Remove all this debugging stuff
__DEBUG__ = not True


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

class TextValidator(wx.Validator):
    """ Generic Validator for TextField and ASCIIField text widgets.
    """
    
    VALID_KEYS = (wx.WXK_LEFT, wx.WXK_UP, wx.WXK_RIGHT, wx.WXK_DOWN,
                  wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN,
                  wx.WXK_INSERT, wx.WXK_DELETE)
    
    def __init__(self, validator, maxLen=None):
        """ Instantiate a text field validator.
        
            @keyword validator: A function that validates the string. 
        """
        self.maxLen = maxLen
        self.isValid = validator 
        wx.Validator.__init__(self)
        self.Bind(wx.EVT_CHAR, self.OnChar)
        self.Bind(wx.EVT_TEXT_PASTE, self.OnPaste)
        

    def Clone(self):
        """ Required in wx.PyValidator subclasses. """
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

        if not wx.Validator.IsSilent():
            wx.Bell()

        return
    
    
    def OnPaste(self, evt):
        """ Validate text pasted into the field.
        """
        txt = getClipboardText()
        current = self.GetWindow().GetValue()
        if self.isValid(current + txt):
            evt.Skip()
        elif not wx.Validator.IsSilent():
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
            "ExcludeID": "exclude",
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

    
    def getPath(self):
        """ Get a string containing the configuration item's label and the
            labels of its parents (if applicable).
        """
        try:
            root = self.Parent.getPath()
            if self.label:
                return "%s : %s" % (root, self.label)
            else:
                return root
        except AttributeError:
            return self.label
        
    
    def __init__(self, element, root):
        """ Constructor. Instantiates a `ConfigBase` and parses parameters out
            of the supplied EBML element.
        
            @param element: The EBML element from which to build the object.
            @param root: The main dialog.
        """
        self.root = root
        self.element = element
        self.isAdvancedFeature = False
        
        # Convert element children to object attributes.
        # First, set any previously undefined attributes to None.
        args = self.ARGS.copy()
        args.update(self.CLASS_ARGS)
        for v in args.values():
            self.setAttribDefault(v, None)
        
        self.valueType = self.DEFAULT_TYPE
        self.exclude = []
        
        for el in self.element.value:
            if el.name == "IsAdvancedFeature":
                self.isAdvancedFeature = bool(el.value)
                continue
                
            if el.name in FIELD_TYPES:
                # Child field: skip now, handle later (if applicable)
                continue
            
            if el.name == "ExcludeID":
                self.exclude.append(el.value)
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
        
        self.expressionVariables = self.root.expressionVariables.copy()


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
        self.field = None
        
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
        self.sizer.Add(p, 4)
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
            self.sizer.Add(self.checkbox, 3, wx.ALIGN_CENTER_VERTICAL)
        else:
            self.checkbox = None
            self.labelWidget = wx.StaticText(self, -1, self.label or '')
            self.sizer.Add(self.labelWidget, 3, wx.ALIGN_CENTER_VERTICAL)
        
        self.addField()
        
        if self.UNITS or self.units:
            self.unitLabel = wx.StaticText(self, -1, self.units or '')
            self.sizer.Add(self.unitLabel, 1, wx.WEST|wx.ALIGN_CENTER_VERTICAL, 
                           border=8)
        else:
            self.unitLabel = None

        if self.tooltip:
            self.SetToolTip(self.tooltip)
            self.labelWidget.SetToolTip(self.tooltip)
            if self.units:
                self.unitLabel.SetToolTip(self.tooltip)
            if self.field is not None:
                self.field.SetToolTip(self.tooltip)
        
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


    def setCheck(self, checked=True, recurse=True):
        """ Set the Field's checkbox, if applicable.
        """
        if self.checkbox is not None:
            self.checkbox.SetValue(checked)
            self.enableChildren(checked)
        
        # Percolate the check upstream, so parent checks will get set.
        # Only setting the check gets propagated, not clearing it. 
        if checked and recurse and hasattr(self.Parent, 'setCheck'):
            self.Parent.setCheck()
            

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
        try:
            if val is not None:
                if self.field is not None:
                    self.field.SetValue(val)
                else:
                    check = bool(val)
            self.setCheck(check)
        except TypeError:
            # Shouldn't happen, but could if the config file is damaged.
            logger.error('Config file had wrong type for %s (ConfigID 0x%X): '
                         '%r (%s)' % (self.__class__.__name__, self.configId,
                                      val, val.__class__.__name__))
        except wx.wxAssertionError as err:
            # Also shouldn't happen, but might if the file is damaged.
            # Happened once, can't repeat.
            logger.error('%s (ConfigID 0x%X, value:%r)' % (err.message, 
                                                           self.configId, val))
        

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
        if evt.IsChecked():
#         if self.checkbox and self.checkbox.IsChecked():
            for cid in self.exclude:
                if cid in self.root.configItems:
                    self.root.configItems[cid].setCheck(False)
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
        it is a checkbox, it is not considered a 'check' field because the
        check *is* its value.
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
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
        """
        self.setAttribDefault('default', '')
        self.setAttribDefault('textLines', 1)
        super(TextField, self).__init__(*args, **kwargs)

    
    def isValid(self, s):
        """ Filter for characters valid in the text field. Used by the field's
            Validator. It just checks the string contents vs. `VALID_CHARS` and
            its length vs. `maxLength`.
        """
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
            self.field.SetSize(-1, s * self.textLines)
        else:
            self.field = wx.TextCtrl(self, -1, str(self.default or ''),
                                     validator=validator)
            
        self.sizer.Add(self.field, 4, wx.EXPAND)
        return self.field
    
    
    def getDisplayValue(self):
        v = super(TextField, self).getDisplayValue()
        if not v:
            return None
        return v


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
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
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
        self.sizer.Add(self.field, 4)
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
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
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
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
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
        self.sizer.Add(self.field,4)
        return self.field


#===============================================================================

@registerField
class EnumField(ConfigWidget):
    """ UI widget for selecting one of several items from a list.
    """
    DEFAULT_TYPE = "UIntValue"
    
    UNITS = False

    
    def __init__(self, *args, **kwargs):
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
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
        self.sizer.Add(self.field, 4)
        
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
            
        self.field.SetToolTip(tt)


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
        if index != wx.NOT_FOUND:
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
            o.default = (self.default >> o.value) & 1
            o.checkbox = wx.CheckBox(self, -1, o.label)
            childSizer.Add(o.checkbox, 0, 
                           wx.ALIGN_LEFT|wx.EXPAND|wx.NORTH|wx.SOUTH, 4)
            
            tooltip = o.tooltip or self.tooltip
            if tooltip:
                o.checkbox.SetToolTip(tooltip)
        
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
            self.SetToolTip(self.tooltip)
            if self.labelWidget is not None:
                self.labelWidget.SetToolTip(self.tooltip)
        
        self.SetSizer(self.sizer)
        
        self.setToDefault()
        
        # Child checks should also fire the 'on check' handler.
        self.Bind(wx.EVT_CHECKBOX, self.OnCheck)


    def getDisplayValue(self):
        """ Get the field's displayed value. 
        """
        if self.checkbox is not None and not self.checkbox.GetValue():
            return None
        if self.isDisabled():
            return None
        
        val = 0
        for o in self.options:
            if o.checkbox.GetValue():
                val = val | (1 << o.value)
        
        return val

    
    def updateDisabled(self):
        """ Automatically enable or disable this field according to its 
            `isDisabled` expression (if any). Individually disabled options
            get set to their default.
        """
        super(BitField, self).updateDisabled()
        
        if not self.isDisabled():
            for o in self.options:
                dis = o.isDisabled()
                o.checkbox.Enable(not dis)
                if dis:
                    o.checkbox.SetValue(bool(o.default))


#===============================================================================
    
@registerField
class DateTimeField(IntField):
    """ UI widget for editing a date/time value.
    """
    DEFAULT_TYPE = "IntValue"
    LABEL = False
    
    LOCAL_TIME = 0
    UTC_TIME = 1
    
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.localTz = getUtcOffset(seconds=True)
        super(DateTimeField, self).__init__(*args, **kwargs)
        
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        h = int(1.6*self.labelWidget.GetSize()[1])
        self.field = DateTimeCtrl(self, -1, size=(-1,h))
        self.sizer.Add(self.field, 4)
        
        self.tzList = wx.Choice(self, -1, choices=['Local Time', 'UTC Time'])
        self.sizer.Add(self.tzList, -1, wx.WEST|wx.ALIGN_CENTER_VERTICAL, 
                       border=8)
        
        self.lastTz = int(self.root.useUtc)
        self.tzList.SetSelection(self.lastTz)
        self.tzList.Bind(wx.EVT_CHOICE, self.OnTzChange)
        
        return self.field


    def enableChildren(self, enabled=True):
        """ Enable/Disable the Field's children.
        """
        super(DateTimeField, self).enableChildren(enabled=enabled)
        self.tzList.Enable(enabled)
    
    
    def isLocalTime(self):
        """ Is the widget showing local time (vs. UTC)?
        """
        return self.tzList.GetSelection() == self.LOCAL_TIME
    
    
    def updateToolTips(self):
        """ Update the Choice's tooltip to match the item displayed.
        """
        offset = self.localTz
        if self.isLocalTime():
            msg = "Time shown is the computer's local time (UTC %s hours)"
        else:
            offset *= -1
            msg = "Time shown is UTC time (local computer time %s hours)"
        if offset >= 0:
            offsetStr = "+ %0.2f" % offset
        else:
            
            offsetStr = "- %0.2f" % abs(offset)
        self.tzList.SetToolTip(msg % offsetStr)
        
    
    def setDisplayValue(self, val, check=True):
        """ Set the Field's value, in epoch seconds UTC.
        """
        if not val:
            val = time.time()
        else:
            if self.isLocalTime():
                val += self.localTz
        
        dt =  wx.DateTime.FromTimeT(long(val))
        super(DateTimeField, self).setDisplayValue(dt, check)
        self.updateToolTips()
    
    
    def getDisplayValue(self):
        """ Get the field's displayed value (epoch seconds UTC). 
        """
        val = super(DateTimeField, self).getDisplayValue()
        if val is None:
            return None
        val = val.GetTicks()
        if self.isLocalTime():
            val -= self.localTz
        return val


    def OnTzChange(self, evt):
        """ Handle Local/UTC selection change.
        """
        # NOTE: This changes the main dialog's useUtc attribute, but it will
        # not update other DateTimeFields. Will need revision if/when we use
        # more than one.
        
        # Don't modify time if selection is the same (event gets fired even if
        # the same Choice item was selected).
        if self.tzList.GetSelection() == self.lastTz:
            return
        
        val = self.field.GetValue()
        t = val.GetTicks()
        if self.isLocalTime():
            dt = wx.DateTime.FromTimeT(long(t + self.localTz))
            self.field.SetValue(dt)
            self.lastTz = self.LOCAL_TIME
            self.root.useUtc = False
        else:
            dt = wx.DateTime.FromTimeT(long(t - self.localTz))
            self.field.SetValue(dt)
            self.lastTz = self.UTC_TIME
            self.root.useUtc = True

        self.updateToolTips()
        

#===============================================================================

@registerField
class UTCOffsetField(FloatField):
    """ Special-case UI widget for entering the local UTC offset, with the
        ability to get the value from the computer.
    """
    DEFAULT_TYPE = "IntValue"

    def __init__(self, *args, **kwargs):
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
        """
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
        self.getOffsetBtn.SetSize(-1, self.field.GetSize()[1])
        self.getOffsetBtn.Bind(wx.EVT_BUTTON, self.OnSetTZ)
        self.sizer.Add(self.getOffsetBtn, 0)

        if self.tooltip:
            self.getOffsetBtn.SetToolTip(self.tooltip)

    
    def OnSetTZ(self, event):
        """ Handle the 'Get Local Offset' button press by getting the local
            time zone offset.
        """
        self.setDisplayValue(getUtcOffset())


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
        self.sizer.Add(self.field, 4)
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
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
        """
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
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
        """
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
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
        """
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
            self.SetToolTip(self.tooltip)
            self.field.SetToolTip(self.tooltip)
        
        self.SetSizer(self.sizer)

        self.Bind(wx.EVT_BUTTON, self.OnButtonPress)


    def OnButtonPress(self, evt):
        """ Handle button press: perform the clock drift test.
        """
        self.SetCursor(wx.Cursor(wx.CURSOR_WAIT))
        try:
            times = self.root.device.getTime()
        except Exception:
            if __DEBUG__:
                raise
            self.showError("Could not read the recorder's clock!", self.label,
                          style=wx.OK|wx.ICON_ERROR)
            return
        
        drift = times[0] - times[1]
        self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
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
        """ Constructor.
        
            @see: `ConfigWidget.__init__()`
        """
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
            
        if widget.isAdvancedFeature and not self.root.showAdvanced:
            widget.Hide()

            
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
        if self.checkbox is not None and not self.checkbox.GetValue():
            return None
        return not self.isDisabled() or None

        
@registerField
class CheckGroup(Group):
    """ A labeled group of configuration items with a checkbox to enable or 
        disable them all. Children appear indented.
    """
    CHECK = True
    DEFAULT_TYPE = "BooleanValue"


    def setToDefault(self, check=False):
        """ Reset the CheckGroup to its default value. The checkbox's state is 
            unchanged if the CheckGroup has no default.
        """
        Group.setToDefault(self, check=check)
        if self.default is not None:
            self.setCheck(self.default)


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
# 
#===============================================================================

# XXX: Remove all this debugging stuff
# dlg = None

# if __name__ == "__main__":
#     import sys
#     
#     print "running %s main" % __file__
#     from idelib.ebmlite import util
#     SCHEMA = loadSchema('config_ui.xml')
#     
#     # XXX: TEST CODE, loads the UI from a file (XML or EBML), specified as a 
#     # command line argument. If no file is specified, the first recorder found 
#     # is used.
# #     sys.argv = ['',  'drs_test/fw20_test.xml']
# #     sys.argv = ['',  'drs_test/newBadCONFIG.xml']
# #     sys.argv = ['',  'drs_test/NoText.UI']
#     if len(sys.argv) > 1:
#         device = None
#         if sys.argv[-1].endswith('.xml'):
#             hints = util.loadXml(sys.argv[-1], SCHEMA)
#         else:
#             hints = SCHEMA.load(sys.argv[-1])
#     else:
#         hints = None
#         from devices import getDevices
#         device = getDevices()[0]
#     
#     app = wx.App()
# 
#     d = configureRecorder(device, hints=hints, modal=not __DEBUG__, 
#                           useUtc=False, saveOnOk=True, showAdvanced=True)
#     
#     if __DEBUG__:
#         # Show the Python shell. NOTE: dialog is non-modal; closing the windows
#         # won't stop the app.
#         print "Dialog shown non-modally; result will not be printed."
#         import wx.py.shell
#         con = wx.py.shell.ShellFrame()
#         con.Show()
#         app.MainLoop()
#     else:
#         print "Dialog (modal) returned {}".format(d)
