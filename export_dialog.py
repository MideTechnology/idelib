'''
Created on Nov 21, 2013

@author: dstokes
'''

import locale

import wx.lib.agw.customtreectrl as CT
import wx; wx=wx
import wx.lib.sized_controls as sc

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
        self.message = kwargs.pop('message', 'Exporting %d of %d samples')
        style = wx.PD_CAN_ABORT|wx.PD_APP_MODAL|wx.PD_REMAINING_TIME
        kwargs.setdefault("style", style)
        super(ModalExportProgress, self).__init__(*args, **kwargs)
        
    
    def __call__(self, count=0, percent=None, total=None, error=None, 
                 done=False):
        if done:
            return
        msg = self.message % (count, total)
        keepGoing, skip = super(ModalExportProgress, self).Update(count, msg)
        self.cancelled = not keepGoing
        return keepGoing, skip


#===============================================================================
# 
#===============================================================================

class ExportDialog(sc.SizedDialog):
    """ The dialog for selecting data to export. This is in a moderately
        generic form; it can be used as-is, or export types with more specific 
        requirements can subclass it.
    """
    
    RB_RANGE_ALL = wx.NewId()
    RB_RANGE_VIS = wx.NewId()
    RB_RANGE_CUSTOM = wx.NewId()
    
    defaultUnits = ("seconds", "s")
    
    def __init__(self, *args, **kwargs):
        """
        """
        style = wx.DEFAULT_DIALOG_STYLE \
            | wx.RESIZE_BORDER \
            | wx.MAXIMIZE_BOX \
            | wx.MINIMIZE_BOX \
            | wx.DIALOG_EX_CONTEXTHELP \
            | wx.SYSTEM_MENU

        self.root = kwargs.pop('root', None)
        kwargs.setdefault('style', style)
        self.units = kwargs.pop("units", self.defaultUnits)
        self.scalar = kwargs.pop("scalar", self.root.timeScalar)

        super(ExportDialog, self).__init__(*args, **kwargs)
        
        self.noBmp = wx.EmptyBitmapRGBA(16,16,0,0,0,1.0)
        self.rangeBtns = []
        
        self.buildUI()
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okButton = self.FindWindowById(wx.ID_OK)

        self.SetMinSize((340,450))
        self.SetMaxSize((500,600))
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
                                       agwStyle=CT.TR_HAS_BUTTONS)
        self.tree.SetSizerProps(expand=True, proportion=1)
        self.treeMsg = wx.StaticText(pane, 0, "")#(export description, i.e. number of columns)")
        
        #=======================================================================
        # Export range selection
        
        wx.StaticLine(pane, -1).SetSizerProps(expand=True)
        wx.StaticText(pane, -1, "Range to Export:")
        rangePane = sc.SizedPanel(pane, -1)
        self._addRangeRB(rangePane, self.RB_RANGE_ALL, "All", style=wx.RB_GROUP),
        self._addRangeRB(rangePane, self.RB_RANGE_VIS, "Visible Range")
        rangeFieldPane = sc.SizedPanel(rangePane,-1)
        rangeFieldPane.SetSizerType("horizontal")
        self._addRangeRB(rangeFieldPane, self.RB_RANGE_CUSTOM, "Specific Range:")
        self.rangeStartT = wx.TextCtrl(rangeFieldPane, -1, "0", size=(80, -1))#, validator=TimeValidator())
        self.rangeEndT = wx.TextCtrl(rangeFieldPane, -1, "999", size=(80, -1))#, validator=TimeValidator())
        wx.StaticText(rangeFieldPane, -1, self.units[1])
        self.rangeMsg = wx.StaticText(rangePane, 0)

        warnPane = sc.SizedPanel(pane,-1)
        warnPane.SetSizerType("horizontal")
        self.rangeWarnIcon = wx.StaticBitmap(warnPane, -1, self.noBmp)
        self.rangeWarnMsg = wx.StaticText(warnPane,-1,"")
        self.rangeWarnMsg.SetForegroundColour("RED")
        self.rangeWarnMsg.SetSizerProps(valign="center")
        warnPane.SetSizerProps(expand=True)
        rangePane.SetSizerProps(expand=True)
        wx.StaticLine(pane, -1).SetSizerProps(expand=True)

        self.buildSpecialUI()


    def buildSpecialUI(self):
        """ For subclasses with unique UI elements, implement this. It is
            called after the main UI elements are added and before the
            OK/Cancel buttons.
        """
        pass


    def InitUI(self):
        """ Set up and display actual data in the dialog.
        """
        self.treeRoot = self.tree.AddRoot(self.root.dataset.name)
        for sensor in self.root.dataset.sensors.itervalues():
            self._addTreeItems(self.treeRoot, sensor, types=(CT.TREE_ITEMTYPE_RADIO,
                                                   CT.TREE_ITEMTYPE_RADIO,
                                                   CT.TREE_ITEMTYPE_CHECK))
        self.tree.Expand(self.treeRoot)
        
        self.range = self.root.getTimeRange()
        scaledRange = self.range[0] * self.scalar, self.range[1] * self.scalar
        visStart, visEnd = self.root.getVisibleRange()
        scaledVisRange = visStart * self.scalar, visEnd * self.scalar
        
        self.rangeStartT.SetValue(str(scaledVisRange[0]))
        self.rangeEndT.SetValue(str(scaledVisRange[1]))
        self.rangeBtns[0].SetLabel("All %s" % self._formatRange(scaledRange))
        self.rangeBtns[1].SetLabel("Visible Time Range %s" % self._formatRange(scaledVisRange))
        
        w,_ = self.GetSize()
        for r in self.rangeBtns[:2]:
            r.SetSize((w-16,-1))
        
        self.showColumnsMsg(msg="")
        self.updateMessages()
        self.OnAnyRBSelected(None)

        
    def _addRangeRB(self, parent, ID, label, **kwargs):
        """ Helper to add range RadioButtons
        """
        self.rangeBtns.append(wx.RadioButton(parent, ID, label, **kwargs))

    
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
            
        childItem = self.tree.AppendItem(parentItem, obj.name, ct_type=ct_type, data=obj)
        if ct_type == CT.TREE_ITEMTYPE_CHECK or self.tree.GetPrevSibling(childItem) is None:
            childItem.Set3StateValue(wx.CHK_CHECKED)
        for c in obj.children:
            self._addTreeItems(childItem, c, types=types[1:])
        if ct_type == CT.TREE_ITEMTYPE_RADIO:
            self.tree.Expand(parentItem)

    
    def getSelectedChannels(self, _item=None, _selected=None):
        """ Get all selected (sub-)channels. Recursive. Don't call with
            arguments. 
        """
        _item = self.treeRoot if _item is None else _item
        _selected = [] if _selected is None else _selected
        for subitem in _item.GetChildren():
            if subitem.HasChildren() and subitem.IsChecked():
                self.getSelectedChannels(subitem, _selected)
            elif subitem.IsChecked():
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


    def showRangeMsg(self, num=0, msg=None):
        """
        """
        if msg is None:
            if num > 0:
                countStr = locale.format("%d", num, grouping=True)
                msg = "Selected time range contains %s samples" % countStr
            else:
                msg = "Selected time range contains %d samples" %\
                    self.getEventCount()
        self.rangeMsg.SetLabel(msg)


    def showWarning(self, icon, msg):
        """ Show a warning message about the selected export time range.
        
            @param icon: An icon ID (e.g. wx.ART_WARNING, wx.ART_ERROR, 
                or wx.ART_INFO)
            @param msg: The text of the message to display.
        """
        if icon is not None:
            bmp = wx.ArtProvider.GetBitmap(icon, wx.ART_CMN_DIALOG, (16,16))
            self.rangeWarnIcon.Show()
            self.rangeWarnIcon.SetBitmap(bmp)
        self.rangeWarnMsg.SetLabel(msg)
        self.rangeWarnMsg.Show()


    def hideWarning(self):
        """ Hide the export range warning.
        """
        self.rangeWarnMsg.SetLabel("")
        self.rangeWarnIcon.Hide()
        self.rangeWarnMsg.Hide()


    def updateMessages(self, event=None):
        """
        """
        numEvents = 0
        channels = self.getSelectedChannels()
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
        return last - first
        

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
        evt.Skip()
        # This song-and-dance is to get around the fact that when the checked
        # item changes, both the previous and new items are considered
        # checked until the event finishes processing.
        treeItem = evt.GetItem()
        if treeItem.GetChildrenCount() == 0:
            treeItem = treeItem.GetParent()
        self.updateMessages()

#===============================================================================
# 
#===============================================================================

class CSVExportDialog(ExportDialog):
    """ A subclass of the standard `ExportDialog`, featuring options
        applicable only to CSV.
    """
    
    def __init__(self, *args, **kwargs):
        self._addHeaders = kwargs.pop('addHeaders', True)
        super(CSVExportDialog, self).__init__(*args, **kwargs)

    def buildSpecialUI(self):
        """ Called before the buttons are added.
        """
        pane = self.GetContentsPane()
        self.headerCheck = wx.CheckBox(pane, -1, "Include column headers")
        self.headerCheck.SetValue(self._addHeaders)

    @property
    def addHeaders(self):
        return self.headerCheck.GetValue()


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

    windowsizes = map(str, [2**x for x in xrange(10,21)])
    defaultWinSize = 2**16
    
    # These will be removed later, once memory usage is accurately computed.
    manyEvents = 750000
    maxEvents = 1000000
    
    
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
        self._samplingOrder = kwargs.pop('samplingOrder', self.SEQUENTIAL)
        self._windowSize = str(kwargs.pop('samplingOrder', ''))
        if self._windowSize not in self.windowsizes:
            self._windowSize = str(self.defaultWinSize)
        super(FFTExportDialog, self).__init__(*args, **kwargs)


    def buildSpecialUI(self):
        """ Called before the OK/Cancel buttons are added.
        """
        subpane = sc.SizedPanel(self.GetContentsPane(),-1)
        subpane.SetSizerType("form")
        subpane.SetSizerProps(expand=True)
        
        wx.StaticText(subpane, -1, "Sampling Window Size:"
                      ).SetSizerProps(valign="center")
        self.sizeList = wx.Choice(subpane, -1, choices=self.windowsizes)
        self.sizeList.SetToolTipString("The size of the 'window' used in "
                                       "Welch's method")
        self.sizeList.SetSizerProps(expand=True)
        self.sizeList.Select(self.sizeList.FindString(self._windowSize))
        
#         wx.StaticText(subpane, -1, "Sampling order:"
#                       ).SetSizerProps(valign="center")
#         self.orderList = wx.Choice(subpane, -1, choices=self.SAMPLE_ORDER)
#         self.orderList.SetSizerProps(expand=True)
#         self.orderList.Select(self._samplingOrder)
        

    def showColumnsMsg(self, num=0, msg=None):
        """ Display a message below the tree view, meant to show the number
            of columns that will be exported.
        """
        if msg is None:
            if num == 1:
                msg = "%d subchannel selected" % num
            else:
                msg = "%d subchannels selected" % num
        self.treeMsg.SetLabel(msg)


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


    @property
    def windowSize(self):
        return int(self.sizeList.GetString(self.sizeList.GetSelection()))
    
    @property
    def samplingOrder(self):
        return self.orderList.GetSelection()

#===============================================================================
# 
#===============================================================================

# XXX: FOR DEVELOPMENT TESTING. REMOVE ME!
if __name__ == '__main__':# or True:
    locale.setlocale(locale.LC_ALL, 'English_United States.1252')
    
#     DIALOG_TO_SHOW = ExportDialog
#     DIALOG_TO_SHOW = CSVExportDialog
    DIALOG_TO_SHOW = FFTExportDialog
    
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
    
    results = {}
    app = wx.App()
    title = "Testing %s" % DIALOG_TO_SHOW.__name__
    dlg = DIALOG_TO_SHOW(None, -1, title, root=FakeViewer())
    result = dlg.ShowModal()
    results['selectedChannels'] = dlg.getSelectedChannels()
    results['exportRange'] = dlg.getExportRange()
    if DIALOG_TO_SHOW == CSVExportDialog:
        results['selectedChannels'] = dlg.getSelectedChannels()
        results['exportRange'] = dlg.getExportRange()
        results['addHeaders'] = dlg.addHeaders
    elif DIALOG_TO_SHOW == FFTExportDialog:
        results['windowSize'] = dlg.windowSize
#         results['samplingOrder'] = dlg.samplingOrder
    dlg.Destroy()
    pprint(results)
    app.MainLoop()