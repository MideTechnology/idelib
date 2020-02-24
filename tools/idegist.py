import os
import sys
import csv

import wx

import idelib.importer
import scripts.idegist
from widgets.multifile import MultiFileSelect
from tools.base import ToolDialog
from tools.raw2mat import ModalExportProgress


###############################################################################
# Tool Metadata
###############################################################################

__author__ = "B. B. Awqatty"
__email__ = "bawqatty@mide.com"
__version_tuple__ = (0, 0, 0)
__version__= ".".join([str(num) for num in __version_tuple__])
__copyright__= "Copyright (c) 2020 Mid\xe9 Technology"


PLUGIN_INFO = {
    "type": "tool",
    "name": "Batch IDE Summarizer",
    "app": u"enDAQ Lab",
}


###############################################################################
# Tool Dialog
###############################################################################

class IdeSummarizer(ToolDialog):
    """ The main dialog. The plan is for all tools to implement a ToolDialog,
        so the tools can be found and started in a generic manner.
    """
    TITLE = "Batch IDE Summarizer"

    OUTPUT_TYPES = (
        "Comma-Separated Values (.CSV)",
        #"Tab-Separated Values (.TXT)",
        #"Pipe (|) Separated Values (.TXT)",
    )

    DELIMITERS = (
        ('.csv', ', '),
        #('.txt', '\t'),
        #('.txt', '|'),
    )

    MEAN_REMOVAL = (
        "None",
        "Total Mean",
        "Rolling Mean"
    )

    timeScalar = 1e-6

    def __init__(self, *args, **kwargs):
        super(IdeSummarizer, self).__init__(*args, **kwargs)

        pane = self.GetContentsPane()

        inPath = self.getPref('defaultDir', os.getcwd())
        outPath = self.getPref('outputPath', '')

        self.inputFiles = MultiFileSelect(
            pane, -1, 
            wildcard="MIDE Data File (*.ide)|*.ide", 
            defaultDir=inPath,
        )
        self.inputFiles.SetSizerProps(expand=True, proportion=1)
        self.outputBtn = wx.lib.filebrowsebutton.FileBrowseButton(
            pane, -1,
            size=(450, -1), 
            labelText="Output File:",
            dialogTitle="Export Path",
            startDirectory=outPath,
            fileMode=wx.FD_SAVE,
        )
        self.outputBtn.SetSizerProps(expand=True, proportion=0)

        wx.StaticLine(pane, -1).SetSizerProps(expand=True)

        subpane = wx.lib.sized_controls.SizedPanel(pane, -1)
        subpane.SetSizerType('form')
        subpane.SetSizerProps(expand=True)

        self.removeMean = self.addChoiceField(
            subpane, "Mean Removal:",
            name="meanRemoval",
            choices=self.MEAN_REMOVAL,
            default=2,
            tooltip=(
                "The method by which to subtract the mean value from the data."
                " Only applicable to channels with recorded minimum/mean"
                "/maximum values (e.g. analog acceleration)."
            ),
        )
        self.startTime = self.addFloatField(
            subpane, "Start Time:", "seconds",
            name="startTime",
            minmax=(0, sys.maxint), 
            tooltip="The start time of the export."
        )
        self.endTime = self.addFloatField(
            subpane, "End Time:", "seconds",
            name="endTime",
            minmax=(0, sys.maxint),
            tooltip="The end time of the export. Cannot be used with Duration.",
        )
        self.duration = self.addFloatField(
            subpane, "Duration:", "seconds",
            name="duration",
            minmax=(0, sys.maxint),
            tooltip=(
                "The length of time from the start to export. Cannot be used"
                " with End Time."
            ),
        )

        self.noBivariates = self.addCheck(
            subpane, "Disable Bivariate References",
            name="noBivariates",
            checked=False
        )

        self.formatField = self.addChoiceField(
            subpane, "Format:", 
            name="outputType",
            choices=self.OUTPUT_TYPES,
            default=0
        )

        self.nameCheck = self.addCheck(
            subpane, "Use channel names in exported filenames",
            checked=True,
            name="useNames",
            tooltip=(
                "Include the name of the source channel in each exported"
                " filename, in addition to the numeric channel ID."
            ),
        )
        self.headerCheck = self.addCheck(
            subpane, "Include Column Headers",
            name="useHeaders",
            tooltip=(
                "Write column descriptions in first row. Applies only to"
                " text-based formats."
            ),
        )
        self.utcCheck = self.addCheck(
            subpane, "Use Absolute UTC Timestamps",
            name="useUtcTimes",
            tooltip=(
                "Write absolute UTC timestamps. Applies only to text-based"
                " formats."
            ),
        )
        self.isoCheck = self.addCheck(
            subpane, "Use ISO Time Format",
            name="useIsoFormat",
            tooltip=(
                "Write timestamps in ISO format. Applies only to text-based"
                " formats."
            ),
        )

#         self.maxSize = self.addIntField(subpane, "Max. File Size:", "MB", 
#             name="maxSize", value=MatStream.MAX_SIZE/1024/1024, 
#             minmax=(16, MatStream.MAX_LENGTH/1024/1024),
#             tooltip="The maximum size of each MAT file. Must be below 2GB.")

        subpane = wx.lib.sized_controls.SizedPanel(pane, -1)
        subpane.SetSizerType('form')
        subpane.SetSizerProps(expand=True)

        self.addBottomButtons()

        self.Bind(wx.EVT_CHOICE, self.OnChoice)

        self.SetMinSize((550, 500))
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
        super(IdeSummarizer, self).OnCheck(evt)
        obj = evt.EventObject
        if obj.IsChecked():
            # end time and duration are mutually exclusive
            if obj == self.endTime:
                self.setCheck(self.duration, False)
            elif obj == self.duration:
                self.setCheck(self.endTime, False)


    def savePrefs(self):
        for c in (self.startTime, self.endTime, self.duration, self.removeMean,
                  self.formatField, self.headerCheck, self.utcCheck, 
                  self.isoCheck, self.noBivariates, self.nameCheck):
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
        output = self.outputBtn.GetValue() or None
        startTime = self.getValue(self.startTime, 0)
        endTime = self.getValue(self.endTime, None)
        duration = self.getValue(self.duration, None)
        outputSelection = self.getValue(self.formatField) 
        headers = self.getValue(self.headerCheck, False)
        useNames = self.getValue(self.nameCheck, False)
        useUtcTime = self.getValue(self.utcCheck, False)
        useIsoFormat = not useUtcTime and self.getValue(self.isoCheck, False)
        noBivariates = self.getValue(self.noBivariates, False)
        removeMean = self.getValue(self.removeMean, 2)
#         maxSize = (self.getValue(self.maxSize) * 1024) or MatStream.MAX_SIZE

        if not output:
            return
        output = os.path.realpath(output)

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
                      useNames=useNames
                      )

        with open(output, 'wb') as csvfile:
            csv_writer = csv.writer(csvfile)

            # Writing column headers
            csv_writer.writerow(scripts.idegist.CsvRowTuple._fields)

            for i, filename in enumerate(sourceFiles, 1):
                basename = os.path.basename(filename)
                updater.message = "Exporting {} (file {} of {})".format(basename, i, len(sourceFiles))
                updater.precision = max(0, min((len(str(os.path.getsize(filename)))/2)-1, 2))
                updater(starting=True)

                ds = idelib.importer.importFile(filename)
                for row in scripts.idegist.summarize(ds):
                    csv_writer.writerow(row)
                ds.close()  # Remember to close your file after you're finished with it!

            exported.update(updater.outputFiles)
            updater.Destroy()

        # TODO: More reporting?
        bulleted = lambda x: " * {}".format(x)
        processed = '\n'.join(bulleted(i) for i in sorted(processed)) or "None"
        exported = '\n'.join(bulleted(i) for i in sorted(exported)) or "None"
        msg = (
            "Files processed:\n{}\n\n"
            "Files generated:\n{}\n\n"
            "Total samples exported: {}"
            .format(processed, exported, totalSamples)
        )
        dlg = wx.lib.dialogs.ScrolledMessageDialog(self, msg, "{}: Complete".format(self.GetTitle()))
        dlg.ShowModal()

        self.savePrefs()


#===============================================================================
# 
#===============================================================================

def launch(parent=None):
    dlg = IdeSummarizer(parent, -1, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
    dlg.ShowModal()


def init(*args, **kwargs):
    return launch

