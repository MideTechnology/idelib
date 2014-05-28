"""

Dialog for selecting recording devices.

@todo: Use the new `Recorder` classes! 

"""

import sys
from collections import namedtuple

import wx; wx=wx
import wx.lib.sized_controls as sc
import wx.lib.mixins.listctrl  as  listmix

from common import hex32
from devices import getDevices, getRecorderConfig, getRecorderInfo
from devices import deviceChanged


#===============================================================================
# 
#===============================================================================

class DeviceSelectionDialog(sc.SizedDialog, listmix.ColumnSorterMixin):
    """ The dialog for selecting data to export.
    """

    ColumnInfo = namedtuple("ColumnInfo", 
                            ['name','propName','formatter','default'])

    COLUMNS = (ColumnInfo("Path", "_PATH", unicode, ''),
               ColumnInfo("Name", "RecorderName", unicode, ''),
               ColumnInfo("Type", "ProductName", unicode, ''),
               ColumnInfo("Serial #", "RecorderSerial", hex32, ''))


    def getDeviceListing(self, dev):
        """ Get the recorder data for its entry in the list.
        """
        # Data comes from two sources: the device info file and user config.
        info = getRecorderInfo(dev) or False
        if info:
            # Add in the user-defined name
            config = getRecorderConfig(dev, {})
            if '_IS_CLASSIC' in info:
                info['RecorderName'] = "Slam Stick"
                info['ProductName'] = "Slam Stick Classic"
                info.update(config)
            else:
                info.update(config.get('RecorderUserData', {}))
        return info


    class DeviceListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
        def __init__(self, parent, ID, pos=wx.DefaultPosition,
                     size=wx.DefaultSize, style=0):
            wx.ListCtrl.__init__(self, parent, ID, pos, size, style)
            listmix.ListCtrlAutoWidthMixin.__init__(self)
            

    def GetListCtrl(self):
        # Required by ColumnSorterMixin
        return self.list

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
        self.autoUpdate = kwargs.pop('autoUpdate', 500)
        kwargs.setdefault('style', style)
        
#         super(DeviceSelectionDialog, self).__init__(*args, **kwargs)
        sc.SizedDialog.__init__(self, *args, **kwargs)
        
        self.recorders = []
        self.recorderPaths = tuple(getDevices())
        self.listWidth = 300
        self.selected = None
        self.selectedIdx = None
        self.firstDrawing = True
                
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

        
        self.list.SetSizerProps(expand=True, proportion=1)

#         self.infoText = wx.StaticText(pane, -1, "Selected device info here.")
#         self.infoText.SetSizerProps(expand=True)
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okButton = self.FindWindowById(wx.ID_OK)
        self.okButton.Enable(False)

        # call deviceChanged() to set the initial state
        deviceChanged(recordersOnly=True)
        self.addColumns()
        self.populateList()
        listmix.ColumnSorterMixin.__init__(self, len(self.ColumnInfo._fields))

        self.Fit()
        self.SetSize((self.listWidth + (self.GetDialogBorder()*4),300))
        self.SetMinSize((self.listWidth + (self.GetDialogBorder()*4),300))
        self.SetMaxSize((1500,600))
        
        self.Layout()
        self.Centre()
    
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self.list)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected, self.list)
        self.list.Bind(wx.EVT_LEFT_DCLICK, self.OnItemDoubleClick)
        self.Bind(wx.EVT_LIST_COL_CLICK, self.OnColClick, self.list)
                   
        # XXX: TEST
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.TimerHandler)
        
        if self.autoUpdate:
            self.timer.Start(self.autoUpdate)


    def TimerHandler(self, evt):
        if deviceChanged(recordersOnly=True):
            self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
            newPaths = tuple(getDevices())
            if newPaths == self.recorderPaths:
                self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
                return
            self.recorderPaths = newPaths
            self.list.ClearAll()
            self.addColumns()
            self.populateList()
            self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


    def addColumns(self):
        for i, c in enumerate(self.COLUMNS):
            self.list.InsertColumn(i, c[0])


    def populateList(self):
        """ Find recorders and add them to the list.
        """
        
        def thing2string(info, col):
            try:
                return col.formatter(info.get(col.propName, col.default))
            except TypeError:
                return col.default
        
        pathWidth = self.GetTextExtent(" Path ")[0]+8
                
        self.recorders = {}
        self.itemDataMap = {} # required by ColumnSorterMixin
        recorders = [self.getDeviceListing(p) for p in getDevices() if p]
        for info in recorders:
            if info is False:
                continue
            path = info['_PATH']
            index = self.list.InsertStringItem(sys.maxint, path)
            self.recorders[index] = info
            self.list.SetColumnWidth(0, max(pathWidth,
                                            self.GetTextExtent(path)[0]))
            for i, col in enumerate(self.COLUMNS[1:], 1):
                self.list.SetStringItem(index, i, thing2string(info, col))
                self.list.SetColumnWidth(i, wx.LIST_AUTOSIZE)
                self.listWidth = max(self.listWidth, 
                                     self.list.GetItemRect(index)[2])
                
            self.list.SetItemData(index, index)
            self.itemDataMap[index] = [info.get(c.propName, c.default) \
                                       for c in self.COLUMNS]
        
        if self.firstDrawing:
            self.list.Fit()
            self.firstDrawing = False


    def getSelected(self):
        if self.selected is None:
            return None
        return self.recorders.get(self.selected, None)
    

    def OnColClick(self, evt):
        # Required by ColumnSorterMixin
        evt.Skip()

    def OnItemSelected(self,evt):
        self.selected = self.list.GetItemData(evt.m_item.GetId())
        self.okButton.Enable(True)
        evt.Skip()

    def OnItemDeselected(self, evt):
        self.selected = None
        self.okButton.Enable(False)
        evt.Skip()


    def OnItemDoubleClick(self, evt):
        if self.list.GetSelectedItemCount() > 0:
            # Close the dialog
            self.EndModal(wx.ID_OK)
        evt.Skip()

#===============================================================================
# 
#===============================================================================

def selectDevice(title="Select Recorder", autoUpdate=1000, parent=None):
    """ Display a device-selection dialog and return the path to a recorder.
        The dialog will (optionally) update automatically when devices are
        added or removed.
        
        @keyword title: A title string for the dialog
        @keyword autoUpdate: A number of milliseconds to delay between checks
            for changes to attached recorders. 0 will never update.
        @return: The path of the selected device.
    """
    result = None
    dlg = DeviceSelectionDialog(parent, -1, title, autoUpdate=autoUpdate)
    
    if dlg.ShowModal() == wx.ID_OK:
        result = dlg.getSelected()
        
    dlg.Destroy()
    if isinstance(result, dict):
        result = result.get('_PATH', None)
    return result


#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':# or True:
    app = wx.App()
    
    result = selectDevice()
    print result
    