'''
Created on Aug 28, 2015

@author: dstokes
'''

import locale
import math
import os.path
import sys
import time

import wx
from wx.lib.dialogs import ScrolledMessageDialog
import wx.lib.filebrowsebutton as FB
import wx.lib.sized_controls as SC

from tools.base import ToolDialog
from tools.raw2mat import ModalExportProgress
from widgets.multifile import MultiFileSelect

from splitter.filesplit import splitFile

#===============================================================================
# 
#===============================================================================

__author__ = "D. R. Stokes"
__email__ = "dstokes@mide.com"
__version_tuple__ = (1,0,1)
__version__= ".".join(map(str, __version_tuple__))
__copyright__=u"Copyright (c) 2015 Mid\xe9 Technology"


PLUGIN_INFO = {"type": "tool",
               "name": "Split IDE Files",
               "description": "Divide one or more IDE files into smaller pieces."
               }


#===============================================================================
# 
#===============================================================================

class SplitterExportProgress(ModalExportProgress):
    """ Subclass of the standard progress dialog, implementing the __call__
        method and other attributes needed for a callback (like the Loader).
    """
    def __call__(self, count=0, percent=None, total=None, error=None, 
                 starting=False, done=False, message=None, filename=None):
        if starting or done:
            self.reset()
            return
        
        if self.startTime is None:
            self.startTime = time.time()

        if percent is None:
            if total:
                percent = (count+0.0) / total
            else:
                percent = self.lastPercent

        msg = self.message or message
        if filename is not None:
            msg = "%s\nWriting %s" % (msg, filename)

        countStr = locale.format("%d", count, grouping=True)
        if total:
            totalStr = locale.format("%d", total, grouping=True)
        else:
            totalStr = "?"
        msg = "%s (%s of %s)" % (msg, countStr, totalStr)
        
        # HACK: The dialog wasn't dismissing properly for some reason, so it
        # is being opened with PD_AUTO_HIDE. Make precent smaller than 1.0
        # so the dialog doesn't disappear with the first of several files.
        percent *= .9999
        
        keepGoing, skip = super(SplitterExportProgress, self).Update(int(percent*1000), msg)
        self.cancelled = not keepGoing
        self.lastPercent = percent
        
        if filename is not None:
            self.outputFiles.add(filename)

        return keepGoing, skip


#===============================================================================
# 
#===============================================================================

class IdeSplitter(ToolDialog):
    """ The main dialog. The plan is for all tools to implement a ToolDialog,
        so the tools can be found and started in a generic manner.
    """
    TITLE = "IDE File Splitter"
    
    def __init__(self, *args, **kwargs):
        super(IdeSplitter, self).__init__(*args, **kwargs)

        pane = self.GetContentsPane()
        
        inPath = self.getPref('defaultDir', os.getcwd())
        outPath = self.getPref('outputPath', '')
        
        self.inputFiles = MultiFileSelect(pane, -1, 
                                          wildcard="MIDE Data File (*.ide)|*.ide", 
                                          defaultDir=inPath)
        self.inputFiles.SetSizerProps(expand=True, proportion=1)
        self.outputBtn = FB.DirBrowseButton(pane, -1, size=(450, -1), 
                                            labelText="Output Directory:",
                                            dialogTitle="Split Export Path",
                                            newDirectory=True,
                                            startDirectory=outPath)
        self.outputBtn.SetSizerProps(expand=True, proportion=0)

        wx.StaticLine(pane, -1).SetSizerProps(expand=True)
        
        subpane = SC.SizedPanel(pane, -1)
        subpane.SetSizerType('form')
        subpane.SetSizerProps(expand=True)

        self.startTime = self.addIntField(subpane, "Start Time:", "seconds", 
            name="startTime", minmax=(0,sys.maxint),
            tooltip="The start time of the export.")
        self.endTime = self.addIntField(subpane, "End Time:", "seconds", 
            name="endTime", minmax=(0,sys.maxint),
            tooltip="The end time of the export. Cannot be used with Duration.")
        self.duration = self.addIntField(subpane, "Duration:", "seconds", 
            name="duration", minmax=(0,sys.maxint),
            tooltip=("The length of time from the start to export. "
                     "Cannot be used with End Time."))
        self.maxSize = self.addIntField(subpane, "Max. File Size:", "MB", 
            name="maxSize", value=16, minmax=(1, 1024*1024*10),
            tooltip=("The maximum size of each generated file. "
                     "Cannot be used if a number of files is specified."))
        self.numSplits = self.addIntField(subpane, "Total number of files:", 
            name="numSplits", value=16, minmax=(1, sys.maxint),
            tooltip=("The maximum size of each generated file. "
                     "Cannot be used if a number of files is specified."))

        self.addBottomButtons()

#         self.setValue(self.startTime, self.getPref("startTime", None))
#         if self.setValue(self.endTime, self.getPref("endTime", None)) is None:
#             self.setValue(self.duration, self.getPref("duration", None))
#         self.setValue(self.maxSize, self.getPref("maxSize", None))
#         self.setValue(self.numSplits, self.getPref("numSplits", None))
        
        self.SetMinSize((550,375))
        self.Layout()
        self.Centre()
        

    #===========================================================================
    # 
    #===========================================================================
    
    def OnCheck(self, evt):
        """ Handle all checkbox events. Bound in base class.
        """
        super(IdeSplitter, self).OnCheck(evt)
        obj = evt.EventObject
        if obj.IsChecked():
            # end time and duration are mutually exclusive
            if obj == self.endTime:
                self.setCheck(self.duration, False)
            elif obj == self.duration:
                self.setCheck(self.endTime, False)
            elif obj == self.maxSize:
                self.setCheck(self.numSplits, False)
            elif obj == self.numSplits:
                self.setCheck(self.maxSize, False)
    
    
    def savePrefs(self):
        for c in (self.startTime, self.endTime, self.duration, self.maxSize, self.numSplits):
            name = c.GetName()
            v = self.getValue(c)
            if v is not False:
                self.setPref(name, v)
            else:
                self.deletePref(name)
        
        self.setPref('outputPath', self.outputBtn.GetValue())
        
        paths = self.inputFiles.GetPaths()
        if len(paths) > 0:
            self.setPref('defaultDir', os.path.dirname(paths[-1]))
        
    
    #===========================================================================
    # 
    #===========================================================================
    
    def run(self, evt=None):
        """
        """
        sourceFiles = self.inputFiles.GetPaths()
        numFiles = len(sourceFiles)
        output = self.outputBtn.GetValue() or None
        startTime = self.getValue(self.startTime) or 0
        endTime = self.getValue(self.endTime) or None
        duration = self.getValue(self.duration) or None
        maxSize = self.getValue(self.maxSize) or 16
        numSplits = self.getValue(self.numSplits) or None
        
        if duration:
            endTime = startTime + duration
        endTime = endTime or None

        # HACK: Progress dialog wasn't updating/closing properly at the end,
        # so using PD_AUTO_HIDE is being used in the style.
        updater = SplitterExportProgress(self.GetTitle(), 
                                         "Splitting...\n\n...", 
                                         parent=self, 
                                         style=(wx.PD_CAN_ABORT|
                                                wx.PD_APP_MODAL|
                                                wx.PD_REMAINING_TIME|
                                                wx.PD_AUTO_HIDE))
        
        exported = set()
        processed = set()
        totalFiles = 0
        
        for n, f in enumerate(sourceFiles, 1):
            if numSplits is not None:
                splits = numSplits
                size = max(1024*1024,
                           int(math.ceil(os.path.getsize(f)/(numSplits+0.0))))
            else:
                size = maxSize * 1024 * 1024
                splits = int(math.ceil(os.path.getsize(f)/(size+0.0)))
    
            numDigits = max(2, len(str(splits)))
            
            savePath = output if output is not None else os.path.dirname(f)
            
            b = os.path.basename(f)
            updater.message = "Splitting %s (file %d of %d)" % (b, n, numFiles)
            updater.precision = max(0, min(2, (len(str(os.path.getsize(f)))/2)-1))
            updater(starting=True)
            
            try:
                totalFiles += splitFile(f, savePath=savePath, 
                                        startTime=startTime, endTime=endTime, 
                                        maxSize=size, numSplits=splits, 
                                        numDigits=numDigits, 
                                        updater=updater)
                processed.add(f)
            except Exception as err:
                # TODO: Handle this exception for real!
                msg = err.message
                if n < numFiles:
                    # Not the last file; ask to abort.
                    msg = "%s\n\nContinue processing next file?" % msg
                    x = wx.MessageBox(msg, "Error", 
                                      wx.YES_NO | wx.ICON_ERROR, parent=updater)
                    if x == wx.ID_NO:
                        # Cancel the remaining exports.
                        break
                    else:
                        # Continue on to next file.
                        # Make sure progress dialog is in the foreground
                        exported.update(updater.outputFiles)
                        updater.Destroy()
                        updater = SplitterExportProgress(self.GetTitle(), 
                                                      updater.message, 
                                                      parent=self)
                else:
                    # Last (or only) file being processed; just alert.
                    msg = "%s\n\nExport cancelled." % msg
                    wx.MessageBox(msg, 
                                  "IDE Splitter Error", 
                                  wx.OK | wx.ICON_ERROR,
                                  parent=updater)
        
        exported.update(updater.outputFiles)
        updater.Destroy()

        # TODO: More reporting?
        bulleted = lambda x: " * {}".format(x)
        processed = '\n'.join(map(bulleted, sorted(processed))) or "None"
        exported = '\n'.join(map(bulleted, sorted(exported))) or "None"
        msg = "Files processed:\n%s\n\nFiles generated:\n%s" % (processed, exported)
        dlg = ScrolledMessageDialog(self, msg, "%s: Complete" % self.GetTitle())
        dlg.ShowModal()

        self.savePrefs()

#===============================================================================
# 
#===============================================================================

def launch(parent=None):
    with IdeSplitter(parent, -1, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
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
    with IdeSplitter(None, -1, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
        dlg.ShowModal()
        print dlg.GetSize()

if __name__ == "__main__":
    test()