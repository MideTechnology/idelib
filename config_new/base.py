'''
New, modular configuration system. Dynamically creates the UI based on the new 
"UI Hints" data. The UI is described in EBML; UI widget classes have the same
names as the elements. The crucial details of the widget type are also encoded
into the EBML ID; in the future, this will be used to create appropriate 
default widgets for new elements.

Created on Jul 6, 2017
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

from fnmatch import fnmatch
import string
import time

import wx
import wx.lib.filebrowsebutton as FB
import wx.lib.scrolledpanel as SP
import wx.lib.sized_controls as SC

from widgets.shared import DateTimeCtrl
from common import makeWxDateTime

from mide_ebml.ebmlite import loadSchema

import logging
logger = logging.getLogger('SlamStickLab.ConfigUI')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")

#===============================================================================
# 
#===============================================================================

# Min/max integers supported by wxPython SpinCtrl
MAX_SIGNED_INT = 2**31 - 1
MIN_SIGNED_INT = -2**31

#===============================================================================
#--- Utility functions
#===============================================================================

# Dictionaries of all known field and tab types. The `@registerField` and 
# `@registerTab` decorators add classes to them, respectively. See 
# `registerField()` and `registerTab()` functions, below.
FIELD_TYPES = {}
TAB_TYPES = {}

def registerField(cls):
    """ Class decorator for registering configuration field types. Field names
        should match the element names in the ``CONFIG.UI`` EBML.
    """
    global FIELD_TYPES
    FIELD_TYPES[cls.__name__] = cls
    return cls


def registerTab(cls):
    """ Class decorator for registering configuration tab types. Tab names
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

class ConfigContainer(object):
    """ A wrapper for the dialog's dictionary of configuration items, which
        dynamically gets values from the corresponding widget. It simplifies
        the field's ``DisplayFormat``, ``ValueFormat``, and ``DisableIf`` 
        expressions. Iterating over it is performed in the order of the
        keys, low to high.
    """
    
    def __init__(self, root):
        self.root = root
    
    
    def get(self, k, default=None):
        if k in self.root.configItems:
            return self.root.configItems[k].getDisplayValue()
        return default


    def __getitem__(self, k):
        return self.root.configItems[k].getDisplayValue()


    def __contains__(self, k):
        return k in self.root.configItems

    
    def __iter__(self):
        return sorted(self.root.configItems.keys())


    def iterkeys(self):
        return self.__iter__()
    
    
    def itervalues(self):
        for k in self.iterkeys():
            yield self[k]

    
    def iteritems(self):
        for k in self.iterkeys():
            yield (k, self[k])

    
    def pop(self, k, default=None):
        return self
    

#===============================================================================
#--- Base classes
#===============================================================================

class ConfigBase(object):
    """ Base/mix-in class for configuration items. Handles parsing attributes
        from EBML. Doesn't do any of the GUI-specific widget work.
        
        @cvar ARGS: A dictionary mapping EBML element names to object attribute
            names. Wildcards are allowed in the element names.
        @cvar CLASS_ARGS: A dictionary mapping additional EBML element names
            to object attribute names. Subclasses can add their own unique
            attributes to this dictionary.
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
    
    # Default expression code objects for DisableIf, ValueFormat, DisplayFormat
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
        if exp is '':
            # Empty string expression: always returns `None` (e.g. the field is
            # used to calculate another config item, not a config item itself)
            return self.noValue
        
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
        """ Constructor. 
        
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
        
        self.valueType = element.schema.get(self.DEFAULT_TYPE)
        
        for el in self.element.value:
            if el.name in FIELD_TYPES:
                # Child field: skip now, handle later (if applicable)
                continue
            
            if el.name.endswith('Value'):
                self.valueType = el.__class__
                
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
        
        if self.configId is not None and self.root is not None:
            self.root.configItems[self.configId] = self
        
        self.expressionVariables = self.root.expresionVariables.copy()


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
        return self.default
    
    
    def getConfigValue(self):
        """
        """
        if self.configId is None:
            return
        try:
            self.expressionVariables['x'] = self.getDisplayValue()
            return eval(self.valueFormat, self.expressionVariables)
        except (KeyError, ValueError, TypeError):
            return None



class ConfigWidget(wx.Panel, ConfigBase):
    """ Base class for a configuration field.
    
        @cvar CHECK: Does this field have a checkbox?
        @cvar UNITS: Should this widget always leave space for the 'units'
            label, even when its EBML description doesn't contain a ``Label``?
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

    
    def isDisabled(self):
        if not self.IsEnabled():
            return True
        return super(ConfigWidget, self).isDisabled()


    def setCheck(self, checked=True):
        """ Set the Field's checkbox, if applicable.
        """
        if self.checkbox is not None:
            self.checkbox.SetValue(checked)
            self.enableChildren(checked)
            
    
    def enableChildren(self, enabled=True):
        """ Enable/Disable the Field's children.
        """
        if self.field is not None:
            self.field.Enable(enabled)
        if self.unitLabel is not None:
            self.unitLabel.Enable(enabled)


    def setRawValue(self, val, check=True):
        """ Set the Field's value, using the data type native to the config
            file. 
        """
        if self.field is not None:
            self.field.SetValue(val)
        else:
            check = bool(val)
        self.setCheck(check)
        

    def setToDefault(self, check=False):
        """ Reset the Field to its default value.
        """
        if self.default is not None:
            self.setRawValue(self.default, check=check)
            
        self.setCheck(check)


    def getDisplayValue(self):
        """ 
        """
        if self.isDisabled():
            return None
        elif self.checkbox is not None and not self.checkbox.GetValue():
            return None
        
        if self.field is not None:
            return self.field.GetValue()
        
        return self.default
    
        
    def OnCheck(self, evt):
        """ Handle checkbox changing.
        """
        self.enableChildren(evt.Checked())
        evt.Skip()


    def OnValueChanged(self, evt):
        self.updateConfigData()
        for k,v in sorted(self.root.configItems.items()):
            if k != self.configId:
                v.updateConfigData()

        
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

    def setRawValue(self, val, check=False):
        """
        """
        self.checkbox.SetValue(bool(val))
    
    
    def getDisplayValue(self):
        """ 
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
    VALID_CHARS = string.ascii_letters #None

    def __init__(self, *args, **kwargs):
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
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated.
            @keyword root: The main dialog.
            @keyword group: The parent group containing the Field.
        """
        # Set some default values
        self.setAttribDefault('min', MIN_SIGNED_INT)
        self.setAttribDefault('max', MAX_SIGNED_INT)
        self.setAttribDefault('default', 0)
        super(IntField, self).__init__(*args, **kwargs)
    
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        # wxPython SpinCtrl values limited to 32b signed integer range
        self.min = int(max(self.min, MIN_SIGNED_INT))
        self.max = int(min(self.max, MAX_SIGNED_INT))
        self.default = max(min(self.default, MAX_SIGNED_INT), MIN_SIGNED_INT)
        
        self.field = wx.SpinCtrl(self, -1, size=(40,-1), 
                                 style=wx.SP_VERTICAL|wx.TE_RIGHT,
                                 min=self.min, max=self.max, 
                                 initial=self.default)
        self.sizer.Add(self.field, 2)
        return self.field


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
        super(UIntField, self).__init__(*args, **kwargs)
        self.min = max(0, self.min)
        self.field.SetRange(self.min, self.max)
        

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
        super(FloatField, self).__init__(*args, **kwargs)

        
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = wx.SpinCtrlDouble(self, -1, 
                                       inc=self.increment,
                                       min=self.min, max=self.max, 
                                       value=str(self.default))
        self.sizer.Add(self.field)
        return self.field


#===============================================================================

@registerField
class EnumField(ConfigWidget):
    """ UI widget for selecting one of several items from a list.
    """
    DEFAULT_TYPE = "UIntValue"
    
    UNITS = False

    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        optionEls = [el for el in self.element.value if el.name=="EnumOption"]
        self.options = [EnumOption(el, self, n) for n,el in enumerate(optionEls)]
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
        evt.Skip()
        

    def setRawValue(self, val, check=True):
        """ Select the appropriate item for the 
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
        """ 
        """
        if self.isDisabled():
            return None
        elif self.checkbox is not None and not self.checkbox.GetValue():
            return None
        
        index = self.field.GetSelection()
        if index != wx.NOT_FOUND and index < len(self.options):
            return self.options[index].getDisplayValue()
        return self.default
    
    
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

    
    def getDisplayValue(self):
        return self.value

    
#===============================================================================

@registerField
class BitField(EnumField):
    """
    """

    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        optionEls = [el for el in self.element.value if el.name=="EnumOption"]
        self.options = [EnumOption(el, self, n) for n,el in enumerate(optionEls)]
        
        for o in self.options:
            o.checkbox = wx.CheckBox(self, -1, o.label)
            self.sizer.Add(o.checkbox, 1, wx.EXPAND|wx.WEST, 8)
        
        return self.sizer
        

    def setRawValue(self, val, check=True):
        """ Select the appropriate item for the 
        """
        for o in self.options:
            o.checkbox.SetValue(bool(val & (1 << o.value)))
        self.setCheck(check)
    

    def initUI(self):
        """ Build the user interface, adding the item label and/or checkbox,
            the appropriate UI control(s) and a 'units' label (if applicable). 
            Separated from `__init__()` for the sake of subclassing.
        """
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        if self.CHECK:
            self.checkbox = wx.CheckBox(self, -1, self.label or '')
            self.labelWidget = self.checkbox
            self.sizer.Add(self.checkbox, 2, wx.ALIGN_CENTER_VERTICAL)
        else:
            self.checkbox = None
            self.labelWidget = wx.StaticText(self, -1, self.label or '')
            self.sizer.Add(self.labelWidget, 2, wx.ALIGN_CENTER_VERTICAL)
        
        self.addField()
        
        self.unitLabel = None

        if self.tooltip:
            self.SetToolTipString(self.tooltip)
        
        if self.checkbox is not None:
            self.Bind(wx.EVT_CHECKBOX, self.OnCheck)
            self.setCheck(False)
        
        self.SetSizer(self.sizer)
        
        self.setToDefault()


    def getDisplayValue(self):
        """ 
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
        return self.field

    
    def enableChildren(self, enabled=True):
        super(DateTimeField, self).enableChildren(enabled=enabled)
        self.utcCheck.Enable(enabled)
    
    
    def setRawValue(self, val, check=True):
        if val == 0:
            val = time.time()
        super(DateTimeField, self).setRawValue(makeWxDateTime(val), check)
    
    
    def getDisplayValue(self):
        """
        """
        val = super(DateTimeField, self).getDisplayValue()
        if val is None:
            return None
        if not self.utcCheck.GetValue():
            val = val.ToUTC()
        return val.GetTicks()
    

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
        self.setAttribDefault('displayFormat', "x/3600")
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
        self.setRawValue(val)


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
#--- Special-case fields/widgets
#===============================================================================

@registerField
class FloatTemperatureField(FloatField):
    """
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault("units", u"\u00b0C")
        self.setAttribDefault("label", "Temperature")
        self.setAttribDefault("min", -40.0)
        self.setAttribDefault("max", 80.0)
        super(FloatTemperatureField, self).__init__(*args, **kwargs)



@registerField
class CheckFloatTemperatureField(FloatTemperatureField):
    """
    """
    CHECK = True
        
        
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
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.field = wx.Button(self, -1, self.label)
        self.sizer.Add(self.field, 0)

        if self.tooltip:
            self.SetToolTipString(self.tooltip)
            self.field.SetToolTipString(self.tooltip)
        
        self.SetSizer(self.sizer)

        self.Bind(wx.EVT_BUTTON, self.OnCheckDrift)


    def OnCheckDrift(self, evt):
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
    
    
    def addChild(self, el):
        """ Add a child field to the Group.
        """
        cls = self.getWidgetClass(el)
        if cls is None:
            return
        
        widget = cls(self, -1, element=el, root=self.root, group=self)
        self.fields.append(widget)
        self.sizer.Add(widget, 0, wx.ALIGN_LEFT|wx.EXPAND|wx.ALL, border=4)

            
    def initUI(self):
        """ Build the user interface, adding the item label and/or checkbox
            (if applicable) and all the child Fields.
        """
        self.fields = []
        outerSizer = wx.BoxSizer(wx.VERTICAL)
        
        if self.LABEL:
            if self.CHECK:
                self.checkbox = wx.CheckBox(self, -1, self.label or '')
                label = self.checkbox
                self.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.checkbox)
            else:
                self.checkbox = None
                label = wx.StaticText(self, -1, self.label or '')
        
            outerSizer.Add(label, 0, wx.NORTH, 4)
            label.SetFont(label.GetFont().Bold())

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
                f.setToDefault(check)


    def getDisplayValue(self):
        """ 
        """
        if self.isDisabled():
            return None
        elif self.checkbox is not None and not self.checkbox.GetValue():
            return None
        
        return self.getConfigValue()
        
        
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
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated. The element's name typically matches that of
                the class.
            @keyword root: The main dialog.
        """
        element = kwargs.pop('element', None)
        root = kwargs.pop('root', self)
        
        # Explicitly call __init__ of base classes to avoid ConfigWidget stuff
        ConfigBase.__init__(self, element, root)
        SP.ScrolledPanel.__init__(self, *args, **kwargs)

        self.SetupScrolling()

        self.initUI()


    def initUI(self):
        """ Build the contents of the tab.
        """
        self.fields = []
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        for el in self.element.value:
            self.addChild(el)
        self.SetSizer(self.sizer)


#===============================================================================
#--- Special-case tabs 
#===============================================================================

@registerTab
class FactoryCalibrationTab(Tab):
    """ Special-case Tab for showing recorder calibration polynomials. The 
        tab's default behavior shows the appropriate info for Slam Stick 
        recorders, no child fields required.
        
        TODO: Implement FactoryCalibrationTab!
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault("label", "Factory Calibration")
        super(FactoryCalibrationTab, self).__init__(*args, **kwargs)


@registerTab
class UserCalibrationTab(FactoryCalibrationTab):
    """ Special-case Tab for showing/editing user calibration polynomials. 
        The tab's default behavior shows the appropriate info for Slam Stick 
        recorders, no child fields required.
        
        TODO: Implement FactoryCalibrationTab!
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault("label", "User Calibration")
        super(UserCalibrationTab, self).__init__(*args, **kwargs)


@registerTab
class DeviceInfoTab(Tab):
    """ Special-case Tab for showing device info. The tab's default behavior
        shows the appropriate info for Slam Stick recorders, no child fields
        required.
        
        TODO: Implement FactoryCalibrationTab!
    """
    def __init__(self, *args, **kwargs):
        self.setAttribDefault("label", "Recorder Info")
        super(DeviceInfoTab, self).__init__(*args, **kwargs)


#===============================================================================
# 
#===============================================================================

class ConfigDialog(SC.SizedDialog):
    """ Root window for recorder configuration.
    """

    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `SizedDialog` arguments, plus:
        
            @keyword device: The recorder to configure (an instance of a 
                `devices.Recorder` subclass)
        """
        self.device = kwargs.pop('device', None)
        try:
            devName = self.device.productName
            if self.device.path:
                devName += (" (%s)" % self.device.path) 
        except AttributeError:
            # Typically, this won't happen outside of testing.
            devName = "Recorder"
        
        # Having 'hints' argument is a temporary hack!
        self.loadConfigUI(kwargs.pop('hints', None))

        kwargs.setdefault("title", "Configure %s" % devName)
        kwargs.setdefault("style", wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        super(ConfigDialog, self).__init__(*args, **kwargs)

        pane = self.GetContentsPane()
        self.notebook = wx.Notebook(pane, -1)
        self.notebook.SetSizerProps(expand=True, proportion=-1)
        
        self.configItems = {}
        self.configValues = ConfigContainer(self)
        
        # Variables to be accessible by field expressions. Includes mapping
        # None to ``null``, making the expressions less specific to Python. 
        self.expresionVariables = {'Config': self.configValues,
                                   'null': None}
                
#         self.buildUI()
        
        # XXX: HACK: Load UIHints from multiple files.
        if self.hints is None:
            schema = loadSchema("config_ui.xml")
            for f in ('General.UI', 'Triggers.UI', 'Channel.UI'):
                self.hints = schema.load(f)
                print f, ("*" * 40)
                util.dump(self.hints)
                self.buildUI()
        else:
            self.buildUI()
        
        self.useLegacyConfig = False
        self.loadConfigData()
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK|wx.CANCEL))
        self.Bind(wx.EVT_BUTTON, self.OnOK, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
        
        self.Fit()
        self.SetMinSize((500, 400))
        self.SetSize((680, 600))


    def buildUI(self):
        """ Construct and populate the UI based on the ConfigUI element.
        """
        for el in self.hints.roots[0]:
            if el.name in TAB_TYPES:
                tabType = TAB_TYPES[el.name]
                tab = tabType(self.notebook, -1, element=el, root=self)
                self.notebook.AddPage(tab, str(tab.label))


    def loadConfigUI(self, defaults=None):
        """ Read the UI definition from the device. For recorders with old
            firmware that doesn't generate a UI description, an appropriate
            generic version is created.
        """
        print "XXX: Implement loadConfigUI()!"
        self.hints = defaults
        

    def loadConfigData(self):
        """ Load config data from the recorder.
        """
        print "XXX: Implement loadConfig()"
        
        self.configData = {}
        self.origConfigData = self.configData.copy()
    
    
    def saveConfigData(self):
        """ Save edited config data to the recorder.
        """
        print "XXX: Implement saveConfig()"
    
    
    def loadLegacyConfigData(self):
        """ Load old-style configuration data (i.e. not ConfigID/value pairs),
            as used by firmware versions prior to [XXX: add FwRev].
        """
        self.useLegacyConfig = True
        print "XXX: Implement loadLegacyConfigData()!"
    
    
    def saveLegacyConfigData(self):
        """ Save old-style configuration data (i.e. not ConfigID/value pairs),
            as used by firmware versions prior to [XXX: add FwRev].
        """
        print "XXX: Implement saveLegacyConfigData()!"
   
    
    def OnOK(self, evt):
        """ Handle dialog OK, saving changes.
        """
        self.saveConfigData()
        evt.Skip()


    def OnCancel(self, evt):
        """ Handle dialog cancel, prompting the user to save any changes.
        """
        if self.configData != self.origConfigData:
            q = wx.MessageBox("Save configuration changes before exiting?",
                              "Configure Device", 
                              wx.YES_NO|wx.CANCEL|wx.CANCEL_DEFAULT, self)
            if q == wx.CANCEL:
                return
            elif q == wx.YES:
                self.saveConfigData()
                
        evt.Skip()


#===============================================================================
# 
#===============================================================================

# __DEBUG__ = False
__DEBUG__ = True

if __name__ == "__main__":
    schema = loadSchema("config_ui.xml")
#     schema = loadSchema("../mide_ebml/ebml/schema/config_ui.xml")
#     testDoc = schema.load('CONFIG.UI')
    
    from mide_ebml.ebmlite import util
    from StringIO import StringIO
    s = StringIO()
    util.xml2ebml('defaults/LOG-0002-100G.xml', s, schema)
    s.seek(0)
    testDoc = schema.load(s)

#     util.dump(testDoc)
    
    app = wx.App()
    dlg = ConfigDialog(None, hints=testDoc)
    
    if __DEBUG__:
        dlg.Show()
        
        import wx.py.shell
        con = wx.py.shell.ShellFrame()
        con.Show()

        app.MainLoop()

            
    else:
        dlg.ShowModal() 

