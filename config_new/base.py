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

from mide_ebml.ebmlite import loadSchema

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

# XXX: These are supposed to cast to the correct type for writing the config
# file. This conversion should probably be done by the encoding, so we should
# only keep track of the output element type (BooleanValue, IntValue, etc.).
def castToBoolean(x):
    return int(bool(x))

def castToInt(x):
    return int(x)

def castToUInt(x):
    return max(0, int(x))

def castToFloat(x):
    return float(x)

def castToASCII(x):
    if isinstance(x, unicode):
        return x.encode('ascii', 'replace')
    return str(x)

def castToText(x):
    if isinstance(x, bytearray):
        x = str(x)
    return unicode(x)

def castToSame(x):
    return x

DATA_TYPES = {
    "BooleanValue": castToBoolean,
    "UIntValue": castToUInt,
    "IntValue": castToInt,
    "FloatValue": castToFloat,
    "ASCIIValue": castToASCII,
    "TextValue": castToText,
    "BinaryValue": castToSame
}


#===============================================================================
# 
#===============================================================================

class ConfigContainer(object):
    """ A wrapper for the dialog's dictionary of configuration items, which
        dynamically gets values from the corresponding widget. It simplifies
        the field's ``DisplayFormat``, ``ValueFormat``, and ``DisableIf`` 
        expressions. 
    """
    
    def __init__(self, root):
        self.root = root
    
    
    def __getitem__(self, k, default=None):
        if k in self.root.configItems:
            return self.root.configItems[k].getDisplayValue()
        return default


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
            "DisableIf": "disableIf",
            "DisplayFormat": "displayFormat",
            "ValueFormat": "valueFormat",
            "*Min": "min",
            "*Max": "max",
            "*Value": "default",
    }
    
    # Class-specific element/attribute mapping. Subclasses can use this for
    # their unique attributes without clobbering the common ones in ARGS.
    CLASS_ARGS = {}
    
    # The name of the default *Value EBML element type used when writing this 
    # item's value to the config file. Used if the definition does not include
    # a *Value element.
    DEFAULT_TYPE = None
    
    # Default expression code objects for 
    noEffect = compile("x", "<ConfigBase.noEffect>", "eval")
    noValue = compile("None", "<ConfigBase.noValue>", "eval")
    
    
    def makeExpression(self, val):
        """ Helper method for compiling an expression in a string into a code
            object that can later be used with `eval()`. Used internally.
        """
        if val is None:
            return self.noEffect
        if val is '':
            return self.noValue
        try:
            return compile(val, "<ConfigBase.makeExpression>", "eval")
        except SyntaxError as err:
            print ("Ignoring bad expression (%s) for %s %r: %r" % 
                   (err.msg, self.__class__.__name__, self.label, err.text))
            return self.noValue

    
    def __init__(self, element, root):
        """ Constructor. 
        
            @param element: The EBML element from which to build the object.
            @param root: The main dialog.
        """
        self.root = root
        self.element = element
        
        # Convert element children to object attributes
        args = self.ARGS.copy()
        args.update(self.CLASS_ARGS)
        for v in args.values():
            if not hasattr(self, v):
                setattr(self, v, None)
        
        self.valueType = self.DEFAULT_TYPE
        
        for el in self.element.value:
            if el.name in FIELD_TYPES:
                # Child field: skip now, handle later (if applicable)
                continue
            
            if el.name.endswith('Value'):
                self.valueType = el.name
                
            if el.name in args:
                # Known element name (verbatim): set attribute
                setattr(self, args[el.name], el.value)
            else:
                # Match wildcards and set attribute
                for k,v in args.items():
                    if fnmatch(el.name, k):
                        setattr(self, v, el.value)

        # Default expressions for converting values between native and display
        self.displayFormat = self.makeExpression(self.displayFormat)
        self.valueFormat = self.makeExpression(self.valueFormat)
        
        # Add this item to the root's dictionary of config items
        if self.configId is not None and self.root is not None:
            self.root.configItems[self.configId] = self

        # Function to cast 
        self.valueCaster = DATA_TYPES.get(self.valueType, castToSame)
            


    def isEnabled(self):
        """ Check the Field's `disableIf` expression (if any) to determine if
            the Field should be enabled.
        """
        if self.disableIf is None:
            return True
        return not eval(self.disableIf, {'config': self.root.config})
        
    
    def getDisplayValue(self):
        """
        """
        return self.default
    
    
    def getConfigValue(self):
        """
        """
        # TODO: Handle errors
        return eval(self.valueFormat, {'x': self.getDisplayValue(),
                                       'Config': self.root.configValues})


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
    }

    
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
            label = self.checkbox
            self.sizer.Add(self.checkbox, 2, wx.ALIGN_CENTER_VERTICAL)
        else:
            self.checkbox = None
            label = wx.StaticText(self, -1, self.label or '')
            self.sizer.Add(label, 2, wx.ALIGN_CENTER_VERTICAL)
        
        self.addField()
        
        if self.UNITS or self.units:
            self.unitLabel = wx.StaticText(self, -1, self.units or '')
            self.sizer.Add(self.unitLabel, 1, wx.WEST|wx.ALIGN_CENTER_VERTICAL, 
                           border=8)
        else:
            self.unitLabel = None

        if self.tooltip:
            self.SetToolTipString(self.tooltip)
            label.SetToolTipString(self.tooltip)
            if self.units:
                self.unitLabel.SetToolTipString(self.tooltip)
            if self.field is not None:
                self.field.SetToolTipString(self.tooltip)
        
        if self.checkbox is not None:
            self.Bind(wx.EVT_CHECKBOX, self.OnCheck)
            self.setCheck(False)
        
        self.SetSizer(self.sizer)
        
        self.setToDefault()


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

    
    def updateConfigData(self):
        """ Update the `Config` variable.
        """
        # TODO: this


    def getDisplayValue(self):
        """ 
        """
        if self.field is not None:
            return self.field.GetValue()
        return self.default
    
        
    def OnCheck(self, evt):
        """ Handle checkbox changing.
        """
        self.enableChildren(evt.Checked())
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

    def setRawValue(self, val, check=False):
        """
        """
        self.checkbox.SetValue(bool(val))
    
    
    def getDisplayValue(self):
        """ 
        """
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
        self.textLines = 1
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
        self.min = MIN_SIGNED_INT
        self.max = MAX_SIGNED_INT
        self.default = 0
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
        self.increment = 0.25
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
        index = self.field.GetSelection()
        if index != wx.NOT_FOUND and index < len(self.options):
            return self.options[index].value
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
class DateTimeField(IntField):
    """ UI widget for editing a date/time value.
    """
    DEFAULT_TYPE = "IntValue"
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = DateTimeCtrl(self, -1)
        self.sizer.Add(self.field, 3)
        return self.field


#===============================================================================

@registerField
class UTCOffsetField(FloatField):
    """ Special-case UI widget for entering the local UTC offset, with the
        ability to get the value from the computer.
    """
    DEFAULT_TYPE = "IntValue"

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
class CheckDriftButton(ConfigWidget):
    """ Special-case "field" consisting of a button that checks the recorder's
        clock versus the host computer's time.
    """
    UNITS = False
    DEFAULT_TYPE = None

    def initUI(self):
        """ Build the user interface, adding the item label and/or checkbox,
            the appropriate UI control(s) and a 'units' label (if applicable). 
            Separated from `__init__()` for the sake of subclassing.
        """
        self.label = self.label or "Check Clock Drift"
        
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.field = wx.Button(self, -1, self.label)
        self.sizer.Add(self.field, 0)

        if self.tooltip:
            self.SetToolTipString(self.tooltip)
            self.field.SetToolTipString(self.tooltip)
        
        self.SetSizer(self.sizer)

        self.Bind(wx.EVT_BUTTON, self.OnCheckDrift)


    def OnCheckDrift(self, evt):
        self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
        times = self.root.device.getTime()
        drift = times[0] - times[1]
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        wx.MessageBox("Clock drift: %.4f seconds" % drift, "Check Clock Drift",
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
        0x42: CheckDateTimeField
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
            # All field EBML IDs have 0x40 as their 2nd byte.
            baseId = el.id & 0x00FF
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
        print "enableChildren", self.fields
        for f in self.fields:
            print f
            if hasattr(f, 'Enable'):
                f.Enable(enabled)


    def setToDefault(self, check=False):
        """ Reset the Field to the default values. Calls `setToDefault()` 
            method of each of its children.
        """
        for f in self.fields:
            if hasattr(f, 'setToDefault'):
                f.setToDefault(check)

        
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

    DEFAULT_NAME = None


    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
            
            @keyword element: The EBML element for which the UI element is
                being generated. The element's name typically matches that of
                the class.
            @keyword root: The main dialog.
        """
        self.label = None
        element = kwargs.pop('element', None)
        root = kwargs.pop('root', self)
        
        # Explicitly call __init__ of base classes to avoid ConfigWidget stuff
        ConfigBase.__init__(self, element, root)
        SP.ScrolledPanel.__init__(self, *args, **kwargs)

        self.SetupScrolling()

        self.label = self.label or self.DEFAULT_NAME
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
    DEFAULT_NAME = "Factory Calibration"


@registerTab
class UserCalibrationTab(FactoryCalibrationTab):
    """ Special-case Tab for showing/editing user calibration polynomials. 
        The tab's default behavior shows the appropriate info for Slam Stick 
        recorders, no child fields required.
        
        TODO: Implement FactoryCalibrationTab!
    """
    DEFAULT_NAME = "User Calibration"


@registerTab
class DeviceInfoTab(Tab):
    """ Special-case Tab for showing device info. The tab's default behavior
        shows the appropriate info for Slam Stick recorders, no child fields
        required.
        
        TODO: Implement FactoryCalibrationTab!
    """
    DEFAULT_NAME = "Device Info"


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
        self.expresionVariables = {'Config': self.configValues}
                
#         self.buildUI()
        
        # XXX: HACK: Load UIHints from multiple files.
        schema = loadSchema("config_ui.xml")
        for f in ('General.UI', 'Triggers.UI', 'Channel.UI'):
            self.hints = schema.load(f)
            print f, ("*" * 40)
            crawl(self.hints)
            self.buildUI()
        
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

def crawl(el, indent=-1):
    """ Test function to dump the structure of a CONFIG.UI EBML file. 
    """
    if indent > -1:
        if el.type == -1:
            print "%s (0x%04X, size %d):" % ((" "*indent*2), "**Unknown**", el.id, el.size),
        else:
            print "%s %s (0x%04X, size %d):" % ((" "*indent*2), el.name, el.id, el.size),
    if indent < 0 or isinstance(el.value, list):
        print
        for i in el:
            crawl(i, indent+1)
    else:
        print repr(el.value)


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    schema = loadSchema("../mide_ebml/ebml/schema/config_ui.xml")
    testDoc = schema.load('CONFIG.UI')
    crawl(testDoc)
    
    app = wx.App()
    dlg = ConfigDialog(None, hints=testDoc)
    dlg.ShowModal()
