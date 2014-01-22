import sys
from collections import namedtuple

import wx; wx=wx
import wx.lib.sized_controls as sc
import  wx.lib.mixins.listctrl  as  listmix

# from devices import getDevices, getRecorderInfo

# XXX: Fake 'devices' fixtures; remove later!
import random

def getDevices():
    return ["%s:\\" % d for d in "EFGHI"]

def getRecorderInfo(x):
    return {'FwRev': 0,
            'HwRev': 1,
            'ProductName': 'Slam Stick X (100g)',
            'RecorderSerial': random.randint(1000000000, 9999999999),
            'RecorderTypeUID': 1,
            'UserDeviceName': 'My Device %s' % x.strip(':\\'),
            'PATH': x}

#===============================================================================
# 
#===============================================================================

class DeviceSelectionDialog(sc.SizedDialog, listmix.ColumnSorterMixin):
    """ The dialog for selecting data to export.
    """

    ColumnInfo = namedtuple("ColumnInfo", ['name','propName','formatter','default'])

    COLUMNS = (ColumnInfo("Path", "PATH", unicode, ''),
               ColumnInfo("Name", "UserDeviceName", unicode, ''),
               ColumnInfo("Type", "ProductName", unicode, ''),
               ColumnInfo("Serial #", "RecorderSerial", hex, ''))

    class DeviceListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
        def __init__(self, parent, ID, pos=wx.DefaultPosition,
                     size=wx.DefaultSize, style=0):
            wx.ListCtrl.__init__(self, parent, ID, pos, size, style)
            listmix.ListCtrlAutoWidthMixin.__init__(self)
            

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
        super(DeviceSelectionDialog, self).__init__(*args, **kwargs)
        
        self.recorders = []
        self.listWidth = 300
        self.selected = None
        self.selectedIdx = None
                
        pane = self.GetContentsPane()
        pane.SetSizerProps(expand=True)

        self.list = self.DeviceListCtrl(pane, -1, 
                                 style=wx.LC_REPORT 
                                 | wx.BORDER_SUNKEN
                                 | wx.LC_SORT_ASCENDING
                                 | wx.LC_VRULES
                                 | wx.LC_HRULES
                                 | wx.LC_SINGLE_SEL
                                 )
        
        for i, c in enumerate(self.COLUMNS):
            self.list.InsertColumn(i, c[0])

        self.list.SetSizerProps(expand=True, proportion=1)

        self.infoText = wx.StaticText(pane, -1, "This is maybe\na multi-line\ntext thing")
        self.infoText.SetSizerProps(expand=True)
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okButton = self.FindWindowById(wx.ID_OK)
        self.okButton.Enable(False)

        self.populateList()
        
        self.Fit()
        self.SetSize((self.listWidth + (self.GetDialogBorder()*4),300))
        self.SetMinSize((self.listWidth + (self.GetDialogBorder()*4),300))
        self.SetMaxSize((1500,600))
        
        self.Layout()
        self.Centre()
    
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self.list)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected, self.list)
        self.list.Bind(wx.EVT_LEFT_DCLICK, self.OnItemDoubleClick)


    def populateList(self):
        """ Find recorders and add them to the list.
        """
        
        def thing2string(info, col):
            try:
                return col.formatter(info.get(col.propName, col.default))
            except TypeError:
                return col.default
        
        pathWidth = self.GetTextExtent(" Path ")[0]+8
        
        self.recorders = [getRecorderInfo(p) for p in getDevices()]
        for info in self.recorders:
            index = self.list.InsertStringItem(sys.maxint, info['PATH'])
            self.list.SetColumnWidth(0, max(pathWidth,
                                            self.GetTextExtent(info['PATH'])[0]))
            for i, col in enumerate(self.COLUMNS[1:], 1):
                self.list.SetStringItem(index, i, thing2string(info, col))
                self.list.SetColumnWidth(i, wx.LIST_AUTOSIZE)
                self.listWidth = max(self.listWidth, self.list.GetItemRect(index)[2])
        
        self.list.Fit()


    def OnItemSelected(self,evt):
        print "Item selected:", evt.m_itemIndex
        self.selectedIdx = evt.m_itemIndex
        self.okButton.Enable(True)
        evt.Skip()

    def OnItemDeselected(self, evt):
        print "Item deselected"
        self.okButton.Enable(self.list.GetSelectedItemCount() > 0)
        evt.Skip()

    def OnItemDoubleClick(self, evt):
        print "Double-click"
        if self.list.GetSelectedItemCount() == 0:
            # Don't close the dialog
            print "nothing selected"
            pass
        else:
            # Close the dialog
            print "selected:", self.list.GetFirstSelected()
            pass
        evt.Skip()

#===============================================================================
# 
#===============================================================================

if __name__ == '__main__': #or True:
    app = wx.App()
    dlg = DeviceSelectionDialog(None, -1, "Import from Recorder")
    result = dlg.ShowModal()
    dlg.Destroy()
    app.MainLoop()    
