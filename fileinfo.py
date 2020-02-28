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

from config_dialog.special_tabs import InfoPanel, CalibrationPanel
import devices
# from idelib import util

#===============================================================================
# 
#===============================================================================

class RecordingCalibrationPanel(CalibrationPanel):
    def getDeviceData(self):
        self.info = self.root.transforms.values()
        self.channels = self.root.channels


#===============================================================================
# 
#===============================================================================

class ChannelInfoPanel(InfoPanel):
    """ Display channel information, e.g. sample rate, minimum and maximum,
        et cetera.
    """
    timeScalar = 1.0/(10**6)

    def formatFloat(self, val):
        """ Helper method to prettify floats.
        """
        return ("%.3f" % val).rstrip('0').rstrip('.')

    
    def plotLink(self, channelId, subchannelId, time, val, msg=None):
        """ Create a link to a channel and a time. 
            Just makes text until linking to viewer channel/time implemented.
        """
        units = self.info.channels[channelId][subchannelId].units
        if units and units[1]:
            units = "%s " % units[1]
        else:
            units = ""
        if msg is None:
            if val is None:
                msg = "%.4f" % time
            else:
                msg = "%.4f %s@ %.4f" % (val, units, time*self.timeScalar)
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
            self.html.append("<p><b>Channel %d: %s</b><ul>" % (cid, c.displayName))
            for subcid, subc in enumerate(c.subchannels):
                events = subc.getSession()
                self.html.append("<li><b>Subchannel %d.%d: %s</b></li>" % \
                                 (cid, subcid, subc.displayName))
                if subc.sensor is not None:
                    self.addItem("Sensor:", "%s (ID:%d)" % (subc.sensor.name, subc.sensor.id))
                if subc.units and subc.units[0]:
                    self.addItem("Data Type:", "%s in %s" % (subc.units))
                if subc.hasDisplayRange:
                    self.addItem("Range:", "%s to %s %s" % 
                                 (subc.displayRange[0], subc.displayRange[1], subc.units[1]))
                
                # Hack for channels with no data.
                if len(events) > 0:
                    try:
                        srate = self.formatFloat(events.getSampleRate())
                        minVal = self.plotLink(cid, subcid, *events.getMin())
                        maxVal = self.plotLink(cid, subcid, *events.getMax())
                        footnote = "*" if events.removeMean else ""
                        
                        self.addItem("Nominal Sample Rate:", "%s Hz" % srate)
                        self.addItem("Minimum Value:", minVal + footnote,
                                     escape=False)
                        self.addItem("Maximum Value:", maxVal + footnote, 
                                     escape=False)
                            
                    except (IndexError, AttributeError):
                        # These can occur in partially damaged files.
                        pass
                    
#                 mmm = events.getRangeMinMeanMax()
#                 if mmm:
#                     self.addItem("Median:", "%.4f" % mmm[1])
                else:
                    footnote = False
                
                # addItem will open a new table, close it.
                self.closeTable() 

                # Add footnote about mean removal
                if footnote and events.removeMean:
                    if events.rollingMeanSpan == -1:
                        msg = "<i>* After total mean removal</i>"
                    else:
                        span = self.formatFloat(events.rollingMeanSpan * self.timeScalar)
                        msg = "<i>* After %s second rolling mean removal</i>" % span
                    self.html.append(msg)

                
            self.html.append("</ul></p>")
        self.html.append("</body></html>")
        self.SetPage(''.join(self.html))

#===============================================================================
# 
#===============================================================================

class SensorInfoPanel(InfoPanel):
    """
    """
    field_names = {'serialNum': 'Serial Number'}
    
    def buildUI(self):
        """ Build and display the contents. This dialog's layout differs from
            other InfoPanels, so it does more work here.
        """
        self.html = ["<html><body>"]
        sensors = sorted(self.info.sensors.items(), key=lambda x: x[0])
        for sid, s in sensors:
            self.html.append("<p><b>Sensor ID: %d</b><ul>" % sid)
            self.addItem("Sensor Type", s.name)
            if s.traceData is not None:
                for k,v in s.traceData.items():
                    self.addItem(self.field_names.get(k, self._fromCamelCase(k)),v)

            self.closeTable() 
            
        self.html.append("</body></html>")
        self.SetPage(''.join(self.html))


#===============================================================================
# Recorder Info: device data stored in a recording, similar to device info. 
#===============================================================================

class RecorderInfoDialog(SC.SizedDialog):
    """ Dialog showing the recorder info from a recording file. Self-contained;
        show the dialog via the `showRecorderInfo()` method.
    """

    EXIT_CONDITIONS = {1: "Button pressed",
                       2: "USB connected",
                       3: "Recording time limit reached",
                       4: "Low battery",
                       5: "File size limit reached",
                       128: "I/O Error"}

    
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
        damaged = "True *" if self.root.fileDamaged else "False"
        if hasattr(self.root, 'ebmldoc'):
            result['File Type'] = "%s (version %s)" % (self.root.ebmldoc.type, 
                                                       self.root.ebmldoc.version)
        else:
            result['File Type'] = "Slam Stick Classic"
        if self.root.exitCondition is not None: 
            ec = self.root.exitCondition
            exitCond = "%s (%s)" % (self.EXIT_CONDITIONS.get(ec, "Unknown"), ec)
        else:
            exitCond = "Not recorded"
        result['Exit Condition'] = exitCond
        result['File Damaged'] = damaged
        result['Number of Sessions'] = str(len(self.root.sessions))
        for s in self.root.sessions:
            t = s.utcStartTime
            if t:
                td = datetime.fromtimestamp(t)
                result['Session %d Start (UTC)' % s.sessionId] = td
        
        if self.root.fileDamaged:
            result['_label0'] = ("* Files marked as 'damaged' are typically "
                                 "the result of the recorder having abruptly "
                                 "closed the file due to its battery running "
                                 "down. In such cases, the contents of the "
                                 "file are usually intact.")
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
            try:
#                 ebmlInfo = util.parse_ebml(self.root.ebmldoc.roots[0]).get('EBML', None)
                ebmlInfo = self.root.ebmldoc.info.copy()
            except AttributeError:
                ebmlInfo = None
#             if ebmlInfo is not None:
#                 ebmlInfo = ebmlInfo[0]
        else:
            ebmlInfo = None
        
        try:    
            self.device = devices.fromRecording(self.root)
        except TypeError:
            self.device = None
        
        pane = self.GetContentsPane()
        notebook = wx.Notebook(pane, -1)
        filePanel = InfoPanel(notebook, -1, root=self, info=fileInfo)
        recordingPanel = InfoPanel(notebook, -1, root=self, info=recordingInfo)
        sensorPanel = SensorInfoPanel(notebook, -1, root=self, info=self.root)
        infoPanel = ChannelInfoPanel(notebook, -1, root=self, info=self.root)
        notebook.AddPage(filePanel, "File Properties")
        notebook.AddPage(recordingPanel, "Recording Properties")
        notebook.AddPage(sensorPanel, "Sensor Info")
        notebook.AddPage(infoPanel, "Channel Info")
        
        if recorderInfo:
            recPanel = InfoPanel(notebook, -1, root=self, info=recorderInfo)
            notebook.AddPage(recPanel, "Device Info")
        
        if self.root.transforms:
            cal = self.root.transforms.values()
            calPanel = RecordingCalibrationPanel(notebook, -1, root=self.root,
                                                 info=cal)
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
            @param root: The `idelib.dataset.Dataset` with info to show
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
        from idelib.classic import importer as classic_importer
        doc = classic_importer.importFile('test_recordings/data.dat')
    else:
        from idelib import importer
        doc=importer.importFile(updater=importer.SimpleUpdater(0.25, quiet=True))
        
    print "filename: %r" % doc.filename
    print "type: %r" % doc.__class__
    
    class Foo(object):
        def __init__(self, data):
            self.recorderInfo = data
            self.filename=data.filename
            
#     doc.loading = True
    RecorderInfoDialog.showRecorderInfo(doc, showAll=False)
