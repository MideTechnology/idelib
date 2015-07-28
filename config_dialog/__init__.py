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

__all__ = ['configureRecorder']

import cgi
from collections import OrderedDict
from datetime import datetime
import string
import time

import wx.lib.sized_controls as SC
from wx.html import HtmlWindow
import wx; wx = wx

from mide_ebml import util
from mide_ebml.parsers import PolynomialParser
# from mide_ebml.ebml.schema.mide import MideDocument
from common import makeWxDateTime, DateTimeCtrl, cleanUnicode
import devices

from ssx import *
from classic import *

# from base import HtmlWindow

#===============================================================================
# 
#===============================================================================

class ConfigDialog(SC.SizedDialog):
    """ The parent dialog for all the recorder configuration tabs. 
    
        @todo: Choose the tabs dynamically based on the recorder type, once
            there are multiple types of recorders using the MIDE format.
    """
    
    ID_IMPORT = wx.NewId()
    ID_EXPORT = wx.NewId()
    
    ICON_INFO = 0
    ICON_WARN = 1
    ICON_ERROR = 2
    
    def buildUI_SSX(self):
        try:
            cal = self.device.getCalibration()
            self.deviceInfo['CalibrationSerialNumber'] = cal['CalibrationSerialNumber']
            self.deviceInfo['CalibrationDate'] = cal['CalibrationDate']
            self.deviceInfo['CalibrationExpirationDate'] = self.device.getCalExpiration()
        except (AttributeError, KeyError):
            pass
        
        self.triggers = SSXTriggerConfigPanel(self.notebook, -1, root=self)
        self.options = OptionsPanel(self.notebook, -1, root=self)
        info = SSXInfoPanel(self.notebook, -1, root=self, info=self.deviceInfo)
        self.channels = ChannelConfigPanel(self.notebook, -1, root=self)
#         self.cal = CalibrationConfigPanel(self.notebook, -1, root=self)
        self.cal = CalibrationPanel(self.notebook, -1, root=self)
        
        self.notebook.AddPage(self.options, "General")
        self.notebook.AddPage(self.triggers, "Triggers")
        self.notebook.AddPage(self.channels, "Channels")
        self.notebook.AddPage(self.cal, "Calibration")
        self.notebook.AddPage(info, "Device Info")
    
    
    def buildUI_Classic(self):
        self.options = ClassicOptionsPanel(self.notebook, -1, root=self)
        self.triggers = ClassicTriggerConfigPanel(self.notebook, -1, root=self)
        info = ClassicInfoPanel(self.notebook, -1, root=self)
        self.notebook.AddPage(self.options, "General")
        self.notebook.AddPage(self.triggers, "Triggers")
        self.notebook.AddPage(info, "Device Info")


    def __init__(self, *args, **kwargs):
        self.device = kwargs.pop('device', None)
        self.root = kwargs.pop('root', None)
        self.setTime = kwargs.pop('setTime', True)
        self.useUtc = kwargs.pop('useUtc', True)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | \
            wx.MINIMIZE_BOX | wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
        
        super(ConfigDialog, self).__init__(*args, **kwargs)
        
        try:
            self.deviceInfo = self.device.getInfo()
            self.deviceConfig = self.device.getConfig()
            self._doNotShow = False
        except:# NotImplementedError:
            wx.MessageBox( 
                "The device configuration data could not be read.", 
                "Configuration Error", parent=self, style=wx.OK|wx.ICON_ERROR)
            self._doNotShow = True
            return
        
        pane = self.GetContentsPane()
        self.notebook = wx.Notebook(pane, -1)
        self.pages = []
        
        # Add pages per device
        if isinstance(self.device, devices.SlamStickX):
            self.buildUI_SSX()
        elif isinstance(self.device, devices.SlamStickClassic):
            self.buildUI_Classic()
        else:
            raise TypeError("Unknown recorder type: %r" % self.device)
        
        # Tab icon stuff
        images = wx.ImageList(16, 16)
        imageIndices = []
        for n,i in enumerate((wx.ART_INFORMATION, wx.ART_WARNING, wx.ART_ERROR)):
            images.Add(wx.ArtProvider.GetBitmap(i, wx.ART_CMN_DIALOG, (16,16)))
            imageIndices.append(n)
        self.notebook.AssignImageList(images)

        for i in xrange(self.notebook.GetPageCount()):
            icon = self.notebook.GetPage(i).tabIcon
            if icon > -1:
                self.notebook.SetPageImage(i, imageIndices[icon])
        
        self.notebook.SetSizerProps(expand=True, proportion=-1)

        buttonpane = SC.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
        wx.Button(buttonpane, self.ID_IMPORT, "Import...").SetSizerProps(halign="left")
        wx.Button(buttonpane, self.ID_EXPORT, "Export...").SetSizerProps(halign="left")
        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        self.Bind(wx.EVT_BUTTON, self.importConfig, id=self.ID_IMPORT)
        self.Bind(wx.EVT_BUTTON, self.exportConfig, id=self.ID_EXPORT)
        wx.Button(buttonpane, wx.ID_APPLY).SetSizerProps(halign="right")
        wx.Button(buttonpane, wx.ID_CANCEL).SetSizerProps(halign="right")
        
        self.SetAffirmativeId(wx.ID_APPLY)
        self.okButton = self.FindWindowById(wx.ID_APPLY)
        
        self.SetMinSize((400, 500))
        self.Fit()
        self.SetSize((480,540))
        
        
    def getData(self, schema=util.DEFAULT_SCHEMA):
        """ Retrieve the values entered in the dialog.
        """
        data = OrderedDict()
        data.update(self.options.getData())
        data.update(self.triggers.getData())
        return data


    def importConfig(self, evt=None):
        done = False
        dlg = wx.FileDialog(self, 
                            message="Choose an exported configuration file",
                            wildcard=("Exported config file (*.cfx)|*.cfx|"
                                      "All files (*.*)|*.*"),
                            style=wx.OPEN|wx.CHANGE_DIR|wx.FILE_MUST_EXIST)
        while not done:
            try:
                d = dlg.ShowModal()
                if d != wx.ID_OK:
                    done = True
                else:
                    try:
                        filename = dlg.GetPath()
                        self.device.importConfig(filename)
                        for i in range(self.notebook.GetPageCount()):
                            self.notebook.GetPage(i).initUI()
                        done = True
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
                            done = md == wx.CANCEL
                        else:
                            s = "older" if cvers < dvers else "newer"
                            md = wx.MessageBox(
                                 "The selected file was exported from a %s "
                                 "version of %s.\nImporting it may cause "
                                 "problems.\n\nImport anyway?" % (s, cname), 
                                 "Configuration Version Mismatch", parent=self, 
                                 style=wx.YES_NO|wx.NO_DEFAULT|wx.ICON_EXCLAMATION)
                            if md == wx.YES:
                                self.device.importConfig(filename, 
                                                         allowOlder=True, 
                                                         allowNewer=True)
                                done = True
    
            except ValueError:
                # TODO: More specific error message (wrong device type
                # vs. not a config file
                md = wx.MessageBox( 
                    "The selected file does not appear to be a valid "
                    "configuration file for this device.", 
                    "Invalid Configuration", parent=self,
                    style=wx.OK | wx.CANCEL | wx.ICON_EXCLAMATION) 
                done = md == wx.CANCEL
        dlg.Destroy()

    
    def exportConfig(self, evt=None):
        dlg = wx.FileDialog(self, message="Export Device Configuration", 
                            wildcard=("Exported config file (*.cfx)|*.cfx|"
                                      "All files (*.*)|*.*"),
                            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.device.exportConfig(dlg.GetPath(), data=self.getData())
            except NotImplementedError:
                # TODO: More specific error message
                wx.MessageBox( 
                    "The configuration data could not be exported to the "
                    "specified file.", "Config Export Failed", parent=self,
                    style=wx.OK | wx.ICON_EXCLAMATION)
        dlg.Destroy()


#===============================================================================
# 
#===============================================================================

def configureRecorder(path, save=True, setTime=True, useUtc=True, parent=None,
                      showMsg=True):
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
        @return: A tuple containing the data written to the recorder (a nested 
            dictionary), whether `setTime` was checked before save, and whether
            `useUTC` was checked before save. `None` is returned if the 
            configuration was cancelled.
    """
    result = None
    
    if isinstance(path, devices.Recorder):
        dev = path
        path = dev.path
    else:
        dev = devices.getRecorder(path)
        
    if not dev:
        raise ValueError("Specified path %r does not appear to be a recorder" %\
                         path)
    dlg = ConfigDialog(parent, -1, "Configure %s (%s)" % (dev.baseName, path), 
                       device=dev, setTime=setTime, useUtc=useUtc)
    
    # Sort of a hack to abort the configuration if data couldn't be read
    # (the dialog itself does it)
    
    if dlg._doNotShow:
        return
    if dlg.ShowModal() != wx.ID_CANCEL:
        useUtc = dlg.useUtc
        setTime = dlg.setTime
        data = dlg.getData()
        if save:
            try:
                dev.saveConfig(data)
            except IOError as err:
                msg = ("An error occurred when trying to update the "
                       " recorder's configuration data.")
                if err.errno == 2:
                    msg += "\nThe recorder appears to have been removed."
                wx.MessageBox(msg, "Configuration Error", wx.OK | wx.ICON_ERROR,
                              parent=parent)
        result = data, dlg.setTime, dlg.useUtc, dev
        
    dlg.Destroy()
    return result


#===============================================================================
# 
#===============================================================================


def testDialog():
    class TestApp(wx.App):
        def getPref(self, name, default=None):
            if name == 'showAdvancedOptions':
                return True
            return default
            
    _app = TestApp()
    recorderPath = devices.getDeviceList()[-1]
    print "configureRecorder() returned %r" % (configureRecorder(recorderPath, 
                                                                 useUtc=True),)

if __name__ == "__main__":
    testDialog()