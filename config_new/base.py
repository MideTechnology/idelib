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

# from collections import OrderedDict

from fnmatch import fnmatch
import string

import wx

from widgets.shared import DateTimeCtrl


#===============================================================================
#--- Utility functions
#===============================================================================

# Dictionary of all known field types. The `@field` class decorator adds them.
# See `field()`, below.
FIELD_TYPES = {}


def field(cls):
    """ Class decorator for registering configuration field types.
    """
    global FIELD_TYPES
    FIELD_TYPES[cls.__name__] = cls
    return cls


#===============================================================================
#--- Base classes
#===============================================================================

class ConfigBase(object):
    """ Base/mix-in class for configuration items. Handles parsing attributes
        from EBML.
        
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
            "*Min": "min",
            "*Max": "max",
            "*Value": "default",
    }
    
    # Class-specific element/attribute mapping. Subclasses can use this for
    # their unique attributes.
    CLASS_ARGS = {}
    
    
    @staticmethod
    def noEffect(x):
        """ Dummy function for values that need no conversion to/from device 
            native data types.
        """
        return x
    
    
    def __init__(self, element, root):
        """ Constructor. 
        
            @param element: The EBML element from which to build the object.
            @param root: The main dialog.
        """
        self.root = root
        self.element = element
        
        args = self.ARGS.copy()
        args.update(self.CLASS_ARGS)
        for v in args.values():
            if not hasattr(self, v):
                setattr(self, v, None)
                
        for el in self.element.value:
            if el.name in FIELD_TYPES:
                # Child field: handle separately.
                continue
            elif el.name in args:
                # Known element name (verbatim): set attribute
                setattr(self, args[el.name], el.value)
            else:
                # Match wildcards and set attribute
                for k,v in args:
                    if fnmatch(el.name, k):
                        setattr(self, v, el.value)
        

    def isEnabled(self):
        """
        """
        if self.disableIf is None:
            return True
        return not eval(self.disableIf, {'config': self.root.config})
        

class ConfigPanel(wx.Panel, ConfigBase):
    """ Base class for configuration UI items.
    """
    
    CHECK = False
    
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
                being generated.
            @keyword root: The main dialog.
        """
        element = kwargs.pop('element', None)
        root = kwargs.pop('root', None)
        
        ConfigBase.__init__(self, element, root)
        wx.Panel.__init__(self, *args, **kwargs)

        if getattr(self, 'tooltip', None):
            self.SetToolTipString(self.tooltip)


class ConfigWidget(ConfigPanel):
    """ Base class for a configuration field.
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        super(ConfigWidget, self).__init__(*args, **kwargs)
        
        if not self.displayFormat:
            self.displayFormat = self.noEffect
        else:
            self.displayFormat = eval("lambda x: %s" % self.displayFormat)
        if not self.valueFormat:
            self.valueFormat = self.noEffect
        else:
            self.valueFormat = eval("lambda x: %s" % self.displayFormat)

        self.initUi()

    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
            Should be overridden in subclasses.
        """
        self.field = None
        p = wx.Panel(self, -1)
        self.sizer.Add(p, 1)
        return p

    
    def initUi(self):
        """ Build the user interface.
        """
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        if self.CHECK:
            self.checkbox = wx.CheckBox(self, -1, self.label)
            label = self.checkbox
            self.sizer.Add(self.checkbox, 0)
        else:
            self.checkbox = None
            label = wx.StaticText(self, -1, self.label)
            self.sizer.Add(label, 0)
        
        self.addField()
        
        units = wx.StaticText(self, -1, self.units or '')
        self.sizer.Add(units, 0)

        if self.tooltip:
            label.SetToolTipString(self.tooltip)
            units.SetToolTipString(self.tooltip)
            if self.field is not None:
                self.field.SetToolTipString(self.tooltip)
        
        self.SetSizer(self.sizer)


    def setRawValue(self, val, check=True):
        """
        """
        if self.field is not None:
            self.field.SetValue(val)
        else:
            check = bool(val)
        self.setCheck(check)

    
    def setCheck(self, checked=True):
        """
        """
        if self.checkox is None:
            return
        self.checkbox.SetValue(checked)
        self.Enable(checked)


#===============================================================================
#--- Non-check fields 
# Container fields excluded (see below).
# Note: BooleanField is technically non-check. 
#===============================================================================

@field
class BooleanField(ConfigWidget):
    """ UI widget for editing a Boolean value. This is a special case; although
        it is a checkbox, it is not considered a 'check' field
    """
    CHECK = True


@field
class TextField(ConfigWidget):
    """ UI widget for editing Unicode text.
    """
    CLASS_ARGS = {'MaxLength': 'maxLength',
                  'TextLines': 'textLines'}


    def __init__(self, *args, **kwargs):
        self.textLines = 1
        super(IntField, self).__init__(*args, **kwargs)

    
    @classmethod
    def isValidChar(cls, c):
        """ Filter for characters valid in the text field. """
        # All characters are permitted in UTF-8 fields.
        return True


    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = wx.TextCtrl(self, -1, str(self.default or ''))
        self.sizer.Add(self.field, 1)
        return self.field


@field
class ASCIIField(TextField):
    """ UI widget for editing ASCII text.
    """
    @classmethod
    def isValidChar(cls, c):
        """ Filter for characters valid in the text field. """
        # Limit to printable ASCII characters.
        return c in string.printable


@field
class IntField(ConfigWidget):
    """ UI widget for editing a signed integer.
    """
    
    def __init__(self, *args, **kwargs):
        # Set some default values
        self.min = -2**16
        self.max = 2**16
        self.default = 0
        super(IntField, self).__init__(*args, **kwargs)
    
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = wx.SpinCtrl(self, -1, size=(60,-1), style=wx.SP_VERTICAL,
                                 min=self.min, max=self.max, 
                                 initial=self.default)
        self.sizer.Add(self.field, 1)
        return self.field


@field
class UIntField(IntField):
    """ UI widget for editing an unsigned integer.
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        super(UIntField, self).__init__(*args, **kwargs)
        self.min = max(0, self.min)
        self.field.SetRange(self.min, self.max)
        

@field
class FloatField(IntField):
    """ UI widget for editing a floating-point value.
    """
    
    CLASS_ARGS = {'FloatIncrement': 'increment'}
        
    def __init__(self, *args, **kwargs):
        self.increment = 0.25
        super(FloatField, self).__init__(*args, **kwargs)

        
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = wx.SpinCtrlDouble(self, -1, size=(60,-1), 
                                       inc=self.increment,
                                       min=self.min, max=self.max, 
                                       value=self.default)
        self.sizer.Add(self.field)
        return self.field


@field
class EnumField(ConfigWidget):
    """ UI widget for selecting one of several items from a list.
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        optionEls = [el for el in self.element.value if el.name=="EnumOption"]
        self.options = [EnumOption(el, self) for el in optionEls]
        
        super(EnumField, self).__init__(*args, **kwargs)

    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = wx.Choice(self, -1, choices=[o.label for o in self.options])
        self.sizer.Add(self.field, 1)
        return self.field


    def setRawValue(self, val, check=True):
        """
        """
        index = -1
        for i,o in enumerate(self.options):
            if o.value == val:
                index = i
                break
        self.field.Select(index)
        self.setCheck(check)
        self.updateToolTips()
    
    
    def updateToolTips(self):
        """ Update the tool tips on the option list to show the text for the
            selected item (if any). Options without tool tips default to that
            of their parent.
        """
        tt = self.tooltip or ''
        index = self.field.GetSelection()
        if index != wx.NOT_FOUND and index < len(self.options):
            tt = self.options[index] or tt
        self.field.SetToolTipString(tt)
    

class EnumOption(ConfigBase):
    """ One choice in an enumeration (e.g. an item in a drop-down list). Note:
        unlike the other classes, this is not itself a UI widget.
    """
    
    def __init__(self, element, parent, **kwargs):
        """ Constructor.
            @keyword element: The EBML element for which the enumeration option
                is being generated.
            @param parent: The parent `EnumField`. 
        """
        super(EnumOption, self).__init__(element, parent, **kwargs)
        
        # a little syntactic sugar: create some more contextually-appropriate 
        # attribute names. 
        self.value = self.default
        self.parent = self.root
    
    
@field
class DateTimeField(IntField):
    """ UI widget for editing a date/time value.
    """
    
    def addField(self):
        self.field = DateTimeCtrl(self, -1)
        self.sizer.Add(self.field, 1)
        return self.field


@field
class UTCOffsetField(IntField):
    """ Special-case UI widget for entering the local UTC offset, with the
        ability to get the value from the computer.
    """
    
    def addField(self):
        p = wx.Panel(self, -1)
        innerSizer = wx.BoxSizer(wx.HORIZONTAL)
        innerSizer.Add(p, 1)
        
        self.field = wx.SpinCtrlDouble(p, -1, size=(60,-1), 
                                       inc=0.25,
                                       min=-12, max=12, 
                                       value=self.default)
        self.getOffsetBtn = wx.Button(p, -1, "Get Local Offset")
        innerSizer.Add(self.field, 1)
        innerSizer.Add(self.getOffsetBtn, 0)
        
        p.SetSizer(innerSizer)
        self.sizer.Add(p, 1)
        
        self.getOffsetBtn.Bind(wx.EVT_BUTTON, self.OnGetOffset)
        
        return p

    
    def OnGetOffset(self, evt):
        """
        """
        # XXX: IMPLEMENT OnGetOffset()!


@field
class BinaryField(ConfigWidget):
    """ Special-case UI widget for selecting binary data.
        FOR FUTURE IMPLEMENTATION.
    """
    

#===============================================================================
#--- Check fields 
# Container fields excluded (see below).
#===============================================================================

@field
class CheckTextField(TextField):
    """ UI widget (with a checkbox) for editing Unicode text.
    """
    CHECK = True


@field
class CheckASCIIField(ASCIIField):
    """ UI widget (with a checkbox) for editing ASCII text.
    """
    CHECK = True
    

@field
class CheckIntField(IntField):
    """ UI widget (with a checkbox) for editing a signed integer.
    """
    CHECK = True


@field
class CheckUIntField(UIntField):
    """ UI widget (with a checkbox) for editing an unsigned integer.
    """
    CHECK = True


@field
class CheckFloatField(FloatField):
    """ UI widget (with a checkbox) for editing a floating-point value.
    """
    CHECK = True


@field
class CheckEnumField(EnumField):
    """ UI widget (with a checkbox) for selecting one of several items from a 
        list.
    """
    CHECK = True


@field
class CheckDateTimeField(DateTimeField):
    """ UI widget (with a checkbox) for editing a date/time value.
    """
    CHECK = True


@field
class CheckUTCOffsetField(UTCOffsetField):
    """ Special-case UI widget (with a checkbox) for entering the local UTC 
        offset, with the ability to get the value from the computer.
    """
    CHECK = True


@field
class CheckBinaryField(BinaryField):
    """ Special-case UI widget (with a checkbox) for selecting binary data.
        FOR FUTURE IMPLEMENTATION.
    """
    CHECK = True
 

#===============================================================================
#--- Container fields 
#===============================================================================

class ConfigContainer(ConfigPanel):
    """
    """
    # Do the contents of the panel appear indented?
    INDENT = False
    
    @classmethod
    def getWidgetClass(cls, el):
        """
        """
        if not cls.isField(el):
            return None
        try:
            return FIELD_TYPES[el.name]
        except KeyError:
            # TODO: try to use 'generic' field for type based on low bits of ID
            raise NameError("Unknown field type: %s" % el.name)
    
    
    @classmethod
    def isField(cls, el):
        """
        """
        # TODO: determine if the element is a field based on its ID.
        return el.name.endswith('Field')
    
        
    def __init__(self, *args, **kwargs):
        """
        """
        kwargs.setdefault('root', kwargs.pop('root', self))
        super(ConfigContainer, self).__init__(*args, **kwargs)
        
        self.widgets = []
        
        self.initUi()
        
        
    def initUi(self):
        """
        """
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        for el in self.element.value:
            cls = self.getWidgetClass(el)
            if cls is None:
                continue
            widget = cls(self, -1, element=el, root=self.root)
            self.widgets.append[widget]
            sizer.Add(widget, 1)

        if self.INDENT:
            outersizer = wx.BoxSizer(wx.HORIZONTAL)
            outersizer.Add(sizer, 1, wx.WEST, 24)
            self.SetSizer(outersizer)
        else:
            self.SetSizer(sizer)
        


class Tab(ConfigContainer):
    """ One tab of configuration items. All configuration dialogs contain
        at least one.
    """


@field
class Group(ConfigContainer):
    """ A group of configuration items. Its children appear indented.
    """
    INDENT = True


@field
class CheckGroup(Group):
    """ A group of configuration items with a checkbox to enable/disable them
        all. Children appear indented.
    """
    CHECK = True


#===============================================================================
# 
#===============================================================================

