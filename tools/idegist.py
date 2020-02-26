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

        self.headerCheck = self.addCheck(
            subpane, "Include Column Headers",
            name="useHeaders",
            tooltip=(
                "Write column descriptions in first row. Applies only to"
                " text-based formats."
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

        self.SetMinSize((550, 350))
        self.Layout()
        self.Centre()
        self.updateFields()


    #===========================================================================
    # 
    #===========================================================================

    def updateFields(self):
        _ext, delimiter = self.DELIMITERS[self.getValue(self.formatField)]
        isText = delimiter is not None


    def OnChoice(self, evt):
        self.updateFields()
        evt.Skip()


    def OnCheck(self, evt):
        """ Handle all checkbox events. Bound in base class.
        """
        super(IdeSummarizer, self).OnCheck(evt)
        obj = evt.EventObject
        if obj.IsChecked():
            pass


    def savePrefs(self):
        for c in (self.formatField, self.headerCheck, self.noBivariates):
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
        outputSelection = self.getValue(self.formatField) 
        headers = self.getValue(self.headerCheck, False)
        noBivariates = self.getValue(self.noBivariates, False)

        if not output:
            return
        output = os.path.realpath(output)

        try:
            outputType, delimiter = self.DELIMITERS[outputSelection]
        except IndexError:
            outputType, delimiter = self.DELIMITERS[0]

        totalSamples = 0
        for filename in sourceFiles:
            ds = idelib.importer.importFile(filename)
            totalSamples += sum(
                len(sch.getSession())
                for ch in ds.channels.values()
                for sch in ch.subchannels
            )
            ds.close()

        processed = set()
        sampleCount = 0

        with open(output, 'wb') as csvfile, \
        wx.ProgressDialog(
            title=self.GetTitle(),
            message="Exporting...\n\n",
            maximum=totalSamples,
            parent=self,
            style=wx.PD_APP_MODAL|wx.PD_AUTO_HIDE|wx.PD_CAN_ABORT,
        ) as updater:
            # Keyword arguments shared by all exports
            params = dict(
                outputType=outputType,
                delimiter=delimiter,
                headers=headers,
                noBivariates=noBivariates,
                updateInterval=1.5,
                out=None,
                updater=updater,
            )

            csv_writer = csv.writer(csvfile)

            # Writing column headers
            csv_writer.writerow(scripts.idegist.CsvRowTuple._fields)

            class StopExecution(Exception):
                pass

            def update_or_raise(*args, **kwargs):
                alive, skipped = updater.Update(*args, **kwargs)
                if not alive:
                    raise StopExecution
                return skipped

            try:
                for i, filename in enumerate(sourceFiles, 1):
                    basename = os.path.basename(filename)
                    update_or_raise(
                        sampleCount,
                        newmsg="Exporting {} (file {} of {})"
                               .format(basename, i, len(sourceFiles)),
                    )

                    with idelib.importer.importFile(filename) as ds:
                        wx.Yield()
                        for channel in ds.channels.values():
                            for subchannel in channel.subchannels:
                                csv_writer.writerow(scripts.idegist.summarize_sch(subchannel))

                                sampleCount += len(subchannel.getSession())
                                update_or_raise(sampleCount)
                                wx.Yield()

                    processed.add(basename)
            except StopExecution:
                pass

        # TODO: More reporting?
        bulleted = lambda x: " * {}".format(x)
        processed = '\n'.join(bulleted(i) for i in sorted(processed)) or "None"
        msg = (
            "Files processed:\n{}\n\n"
            "Total samples exported: {}"
            .format(processed, sampleCount)
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

