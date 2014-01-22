'''
Created on Nov 21, 2013

@author: dstokes
'''

import wx.lib.agw.customtreectrl as CT
import wx; wx=wx
import wx.lib.sized_controls as sc


# XXX: FOR TESTING vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
import importer
doc=importer.importFile(updater=importer.SimpleUpdater(0.01))
class FakeViewer(object):
    dataset = doc
    session = doc.lastSession
# XXX: FOR TESTING ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#===============================================================================
# 
#===============================================================================

class ModalExportProgress(wx.ProgressDialog):
    """ Subclass of the standard progress dialog, implementing the __call__
        method and other attributes needed for a callback (like the Loader).
    """
    def __init__(self, *args, **kwargs):
        self.cancelled = False
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

class ExportDialog(wx.Dialog):
    """ The dialog for selecting data to export.
    """
    
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

        pre = wx.PreDialog()
        pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
        pre.Create(*args, **kwargs)
        self.PostCreate(pre)

        mainsizer = wx.BoxSizer(wx.VERTICAL)

        #=======================================================================
        # Channel/Plot Export Selection
        #=======================================================================
    
        treebox = wx.StaticBox(self, -1, "Data Source")
        tbsizer = wx.StaticBoxSizer(treebox, wx.VERTICAL)
        self.tree  = CT.CustomTreeCtrl(self, -1, 
                                       style=wx.SUNKEN_BORDER,
                                       agwStyle=CT.TR_HAS_BUTTONS)
        self.treeMsg = wx.StaticText(self, 0, "")
        tbsizer.Add(self.tree, 1, wx.EXPAND)
        tbsizer.Add(self.treeMsg, 0, wx.EXPAND)
        mainsizer.Add(tbsizer,  2, wx.EXPAND|wx.ALL,4)
        
        #=======================================================================
        # Export range selection
        #=======================================================================
        
        rangeBox = wx.StaticBox(self, -1, "Export Range")
        rangeBoxSizer = wx.StaticBoxSizer(rangeBox, wx.VERTICAL)
        rangeBoxIntSizer = wx.GridBagSizer(4, 3)
        rangeAllRB = wx.RadioButton(self, -1, " All ", style = wx.RB_GROUP)
        rangeVisRB = wx.RadioButton(self, -1, " Visible Time Range ")
        rangeSpecRB = wx.RadioButton(self, -1, " Specific Time Range: ")
        rangeStartT = wx.TextCtrl(self, -1, "0", size=(80, -1))
        rangeEndT = wx.TextCtrl(self, -1, str(2**32), size=(80, -1))
        rangeWarnSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.rangeWarnIcon = wx.StaticBitmap(self, -1, wx.EmptyBitmap(16,16))
        self.rangeWarnMsg = wx.StaticText(self,-1,"Test")
        self.rangeWarnMsg.SetForegroundColour("RED")
        rangeWarnSizer.AddMany(((self.rangeWarnIcon,-1),
                                (self.rangeWarnMsg,0,wx.EXPAND|wx.ALL)))
        rangeBoxIntSizer.AddMany(((rangeAllRB, (0,0)), 
                                  (rangeVisRB, (1,0)),
                                  (rangeSpecRB, (2,0)),
                                  (rangeStartT, (2,1)),
                                  (wx.StaticText(self, -1, "-"), (2,2)),
                                  (rangeEndT, (2,3)),
                                  (rangeWarnSizer, (3,0),(1,3))))
        rangeBoxSizer.Add(rangeBoxIntSizer)
        
        mainsizer.Add(rangeBoxSizer, 1, wx.EXPAND|wx.ALL,4)
        
        #=======================================================================
        # Final setup
        #=======================================================================

        btnSizer = wx.BoxSizer(wx.HORIZONTAL)        
        self.exportBtn = wx.Button(self, wx.ID_SAVE, "Export")
        self.cancelBtn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        btnSizer.Add(self.cancelBtn, 0, wx.ALIGN_RIGHT, 4)
        btnSizer.Add(self.exportBtn, 0, wx.ALIGN_RIGHT, 4)
        mainsizer.Add(btnSizer, 0, wx.ALIGN_BOTTOM | wx.ALIGN_RIGHT, 4)
        
        if self.root.dataset is not None:
            self.InitUI()
            
        self.SetSizer(mainsizer)
        mainsizer.Fit(self)
        self.Layout()
        self.Centre()


    def InitUI(self):
        """ Set up and display actual data in the dialog.
        """
        treeRoot = self.tree.AddRoot(self.root.dataset.name)
        for sensor in self.root.dataset.sensors.itervalues():
            self._addTreeItems(treeRoot, sensor, types=(CT.TREE_ITEMTYPE_RADIO,
                                                   CT.TREE_ITEMTYPE_RADIO,
                                                   CT.TREE_ITEMTYPE_CHECK))
        self.tree.Expand(treeRoot)
        self.showRangeMsg(wx.ART_WARNING, "This is a test warning")
        self.showColumnsMsg("Exporting 3 columns (time + 2 data)")
            
        
    
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


    def showColumnsMsg(self, msg):
        """ Display a message below the tree view, meant to show the number
            of columns that will be exported.
        """
        self.treeMsg.SetLabel(msg)


    def showRangeMsg(self, icon, msg):
        """ Show a warning message about the selected export time range.
        
            @param icon: An icon ID (e.g. wx.ART_WARNING, wx.ART_ERROR, 
                or wx.ART_INFO)
            @param msg: The text of the message to display.
        """
        bmp = wx.ArtProvider.GetBitmap(icon, wx.ART_CMN_DIALOG, (16,16))
        self.rangeWarnIcon.SetBitmap(bmp)
        self.rangeWarnMsg.SetLabel(msg)
        self.rangeWarnIcon.Show()
        self.rangeWarnMsg.Show()


    def hideRangeMsg(self):
        """ Hide the export range warning.
        """
        self.rangeWarnMsg.SetLabel("")
        self.rangeWarnIcon.Hide()
        self.rangeWarnMsg.Hide()


class ExportDialog2(sc.SizedDialog):
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

        super(ExportDialog2, self).__init__(*args, **kwargs)
        
        self.noBmp = wx.EmptyBitmapRGBA(16,16,0,0,0,1.0)
        self.rangeBtns = []
        self.rangeFields = []
        pane = self.GetContentsPane()

        #=======================================================================
        # Channel/Plot Export Selection
        #=======================================================================
    
        self.tree  = CT.CustomTreeCtrl(pane, -1, 
                                       style=wx.SUNKEN_BORDER,
                                       agwStyle=CT.TR_HAS_BUTTONS)
        self.tree.SetSizerProps(expand=True, proportion=1)
        self.treeMsg = wx.StaticText(pane, 0, "(export description, i.e. number of columns)")
        
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

        self.SetMinSize((340,320))
        self.SetMaxSize((500,600))
        self.Fit()
        
        if self.root.dataset is not None:
            self.InitUI()
            
        self.Layout()
        self.Centre()


    def InitUI(self):
        """ Set up and display actual data in the dialog.
        """
        self.OnAnyRBSelected(None)
        treeRoot = self.tree.AddRoot(self.root.dataset.name)
        for sensor in self.root.dataset.sensors.itervalues():
            self._addTreeItems(treeRoot, sensor, types=(CT.TREE_ITEMTYPE_RADIO,
                                                   CT.TREE_ITEMTYPE_RADIO,
                                                   CT.TREE_ITEMTYPE_CHECK))
        self.tree.Expand(treeRoot)
        
        self.Bind(wx.EVT_RADIOBUTTON, self.OnAnyRBSelected)
        
        self.showRangeMsg(wx.ART_WARNING, "This is a test warning")
        self.showColumnsMsg("Exporting 3 columns (time + 2 data)")
        
        
    def _addRangeRB(self, parent, ID, label, **kwargs):
        """
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


    def showColumnsMsg(self, msg):
        """ Display a message below the tree view, meant to show the number
            of columns that will be exported.
        """
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
    
     
# if __name__ == '__main__':
if True:
    app = wx.App()
    dlg = ExportDialog2(None, -1, "Export to CSV", root=FakeViewer)
    result = dlg.ShowModal()
    dlg.Destroy()
#     app.MainLoop()