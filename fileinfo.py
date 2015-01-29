"""
Components related to displaying recording file properties.
"""

from collections import OrderedDict
from datetime import datetime
import locale
import os.path
import sys

import wx; wx = wx
import wx.lib.sized_controls as SC

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

class ChannelInfoPanel(InfoPanel):
    """ Display channel information, e.g. sample rate, minimum and maximum,
        et cetera.
    """
    timeScalar = 1.0/(10**6)
    
    
    def plotLink(self, channelId, subchannelId, time, val, msg=None):
        """ Create a link to a channel and a time. 
            Just makes text until linking to viewer channel/time implemented.
        """
        if msg is None:
            if val is None:
                msg = "%.4f" % time
            else:
                msg = "%.4f @ %.4f" % (val, time*self.timeScalar)
#         return '<b><a href="viewer:%s.%s@%s">%s</a></b>' % \
#             (channelId, subchannelId, time, msg)
        return '<b>%s</b>' % msg
    

    def buildUI(self):
        """ Build and display the contents. This dialog's layout differs from
            other InfoPanels, so it does more work here.
        """
        self.html = ["<html><body>"]
        if self.info.loading:
            self.addLabel("<b>Note:</b> This dialog was opened while the "
                          "recording was still importing; minimum and maximum "
                          "values will not reflect the entire data set. ",
                          warning=True)
        for cid, c in self.info.channels.iteritems():
            self.html.append("<p><b>Channel %02x: %s</b><ul>" % (cid, c.name))
            for subcid, subc in enumerate(c.subchannels):
                events = subc.getSession()
                self.html.append("<li><b>Subchannel %02x.%d: %s</b></li>" % \
                                 (cid, subcid, subc.name))
                
                self.addItem("Sensor Range:", "%s to %s %s" % 
                   (subc.displayRange[0], subc.displayRange[1], subc.units[0]))
                
                # Hack for channels with no data.
                if len(events) > 0:
                    srate = ("%.3f" % events.getSampleRate()).rstrip('0')
                    srate = srate + '0' if srate.endswith('.') else srate
                    self.addItem("Nominal Sample Rate:", "%s Hz" % srate)
                    self.addItem("Minimum Value:", 
                                 self.plotLink(cid, subcid, *events.getMin()),
                                 escape=False)
                    self.addItem("Maximum Value:", 
                                 self.plotLink(cid, subcid, *events.getMax()),
                                 escape=False)
                    
#                 mmm = events.getRangeMinMeanMax()
#                 if mmm:
#                     self.addItem("Median:", "%.4f" % mmm[1])
                
                # addItem will open a new table, close it.
                self.closeTable() 
                
            self.html.append("</ul></p>")
        self.html.append("</body></html>")
        self.SetPage(''.join(self.html))


#===============================================================================
# Recorder Info: device data stored in a recording, similar to device info. 
#===============================================================================

class RecorderInfoDialog(SC.SizedDialog):
    """ Dialog showing the recorder info from a recording file. Self-contained;
        show the dialog via the `showRecorderInfo()` method.
    """
    def _strInt(self, val):
        try:
            return locale.format("%d", val, grouping=True)
        except TypeError:
            return str(val)
    
    def getFileInfo(self):
        """ Get basic file stats from the filesystem. """
        result = OrderedDict()
        fn = self.root.filename
        result['Path'] = os.path.abspath(fn)
        result['File Size'] = "%s bytes" % self._strInt(os.path.getsize(fn))
        ctime = datetime.fromtimestamp(os.path.getctime(fn))
        if 'win' in sys.platform:
            result['Creation Time'] = ctime
        else:
            result['Last Metadata Change'] = ctime
        result['Last Modified'] = datetime.fromtimestamp(os.path.getmtime(fn))
        result['_label0'] = ("Dates shown here are according to the "
                             "file system. Dates in the Recording Properties "
                             "may be more accurate.")
        return result
        
    
    def getRecordingInfo(self):
        """
        """
        result = OrderedDict()
        result['File Damaged'] = str(self.root.fileDamaged)
        result['Number of Sessions'] = str(len(self.root.sessions))
        for s in self.root.sessions:
            t = s.utcStartTime
            if t:
                td = datetime.fromtimestamp(t)
                result['Session %d Start (UTC)' % s.sessionId] = td
        return result


    def getRecorderInfo(self):
        if self.root.recorderInfo is None:
            return None
        result = self.root.recorderInfo.copy()
        for d in ('CalibrationDate', 'CalibrationExpiry'):
            if d in result:
                result[d] = datetime.fromtimestamp(result[d])
        return result


    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        showAll = kwargs.pop('showAll', False)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.SYSTEM_MENU)
        
        super(RecorderInfoDialog, self).__init__(*args, **kwargs)
        
        fileInfo = self.getFileInfo()
        recordingInfo = self.getRecordingInfo()
        recorderInfo = self.getRecorderInfo()
        if hasattr(self.root, "ebmldoc"):
            ebmlInfo = util.parse_ebml(self.root.ebmldoc.roots[0]).get('EBML', None)
            if ebmlInfo is not None:
                ebmlInfo = ebmlInfo[0]
        else:
            ebmlInfo = None
        
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
        
        if self.root.transforms:
            calPanel = RecordingCalibrationPanel(notebook, -1, root=self.root)
            notebook.AddPage(calPanel, "Calibration")
        
        if showAll and ebmlInfo is not None:
            ebmlPanel = InfoPanel(notebook, -1, root=self, info=ebmlInfo)
            notebook.AddPage(ebmlPanel, "EBML Headers")

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK))
        
        notebook.SetSizerProps(expand=True, proportion=-1)
        self.SetMinSize((640, 480))
        self.Fit()


    @classmethod
    def showRecorderInfo(cls, ebmldoc, showAll=False):
        """ Display information about the device that made a recording.
            @param root: The `mide_ebml.dataset.Dataset` with info to show
        """
        
        dlg = cls(None, -1, "%s Recording Properties" % ebmldoc.filename, 
                  root=ebmldoc, showAll=showAll)
        dlg.ShowModal()
        dlg.Destroy()
        

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    CLASSIC_TEST = not True
    
    print "Starting test..."
    if CLASSIC_TEST:
        from mide_ebml.classic import importer as classic_importer
        doc = classic_importer.importFile('test_recordings/data.dat')
    else:
        from mide_ebml import importer
        doc=importer.importFile(updater=importer.SimpleUpdater(0.25, quiet=True))
        
    print "filename: %r" % doc.filename
    print "type: %r" % doc.__class__
    
    class Foo(object):
        def __init__(self, data):
            self.recorderInfo = data
            self.filename=data.filename
            
#     doc.loading = True
    RecorderInfoDialog.showRecorderInfo(doc, True)
