"""
Components related to displaying recording file properties.
"""

from collections import OrderedDict
from datetime import datetime
import locale
import os.path
import sys

import wx.lib.sized_controls as sc
import wx; wx = wx

from config_dialog import InfoPanel
from mide_ebml import util
from mide_ebml.parsers import renameKeys

#===============================================================================
# Recorder Info: device data stored in a recording, similar to device info. 
#===============================================================================

class RecorderInfoDialog(sc.SizedDialog):
    """ Dialog showing the recorder info from a recording file. Self-contained;
        show the dialog via the `showRecorderInfo()` method.
    """
    
    def getFileInfo(self):
        """ Get basic file stats from the filesystem. """
        result = OrderedDict()
        fn = self.root.filename
        filesize = locale.format("%d", os.path.getsize(fn), grouping=True)
        result['Path'] = os.path.abspath(fn)
        result['File Size'] = "%s bytes" % filesize
        ctime = datetime.fromtimestamp(os.path.getctime(fn))
        if 'win' in sys.platform:
            result['Creation Time'] = ctime
        else:
            result['Last Metadata Change'] = ctime
        result['Last Modified'] = datetime.fromtimestamp(os.path.getmtime(fn))
        result['_label0'] = "Dates shown here are according to the file system."
        result['_label1'] = "Dates in the Recording Properties may be more accurate."
        return result
        
    
    def getRecordingInfo(self):
        """
        """
        result = OrderedDict()
        result['File Damaged'] = str(self.root.fileDamaged)
        result['Number of Sessions'] = locale.format("%d", 
                                                     len(self.root.sessions), 
                                                     grouping=True)
        for s in self.root.sessions:
            t = s.utcStartTime
            if t:
                td = datetime.fromtimestamp(t)
                result['Session %d Start (UTC)' % s.sessionId] = td
        return result


    def getRecorderInfo(self):
        names = {'ProductName': "Product Name",
                 'PartNumber': "Part Number",
                 "RecorderSerial": "Recorder Serial #",
                 "RecorderTypeUID": "Recorder Type ID",
                 "HwRev": "Hardware Version",
                 "FwRev": "Firmware Version",
                 "DateOfManufacture": "Date of Manufacture",
                 "CalibrationDate": "Calibration Date",
                 "CalibrationSerialNumber": "Calibration Serial #",
                 "CalibrationExpiry": "Calibration Expiry Date",
        }
        result = self.root.recorderInfo
        for d in ('DateOfManufacture', 'CalibrationDate', 'CalibrationExpiry'):
            if d in result:
                result[d] = datetime.fromtimestamp(result[d])
        return renameKeys(result, names, exclude=False, recurse=False)


    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.SYSTEM_MENU)
        
        super(RecorderInfoDialog, self).__init__(*args, **kwargs)
        
        fileInfo = self.getFileInfo()
        recordingInfo = self.getRecordingInfo()
        recorderInfo = self.getRecorderInfo() #self.root.recorderInfo
        ebmlInfo = util.parse_ebml(self.root.ebmldoc.roots[0]).get('EBML', None)
        if ebmlInfo is not None:
            ebmlInfo = ebmlInfo[0]
        
        pane = self.GetContentsPane()
        notebook = wx.Notebook(pane, -1)
        filePanel = InfoPanel(notebook, -1, root=self, info=fileInfo)
        recordingPanel = InfoPanel(notebook, -1, root=self, info=recordingInfo)
        notebook.AddPage(filePanel, "File Properties")
        notebook.AddPage(recordingPanel, "Recording Properties")
        
        if recorderInfo:
            recPanel = InfoPanel(notebook, -1, root=self, info=recorderInfo)
            notebook.AddPage(recPanel, "Device Info")
            
        ebmlPanel = InfoPanel(notebook, -1, root=self, info=ebmlInfo)
        notebook.AddPage(ebmlPanel, "EBML Headers")

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK))
        
        notebook.SetSizerProps(expand=True, proportion=-1)
        self.SetMinSize((436, 400))
        self.Fit()

    @classmethod
    def showRecorderInfo(cls, ebmldoc):
        """ Display information about the device that made a recording.
            @param root: The `mide_ebml.dataset.Dataset` with info to show
        """
        
#         if not ebmldoc.recorderInfo:
#             dlg = wx.MessageDialog(None, 
#                'The recording file contains no recorder device info',
#                'Recorder Properties', wx.OK | wx.ICON_INFORMATION)
#         else:
        dlg = cls(None, -1, "%s Recording Properties" % ebmldoc.filename, 
                  root=ebmldoc)
        dlg.ShowModal()
        dlg.Destroy()
        

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
#     print configureRecorder("G:\\")


    from mide_ebml import importer
    doc=importer.importFile(updater=importer.SimpleUpdater(0.01))

    class Foo(object):
        def __init__(self, data):
            self.recorderInfo = data
            self.filename="foo.ide"

    RecorderInfoDialog.showRecorderInfo(doc)
#     RecorderInfoDialog.showRecorderInfo(Foo(None))