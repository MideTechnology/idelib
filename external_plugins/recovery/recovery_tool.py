import locale
import os.path
from time import time

import wx
import  wx.lib.filebrowsebutton as FB

from mide_ebml import recovery
from tools.base import ToolDialog
from __builtin__ import True

#===============================================================================
# Plugin information. Used by plugin creation utility to generate manifest data
#===============================================================================

__author__ = "D. R. Stokes"
__email__ = "dstokes@mide.com"
__version_tuple__ = (0,1,0)
__version__= ".".join(map(str, __version_tuple__))
__copyright__=u"Copyright (c) 2017 Mid\xe9 Technology"


PLUGIN_INFO = {"type": "tool",
               "name": "IDE Data Recovery Tool",
               "app": u"Slam\u2022Stick Lab",
               "minAppVersion": (1,8,0),
               }

#===============================================================================
# 
#===============================================================================

class SimpleProgressDialog(wx.ProgressDialog):
    """ An update dialog, compatible with the recovery update callback.
    """

    UPDATE_INTERVAL = .5

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('style', (  wx.PD_APP_MODAL
                                    #| wx.PD_CAN_ABORT
                                    | wx.PD_ESTIMATED_TIME
                                    | wx.PD_REMAINING_TIME
                                    ))
        kwargs.setdefault('maximum', 1000)
        
        wx.ProgressDialog.__init__(self, *args, **kwargs)
        self.nextUpdate = 0
        self.lastValue = -1

    
    def __call__(self, pos, recovered, filesize):
        """
        """
        cancelled = self.WasCancelled()
        if cancelled:
            return True
        
        t = time()
        if t <= self.nextUpdate:
            return
        self.nextUpdate = t + self.UPDATE_INTERVAL
        
        done = int(((pos+0.0)/filesize) * 1000)
        if done != self.lastValue:
            num = locale.format("%d", recovered, grouping=True)
            cancelled = not self.Update(done, "Data blocks recovered: %s" % num)
            
        self.lastValue = done
        return cancelled


#===============================================================================
# 
#===============================================================================

class RecoveryTool(ToolDialog):
    """
    """
    TITLE = "IDE Data Recovery Tool"

    DEFAULT_OUTPUT = "recovered.IDE"
    MODES = ("Normal (may be faster)",
             "Thorough (may recover more data)")

    def __init__(self, *args, **kwargs):
        """
        """
        super(RecoveryTool, self).__init__(*args, **kwargs)
        
        pane = self.GetContentsPane()
        pane.SetSizerType("form")
        
        self.lastInput = ''
        self.progress = None

        wx.StaticText(pane, -1, "Input File:").SetSizerProps(valign='center')
        self.inputField = FB.FileBrowseButton(pane, -1,  labelText="",
            changeCallback=self.OnInputSelected, fileMask="*.IDE", 
            fileMode=wx.FD_OPEN|wx.FD_CHANGE_DIR|wx.FD_FILE_MUST_EXIST)
        self.inputField.SetSizerProps(expand=True)
        
        wx.StaticText(pane, -1, "Output File:").SetSizerProps(valign='center')
        self.outputField = FB.FileBrowseButton(pane, -1, labelText="",
            initialValue=self.DEFAULT_OUTPUT, fileMask="*.IDE",
            fileMode=wx.FD_SAVE|wx.CHANGE_DIR)#|wx.FD_OVERWRITE_PROMPT)
        self.outputField.SetSizerProps(expand=True)

        wx.StaticText(pane, -1, "Recovery Mode:").SetSizerProps(valign='center')
        self.modeChoice = wx.Choice(pane, -1, choices=self.MODES)
        self.modeChoice.SetSizerProps(expand=True)
        self.modeChoice.SetSelection(self.getPref('mode', 0))

        self.addBottomButtons()
        
        self.Fit()
        self.SetMinSize((500, self.GetSizeTuple()[1]))
        self.Layout()
        self.Centre()


    def makeOutName(self, filename):
        """
        """
        if not filename:
            return self.DEFAULT_OUTPUT
        try:
            base, ext = os.path.splitext(filename)
            return base + "_recovered" + ext
        except (AttributeError, TypeError):
            return self.DEFAULT_OUTPUT
        

    def OnInputSelected(self, evt):
        """
        """
        filename = evt.GetString()
        out = self.outputField.GetValue()

        if out == self.DEFAULT_OUTPUT or out == self.makeOutName(self.lastInput):
            self.outputField.SetValue(self.makeOutName(filename))
    
        self.lastInput = filename

    
    #===========================================================================
    # 
    #===========================================================================
    
    def run(self, evt=None):
        """
        """
        inputFile = self.inputField.GetValue()
        outputFile = self.outputField.GetValue()
        fast = bool(self.modeChoice.GetSelection())
        unknown = False # TODO: Make this an option?

        inBase = os.path.basename(inputFile)
        outBase = os.path.basename(outputFile)

        if not inBase:
            wx.MessageBox("No source file selected!" % inBase, 
                          "IDE Data Recovery", style=wx.OK|wx.ICON_EXCLAMATION)
            return

        if not outBase:
            wx.MessageBox("No output file selected!" % inBase, 
                          "IDE Data Recovery", style=wx.OK|wx.ICON_EXCLAMATION)
            return

        if not os.path.exists(inputFile):
            wx.MessageBox("The file %s does not exist." % inBase, 
                          "IDE Data Recovery", style=wx.OK|wx.ICON_EXCLAMATION)
            return

        if os.path.realpath(inputFile) == os.path.realpath(outputFile):
            wx.MessageBox("The input name and the output name cannot be identical.", 
                          "IDE Data Recovery", style=wx.OK|wx.ICON_EXCLAMATION)
            return

        if os.path.exists(outputFile):
            q = wx.MessageBox("The output file %s already exists.\n"
                              "Do you want to replace it?" % outBase,
                              "IDE Data Recovery", parent=self, 
                              style=wx.YES_NO|wx.NO_DEFAULT|wx.ICON_EXCLAMATION)
            if q == wx.NO:
                return
        
        self.progress = SimpleProgressDialog(
                     "Recovering Data from %s" % os.path.basename(inputFile), 
                     "Recovering data from %s" % inputFile,
                     parent=self)
        
        recovery.recoverData(inputFile, outputFile, fast=fast, 
                             unknown=unknown, callback=self.progress)

        wx.Yield()
        self.progress.Destroy()


#===============================================================================
# 
#===============================================================================

def launch(parent=None):
    dlg = RecoveryTool(parent, -1, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
    dlg.ShowModal()
    

def init(*args, **kwargs):
    return launch


#===============================================================================
# 
#===============================================================================


def test(*args, **kwargs):
    class TestApp(wx.App):
        def __init__(self, *args, **kwargs):
            super(TestApp, self).__init__(*args, **kwargs)
            self.locale = wx.Locale(wx.LANGUAGE_ENGLISH_US)
            
        def getPref(self, name, default=None, section=None):
            print "getPref %s.%s" % (section, name)
            if 'defaultDir' in name:
                return u'C:\\Users\\dstokes\\workspace\\SSXViewer\\test_recordings'
            return default
    
        def setPref(self, name, val, section=None, persistent=True):
            print "setPref %s.%s = %r" % (section, name, val)
            return val
        
        def deletePref(self, name=None, section=None):
            print "deletePref %s.%s" % (section, name)
            pass

        
    _app = TestApp()
    dlg = RecoveryTool(None, -1, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
    dlg.ShowModal()
    print dlg.GetSize()

if __name__ == "__main__":
    test()