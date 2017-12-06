'''
Created on Aug 11, 2015

@author: dstokes
'''
import os.path
import sys

import wx
from wx.lib.dialogs import ScrolledMessageDialog
import wx.lib.filebrowsebutton as FB
import wx.lib.sized_controls as SC

from tools.base import ToolDialog
from widgets.multifile import MultiFileSelect
from raw2mat import ModalExportProgress

from ide2mat.ide2csv import ideExport

#===============================================================================
# 
#===============================================================================

__author__ = "D. R. Stokes"
__email__ = "dstokes@mide.com"
__version_tuple__ = (1,0,1)
__version__= ".".join(map(str, __version_tuple__))
__copyright__=u"Copyright (c) 2015 Mid\xe9 Technology"


PLUGIN_INFO = {"type": "tool",
               "name": "Batch IDE Exporter",
               "app": u"Slam\u2022Stick Lab",
               "minAppVersion": (1,4,2),
               }


#===============================================================================
# 
#===============================================================================

class Ide2Csv(ToolDialog):
    """ The main dialog. The plan is for all tools to implement a ToolDialog,
        so the tools can be found and started in a generic manner.
    """
    TITLE = "Batch IDE Exporter"
    
    OUTPUT_TYPES = ("Comma-Separated Values (.CSV)",
                    "Tab-Separated Values (.TXT)",
                    "Pipe (|) Separated Values (.TXT)",
                    "MATLAB (.MAT)")
    
    DELIMITERS = (('.csv', ', '),
                  ('.txt', '\t'),
                  ('.txt', '|'),
                  ('.mat', None))
    
    MEAN_REMOVAL = ("None",
                    "Total Mean",
                    "Rolling Mean")

    timeScalar = 1.0/(10**6)
    
    def __init__(self, *args, **kwargs):
        super(Ide2Csv, self).__init__(*args, **kwargs)

        pane = self.GetContentsPane()
        
        inPath = self.getPref('defaultDir', os.getcwd())
        outPath = self.getPref('outputPath', '')
        
        self.inputFiles = MultiFileSelect(pane, -1, 
                                          wildcard="MIDE Data File (*.ide)|*.ide", 
                                          defaultDir=inPath)
        self.inputFiles.SetSizerProps(expand=True, proportion=1)
        self.outputBtn = FB.DirBrowseButton(pane, -1, size=(450, -1), 
                                            labelText="Output Directory:",
                                            dialogTitle="Export Path",
                                            newDirectory=True,
                                            startDirectory=outPath)
        self.outputBtn.SetSizerProps(expand=True, proportion=0)

        wx.StaticLine(pane, -1).SetSizerProps(expand=True)
        
        subpane = SC.SizedPanel(pane, -1)
        subpane.SetSizerType('form')
        subpane.SetSizerProps(expand=True)

        self.removeMean = self.addChoiceField(subpane, "Mean Removal:",
            name="meanRemoval", choices=self.MEAN_REMOVAL, default=2)
        self.startTime = self.addFloatField(subpane, "Start Time:", "seconds", 
            name="startTime", minmax=(0,sys.maxint), 
            tooltip="The start time of the export.")
        self.endTime = self.addFloatField(subpane, "End Time:", "seconds", 
            name="endTime", minmax=(0,sys.maxint),
            tooltip="The end time of the export. Cannot be used with Duration.")
        self.duration = self.addFloatField(subpane, "Duration:", "seconds", 
            name="duration", minmax=(0,sys.maxint),
            tooltip=("The length of time from the start to export. "
                     "Cannot be used with End Time."))

        self.noBivariates = self.addCheck(subpane, "Disable Bivariate References",
            name="noBivariates", checked=False)

        self.formatField = self.addChoiceField(subpane, "Format:", 
            name="outputType", choices=self.OUTPUT_TYPES, default=0)

        self.headerCheck = self.addCheck(subpane, "Include Column Headers",
            name="useHeaders", tooltip=("Write column descriptions in first row. "
                                        "Applies only to text-based formats."))
        self.utcCheck = self.addCheck(subpane, "Use Absolute UTC Timestamps",
            name="useUtcTimes", tooltip=("Write absolute UTC timestamps. "
                                         "Applies only to text-based formats."))
        self.isoCheck = self.addCheck(subpane, "Use ISO Time Format",
            name="useIsoFormat", tooltip=("Write timestamps in ISO format. "
                                          "Applies only to text-based formats."))
        
#         self.maxSize = self.addIntField(subpane, "Max. File Size:", "MB", 
#             name="maxSize", value=MatStream.MAX_SIZE/1024/1024, 
#             minmax=(16, MatStream.MAX_LENGTH/1024/1024),
#             tooltip="The maximum size of each MAT file. Must be below 2GB.")
    
        subpane = SC.SizedPanel(pane, -1)
        subpane.SetSizerType('form')
        subpane.SetSizerProps(expand=True)
        
        self.addBottomButtons()
        
        self.Bind(wx.EVT_CHOICE, self.OnChoice)
        
        self.SetMinSize((550,500))
        self.Layout()
        self.Centre()
        self.updateFields()
        

    #===========================================================================
    # 
    #===========================================================================
    
    def updateFields(self):
        _ext, delimiter = self.DELIMITERS[self.getValue(self.formatField)]
        isText = delimiter is not None
        
        self.enableField(self.headerCheck, isText)
        self.enableField(self.utcCheck, isText)
        self.enableField(self.isoCheck, isText and self.getValue(self.utcCheck))
    
    
    def OnChoice(self, evt):
        self.updateFields()
        evt.Skip()
        
    
    def OnCheck(self, evt):
        """ Handle all checkbox events. Bound in base class.
        """
        super(Ide2Csv, self).OnCheck(evt)
        obj = evt.EventObject
        if obj.IsChecked():
            # end time and duration are mutually exclusive
            if obj == self.endTime:
                self.setCheck(self.duration, False)
            elif obj == self.duration:
                self.setCheck(self.endTime, False)
    
    
    def savePrefs(self):
        for c in (self.startTime, self.endTime, self.duration, self.removeMean,
                  self.formatField, self.headerCheck, self.utcCheck, self.isoCheck,
                  self.noBivariates):
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
        startTime = self.getValue(self.startTime, 0)
        endTime = self.getValue(self.endTime, None)
        duration = self.getValue(self.duration, None)
        outputSelection = self.getValue(self.formatField) 
        headers = self.getValue(self.headerCheck, False)
        useUtcTime = self.getValue(self.utcCheck, False)
        useIsoFormat = not useUtcTime and self.getValue(self.isoCheck, False)
        noBivariates = self.getValue(self.noBivariates, False)
        removeMean = self.getValue(self.removeMean, 2)
#         maxSize = (self.getValue(self.maxSize) * 1024) or MatStream.MAX_SIZE
        
        if removeMean == 1:
            meanSpan = -1
        else:
            meanSpan = 5.0
        
        try:
            outputType, delimiter = self.DELIMITERS[outputSelection]
        except IndexError:
            outputType, delimiter = self.DELIMITERS[0]
        
        if duration:
            endTime = startTime + duration
        if isinstance(startTime, (int, float)):
            startTime /= self.timeScalar
        if isinstance(endTime, (int, float)):
            endTime /= self.timeScalar
        endTime = endTime or None

        updater = ModalExportProgress(self.GetTitle(), "Exporting...\n\n", 
                                      parent=self)
        
        exported = set()
        processed = set()
        totalSamples = 0
        
        # Keyword arguments shared by all exports
        params = dict(outputType=outputType, 
                      delimiter=delimiter, 
                      headers=headers, 
                      useUtcTime=useUtcTime, 
                      useIsoFormat=useIsoFormat, 
                      noBivariates=noBivariates, 
                      removeMean=bool(removeMean), 
                      meanSpan=meanSpan, 
                      updateInterval=1.5, 
                      out=None, 
                      updater=updater, 
                      )
        
        for n, f in enumerate(sourceFiles, 1):
            b = os.path.basename(f)
            updater.message = "Exporting %s (file %d of %d)" % (b, n, numFiles)
            updater.precision = max(0, min(2, (len(str(os.path.getsize(f)))/2)-1))
            updater(starting=True)
            try:
                num = ideExport(f, output, startTime=startTime, endTime=endTime, 
                                **params)
                totalSamples += num
                processed.add(f)
            except Exception as err:
                # TODO: Handle this exception for real!
                msg = err.message
                if n < numFiles:
                    # Not the last file; ask to abort.
                    msg = "%s\n\nContinue exporting next file?" % msg
                    x = wx.MessageBox(msg, "Error", wx.YES_NO | wx.ICON_ERROR,
                                      parent=updater)
                    if wx.GetKeyState(wx.WXK_CONTROL) and wx.GetKeyState(wx.WXK_SHIFT):
                        raise
                    if x == wx.NO:
                        # Cancel the remaining exports.
                        break
                    else:
                        # Continue on to next file.
                        # Make sure progress dialog is in the foreground
                        exported.update(updater.outputFiles)
                        updater.Destroy()
                        updater = ModalExportProgress(self.GetTitle(), 
                                                      updater.message, 
                                                      parent=self)
                else:
                    # Last (or only) file being processed; just alert.
                    msg = "%s\n\nExport cancelled." % msg
                    wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR,
                                  parent=updater)
                    if wx.GetKeyState(wx.WXK_CONTROL) and wx.GetKeyState(wx.WXK_SHIFT):
                        raise
        
        exported.update(updater.outputFiles)
        updater.Destroy()

        # TODO: More reporting?
        bulleted = lambda x: " * {}".format(x)
        processed = '\n'.join(map(bulleted, sorted(processed))) or "None"
        exported = '\n'.join(map(bulleted, sorted(exported))) or "None"
        msg = "Files processed:\n%s\n\nFiles generated:\n%s\n\nTotal samples exported: %d" % (processed, exported, totalSamples)
        dlg = ScrolledMessageDialog(self, msg, "%s: Complete" % self.GetTitle())
        dlg.ShowModal()

        self.savePrefs()

#===============================================================================
# 
#===============================================================================

def launch(parent=None):
    dlg = Ide2Csv(parent, -1, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
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
    dlg = Ide2Csv(None, -1, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
    dlg.ShowModal()
    print dlg.GetSize()

if __name__ == "__main__":
    test()