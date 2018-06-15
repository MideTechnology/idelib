'''
Dialogs for exporting data: selecting channels, time range, progress, et cetera.

@todo: Validate time fields.

Created on Nov 21, 2013
@author: dstokes
'''

import locale
import os.path
# import sys

import wx.lib.agw.customtreectrl as CT
import wx; wx=wx
import wx.lib.sized_controls as sc
from collections import defaultdict

# from base import TimeValidator

#===============================================================================
# 
#===============================================================================

class ModalExportProgress(wx.ProgressDialog):
    """ Subclass of the standard progress dialog, implementing the __call__
        method and other attributes needed for a callback (like the Loader).
    """
    def __init__(self, *args, **kwargs):
        self.cancelled = False
        self.message = kwargs.pop('message', 'Exporting %s of %s samples')
        style = wx.PD_CAN_ABORT|wx.PD_APP_MODAL|wx.PD_REMAINING_TIME
        kwargs.setdefault("style", style)
        # XXX: TEST
        kwargs['maximum'] = 1000
        super(ModalExportProgress, self).__init__(*args, **kwargs)
        
    
    def __call__(self, count=0, percent=None, total=None, error=None, 
                 done=False, **kwargs):
        if done:
            return

        if percent is None and total:
            percent = (count+0.0) / total
        percent = int(1000*percent)
        msg = self.message % (locale.format("%d", count, grouping=True),
                              locale.format("%d", total, grouping=True))
        keepGoing, skip = super(ModalExportProgress, self).Update(percent, msg)
        self.cancelled = not keepGoing
        return keepGoing, skip


#===============================================================================
# 
#===============================================================================

class ExportDialog(sc.SizedDialog):
    """ The dialog for selecting data to export. This is in a moderately
        generic form; it can be used as-is, or export types with more specific 
        requirements can subclass it.
        
        @cvar DEFAULT_TITLE: The dialog's default title.
        @cvar DEFAULT_UNITS: 
        @cvar WHAT: The 'verb' associated with the data, e.g. 'rendering',
            for use in warning dialogs.
    """
    
    RB_RANGE_ALL = wx.NewId()
    RB_RANGE_VIS = wx.NewId()
    RB_RANGE_CUSTOM = wx.NewId()
    
    DEFAULT_TITLE = "Export Data"
    DEFAULT_UNITS = ("seconds", "s")
    WHAT = "exporting"
    
    # Means removal options and its overly-verbose tooltip.
    MEANS = ['None', 'Rolling Mean', 'Total Mean']
    
    def __init__(self, *args, **kwargs):
        """
        """
        style = wx.DEFAULT_DIALOG_STYLE \
            | wx.RESIZE_BORDER \
            | wx.MAXIMIZE_BOX \
            | wx.MINIMIZE_BOX \
            | wx.DIALOG_EX_CONTEXTHELP \
            | wx.SYSTEM_MENU

        self.app = wx.GetApp()
        self.root = kwargs.pop('root', None)
        kwargs.setdefault('style', style)
        kwargs.setdefault('title', self.DEFAULT_TITLE)
        self.units = kwargs.pop("units", self.DEFAULT_UNITS)
        self.scalar = kwargs.pop("scalar", self.root.timeScalar)
        self.removeMean = kwargs.pop("removeMean", 2)
        self.noBivariates = kwargs.pop("noBivariates", False)
        self.byType = kwargs.pop("byType", False)
        self.showIds = kwargs.pop('showIds', True)

        super(ExportDialog, self).__init__(*args, **kwargs)
        
        self.noBmp = wx.EmptyBitmapRGBA(16,16,0,0,0,1.0)
        self.rangeBtns = []
        
        self.buildUI()
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okButton = self.FindWindowById(wx.ID_OK)

        self.SetMinSize((340,450))
        self.SetMaxSize((600,1000))
        self.Fit()
        
        if self.root.dataset is not None:
            # This should never occur outside of testing.
            self.InitUI()
            
        self.Layout()
        self.Centre()
        
        self.Bind(wx.EVT_RADIOBUTTON, self.OnAnyRBSelected)
        self.Bind(CT.EVT_TREE_ITEM_CHECKED, self.OnTreeItemSelected)
        self.Bind(wx.EVT_TEXT, self.updateMessages)


    def _formatRange(self, val):
        """ Helper method that formats a time range. """
        msg = "(%%s to %%s %s)" % self.units[1]
        return msg % \
            tuple(map(lambda x: ("%.4f" % x).rstrip("0.") if x else "0",val))


    def getRangeField(self, field, default=None):
        """ Get the actual time, scaled to nanoseconds, from a range field.
        """
        val = field.GetValue()
        if not val:
            return default
        try:
            return float(val) / self.scalar
        except ValueError:
            return default


    def buildUI(self):
        """ Add controls (except the OK/Cancel buttons) to the dialog.
            Separated from `__init__` in order to easily allow subclasses
            to add widgets.
        """
        pane = self.GetContentsPane()

        #=======================================================================
        # Channel/Plot Export Selection
    
        self.tree  = CT.CustomTreeCtrl(pane, -1, 
                                       style=wx.SUNKEN_BORDER,
                                       agwStyle=CT.TR_HAS_BUTTONS|CT.TR_HIDE_ROOT)
        self.tree.SetSizerProps(expand=True, proportion=1)
        self.treeMsg = wx.StaticText(pane, 0, "")
        
        #=======================================================================
        # Export range selection
        
        wx.StaticLine(pane, -1).SetSizerProps(expand=True)
        wx.StaticText(pane, -1, "Range to Export:")
        rangePane = sc.SizedPanel(pane, -1)
        self._addRangeRB(rangePane, self.RB_RANGE_ALL, "All", style=wx.RB_GROUP)
        self._addRangeRB(rangePane, self.RB_RANGE_VIS, "Visible Range").SetValue(True)
        rangeFieldPane = sc.SizedPanel(rangePane,-1)
        rangeFieldPane.SetSizerType("horizontal")
        self._addRangeRB(rangeFieldPane, self.RB_RANGE_CUSTOM, "Specific Range:")
        self.rangeStartT = wx.TextCtrl(rangeFieldPane, -1, "0", size=(80, -1))#, validator=TimeValidator())
        self.rangeEndT = wx.TextCtrl(rangeFieldPane, -1, "999", size=(80, -1))#, validator=TimeValidator())
        wx.StaticText(rangeFieldPane, -1, self.units[1])
        self.rangeMsg = wx.StaticText(rangePane, 0)

        wx.StaticLine(pane, -1).SetSizerProps(expand=True)

        self.removeMeanList, _ = self._addChoice("Mean Removal:", self.MEANS, 
             default=self.removeMean, 
             tooltip=("The method by which to subtract the mean value from the "
                     "data. Only applicable to channels with recorded "
                     "minimum/mean/maximum values (e.g. analog acceleration)."))

        self.noBivariatesCheck, _ = self._addCheck("Disable Bivariate References",
             default=self.noBivariates, 
             tooltip=("Prevent bivariate calibration polynomials from "
                      "referencing other channels (e.g. accelerometer "
                      "temperature compensation). Disabling references "
                      "improves performance."))

        self.buildSpecialUI()

        warnPane = sc.SizedPanel(pane,-1)
        warnPane.SetSizerType("horizontal")
        self.warningIcon = wx.StaticBitmap(warnPane, -1, self.noBmp)
        self.warningMsg = wx.StaticText(warnPane,-1," ")
        self.warningMsg.SetForegroundColour("RED")
        self.warningMsg.SetSizerProps(valign="center")
        warnPane.SetSizerProps(expand=True)
        rangePane.SetSizerProps(expand=True)


    def buildSpecialUI(self):
        """ For subclasses with unique UI elements, implement this. It is
            called after the main UI elements are added and before the
            OK/Cancel buttons.
        """
        pass


    def populateChannelTree(self):
        """ Build the tree view, divided up by channel. Used for export.
        """
        for channel in self.root.dataset.channels.itervalues():
            if not channel.subchannels:
                continue
            self._addTreeItems(self.treeRoot, channel, 
                               types=(CT.TREE_ITEMTYPE_RADIO, 
                                      CT.TREE_ITEMTYPE_CHECK))
#         self.tree.Expand(self.treeRoot)
        self.tree.ExpandAll()
    
    
    def _getChannelName(self, ch):
        if not self.showIds:
            return ch.displayName
        if ch.parent is None:
            return "Channel %d: %s" % (ch.id, ch.displayName)
        return "Channel %d.%d: %s" % (ch.parent.id, ch.id, ch.displayName)
        
    
    
    def populateTypeTree(self):
        """ Build the tree view, divided up by data type. Used for rendering.
        """
        types = defaultdict(list)
        for ch in self.root.dataset.channels.itervalues():
            if not self.root.showDebugChannels and ch.name.startswith("DEBUG"):
                continue
            for subc in ch.subchannels:
                types[subc.units[0]].append(subc)
        
        first = True
        for plotType in sorted(types.keys()):
            objs = types[plotType]
            if not objs:
                continue
            
            parentItem = self.tree.AppendItem(self.treeRoot, plotType, 
                                              ct_type=CT.TREE_ITEMTYPE_RADIO)
            if first:
                parentItem.Set3StateValue(wx.CHK_CHECKED)
                first = False
                
            for subc in sorted(objs, key=self._getChannelName):
                item = self.tree.AppendItem(parentItem, 
                                            self._getChannelName(subc), 
                                            ct_type=CT.TREE_ITEMTYPE_CHECK, 
                                            data=subc)
                item.Set3StateValue(wx.CHK_CHECKED)
        self.tree.ExpandAll()
            
            

    def InitUI(self):
        """ Set up and display actual data in the dialog.
        """
#         self.treeRoot = self.tree.AddRoot(self.root.dataset.name)
        self.treeRoot = self.tree.AddRoot(os.path.basename(self.root.dataset.filename))
        
        if self.byType:
            self.populateTypeTree()
        else:
            self.populateChannelTree()
        
        self.range = self.root.getTimeRange()
        scaledRange = self.range[0] * self.scalar, self.range[1] * self.scalar
        visStart, visEnd = self.root.getVisibleRange()
        scaledVisRange = visStart * self.scalar, visEnd * self.scalar

        self.rangeStartT.SetValue(str(scaledVisRange[0]))
        self.rangeEndT.SetValue(str(scaledVisRange[1]))
        self.rangeBtns[0].SetLabel("All %s" % self._formatRange(scaledRange))
        self.rangeBtns[1].SetLabel("Visible Time Range %s" % \
                                   self._formatRange(scaledVisRange))
        
        w,_ = self.GetSize()
        for r in self.rangeBtns[:2]:
            r.SetSize((w-16,-1))
        
        self.showColumnsMsg(msg="")
        self.updateMessages()
        self.OnAnyRBSelected(None)

        
    def _addRangeRB(self, parent, ID, label, **kwargs):
        """ Helper to add range RadioButtons
        """
        rb = wx.RadioButton(parent, ID, label, **kwargs)
        self.rangeBtns.append(rb)
        return rb

    
    def _addTreeItems(self, parentItem, obj, types=None, 
                 defaultType=CT.TREE_ITEMTYPE_CHECK):
        """ Helper to add items to the tree view.
        """
        if obj is None:
            return
        if not self.root.showDebugChannels and obj.name.startswith("DEBUG"):
            return
         
        if types:
            ct_type = types[0]
        else:
            ct_type = defaultType
            
        childItem = self.tree.AppendItem(parentItem, self._getChannelName(obj), 
                                         ct_type=ct_type, data=obj)
        if ct_type == CT.TREE_ITEMTYPE_CHECK or self.tree.GetPrevSibling(childItem) is None:
            childItem.Set3StateValue(wx.CHK_CHECKED)
        for c in obj.children:
            self._addTreeItems(childItem, c, types=types[1:])
        if parentItem is not self.treeRoot and ct_type == CT.TREE_ITEMTYPE_RADIO:
            self.tree.Expand(parentItem)


    def _addChoice(self, label, choices, default=None, tooltip=None, parent=None):
        """ Add a drop-down list widget. 
        
            @param label: 
            @param choices: A list of strings 
            @keyword default: The pre-selected item, either a string or an index
                into `choices`.
            @keyword tooltip: A pop-up help string.
            @keyword parent: The list's parent. Use if adding multiple choice
                controls.
            @return: A tuple with (control, parent)
        """
        if parent is None:
            parent = sc.SizedPanel(self.GetContentsPane(),-1)
            parent.SetSizerType("form")
            parent.SetSizerProps(expand=True)
        l = wx.StaticText(parent, -1, label)
        l.SetSizerProps(valign="center")
        ctrl = wx.Choice(parent, -1, choices=choices)
        if tooltip:
            ctrl.SetToolTipString(tooltip)
        ctrl.SetSizerProps(expand=True)
        if isinstance(default, basestring) and default in choices:
            ctrl.Select(choices.index(default))
        elif isinstance(default, int):
            ctrl.Select(default)
        ctrl._label = l
        return ctrl, parent


    def _addCheck(self, label, default=False, tooltip=None, parent=None):
        """ Add a checkbox widget. 
        
            @param label: The checkbox's text
            @keyword default: `True` to check, `False` if unchecked.
            @keyword tooltip: A pop-up help string.
            @keyword parent: The list's parent, if not the window's main pane.
            @return: A tuple with (control, parent)
        """
        if parent is None:
            parent = self.GetContentsPane()
        ctrl = wx.CheckBox(parent, -1, label)
        ctrl.SetValue(default)
        if isinstance(tooltip, basestring):
            ctrl.SetToolTipString(tooltip)
        return ctrl, parent
    
    
    def getSelectedChannels(self, _item=None, _selected=None):
        """ Get all selected (sub-)channels. Recursive. Don't call with
            arguments. 
        """
        parentItem = self.treeRoot if _item is None else _item
        _selected = [] if _selected is None else _selected
        if _item is not None and not _item.IsChecked():
            return _selected
        for subitem in parentItem.GetChildren():
            if not subitem.IsEnabled():
                continue
            if subitem.HasChildren() and subitem.IsChecked():
                self.getSelectedChannels(subitem, _selected)
            elif subitem.IsChecked() and subitem.IsEnabled():
                _selected.append(subitem.GetData())
                
        return _selected
    
    
    def getExportRange(self):
        """ Get the actual export range: the manually entered numbers,
            the visible range, or the entirety of the dataset.
        """
        if self.rangeBtns[2].GetValue():
            # selected range
            return (self.getRangeField(self.rangeStartT, self.range[0]),
                    self.getRangeField(self.rangeEndT, self.range[1]))
            pass
        elif self.rangeBtns[1].GetValue():
            # visible range
            return self.root.getVisibleRange()
        else:
            # All (presumably)
            return self.range


    def getSettings(self):
        """ Retrieve the settings specified in the dialog as a dictionary. The
            dictionary contains the following keys:
            
                * channels: a list of `mide_ebml.dataset.SubChannel` objects.
                * indexRange: The first and last event index in the specified
                    interval of time.
                * numRows: The number of samples in the given channel in the
                    specified interval.
                * source: The `mide_ebml.dataset.EventList` for the parent
                    channel in the current session.
                * timeRange: The specified interval's start and end times.

            @return: A dictionary of settings or `None` if there's a problem
                (e.g. no channels have been selected).
        """
        channels = self.getSelectedChannels()
        if len(channels) == 0:
            # This should never happen, but just in case:
            return None
        
        source = channels[0].parent.getSession(self.root.session.sessionId)
        startTime, stopTime = self.getExportRange()
        startIdx, stopIdx = source.getRangeIndices(startTime, stopTime)
        callbackInt = wx.GetApp().getPref('exportCallbackInterval', 0.0005)

        return {'startTime': startTime,
                'endTime': stopTime,
                'start': startIdx,
                'stop': stopIdx,
                'subchannels': channels,
                'numRows': stopIdx - startIdx,
                'removeMean': self.removeMeanList.GetSelection(),
                'source': source,
                'callbackInterval':  callbackInt,
                'noBivariates': self.noBivariatesCheck.GetValue()
                }
    

    def showColumnsMsg(self, num=0, msg=None):
        """ Display a message below the tree view, meant to show the number
            of columns that will be exported.
        """
        if msg is None:
            if num == 1:
                msg = "1 subchannel selected"
            else:
                msg = "%d subchannels selected" % num
        self.treeMsg.SetLabel(msg)


    def showRangeMsg(self, num=0, msg=None):
        """ Display a message about the selected time range (i.e. the number
            of samples it contains).
        """
        if msg is None:
            if num == 0:
                num = self.getEventCount()
            num = max(0, num)
            countStr = locale.format("%d", num, grouping=True)
            msg = "Selected time range contains %s samples" % countStr
        self.rangeMsg.SetLabel(msg)


    def showWarning(self, icon, msg):
        """ Show a warning message about the selected export time range.
        
            @param icon: An icon ID (e.g. wx.ART_WARNING, wx.ART_ERROR, 
                or wx.ART_INFO)
            @param msg: The text of the message to display.
        """
        if icon is not None:
            bmp = wx.ArtProvider.GetBitmap(icon, wx.ART_CMN_DIALOG, (16,16))
            self.warningIcon.Show()
            self.warningIcon.SetBitmap(bmp)
        self.warningMsg.SetLabel(msg)
        self.warningMsg.Show()


    def hideWarning(self):
        """ Hide the export range warning.
        """
        self.warningMsg.SetLabel("")
        self.warningIcon.SetBitmap(self.noBmp)
#         self.warningIcon.Hide()
#         self.warningMsg.Hide()


    def updateMessages(self, event=None, treeItem=None):
        """ Update the number of selected channels and time range messages.
        
            @keyword event: a `wx.Event`, so this method can be used as an
                event handler.
            @keyword item: The selected parent item in the tree. Used by the
                tree item check handler to work around an issue detecting
                selected items. Do not use.
        """
        numEvents = 0
        channels = self.getSelectedChannels(_item=treeItem)
        self.showColumnsMsg(len(channels))
        if len(channels) > 0:
            numEvents = self.getEventCount()
        self.showRangeMsg(numEvents)
        self.validateSettings(channels)
        

    def validateSettings(self, selected=None):
        """ High-level validation of input range; handles warning displays
            and enabling the "OK" button.
        """
        okToExport = True
        if selected is None:
            selected = self.getSelectedChannels()
        
        self.showColumnsMsg(len(selected))

        okToExport = okToExport and len(selected) > 0        
        self.okButton.Enable(okToExport)
        return True


    def getEventCount(self):
        """ Get the number of events in the specified time span.
        """
        subchannels = self.getSelectedChannels()
        if len(subchannels) == 0:
            return 0
        timerange = self.getExportRange()
        if timerange[0] >= timerange[1]:
            return 0
        events = subchannels[0].getSession(self.root.session.sessionId)
        first, last = events.getRangeIndices(*timerange)
        return (last - first) * len(subchannels)
        

    #===========================================================================
    # 
    #===========================================================================

    def OnAnyRBSelected(self, evt):
        """ Event handler for any RadioButton change.
        """
        if evt is None:
            rbId = None
        else:
            # Since the 3rd radio button is not immediately following the 
            # 2nd, Windows doesn't connect them. Set/reset manually.
            rbId = evt.GetId()
            for rb in self.rangeBtns:
                if rb.GetId() != rbId:
                    rb.SetValue(False)
                
        custom = rbId == self.RB_RANGE_CUSTOM
        self.rangeStartT.Enable(custom)
        self.rangeEndT.Enable(custom)
        self.updateMessages()


    def OnTreeItemSelected(self, evt):
        """ Event handler for tree item selection.
        """
        # This song-and-dance is to get around the fact that when the checked
        # item changes, both the previous and new items are considered
        # checked until the event finishes processing.
        treeItem = evt.GetItem()
        if treeItem.GetChildrenCount() == 0:
            treeItem = treeItem.GetParent()
            
        self.updateMessages(treeItem=treeItem)


    #===========================================================================
    # 
    #===========================================================================

    @classmethod
    def makeSettings(cls, *args, **kwargs):
        """ Create a settings dict based on an input from initSettings
        """
        initSettings = kwargs["initSettings"]
        root = kwargs['root']
        import time
        while root.dataset.loading:
            time.sleep(1)
        time.sleep(1)
        channelName = kwargs.pop('channel', 'adc').lower()
        for key, channelCheck in root.dataset.channels.iteritems():
            if channelCheck.displayName.lower() == channelName:
                channels = channelCheck.children
                break
        source = channels[0].parent.getSession(root.session.sessionId)
        try:
            startTime = float(initSettings["startTime"])
        except:
            startTime = -1
        try:
            stopTime = float(initSettings["stopTime"])
        except:
            stopTime = 100
        stopTime *= 1e6
        startIdx, stopIdx = source.getRangeIndices(startTime, stopTime)
        callbackInt = wx.GetApp().getPref('exportCallbackInterval', 0.0005)
        try:
            removeMean = int(initSettings["removeMean"])
            if not 0 <= removeMean <= 2:
                raise
        except:
            removeMean = 2
        noBivariatesCheck = initSettings.get("noBivariatesCheck", False)
        channels.sort(key=lambda x: x.name)
        return {'startTime': startTime,
                'endTime': stopTime,
                'start': startIdx,
                'stop': stopIdx,
                'subchannels': channels,
                'numRows': stopIdx - startIdx,
                'removeMean': removeMean,
                'source': source,
                'callbackInterval': callbackInt,
                'noBivariates': noBivariatesCheck
                }

    @classmethod
    def getExport(cls, *args, **kwargs):
        """ Display the export settings dialog and return the results. Standard
            warnings and error messages will be displayed (no data, etc).
            
            @keyword root: The root viewer window.
            @keyword title: The dialog's title, overrides the dialog's default.
            @keyword parent: The dialog's parent. Defaults to `root` if `root`
                is applicable.
            @keyword warnSlow: If `True`, warn the user if an import is 
                underway (it will make export slow).
            @keyword sortChannels: If `True`, sort channels by name.
            @return: A dictionary of settings or `None`
        """
#         title = kwargs.setdefault('title', cls.DEFAULT_TITLE)
        initSettings = kwargs.pop("initSettings", False)
        if initSettings:
            return cls.makeSettings(initSettings=initSettings, *args, **kwargs)

        root = kwargs['root']
        parent = root if isinstance(root, wx.Window) else None
        warnSlow = kwargs.pop('warnSlow', True)
        sortChannels = kwargs.pop('sortChannels', True)
        
        dialog = cls(parent, -1, **kwargs)
        result = dialog.ShowModal()
        settings = dialog.getSettings()
        numRows = dialog.getEventCount()
        title = dialog.GetTitle()
        dialog.Destroy()

        if result == wx.ID_CANCEL or settings is None:
            return None

        if numRows <= 0:
            root.ask("The export range contained no data.", title,
                     style=wx.OK, icon=wx.ICON_ERROR)
            return None

        if warnSlow and root.dataset.loading:
            x = root.ask("A dataset is currently being loaded. This will "
                         "make %s slow and may produce inconsistencies in the "
                         "data. \n\nDo you want to continue?" % cls.WHAT, 
                         title)
            if x != wx.ID_YES:
                return None
        
        if sortChannels:
            settings['subchannels'].sort(key=lambda x: x.name)

        return settings

    
#===============================================================================
# 
#===============================================================================

class CSVExportDialog(ExportDialog):
    """ A subclass of the standard `ExportDialog`, featuring options
        applicable only to CSV.
    """
    
    DEFAULT_TITLE= "Export Data"
    
    def __init__(self, *args, **kwargs):
        self._addHeaders = kwargs.pop('addHeaders', False)
        self._utcTime = kwargs.pop('useUtcTime', False)
        self._isoTime = kwargs.pop('useIsoFormat', False)
        self.exportType = kwargs.pop('exportType', 'csv').lower()
        
        self.DEFAULT_TITLE = "Export %s" % self.exportType.upper()
        kwargs.setdefault('title', self.DEFAULT_TITLE)
        super(CSVExportDialog, self).__init__(*args, **kwargs)


    def buildSpecialUI(self):
        """ Called before the buttons are added.
        """
#         self.removeMeanList, _ = self._addChoice("Mean Removal:", self.MEANS, 
#              self.removeMean, tooltip="Subtract a the mean from the data. "
#                                       "Not applicable to all channels.")
        self.headerCheck, subpane = self._addCheck("Include Column Headers",
                                     default=self._addHeaders)
        self.utcCheck, _ = self._addCheck("Use Absolute UTC Timestamps",
                                          default=self._utcTime, parent=subpane)
        self.isoCheck, _ = self._addCheck("Use ISO Time Format",
                                          default=self._isoTime, parent=subpane)
        
        self.isoCheck.Enable(self._utcTime)
        self.utcCheck.Bind(wx.EVT_CHECKBOX, self.OnUtcCheck)

        if self.exportType == 'mat':
            self.headerCheck.SetLabel("Include Channel Names")
            self.isoCheck.Hide()


    def showColumnsMsg(self, num=0, msg=None):
        """ Display a message below the tree view, meant to show the number
            of columns that will be exported.
        """
        if msg is None:
            if num == 0:
                msg = "No columns selected"
            else:
                msg = "Exporting %d columns (time + %d data)" % (num+1,num)
        self.treeMsg.SetLabel(msg)


    def OnUtcCheck(self, evt):
        self.isoCheck.Enable(evt.IsChecked())


    def getSettings(self):
        """ Retrieve the settings specified in the dialog as a dictionary. The
            dictionary contains the following keys:
            
                * addHeaders: `True` if the 'Include Column Headers' option
                    was checked.
                * channels: a list of `mide_ebml.dataset.SubChannel` objects.
                * indexRange: The first and last event index in the specified
                    interval of time.
                * numRows: The number of samples in the given channel in the
                    specified interval.
                * source: The `mide_ebml.dataset.EventList` for the parent
                    channel in the current session.
                * timeRange: The specified interval's start and end times.

            @return: A dictionary of settings or `None` if there's a problem
                (e.g. no channels have been selected).
        """
        result = super(CSVExportDialog, self).getSettings()
        if result is None:
            return None
        
        removeMeanType = self.removeMeanList.GetSelection()
        result['removeMean'] = removeMeanType > 0
        if removeMeanType == 1:
            result['meanSpan'] = self.app.getPref('rollingMeanSpan', 5.0) / self.root.timeScalar
        else:
            result['meanSpan'] = -1
            
        result['headers'] = self.headerCheck.GetValue()
        result['useUtcTime'] = self.utcCheck.GetValue()
        result['useIsoFormat'] = self.isoCheck.GetValue()
        result['timeScalar'] = self.root.timeScalar
        return result

#===============================================================================
# 
#===============================================================================

class FFTExportDialog(ExportDialog):
    """ A subclass of the standard `ExportDialog`, featuring options
        applicable only to FFT.
    """

    SEQUENTIAL = 0
    INTERLACED = 1
    SAMPLE_ORDER = ['Sequential', 'Interlaced']

    WINDOW_SIZES = map(str, [2**x for x in xrange(10,21)])
    DEFAULT_WINDOW_SIZE = 2**16
    
    # These will be removed later, once memory usage is accurately computed.
    manyEvents = 10**6
    maxEvents = manyEvents * 4
    
    DEFAULT_TITLE = "Render FFT"
    WHAT = "rendering"
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the same arguments as any other dialog, plus
            some additional keywords:
            
            @keyword root: The root Viewer window
            @keyword units: The range units to show (e.g. seconds) 
            @keyword scalar: The range units scalar for the display.
            @keyword windowSize: The size of the sample window for use with
                Welch's method
            @keyword samplingOrder: The order in which the samples are taken.
                Not currently implemented.
        """
        self.app = wx.GetApp()
        self._samplingOrder = kwargs.pop('samplingOrder', self.SEQUENTIAL)
        self.windowSize = str(self.app.getPref('psd.windowSize', self.DEFAULT_WINDOW_SIZE))

        if self.windowSize not in self.WINDOW_SIZES:
            self.windowSize = str(self.DEFAULT_WINDOW_SIZE)

        super(FFTExportDialog, self).__init__(*args, **kwargs)


    def buildSpecialUI(self):
        """ Called before the OK/Cancel buttons are added.
        """
        pass
        # TODO: Fix windowed FFT calculation, re-enable window size UI
#         self.sizeList, _subpane = self._addChoice("Sampling Window Size:",
#             choices=self.WINDOW_SIZES, default=self.windowSize, 
#             tooltip="The size of the 'window' used in Welch's method")
        
#         self.orderList, _ = self._addChoice("Sampling Order:",
#             choices=self.SAMPLE_ORDER, default=self._samplingOrder,
#             parent = subpane)        


    def validateSettings(self, selected=None):
        """ High-level validation of input range; handles warning displays
            and enabling the "OK" button.
        """
        okToExport = super(FFTExportDialog, self).validateSettings(selected)
        
        numEvents = self.getEventCount()
        
        eventLimits = self.getSafeEventCount()
        if numEvents > eventLimits[0]:
            if numEvents > eventLimits[1]:
                # TODO: possibly disable OK, but this guess is too broad, so
                #    just warn and go ahead and let them try to export.
                icon = wx.ART_ERROR
            else:
                icon = wx.ART_WARNING

            self.showWarning(icon, 
                            "Memory may be insufficient for this many samples")
        else:
            self.hideWarning()
        
        self.okButton.Enable(okToExport)
        return True


    def getSafeEventCount(self):
        """ Get the number of events that the available memory can support.
        
            @return: A tuple with the max safe count and the upper limit.
        """
        # TODO: Actually compute how many events will exceed available memory.
        return self.manyEvents, self.maxEvents


    def getSettings(self):
        """ Retrieve the settings specified in the dialog as a dictionary. The
            dictionary contains the following keys:
            
                * channels: a list of `mide_ebml.dataset.SubChannel` objects.
                * indexRange: The first and last event index in the specified
                    interval of time.
                * numRows: The number of samples in the given channel in the
                    specified interval.
                * source: The `mide_ebml.dataset.EventList` for the parent
                    channel in the current session.
                * timeRange: The specified interval's start and end times.
                * windowSize: The specified window (a/k/a slice) size for use
                    with Welch's Method.

            @return: A dictionary of settings or `None` if there's a problem
                (e.g. no channels have been selected).
        """
        result = super(FFTExportDialog, self).getSettings()
        if result is None:
            return None
        
#         windowSize = int(self.sizeList.GetString(self.sizeList.GetSelection()))
#         result['windowSize'] = windowSize
#         result['samplingOrder'] = self.orderList.GetSelection()
        return result


#===============================================================================
# 
#===============================================================================


class PSDExportDialog(FFTExportDialog):
    """ A subclass of the standard `ExportDialog`, featuring options
        applicable only to a PSD.
    """
    
    DEFAULT_TITLE = "Render PSD"
    WHAT = "rendering"
    
    def __init__(self, *args, **kwargs):
        # Keep separate many/max values for standard and windowed calculation.
        # The windowed version is less memory intensive, but the total number
        # of samples still counts.
        self.root = kwargs['root']
        self.app = wx.GetApp()
        self.useWelch = self.app.getPref('psd.useWelch', False) 
        self.fftMany = self.manyEvents, self.maxEvents
        self.welchMany = self.manyEvents*8, self.maxEvents*8
        
        super(PSDExportDialog, self).__init__(*args, **kwargs)
        self.OnWelchChecked(self.useWelch)
    
    
    def buildSpecialUI(self):
        """ Called before the OK/Cancel buttons are added.
        """
        # TODO: Fix windowed FFT calculation, re-enable window size UI
#         wx.StaticLine(self.GetContentsPane(), -1).SetSizerProps(expand=True)
        self.welchCheck, _ = self._addCheck("Use windowed method", self.useWelch,
            tooltip="If checked, Welch's method is used to calculate the PSD; output will be in dB/Hz.")
        self.sizeList, _ = self._addChoice("Sampling Window Size:",
            choices=self.WINDOW_SIZES, default=self.windowSize, 
            tooltip="The size of the 'window' (in samples) used in Welch's method")
        self.welchCheck.Bind(wx.EVT_CHECKBOX, self.OnWelchChecked)


    @classmethod
    def makeSettings(cls, *args, **kwargs):
        """ Create a settings dict based on an input from initSettings
        """
        result = super(PSDExportDialog, cls).makeSettings(*args, **kwargs)
        initSettings = kwargs["initSettings"]
        try:
            result['windowSize'] = int(initSettings["windowSize"])
        except:
            result['windowSize'] = 2**14

        result['useWelch'] = initSettings["useWelch"]
        return result


    def OnWelchChecked(self, evt):
        """ Handle the 'use windowed' checkbox changing. Can also be called
            manually with either `True` or `False` to explicitly enable/disable
            the related UI elements.
        """
        if isinstance(evt, bool):
            checked = evt
        else:
            checked = evt.Checked()
        self.sizeList.Enable(checked)
        self.sizeList._label.Enable(checked)
        
        if checked:
            self.manyEvents, self.maxEvents = self.welchMany
        else:
            self.manyEvents, self.maxEvents = self.fftMany
            
        self.updateMessages()


    def getSettings(self):
        """ Retrieve the settings specified in the dialog as a dictionary. The
            dictionary contains the following keys:
            
                * channels: a list of `mide_ebml.dataset.SubChannel` objects.
                * indexRange: The first and last event index in the specified
                    interval of time.
                * numRows: The number of samples in the given channel in the
                    specified interval.
                * source: The `mide_ebml.dataset.EventList` for the parent
                    channel in the current session.
                * timeRange: The specified interval's start and end times.
                * windowSize: The specified window (a/k/a slice) size for use
                    with Welch's Method.

            @return: A dictionary of settings or `None` if there's a problem
                (e.g. no channels have been selected).
        """
        result = super(PSDExportDialog, self).getSettings()
        if result is None:
            return None
        
        windowSize = int(self.sizeList.GetString(self.sizeList.GetSelection()))
        result['windowSize'] = windowSize
        result['useWelch'] = self.welchCheck.GetValue()
        
        return result

#===============================================================================
# 
#===============================================================================

class SpectrogramExportDialog(FFTExportDialog):
    """ A subclass of the standard `ExportDialog`, featuring options
        applicable only to a Spectrogram.
    """
    
    DEFAULT_TITLE = "Render Spectrogram"
    WHAT = "rendering"
    
    SLICES = map(str, [2**x for x in xrange(9)])
    DEFAULT_SLICES = "4"
    
    manyEvents = FFTExportDialog.manyEvents * 4
    maxEvents = FFTExportDialog.maxEvents * 4
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.slicesPerSec = str(kwargs.pop('slices', self.DEFAULT_SLICES))
        if self.slicesPerSec not in self.SLICES:
            self.slicesPerSec = self.DEFAULT_SLICES
        super(SpectrogramExportDialog, self).__init__(*args, **kwargs)
        
    
    def buildSpecialUI(self):
        """ Called before the OK/Cancel buttons are added.
        """
#         self.sizeList, subpane = self._addChoice("Sampling Window Size:",
#             choices=self.WINDOW_SIZES, default=self.windowSize, 
#             tooltip="The size of the 'window' used in Welch's method")
        
#         wx.StaticLine(self.GetContentsPane(), -1).SetSizerProps(expand=True)
        subpane = None
        self.resList, _parent = self._addChoice("Slices per Second:", 
            choices=self.SLICES, default=self.slicesPerSec,
            tooltip="The granularity of the horizontal axis", 
            parent = subpane)


    def getSampleRate(self):
        """ Get the sample rate of the selected subchannels.
        """
        subchannels = self.getSelectedChannels()
        if len(subchannels) == 0:
            return None
        events = subchannels[0].getSession(self.root.session.sessionId)
        return events.getSampleRate()


    @classmethod
    def makeSettings(cls, *args, **kwargs):
        """ Create a settings dict based on an input from initSettings
        """
        initSettings = kwargs["initSettings"]
        result = super(SpectrogramExportDialog, cls).makeSettings(*args, **kwargs)
        try:
            result['slicesPerSec'] = int(initSettings["windowSize"])
        except:
            result['slicesPerSec'] = 2**14

        result['useWelch'] = initSettings["useWelch"]
        return result


    def getSettings(self):
        """ Retrieve the settings specified in the dialog as a dictionary. The
            dictionary contains the following keys:
            
                * channels: a list of `mide_ebml.dataset.SubChannel` objects.
                * indexRange: The first and last event index in the specified
                    interval of time.
                * numRows: The number of samples in the given channel in the
                    specified interval.
                * slices: The number of slices per second to plot (i.e. the
                    X resolution).
                * source: The `mide_ebml.dataset.EventList` for the parent
                    channel in the current session.
                * timeRange: The specified interval's start and end times.
                * windowSize: The specified window (a/k/a slice) size for use
                    with Welch's Method.

            @return: A dictionary of settings or `None` if there's a problem
                (e.g. no channels have been selected).
        """
#         result = super(SpectrogramExportDialog, self).getSettings()
        result = ExportDialog.getSettings(self)
        if result is None:
            return None
        
        slices = int(self.resList.GetString(self.resList.GetSelection()))
        result['slicesPerSec'] = slices
        return result


#===============================================================================
# 
#===============================================================================


# XXX: FOR DEVELOPMENT TESTING. REMOVE ME!
if __name__ == '__main__':# or True:
    locale.setlocale(locale.LC_ALL, 'English_United States.1252')
    
    from pprint import pprint
    from mide_ebml import importer
    doc=importer.importFile(updater=importer.SimpleUpdater(0.01))
    
    class FakeViewer(object):
        dataset = doc
        session = doc.lastSession
        timeScalar = 1.0/(10**6)
        timerange = (1043273L*2,7672221086L)
        showDebugChannels = True
        
        def getVisibleRange(self):
            return 0, 2**32-1
        
        def getTimeRange(self):
            return self.timerange
        
    
    class FakeApp(wx.App):
        def getPref(self, k, default):
            return default
        
        
    root=FakeViewer()
    
    DIALOGS_TO_SHOW = (
#         (ExportDialog, {'root': root}),
        (CSVExportDialog, {'root': root, 'exportType':'CSV', 'byType': False}),
        (CSVExportDialog, {'root': root, 'exportType':'MAT'}),
        (FFTExportDialog, {'root': root, 'byType': True}),
        (PSDExportDialog, {'root': root, 'byType': True}),
        (SpectrogramExportDialog, {'root': root, 'byType': True}),
    )
    
    app = FakeApp()
    for dialogClass, kwargs in DIALOGS_TO_SHOW:
        title = "Testing %s" % dialogClass.__name__
        results = dialogClass.getExport(**kwargs)#, title=title)

        print ("*"*5), title, ("*"*5)
        pprint(results)
    app.MainLoop()