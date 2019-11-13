'''
Created on Nov 13, 2019

@author: dstokes
'''

from collections import namedtuple
import os.path

import wx
import wx.lib.sized_controls as SC
import wx.lib.mixins.listctrl as listmix

# from base import Tab


#===============================================================================
# 
#===============================================================================

WifiInfo = namedtuple("WifiInfo", ('ssid','strength', 'security', 'known'))


#===============================================================================
# 
#===============================================================================

class WifiSelectionTab(SC.SizedPanel):#Tab):
    """
    """
    label = "Wi-Fi"
    COLUMNS = ("AP", "Security")

    class WifiListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
        # Required to create an auto-resizing list
        def __init__(self, parent, ID, pos=wx.DefaultPosition,
                     size=wx.DefaultSize, style=0):
            wx.ListCtrl.__init__(self, parent, ID, pos, size, style)
            listmix.ListCtrlAutoWidthMixin.__init__(self)
            
            self.setResizeColumn(0)


    def __init__(self, *args, **kwargs):
        """
        """
        # This will get largely redone once this is a Tab.
        super(WifiSelectionTab, self).__init__(*args, **kwargs)
        
        self.initUI()
        
    
    def getInfo(self):
        """
        """
        # XXX: HACK: Bogus data for testing
        self.info = [WifiInfo("MIDE-Corp", .9, 'WPA', True),
                     WifiInfo("MIDE-Guest", .7, 'WPA2', False),
                     WifiInfo("EarthAP", .5, None, True),
                     WifiInfo("MoonAP", .3, 'WPA', False)]
        
        self.lastSSID = "Missing" #self.info[2][0]
    
    
    def initUI(self):
        """ Build the user interface, populating the Tab. 
            Separated from `__init__()` for the sake of subclassing.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Load wifi signal strength icons. Also includes a 'not found' icon.
        filename = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                 '../resources/wifi-%s.png'))
        
        self.il = wx.ImageList(20,16)
        self.icons = [self.il.Add(wx.Icon(filename % n))
                      for n in (0,25,50,75,100, None)]

        # Set up the AP list
        self.list = self.WifiListCtrl(self, -1,
            style=(wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SORT_ASCENDING |
                   wx.LC_VRULES | wx.LC_HRULES | wx.LC_SINGLE_SEL))

        sizer.Add(self.list, 1, wx.EXPAND|wx.ALL, 8)

        self.list.SetImageList(self.il, wx.IMAGE_LIST_SMALL)
        info = wx.ListItem()
        info.SetMask(wx.LIST_MASK_TEXT|wx.LIST_MASK_IMAGE|wx.LIST_MASK_FORMAT)
        info.SetImage(-1)
        info.SetAlign(0)
        info.SetText(self.COLUMNS[0])
        self.list.InsertColumn(0, info)
        self.list.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        
        self.list.InsertColumn(1, self.COLUMNS[1], width=wx.LIST_AUTOSIZE)
        
        font = self.list.GetFont()
        self.boldFont = font.Bold()
        self.italicFont = font.Italic()
        self.notFoundColor = wx.Colour(127,127,127)
        
        # Rescan button (and footnote text)
        scansizer = wx.BoxSizer(wx.HORIZONTAL)
        rescanLabel = wx.StaticText(self, -1, "* Currently configured AP")
        rescan = wx.Button(self, -1, "Rescan")
        rescanLabel.SetFont(self.italicFont)
        scansizer.Add(rescanLabel, 1, wx.EXPAND|wx.ALIGN_LEFT|wx.ALL, 8)
        scansizer.Add(rescan, 0, wx.ALIGN_RIGHT|wx.EAST|wx.SHAPED, 8)
        sizer.Add(scansizer, 0, wx.EXPAND)

        # Password field components
        pwsizer = wx.BoxSizer(wx.HORIZONTAL)
        labelsize = self.GetTextExtent("Change Password:")
        self.pwCheck = wx.CheckBox(self, -1, "")
        self.pwLabel = wx.StaticText(self, -1, "Change Password:",
                                     size=labelsize, style=wx.ALIGN_RIGHT)
        self.pwField = wx.TextCtrl(self, -1, style=wx.TE_PASSWORD)
        self.pwCheck.Enable(False)
        self.pwLabel.Enable(False)
        self.pwField.Enable(False)
        
        pwstyle = wx.ALIGN_CENTER_VERTICAL|wx.RESERVE_SPACE_EVEN_IF_HIDDEN
        pwsizer.AddMany(((self.pwCheck, 0, pwstyle),
                         (self.pwLabel, 0, pwstyle|wx.ALIGN_RIGHT|wx.EAST, 4),
                         (self.pwField, 1, pwstyle|wx.EXPAND)))
        sizer.Add(pwsizer, 0, wx.EXPAND|wx.ALL, 8)

        self.SetSizer(sizer)

        rescan.Bind(wx.EVT_BUTTON, self.OnRescan)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self.list)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected, self.list)
        self.pwField.Bind(wx.EVT_SET_FOCUS, self.OnPasswordFocus)

        self.populate()
        

    def populate(self):
        """ Fill out the AP list.
        """
        self.selected = -1
        self.lastSelected = -2
        
        self.list.DeleteAllItems()
        self.getInfo()
        
        knownAPs = []
        for ap in self.info:
            icon = self.icons[int(ap.strength * 5)]
            idx = self.list.InsertItem(self.list.GetItemCount(), ap.ssid, icon)
            self.list.SetItem(idx, 1, str(ap.security))
            
            if not ap.known:
                # AP not previously configured; mark it.
                item = self.list.GetItem(idx)
                item.SetFont(self.italicFont)
                self.list.SetItem(item)
            if ap.ssid == self.lastSSID:
                # The previously selected AP
                item = self.list.GetItem(idx)
                item.SetFont(self.boldFont)
                item.SetText(item.GetText() + " *")
                self.list.SetItem(item)
            
            knownAPs.append(ap.ssid)
        
        # Previously selected AP isn't in the list (out of range?)
        if self.lastSSID not in knownAPs:
            ssid = self.lastSSID + " *"
            idx = self.list.InsertItem(self.list.GetItemCount(), ssid,
                                       self.icons[-1])
            item = self.list.GetItem(idx)
            item.SetTextColour(self.notFoundColor)
            item.SetFont(self.boldFont)
            self.list.SetItem(item)
        

    #===========================================================================
    # 
    #===========================================================================
    
    def OnRescan(self, evt):
        """ Handle "Rescan" button press.
        """
        self.populate()


    def OnItemSelected(self, evt): 
        """ Handle an AP list item getting selected.
        """
        self.pwLabel.Enable()
        self.pwField.Enable()
        
        self.selected = evt.GetIndex()
        if self.info[self.selected].known:
            self.pwCheck.SetValue(False)
            self.pwCheck.Enable(True)
            self.pwLabel.SetLabelText("Change Password:")
        else:
            self.pwCheck.Enable(False)
            self.pwCheck.SetValue(True)
            self.pwLabel.SetLabelText("Set Password:")

        self.pwField.SetValue("")


    def OnItemDeselected(self, evt):
        """ Handle an AP list item getting deselected.
        """
        self.selected = 0


    def OnPasswordFocus(self, evt):
        """ Handle the password field being clicked in.
        """
        # Erase the field unless the user hasn't changed selected AP
        if self.selected != self.lastSelected:
            self.pwField.SetValue('')
            self.pwCheck.SetValue(True)
            self.lastSelected = self.selected
            
        evt.Skip()


    #===========================================================================
    # 
    #===========================================================================
    
    def save(self):
        """ Save Wi-Fi configuration data to the device.
        """
        pass



#===============================================================================
# 
#===============================================================================

class TestConfigDialog(SC.SizedDialog):
    """ Root window for recorder configuration.
        THIS IS STAND-IN. REMOVE LATER.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `SizedDialog` arguments.
        """
        super(TestConfigDialog, self).__init__(*args, **kwargs)

        pane = self.GetContentsPane()
        self.notebook = wx.Notebook(pane, -1)
        self.notebook.SetSizerProps(expand=True, proportion=-1)
        
        p = WifiSelectionTab(self.notebook, -1)
        self.notebook.AddPage(p, p.label)
                
        buttonpane = SC.SizedPanel(pane,-1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)

        self.setClockCheck = wx.CheckBox(buttonpane, -1, "Set device clock on exit")
        self.setClockCheck.SetSizerProps(expand=True, border=(['top', 'bottom'], 8))

        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        wx.Button(buttonpane, wx.ID_OK)
        wx.Button(buttonpane, wx.ID_CANCEL)
        buttonpane.SetSizerProps(halign='right')
        
        self.SetAffirmativeId(wx.ID_OK)
        
        self.Fit()
        self.SetMinSize((500, 480))
        self.SetSize((620, 700))



#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    
    dlg = TestConfigDialog(None, -1, "Config test",
                           style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
    
    dlg.ShowModal()
    
