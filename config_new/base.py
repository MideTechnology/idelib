'''
New, modular configuration system. Dynamically creates the UI based on the new 
"UI Hints" data. The UI is described in EBML; UI widget classes have the same
names as the elements. The crucial details of the widget type are also encoded
into the EBML ID; in the future, this will be used to create appropriate 
default widgets for new elements.

Created on Jul 6, 2017

TODO: Finish this! Requires the schema to be completed, and some test EBML
    generated.
TODO: Make sure all the items have reasonable sizes compared to each other.
'''
from wx import MessageDialog

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

# from collections import OrderedDict

from fnmatch import fnmatch
import string

import wx
import wx.lib.filebrowsebutton as FB
import wx.lib.scrolledpanel as SP
import wx.lib.sized_controls as SC

from widgets.shared import DateTimeCtrl

from mide_ebml.ebmlite import Schema


#===============================================================================
#--- Utility functions
#===============================================================================

# Dictionary of all known field types. The `@field` class decorator adds them.
# See `field()` decorator function, below.
FIELD_TYPES = {}


def field(cls):
    """ Class decorator for registering configuration field types.
    """
    global FIELD_TYPES
    FIELD_TYPES[cls.__name__] = cls
    return cls

#===============================================================================
# 
#===============================================================================

class TextValidator(wx.PyValidator):
    """ Validator for TextField and ASCIIField text widgets.
    
        @todo: Make it validate pasted text (currently only validates typing).
    """
    
    def __init__(self, validator=None, maxLen=None):
        """ Instantiate a text field validator.
        
            @keyword validChars: A string of chars 
        """
        self.maxLen = maxLen
        self.isValid = validator 
        wx.PyValidator.__init__(self)
        self.Bind(wx.EVT_CHAR, self.OnChar)


    def Clone(self):
        return TextValidator(self.isValid, self.maxLen)
    
    
    def TransferToWindow(self):
        """ Required in wx.PyValidator subclasses. """
        return True
    
    
    def TransferFromWindow(self):
        """ Required in wx.PyValidator subclasses. """
        return True
    
    
    def Validate(self, win):
        return self.isValid(self.GetWindow().GetValue())


    def OnChar(self, event):
        key = event.GetKeyCode()
        char = unichr(key)
        tc = self.GetWindow()
        val = tc.GetValue()

        if key < wx.WXK_SPACE or key == wx.WXK_DELETE:
            event.Skip()
            return

        if self.isValid(char) and len(val) < self.maxLen:
            event.Skip()
            return

        if not wx.Validator_IsSilent():
            wx.Bell()

        # Returning without calling even.Skip eats the event before it
        # gets to the text control
        return
    
    
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
        
        # Convert element children to object attributes
        args = self.ARGS.copy()
        args.update(self.CLASS_ARGS)
        for v in args.values():
            if not hasattr(self, v):
                setattr(self, v, None)
        
        for el in self.element.value:
            if el.name in FIELD_TYPES:
                # Child field: skip now, handle later (if applicable)
                continue
            elif el.name in args:
                # Known element name (verbatim): set attribute
                setattr(self, args[el.name], el.value)
            else:
                # Match wildcards and set attribute
                for k,v in args.items():
                    if fnmatch(el.name, k):
                        setattr(self, v, el.value)

        # Default expressions for converting values between native and display
        if not self.displayFormat:
            self.displayFormat = self.noEffect
        else:
            self.displayFormat = eval("lambda x: %s" % self.displayFormat)
        if not self.valueFormat:
            self.valueFormat = self.noEffect
        else:
            self.valueFormat = eval("lambda x: %s" % self.displayFormat)


    def isEnabled(self):
        """ Check the Field's `disableIf` expression (if any) to determine if
            the Field should be enabled.
        """
        if self.disableIf is None:
            return True
        return not eval(self.disableIf, {'config': self.root.config})
        


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
                being generated.
            @keyword root: The main dialog.
            @keyword group: The parent group containing the Field.
        """
        element = kwargs.pop('element', None)
        root = kwargs.pop('root', None)
        self.group = kwargs.pop('group', None)
        
        ConfigBase.__init__(self, element, root)
        wx.Panel.__init__(self, *args, **kwargs)

        self.initUi()
    
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
            Separated from `initUi()` for subclassing. This method should be 
            overridden in subclasses.
        """
        self.field = None
        p = wx.Panel(self, -1)
        self.sizer.Add(p, 3)
        return p

    
    def initUi(self):
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
            self.setRawValue(self.default, check)
            
        self.setCheck(check)

        
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

@field
class BooleanField(ConfigWidget):
    """ UI widget for editing a Boolean value. This is a special case; although
        it is a checkbox, it is not considered a 'check' field
    """
    CHECK = True


    def setRawValue(self, val):
        """
        """
        self.checkbox.SetValue(bool(val))
    
    
    def getRawValue(self):
        """ 
        """
        return self.checkbox.GetValue()


@field
class TextField(ConfigWidget):
    """ UI widget for editing Unicode text.
    """
    CLASS_ARGS = {'MaxLength': 'maxLength',
                  'TextLines': 'textLines'}

    UNITS = False
    
    # String of valid characters. 'None' means all are valid.
    VALID_CHARS = None

    def __init__(self, *args, **kwargs):
        self.textLines = 1
        super(TextField, self).__init__(*args, **kwargs)

    
    def isValid(self, s):
        """ Filter for characters valid in the text field. """
        # All characters are permitted in UTF-8 fields.
        if self.VALID_CHARS is None:
            return True
        return all(c in self.VALID_CHARS for c in s)


    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        validator = TextValidator(self.isValid, self.maxLength)
#         self.textLines=4
        if self.textLines > 1:
            self.field = wx.TextCtrl(self, -1, str(self.default or ''),
                                     style=wx.TE_MULTILINE|wx.TE_PROCESS_ENTER,
                                     validator=validator)
#             s = self.field.GetSize()
#             self.field.SetSizeWH(-1, s[1] * self.textLines)
        else:
            self.field = wx.TextCtrl(self, -1, str(self.default or ''),
                                     validator=validator)
            
        self.sizer.Add(self.field, 3)
        return self.field


@field
class ASCIIField(TextField):
    """ UI widget for editing ASCII text.
    """
    
    # String of valid characters, limited to the printable part of 7b ASCII.
    VALID_CHARS = string.printable



@field
class IntField(ConfigWidget):
    """ UI widget for editing a signed integer.
    """
    
    def __init__(self, *args, **kwargs):
        """ 
        """
        # Set some default values
        self.min = -2**16
        self.max = 2**16
        self.default = 0
        super(IntField, self).__init__(*args, **kwargs)
    
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = wx.SpinCtrl(self, -1, size=(40,-1), 
                                 style=wx.SP_VERTICAL|wx.TE_RIGHT,
                                 min=self.min, max=self.max, 
                                 initial=self.default)
        self.sizer.Add(self.field, 2)
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
        """ 
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


@field
class EnumField(ConfigWidget):
    """ UI widget for selecting one of several items from a list.
    """
        
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
        """
        optionEls = [el for el in self.element.value if el.name=="EnumOption"]
        self.options = [EnumOption(el, self) for el in optionEls]
        choices = [u"%s" % o.label for o in self.options]
        
        self.field = wx.Choice(self, -1, choices=choices)
        self.sizer.Add(self.field, 3)
        
        self.Bind(wx.EVT_CHOICE, self.OnChoice)
        return self.field


    def OnChoice(self, evt):
        """ Handle option selected.
        """
        self.updateToolTips()
        evt.Skip()
        

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
            tt = self.options[index].tooltip or tt
            
        self.field.SetToolTipString(tt)

        
        

class EnumOption(ConfigBase):
    """ One choice in an enumeration (e.g. an item in a drop-down list). Note:
        unlike the other classes, this is not itself a UI field.
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
        """ Class-specific method for adding the appropriate type of widget.
        """
        self.field = DateTimeCtrl(self, -1)
        self.sizer.Add(self.field, 3)
        return self.field


@field
class UTCOffsetField(IntField):
    """ Special-case UI widget for entering the local UTC offset, with the
        ability to get the value from the computer.
    """
    
    def addField(self):
        """ Class-specific method for adding the appropriate type of widget.
            The UTC offset field consists of a 'spinner' control and a button.
        """
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
        """ Handle button press: get the computer's local UTC offset.
        """
        # XXX: IMPLEMENT OnGetOffset()!


@field
class BinaryField(ConfigWidget):
    """ Special-case UI widget for selecting binary data.
        FOR FUTURE IMPLEMENTATION.
    """
    
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

@field
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
    
    
    @classmethod
    def getWidgetClass(cls, el):
        """ Get the appropriate class for an EBML *Field element. Elements
            without a specialized subclass will get a generic widget for their
            basic data type.
            
            Note: does not handle IDs not present in the schema!
        """
        if el.name in FIELD_TYPES:
            return FIELD_TYPES[el.name]
        
        elif el.id & 0xFF00 == 0x4000:
            # All field EBML IDs have 0x40 as their 2nd byte.
            baseId = el.id & 0x00FF
            if baseId in cls.DEFAULT_FIELDS:
                return cls.DEFAULT_FIELDS[baseId]
            else:
                raise NameError("Unknown field type: %s" % el.name)
        
        return None
    
    
    def addField(self):
        """ Create all child fields. Returns a sizer containing the children.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)
            
        for el in self.element.value:
            cls = self.getWidgetClass(el)
            if cls is None:
                # Not a field (could be Label, ConfigID, etc.)
                continue
            
            # XXX: REMOVE
            if not el.value:
                continue
            
            widget = cls(self, -1, element=el, root=self.root, group=self)
            self.fields.append(widget)
            sizer.Add(widget, 0, wx.ALIGN_LEFT|wx.EXPAND|wx.ALL, border=4)
        
        return sizer

            
    def initUi(self):
        """ Build the user interface, adding the item label and/or checkbox
            (if applicable) and all the child Fields.
        """
        self.fields = []
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        if self.LABEL:
            if self.CHECK:
                self.checkbox = wx.CheckBox(self, -1, self.label or '')
                label = self.checkbox
                self.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.checkbox)
                self.enableChildren(False)
            else:
                self.checkbox = None
                label = wx.StaticText(self, -1, self.label or '')
        
            sizer.Add(label, 0, wx.NORTH, 4)
            label.SetFont(label.GetFont().Bold())

        sizer.Add(self.addField(), 1, wx.WEST|wx.EXPAND, 24)
        self.SetSizer(sizer)
        

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

        
@field
class CheckGroup(Group):
    """ A labeled group of configuration items with a checkbox to enable or 
        disable them all. Children appear indented.
    """
    CHECK = True


class Tab(SP.ScrolledPanel, Group):
    """ One tab of configuration items. All configuration dialogs contain at 
        least one. The Tab's label is used as the name shown on the tab.
    """
    LABEL = False
    CHECK = False

    def __init__(self, *args, **kwargs):
        """
        """
        element = kwargs.pop('element', None)
        root = kwargs.pop('root', self)
        
        # Explicitly call __init__ of base classes to avoid ConfigWidget stuff
        ConfigBase.__init__(self, element, root)
        SP.ScrolledPanel.__init__(self, *args, **kwargs)

        self.SetupScrolling()

        self.initUi()


    def initUi(self):
        """ 
        """
        self.fields = []
        self.SetSizer(self.addField())


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
            devName = "Recorder"

        kwargs.setdefault("title", "Configure %s" % devName)
        
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        # XXX: TEMP - eventually, get this from the device.
        self.hints = kwargs.pop('hints', None)
                
        super(ConfigDialog, self).__init__(*args, **kwargs)

        self.loadConfigData()
        self.buildUI()
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK|wx.CANCEL))
        self.Bind(wx.EVT_BUTTON, self.OnOK, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
        
        self.Fit()
        self.SetMinSize((500, 400))
        self.SetSize((680, 600))


    def buildUI(self):
        """ Construct and populate the UI based on the ConfigUI element.
        """
        pane = self.GetContentsPane()
        self.notebook = wx.Notebook(pane, -1)
        self.notebook.SetSizerProps(expand=True, proportion=-1)

        for el in self.hints.roots[0]:
            if el.name == "Tab":
                tab = Tab(self.notebook, -1, element=el, root=self)
                self.notebook.AddPage(tab, str(tab.label))


    def loadConfigData(self):
        """ Load config data from the recorder.
        """
        print "XXX: Implement loadConfig()"
        
        self.configData = {}
        self.origConfigData = None #self.configData.copy()
    
    
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
        print "%s %s:" % ((" "*indent*2), el.name),
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
    schema = Schema("../mide_ebml/ebml/schema/config_ui.xml")
    testDoc = schema.load('CONFIG.UI')
    crawl(testDoc)
    
    app = wx.App()
    dlg = ConfigDialog(None, hints=testDoc)
    dlg.ShowModal()
