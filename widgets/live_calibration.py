'''
Module widgets.live_calibration

Created on Jan 5, 2016
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2016 Mide Technology Corporation"

import os.path

import wx
import wx.lib.sized_controls as SC

from config_dialog.ssx import EditableCalibrationPanel
from devices import SlamStickX
from mide_ebml.ebml.schema.mide import MideDocument
from mide_ebml.parsers import CalibrationListParser

#===============================================================================
# 
#===============================================================================

class LiveCalibrationDialog(SC.SizedDialog):
    """ A dialog for editing the calibration data in the currently open 
        recording. 
    """
    
    ID_IMPORT = wx.NewId()
    ID_EXPORT = wx.NewId()
    
    IMPORT_TYPES=("Any Calibration File Type (*.cal, *.dat, *.ide)|*.cal;*.dat;*.ide|"
                  "Exported Calibration File (*.cal)|*.cal|"
                  "MIDE Recording File (*.ide)|*.ide|"
                  "User Calibration File (usercal.dat)|*.dat|"
                  "All files (*.*)|*.*")

    FIELD_PAD = 8 # Padding for use when calculating field height
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        self.doc = self.root.dataset
        self.dev = SlamStickX.fromRecording(self.doc)
        kwargs.setdefault("style", (wx.DEFAULT_DIALOG_STYLE | \
                                    wx.RESIZE_BORDER | \
                                    wx.MAXIMIZE_BOX | \
                                    wx.MINIMIZE_BOX | \
                                    wx.DIALOG_EX_CONTEXTHELP | \
                                    wx.SYSTEM_MENU))
        kwargs.setdefault("title", "Edit Calibration Polynomials")
        
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
        """
        """
        # The keyword arguments used by the error dialog, defined once to
        # tidy things up a little.
        errArgs = {'parent': self, 'caption': 'Import Error', 
                   'style': wx.OK | wx.CANCEL | wx.ICON_EXCLAMATION}
        
        filename = None
        dlg = wx.FileDialog(self, wildcard=self.IMPORT_TYPES,
                            message="Choose a file containing calibration data",
                            style=wx.OPEN|wx.CHANGE_DIR|wx.FILE_MUST_EXIST)
        
        while True:
            try:
                d = dlg.ShowModal()
                if d != wx.ID_OK:
                    # Cancel.
                    break

                filename = dlg.GetPath()
                basename = os.path.basename(filename)
                if basename.lower().endswith('.ide'):
                    cal = self.importFromRecording(filename)
                else:
                    cal = self.dev.getUserCalPolynomials(filename)
                    
                if cal is None:
                    msg = ("Could not read '%s'.\n\nThe specified file "
                           "contained no usable calibration data." % basename)
                    md = wx.MessageBox(msg, **errArgs)
                    if md == wx.CANCEL:
                        break
                elif sorted(cal.keys()) != sorted(self.calList.info.keys()):
                    msg = ("Calibration data in '%s' could not be used."
                           "\n\nCalibration IDs in the specified file "
                           "do not match those in this recording." % basename)
                    if filename.lower().endswith('.ide'):
                        msg += ("\n\nThe file may have been recorded by a "
                                "device with a different firmware "
                                "version.")
                    md = wx.MessageBox(msg, **errArgs) 
                    if md == wx.CANCEL:
                        break
                else:
                    self.calList.info = cal
                    self.calList.updateCalDisplay()
                    break
                
            except (ValueError, AttributeError, IOError):
                # TODO: More specific error message (wrong device type
                # vs. not a config file
                if filename is None:
                    msg = "Could not read calibration file."
                else:
                    msg = "Could not read '%s'." % os.path.basename(filename)
                msg += ("\n\nThe specified file may be damaged, or may contain"
                        " no usable calibration data.")
                md = wx.MessageBox(msg, **errArgs)
                if md == wx.CANCEL:
                    break
                
        dlg.Destroy()
        
    
    def exportCal(self, evt=None):
        """
        """
        dlg = wx.FileDialog(self, 
                            message="Export calibration",
                            wildcard=("Exported calibration file (*.cal)|*.cal|"
                                      "User calibration file (usercal.dat)|*.dat"),
                            style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.dev.writeUserCal(self.calList.info, filename=dlg.GetPath())
            except None:
                pass
            
        dlg.Destroy()


    def importFromRecording(self, filename):
        """ Read calibration polynomials from an IDE file.
        """
        calPolys = None
        with open(filename, 'rb') as f:
            doc = MideDocument(f)
            for el in doc.iterroots():
                if el.name == "CalibrationList":
                    calPolys = CalibrationListParser(None).parse(el)
                    if calPolys:
                        calPolys = {p.id: p for p in calPolys if p is not None}
                    break
                if 'ChannelDataBlock' in el.name:
                    break
        return calPolys


#===============================================================================
# 
#===============================================================================

def editCalibration(root):
    """ Launch the 'live' calibration editing dialog.
    
        @param root: The parent `Viewer` window.
        @return: ``True`` if changes were made, ``False`` if not. 
    """
    doc = root.dataset
    changed = False
    dlg = LiveCalibrationDialog(None, -1, root=root)
    if dlg.ShowModal() != wx.ID_CANCEL:
        doc.transforms = dlg.calList.info
        for ch in doc.channels.values():
            if ch.transform is not None:
                ch.setTransform(doc.transforms[ch.transform.id], update=False)
            for subch in ch.subchannels:
                if subch.transform is not None:
                    subch.setTransform(doc.transforms[subch.transform.id], update=False)
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
        