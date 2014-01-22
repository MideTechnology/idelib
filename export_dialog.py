'''
Created on Nov 21, 2013

@author: dstokes
'''

import wx.lib.agw.customtreectrl as CT
import wx; wx=wx
import wx.lib.sized_controls as sc

#===============================================================================
# 
#===============================================================================

class ModalExportProgress(wx.ProgressDialog):
    """ Subclass of the standard progress dialog, implementing the __call__
        method and other attributes needed for a callback (like the Loader).
    """
    def __init__(self, *args, **kwargs):
        self.cancelled = False
        style = wx.PD_CAN_ABORT|wx.PD_APP_MODAL|wx.PD_REMAINING_TIME
        kwargs.setdefault("style", style)
        super(ModalExportProgress, self).__init__(*args, **kwargs)
        
    
    def __call__(self, count=0, percent=None, total=None, error=None, done=False):
        if done:
            return
        msg = "Exporting %d of %d" % (count, total)
        keepGoing, skip = super(ModalExportProgress, self).Update(count, msg)
        self.cancelled = not keepGoing
        return keepGoing, skip


#===============================================================================
# 
#===============================================================================


class ExportDialog(sc.SizedDialog):
    """ The dialog for selecting data to export.
    """
    
    RB_RANGE_ALL = wx.NewId()
    RB_RANGE_VIS = wx.NewId()
    RB_RANGE_CUSTOM = wx.NewId()
    
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

        super(ExportDialog, self).__init__(*args, **kwargs)
        
        self.noBmp = wx.EmptyBitmapRGBA(16,16,0,0,0,1.0)
        self.rangeBtns = []
        pane = self.GetContentsPane()

        #=======================================================================
        # Channel/Plot Export Selection
        #=======================================================================
    
        self.tree  = CT.CustomTreeCtrl(pane, -1, 
                                       style=wx.SUNKEN_BORDER,
                                       agwStyle=CT.TR_HAS_BUTTONS)
        self.tree.SetSizerProps(expand=True, proportion=1)
        self.treeMsg = wx.StaticText(pane, 0, "")#(export description, i.e. number of columns)")
        
        #=======================================================================
        # Export range selection
        #=======================================================================
        
        wx.StaticLine(pane, -1).SetSizerProps(expand=True)
        wx.StaticText(pane, -1, "Time Range to Export:")
        rangePane = sc.SizedPanel(pane, -1)
        self._addRangeRB(rangePane, self.RB_RANGE_ALL, "All", style=wx.RB_GROUP),
        self._addRangeRB(rangePane, self.RB_RANGE_VIS, "Visible Time Range")
        rangeFieldPane = sc.SizedPanel(rangePane,-1)
        rangeFieldPane.SetSizerType("horizontal")
        self._addRangeRB(rangeFieldPane, self.RB_RANGE_CUSTOM, "Specific Time Range:")
        self.rangeStartT = wx.TextCtrl(rangeFieldPane, -1, "0", size=(80, -1))
        self.rangeEndT = wx.TextCtrl(rangeFieldPane, -1, str(2**32*.0000001), size=(80, -1))
        self.rangeMsg = wx.StaticText(rangePane, 0)#, "Export will contain x rows")


        warnPane = sc.SizedPanel(pane,-1)
        warnPane.SetSizerType("horizontal")
        self.rangeWarnIcon = wx.StaticBitmap(warnPane, -1, self.noBmp)
        self.rangeWarnMsg = wx.StaticText(warnPane,-1,"")
        self.rangeWarnMsg.SetForegroundColour("RED")
        warnPane.SetSizerProps(expand=True)
        rangePane.SetSizerProps(expand=True)
        wx.StaticLine(pane, -1).SetSizerProps(expand=True)
        
        #=======================================================================
        # Final setup
        #=======================================================================
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okButton = self.FindWindowById(wx.ID_OK)

        self.SetMinSize((340,450))
        self.SetMaxSize((500,600))
        self.Fit()
        
        if self.root.dataset is not None:
            self.InitUI()
            
        self.Layout()
        self.Centre()
        
        self.Bind(wx.EVT_RADIOBUTTON, self.OnAnyRBSelected)
        self.Bind(CT.EVT_TREE_ITEM_CHECKED, self.OnTreeItemSelected)
#         self.tree.Bind(CT.EVT_TREE_SEL_CHANGED, self.validateSettings)


    def _formatTime(self, val):
        
        return "(%s to %s)" % tuple(map(lambda x: ("%.4f" % x).rstrip("0.") if x else "0",val))


    def getRangeField(self, field, default=None):
        """
        """
        val = field.GetValue()
        if not val:
            return default
        try:
            return float(val) / self.root.timeScalar
        except ValueError:
            return default


    def InitUI(self):
        """ Set up and display actual data in the dialog.
        """
        self.OnAnyRBSelected(None)
        self.treeRoot = self.tree.AddRoot(self.root.dataset.name)
        for sensor in self.root.dataset.sensors.itervalues():
            self._addTreeItems(self.treeRoot, sensor, types=(CT.TREE_ITEMTYPE_RADIO,
                                                   CT.TREE_ITEMTYPE_RADIO,
                                                   CT.TREE_ITEMTYPE_CHECK))
        self.tree.Expand(self.treeRoot)
        
        self.range = self.root.getTimeRange()
        scaledRange = self.range[0] * self.root.timeScalar, self.range[1] * self.root.timeScalar
        visStart, visEnd = self.root.getVisibleRange()
        scaledVisRange = visStart * self.root.timeScalar, visEnd * self.root.timeScalar
        
        self.rangeStartT.SetValue(str(scaledVisRange[0]))
        self.rangeEndT.SetValue(str(scaledVisRange[1]))
        self.rangeBtns[0].SetLabel("All %s" % self._formatTime(scaledRange))
        self.rangeBtns[1].SetLabel("Visible Time Range %s" % self._formatTime(scaledVisRange))
        
        w,_ = self.GetSize()
        for r in self.rangeBtns[:2]:
            r.SetSize((w-16,-1))
        
        self.showColumnsMsg(msg="")
        
        
    def _addRangeRB(self, parent, ID, label, **kwargs):
        """ Helper to add range radiobuttons
        """
        self.rangeBtns.append(wx.RadioButton(parent, ID, label, **kwargs))

    
    def _addTreeItems(self, parentItem, obj, types=None, 
                 defaultType=CT.TREE_ITEMTYPE_CHECK):
        """ Helper to add items to the tree view.
        """
        if obj is None:
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
        """
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
        """
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


    def showRangeMsg(self, icon, msg):
        """ Show a warning message about the selected export time range.
        
            @param icon: An icon ID (e.g. wx.ART_WARNING, wx.ART_ERROR, 
                or wx.ART_INFO)
            @param msg: The text of the message to display.
        """
        bmp = wx.ArtProvider.GetBitmap(icon, wx.ART_CMN_DIALOG, (16,16))
        self.rangeWarnIcon.Show()
        self.rangeWarnIcon.SetBitmap(bmp)
        self.rangeWarnMsg.SetLabel(msg)
        self.rangeWarnMsg.Show()


    def hideRangeMsg(self):
        """ Hide the export range warning.
        """
        self.rangeWarnMsg.SetLabel("")
        self.rangeWarnIcon.Hide()
        self.rangeWarnMsg.Hide()


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

    #===========================================================================
    # 
    #===========================================================================

    def OnAnyRBSelected(self, evt):
        """
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


    def OnTreeItemSelected(self, evt):
        """
        """
        evt.Skip()
        # This song-and-dance is to get around the fact that when the checked
        # item changes, both the previous and new items are considered
        # checked until the event finishes processing.
        treeItem = evt.GetItem()
        if treeItem.GetChildrenCount() == 0:
            treeItem = treeItem.GetParent()
        self.validateSettings(self.getSelectedChannels(treeItem))

    


        
     
if __name__ == '__main__': #or True:
    import importer
    doc=importer.importFile(updater=importer.SimpleUpdater(0.01))
    
    class FakeViewer(object):
        dataset = doc
        session = doc.lastSession
        timeScalar = 1.0/(10**6)
        timerange = (1043273L*2,7672221086L)
        
        def getVisibleRange(self):
            return 0, 2**32-1
        
        def getTimeRange(self):
            return self.timerange
        
    app = wx.App()
    dlg = ExportDialog(None, -1, "Export to CSV", root=FakeViewer())
    result = dlg.ShowModal()
    selectedChannels = dlg.getSelectedChannels()
    exportRange = dlg.getExportRange()
    dlg.Destroy()
    print exportRange, selectedChannels
    app.MainLoop()