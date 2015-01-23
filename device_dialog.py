"""
Dialog for selecting recording devices.

"""
import random

import struct
import sys
from collections import namedtuple

import wx; wx=wx
import wx.lib.sized_controls as sc
import wx.lib.mixins.listctrl  as  listmix

# from common import hex32
from common import cleanUnicode
from devices import getDevices, getDeviceList
from devices import deviceChanged

#===============================================================================
# 
#===============================================================================

class DeviceSelectionDialog(sc.SizedDialog, listmix.ColumnSorterMixin):
    """ The dialog for selecting data to export.
    """

    ID_SET_TIME = wx.NewId()

    ColumnInfo = namedtuple("ColumnInfo", 
                            ['name','propName','formatter','default'])

    COLUMNS = (ColumnInfo("Path", "path", cleanUnicode, ''),
               ColumnInfo("Name", "name", cleanUnicode, ''),
               ColumnInfo("Type", "productName", cleanUnicode, ''),
               ColumnInfo("Serial #", "serial", cleanUnicode, ''))

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
        
        sc.SizedDialog.__init__(self, *args, **kwargs)
        
        self.recorders = []
        self.recorderPaths = tuple(getDeviceList())
        self.listWidth = 300
        self.selected = None
        self.selectedIdx = None
        self.firstDrawing = True
                
        pane = self.GetContentsPane()
        pane.SetSizerProps(expand=True)

        self.list = self.DeviceListCtrl(pane, -1, 
             style=(wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SORT_ASCENDING
                    | wx.LC_VRULES | wx.LC_HRULES | wx.LC_SINGLE_SEL))

        images = wx.ImageList(16, 16)
        for i in (wx.ART_INFORMATION, wx.ART_WARNING, wx.ART_ERROR):
            images.Add(wx.ArtProvider.GetBitmap(i, wx.ART_CMN_DIALOG, (16,16)))
        self.list.AssignImageList(images, wx.IMAGE_LIST_SMALL)
        
        self.list.SetSizerProps(expand=True, proportion=1)

        # Selected device info
        self.infoText = wx.StaticText(pane, -1, "")
        self.infoText.SetSizerProps(expand=True)

        buttonpane = sc.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
        self.setClockButton = wx.Button(buttonpane, self.ID_SET_TIME, "Set All Clocks")
        self.setClockButton.SetSizerProps(halign="left")
        self.setClockButton.SetToolTipString("Set the time of every attached recorder with a RTC")
        sc.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        self.okButton = wx.Button(buttonpane, wx.ID_OK)
        self.okButton.SetSizerProps(halign="right")
        self.okButton.Enable(False)
        self.cancelButton = wx.Button(buttonpane, wx.ID_CANCEL)
        self.cancelButton.SetSizerProps(halign="right")

        self.Bind(wx.EVT_BUTTON, self.setClocks, id=self.ID_SET_TIME)
        
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
        
        self.lastToolTipItem = -1
        self.list.Bind(wx.EVT_MOTION, self.OnListMouseMotion)
        
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.TimerHandler)
        
        if self.autoUpdate:
            self.timer.Start(self.autoUpdate)


    def TimerHandler(self, evt):
        if deviceChanged(recordersOnly=True):
            self.SetCursor(wx.StockCursor(wx.CURSOR_ARROWWAIT))
            newPaths = tuple(getDeviceList())
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


    def setItemIcon(self, index, dev):
        # TODO: Make this actually display a useful message (expired cal, etc.)
        pass
#         if "Classic" in dev.productName:
#             self.listToolTips[index] = "This is a classic"
#             self.list.SetItemImage(index, 0)


    def populateList(self):
        """ Find recorders and add them to the list.
        """
        
        def thing2string(dev, col):
            try:
                return col.formatter(getattr(dev, col.propName, col.default))
            except TypeError:
                return col.default
        
        widths = [self.list.GetTextExtent(p)[0] for p in self.recorderPaths]
        pathWidth = max(self.GetTextExtent(" Path ")[0], *widths) + 24
                
        self.recorders = {}
        self.itemDataMap = {} # required by ColumnSorterMixin
        
        # This is to provide tool tips for individual list rows
        self.listToolTips = [None] * len(self.recorderPaths)

        self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
            # Reuse the list of paths to get the list of Recorder objects
        
        for dev in getDevices(self.recorderPaths):
            try:
                path = dev.path
                index = self.list.InsertStringItem(sys.maxint, path)
                self.recorders[index] = dev
                self.list.SetColumnWidth(0, max(pathWidth,
                                                self.GetTextExtent(path)[0]))
                for i, col in enumerate(self.COLUMNS[1:], 1):
                    self.list.SetStringItem(index, i, thing2string(dev, col))
                    self.list.SetColumnWidth(i, wx.LIST_AUTOSIZE)
                    self.listWidth = max(self.listWidth, 
                                         self.list.GetItemRect(index)[2])
                    
                self.list.SetItemData(index, index)
                self.itemDataMap[index] = [getattr(dev, c.propName, c.default) \
                                           for c in self.COLUMNS]

                self.setItemIcon(index, dev)
                
            except:
                wx.MessageBox(
                    "An error occurred while trying to access a recorder (%s)."
                    "\n\nThe device's configuration data may be damaged. "
                    "Try disconnecting and reconnecting the device." % dev.path, 
                    "Device Error", parent=self)
                self.list.DeleteItem(index)

        if self.firstDrawing:
            self.list.Fit()
            self.firstDrawing = False

        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


    def getSelected(self):
        if self.selected is None:
            return None
        return self.recorders.get(self.selected, None)
    

    def OnColClick(self, evt):
        # Required by ColumnSorterMixin
        evt.Skip()

    def OnItemSelected(self,evt):
        self.selected = self.list.GetItemData(evt.m_item.GetId())
        if self.listToolTips[self.selected] is not None:
            self.infoText.SetLabel(self.listToolTips[self.selected])
        self.okButton.Enable(True)
        evt.Skip()

    def OnItemDeselected(self, evt):
        self.selected = None
        self.okButton.Enable(False)
        self.infoText.SetLabel("")
        evt.Skip()


    def OnItemDoubleClick(self, evt):
        if self.list.GetSelectedItemCount() > 0:
            # Close the dialog
            self.EndModal(wx.ID_OK)
        evt.Skip()


    def OnListMouseMotion(self, evt):
        # This determines the list item under the mouse and shows the
        # appropriate tool tip, if any
        index, _ = self.list.HitTest(evt.GetPosition())
        if index != -1 and index != self.lastToolTipItem:
            item = self.list.GetItemData(index)
            if self.listToolTips[item] is not None:
                self.list.SetToolTipString(self.listToolTips[item])
            else:
                self.list.UnsetToolTip()
            self.lastToolTipItem = index
        evt.Skip()
        

    def setClocks(self, evt=None):
        butts = self.okButton, self.cancelButton, self.setClockButton
        self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
        for b in butts:
            b.Enable(False)
        for rec in self.recorders.values():
            rec.setTime()
        for b in butts:
            b.Enable(True)
        self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))


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

if __name__ == '__main__':
    app = wx.App()
    
    result = selectDevice()
    print result
    