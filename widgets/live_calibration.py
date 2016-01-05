'''
Module widgets.live_calibration

Created on Jan 5, 2016
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2016 Mide Technology Corporation"

import wx
import wx.lib.sized_controls as SC

from devices import SlamStickX
from config_dialog.ssx import EditableCalibrationPanel

#===============================================================================
# 
#===============================================================================

class LiveCalibrationDialog(SC.SizedDialog):
    """ The parent dialog for all the recorder configuration tabs. 
    
        @todo: Choose the tabs dynamically based on the recorder type, once
            there are multiple types of recorders using the MIDE format.
    """
    
    ID_IMPORT = wx.NewId()
    ID_EXPORT = wx.NewId()
    
    ICON_INFO = 0
    ICON_WARN = 1
    ICON_ERROR = 2
    
    FIELD_PAD = 8 # Padding for use when calculating field height
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        self.doc = self.root.dataset
        self.dev = SlamStickX.fromRecording(self.doc)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | \
            wx.MINIMIZE_BOX | wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
        
        super(LiveCalibrationDialog, self).__init__(*args, **kwargs) 

        if not hasattr(self.doc, 'originalTransforms'):
            self.doc.originalTransforms = {c.id: c.copy() for c in self.doc.transforms.values()}
            
        pane = self.GetContentsPane()
        
        self.calList = EditableCalibrationPanel(pane, -1, root=self.root,
                                                channels=self.doc.channels,
                                                factoryCal=self.doc.originalTransforms,
                                                editable=True, info=self.doc.transforms,
                                                style=wx.BORDER_THEME)
        self.calList.SetSizerProps(expand=True, proportion=-1)

        # This stuff is just to create non-standard buttons, right aligned,
        # with a gap. It really should not be this hard to do. This approach is
        # probably not optimal or properly cross-platform.
        SC.SizedPanel(self.GetContentsPane(), -1, size=(8,self.FIELD_PAD))
        
        buttonpane = SC.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
        wx.Button(buttonpane, self.ID_IMPORT, "Import...").SetSizerProps(halign="left")
        wx.Button(buttonpane, self.ID_EXPORT, "Export...").SetSizerProps(halign="left")
        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        self.Bind(wx.EVT_BUTTON, self.importCal, id=self.ID_IMPORT)
        self.Bind(wx.EVT_BUTTON, self.exportCal, id=self.ID_EXPORT)
        wx.Button(buttonpane, wx.ID_APPLY).SetSizerProps(halign="right")
        wx.Button(buttonpane, wx.ID_CANCEL).SetSizerProps(halign="right")
        
        self.SetAffirmativeId(wx.ID_APPLY)
        self.okButton = self.FindWindowById(wx.ID_APPLY)
        
        self.SetMinSize((400, 500))
        self.Fit()
        self.SetSize((560,560))
    
    
    def importCal(self, evt=None):
        done = False
        filename = None
        dlg = wx.FileDialog(self, 
                            message="Choose an exported calibration file",
                            wildcard=("Exported calibration file (*.cal)|*.cal|"
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
                        cal = self.dev.getUserCalPolynomials(filename)
                        self.calList.info = cal
                        self.calList.updateCalDisplay()
                        done = True
                    except Exception as err:
                        print err
                
            except ValueError:
                # TODO: More specific error message (wrong device type
                # vs. not a config file
                if filename is None:
                    msg = "Could not read calibration file."
                else:
                    msg = "Could not read calibration file '%s'!" % filename
                md = wx.MessageBox(msg, parent=self,
                                   style=wx.OK | wx.CANCEL | wx.ICON_EXCLAMATION) 
                done = md == wx.CANCEL
        dlg.Destroy()
        
    
    def exportCal(self, evt=None):
        dlg = wx.FileDialog(self, 
                            message="Export calibration",
                            wildcard=("Exported calibration file (*.cal)|*.cal|"
                                      "All files (*.*)|*.*"),
                            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.dev.writeUserCal(self.calList.info, filename=dlg.GetPath())
            except None:
                pass
            
        dlg.Destroy()


#===============================================================================
# 
#===============================================================================

def editCalibration(root):
    doc = root.dataset
    changed = False
    dlg = LiveCalibrationDialog(None, -1, root=root)
    if dlg.ShowModal() != wx.ID_CANCEL:
        doc.transforms = dlg.calList.info
        for channel in doc.channels.values():
            if channel.transform is not None:
                channel.setTransform(doc.transforms[channel.transform.id], update=False)
            for subchannel in channel.subchannels:
                if subchannel.transform is not None:
                    subchannel.setTransform(doc.transforms[subchannel.transform.id], update=False)
        doc.updateTransforms()
        changed = True
    dlg.Destroy()
    return changed


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    from mide_ebml.importer import importFile
    
    class TestApp(wx.App):
        dataset = importFile()
        
        def getPref(self, name, default=None):
            if name == 'showAdvancedOptions':
                return True
            return default
    
    _app = TestApp()
    print "original transforms:",_app.dataset.transforms
    editCalibration(_app)
    print "      after editing:",_app.dataset.transforms
        