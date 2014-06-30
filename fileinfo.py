"""
Components related to displaying recording file properties.
"""

from collections import OrderedDict
from datetime import datetime
import locale
import os.path
import sys

import wx; wx = wx
import wx.lib.sized_controls as sc
import wx.html

from config_dialog import InfoPanel, CalibrationPanel
from mide_ebml import util


#===============================================================================
# 
#===============================================================================

class RecordingCalibrationPanel(CalibrationPanel):
    def getDeviceData(self):
        self.info = self.root.transforms.values()
        
#===============================================================================
# 
#===============================================================================

class ChannelInfoPanel(wx.html.HtmlWindow):
    """
    """
    timeScalar = 1.0/(10**6)
    
    def generateContents(self):
        """
        """
        html = ["<html><body>"]
        for cid, c in self.info.channels.iteritems():
            html.append("<p><b>Channel %02x: %s</b><font size='-1'><ul>" % \
                        (cid, c.name))
            for subcid, subc in enumerate(c.subchannels):
                events = subc.getSession()
                srate = ("%.3f" % events.getSampleRate()).rstrip('0')
                html.append("<li><b>Subchannel %02x.%d: %s</b></li>" % \
                            (cid, subcid, subc.name))
                html.append("<ul><li>")
                h = []
                h.append("Range: <b>%s to %s %s</b>" % \
                   (subc.displayRange[0], subc.displayRange[1], subc.units[0]))
                h.append("Nominal Sample Rate: <b>%s Hz</b>" % srate)
                cmax = events.getMax()
                cmin= events.getMin()
                h.append("Minimum Value: <b>%.4f %s @ %.4f</b>" % \
                         (cmin[-1], subc.units[0], cmin[-2]*self.timeScalar))
                h.append("Maximum Value: <b>%.4f %s @ %.4f</b>" % \
                         (cmax[-1], subc.units[0], cmax[-2]*self.timeScalar))
                html.append("</li><li>".join(h))
                html.append("</li></ul>")
            html.append("</ul></font></p>")
        html.append("</body></html>")
        return ''.join(html)

    
    def __init__(self, *args, **kwargs):
        """
        """
        self.root = kwargs.pop('root', None)
        self.info = kwargs.pop('info', None)
        self.sessionId = kwargs.pop('sessionId', 0)
        super(ChannelInfoPanel, self).__init__(*args, **kwargs)
        if self.info is not None:
            self.SetPage(self.generateContents())
    

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
        result = self.root.recorderInfo.copy()
        for d in ('CalibrationDate', 'CalibrationExpiry'):
            if d in result:# and not isinstance(result[d], datetime):
                result[d] = datetime.fromtimestamp(result[d])
        return result


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
        infoPanel = ChannelInfoPanel(notebook, -1, root=self, info=self.root)
        notebook.AddPage(filePanel, "File Properties")
        notebook.AddPage(recordingPanel, "Recording Properties")
        notebook.AddPage(infoPanel, "Channel Info")
        
        if recorderInfo:
            recPanel = InfoPanel(notebook, -1, root=self, info=recorderInfo)
            notebook.AddPage(recPanel, "Device Info")
        
        calPanel = RecordingCalibrationPanel(notebook, -1, root=self.root)
        notebook.AddPage(calPanel, "Calibration")
        
        ebmlPanel = InfoPanel(notebook, -1, root=self, info=ebmlInfo)
        notebook.AddPage(ebmlPanel, "EBML Headers")

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK))
        
        notebook.SetSizerProps(expand=True, proportion=-1)
        self.SetMinSize((640, 480))
        self.Fit()

    @classmethod
    def showRecorderInfo(cls, ebmldoc):
        """ Display information about the device that made a recording.
            @param root: The `mide_ebml.dataset.Dataset` with info to show
        """
        
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
    print "filename: %r" % doc.filename

    class Foo(object):
        def __init__(self, data):
            self.recorderInfo = data
            self.filename=data.filename

    RecorderInfoDialog.showRecorderInfo(doc)
#     RecorderInfoDialog.showRecorderInfo(Foo(None))