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
from __future__ import absolute_import, print_function

import errno
import os

import wx
import wx.lib.sized_controls as SC

from common import makeBackup, restoreBackup
from mide_ebml.ebmlite import loadSchema

import devices

from .base import __DEBUG__, logger
from . import base

# Widgets. Even though these modules aren't used directly, they need to be
# imported so that their contents can get into the `base.TAB_TYPES` dictionary.
from . import classic
from . import legacy
from . import wifi_tab


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
        self.schema = loadSchema('config_ui.xml')

        self.setTime = kwargs.pop('setTime', True)
        self.device = kwargs.pop('device', None)
        self.keepUnknown = kwargs.pop('keepUnknownItems', False)
        self.saveOnOk = kwargs.pop('saveOnOk', True)
        self.useUtc = kwargs.pop('useUtc', True)
        self.showAdvanced = kwargs.pop('showAdvanced', False)
        
        self.postConfigMessage = None
                
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
        self.configValues = base.ConfigContainer(self)
        self.displayValues = base.DisplayContainer(self)
        
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
        self.SetSize((620, 700))


    def buildUI(self):
        """ Construct and populate the UI based on the ConfigUI element.
        """
        for el in self.hints[0]:
            if el.name in base.TAB_TYPES:
                tabType = base.TAB_TYPES[el.name]
                tab = tabType(self.notebook, -1, element=el, root=self)
                
                if not tab.isAdvancedFeature or self.showAdvanced:
                    self.notebook.AddPage(tab, str(tab.label))
                    self.tabs.append(tab)
            elif el.name == "PostConfigMessage":
                self.postConfigMessage = el.value


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
            self.hints = self.schema.load(filename)
        

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
        # TODO: Configuration handling, including format/version detection,
        # should be in the Recorder class. 'old' and 'new' are relative.
        self.devUsesOldConfig = getattr(self.device, 'usesOldConfig', False)
        self.devUsesNewConfig = getattr(self.device, 'usesNewConfig', True)
        
        # Mostly for testing. Will probably be removed.
        if self.device is None:
            self.configData = self.origConfigData = {}
            return self.configData
        
        # First, try to get the new config ID/value data.
        self.useLegacyConfig = not self.devUsesNewConfig
        self.configData = self.device.getConfigItems()
        if not self.configData:
            # Try to get the legacy config data.
            if self.device.getConfig():
                self.configData = legacy.loadConfigData(self.device)
                self.useLegacyConfig = True
            else:
                # No config data. Use version appropriate for FW version.
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

        if self.useLegacyConfig and self.devUsesNewConfig:
            self.useLegacyConfig = legacy.useLegacyFormatPrompt(self)
        
        try:
            if self.useLegacyConfig:
                return legacy.saveConfigData(self.configData, self.device)
            
            values = []
            for k,v in self.configData.items():
                if k not in self.configItems:
                    # TODO: Keep value types of unknown config file items, so
                    # they can be written back. For now, just skip.
                    continue
                elType = self.configItems[k]
                if elType.valueType is not None:
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
                            style=wx.FD_OPEN|wx.FD_CHANGE_DIR|wx.FD_FILE_MUST_EXIST,
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
                        md = self.showError( 
                            "The selected file does not appear to be a  "
                            "valid configuration file for this device.", 
                            "Invalid Configuration", 
                            style=wx.OK | wx.CANCEL | wx.ICON_EXCLAMATION) 
                    else:
                        s = "an older" if cvers < dvers else "a newer"
                        md = self.showError(
                             "The selected file was exported from %s "
                             "version of %s.\nImporting it may cause "
                             "problems.\n\nImport anyway?" % (s, cname), 
                             "Configuration Version Mismatch",  
                             style=wx.YES_NO|wx.NO_DEFAULT|wx.ICON_EXCLAMATION)
                        if md == wx.YES:
                            self.device.importConfig(filename, 
                                                     allowOlder=True, 
                                                     allowNewer=True)

        except ValueError:
            # TODO: More specific error message (wrong device type
            # vs. not a config file
            md = self.showError( 
                "The selected file does not appear to be a valid "
                "configuration file for this device.", 
                "Invalid Configuration", 
                style=wx.OK | wx.ICON_EXCLAMATION) 
            
        dlg.Destroy()

    
    def OnExportButton(self, evt):
        """ Handle the "Import..." button.
         
            @todo: Refactor to support new config format (means modifying 
                things in the `devices` module).
        """ 
        dlg = wx.FileDialog(self, message="Export Device Configuration", 
                            style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT, 
                            wildcard=("Exported config file (*.cfx)|*.cfx|"
                                      "All files (*.*)|*.*"))
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.device.exportConfig(dlg.GetPath(), data=self.getData())
                    
            except Exception as err:
                # TODO: More specific error message
                logger.error('Could not export configuration (%s: %s)' % 
                             (err.__class__.__name__, err))
                self.showError( 
                    "The configuration data could not be exported to the "
                    "specified file.", "Config Export Failed", 
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
        
        except (IOError, WindowsError) as err:
            msg = ("An error occurred when trying to update the recorder's "
                   "configuration data.\n\n")
            if err.errno == errno.ENOENT:
                msg += "The recorder appears to have been removed"
            else:
                msg += os.strerror(err.errno)
                 
            if self.showAdvanced:
                if err.errno in errno.errorcode:
                    msg += " (%s)" % errno.errorcode[err.errno]
                else:
                    msg += " (error code %d)" % err.errno
             
            if not msg.endswith(('.', '!')):
                msg += "."
             
            self.showError(msg, "Configuration Error")
            evt.Skip()
            return
        
        except Exception as err:
            if __DEBUG__:
                raise
            
            msg = ("An unexpected %s occurred when trying to update the "
                   "recorder's configuration data.\n\n" % err.__class__.__name__)
            if self.showAdvanced:
                msg += "%s" % str(err).capitalize()

            if not msg.endswith(('.', '!')):
                msg += "."

            self.showError(msg, "Configuration Error")
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
                self.showError("The recorder's clock could not be set.", 
                              "Configure Device", 
                              style=wx.OK|wx.OK_DEFAULT|wx.ICON_WARNING)
                
        evt.Skip()


    def OnCancel(self, evt):
        """ Handle dialog cancel, prompting the user to save any changes.
        """
        if self.configChanged():
            q = self.showError("Save configuration changes before exiting?",
                              "Configure Device", 
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
        

    def showError(self, msg, caption, style=wx.OK|wx.OK_DEFAULT|wx.ICON_ERROR,
                  err=None):
        """ Show an error message. Wraps the standard message box to add some
            debugging stuff.
        """
        q = wx.MessageBox(msg, caption, style=style, parent=self)
        if wx.GetKeyState(wx.WXK_CONTROL) and wx.GetKeyState(wx.WXK_SHIFT):
            raise
        if err is not None:
            logger.debug("%s: %r" % (msg, err))
        return q

#===============================================================================
# 
#===============================================================================

def configureRecorder(path, setTime=True, useUtc=True, parent=None,
                      keepUnknownItems=True, hints=None, saveOnOk=True, 
                      modal=True, showAdvanced=False):
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
        @return: `None` if configuration was cancelled, else a tuple 
            containing:
                * The data written to the recorder (a nested dictionary)
                * Whether `setTime` was checked before save
                * Whether `useUTC` was checked before save
                * The configured device itself
                * The post-configuration message (could be `None`)
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
#     global dlg
    dlg = ConfigDialog(parent, hints=hints, device=dev, setTime=setTime,
                       useUtc=useUtc, keepUnknownItems=keepUnknownItems,
                       saveOnOk=saveOnOk, showAdvanced=showAdvanced)
    
    if modal:
        dlg.ShowModal()
    else:
        dlg.Show()
    
    result = dlg.configData
    setTime = dlg.setClockCheck.GetValue()
    useUtc = dlg.useUtc
    msg = dlg.postConfigMessage or getattr(dev, "POST_CONFIG_MSG", None)
    
    if not modal:
        return dlg
    
    dlg.Destroy()
    
    if result is None:
        return None
    
    return result, setTime, useUtc, dev, msg
