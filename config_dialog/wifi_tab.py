'''
Tab for configuring Wi-Fi. May get moved into 
Created on Nov 13, 2019

@author: dstokes
'''

from collections import namedtuple
import os.path

import wx
import wx.lib.sized_controls as SC
import wx.lib.mixins.listctrl as listmix

# from base import Tab
from base import logger

#===============================================================================
# 
#===============================================================================

WifiInfo = namedtuple("WifiInfo",
                      ('ssid', 'strength', 'security', 'known', 'selected'))


AUTH_TYPES = ("None", "WPA", "WPA2", "Whatever")
DEFAULT_AUTH = 1

#===============================================================================
# 
#===============================================================================

class AddWifiDialog(SC.SizedDialog):
    """ Simple dialog for entering data to connect to a hidden (or out-of-range
        network.
    """
    
    def __init__(self, parent, wxId=-1, title="Add Access Point",
                 style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, 
                 booleanAuth=True, authType=DEFAULT_AUTH, **kwargs):
        """ Constructor. Takes standard dialog arguments, plus:
            
            @keyword booleanAuth: If `True`, the specific type of authorization
                isn't selectable, just its presence or absence. For future use.
            @keyword authType: The default authorization type number. Will
                be a preference or the last value used, read from the
        """
        self.booleanAuth = booleanAuth
        super(AddWifiDialog, self).__init__(parent, wxId, title=title, 
                                            style=style, **kwargs)

        pane = self.GetContentsPane()
        pane.SetSizerType("form")

        wx.StaticText(pane, -1, "SSID (Name):").SetSizerProps(valign='center')
        self.ssidField = wx.TextCtrl(pane, -1, "")
        self.ssidField.SetSizerProps(expand=True, valign='center')

        wx.StaticText(pane, -1, "Security:").SetSizerProps(valign='center')
        if booleanAuth:
            self.authField = wx.CheckBox(pane, -1, "Password Required")
            self.authField.SetValue(bool(self.authType))
            self.pwField.Enable(self.authField.GetValue())
            self.Bind(wx.EVT_CHECKBOX, self.OnAuthCheck)
        else:
            self.authField = wx.Choice(pane, -1, choices=AUTH_TYPES)
            self.authField.SetSelection(authType)
            self.pwField.Enable(self.authField.GetSelection() != 0)
            self.Bind(wx.EVT_CHOICE, self.OnAuthChoice)
        self.authField.SetSizerProps(expand=True, valign='center')

        wx.StaticText(pane, -1, "Password:").SetSizerProps(valign='center')
        self.pwField = wx.TextCtrl(pane, -1, "", style=wx.TE_PASSWORD)
        self.pwField.SetSizerProps(expand=True, valign='center')

        # add dialog buttons
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))

        # a little trick to make sure that you can't resize the dialog to
        # less screen space than the controls need
        self.Fit()
        size = self.GetSize() + wx.Size(60,0)
        self.SetSize(size)
        self.SetMinSize(size)
        self.ssidField.SetFocus()


    def OnAuthChoice(self, evt):
        """ Handle authorization selection from the drop-down list, if
            not `booleanAuth`.
        """
        self.pwField.Enable(self.authField.GetSelection() != 0)
        evt.Skip()


    def OnAuthCheck(self, evt):
        """ Handle authorization selection checkbox, if `booleanAuth`.
        """
        self.pwField.Enable(self.authField.GetValue())


    def getValue(self):
        """ Retrieve the dialog's data.
        
            @return: A tuple containing a new `WifiInfo` and the password
        """
        if self.booleanAuth:
            auth = self.authField.GetValue()
        else:
            auth = AUTH_TYPES[self.authField.GetSelection()]
            
        result = WifiInfo(self.ssidField.GetValue(), -1, auth, False, True)

        return result, self.pwField.GetValue()
    

#===============================================================================
# 
#===============================================================================

class WifiSelectionTab(SC.SizedPanel):#Tab):
    """ Tab for selecting the wireless access point for a W-series recorder.
        This communicates directly with the device to get the visible
        networks and to save passwords.
    """
    COLUMNS = ("Wi-Fi Network", "Security")

    # 'Constant' value for the label, read from CONFIG_UI for 'normal' tabs
    label = "Wi-Fi"
    
    # FUTURE: Once multiple saved passwords is a thing, this will be provided
    # in the CONFIG_UI data.
    storeMultiplePasswords = False
    
    # FUTURE: Current HW only specifies authentication's presence or absence.
    # Future hardware might now. Will eventually be in CONFIG_UI data
    booleanAuth = True


    class WifiListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
        # Required to create an auto-resizing list
        def __init__(self, parent, ID, pos=wx.DefaultPosition,
                     size=wx.DefaultSize, style=0):
            wx.ListCtrl.__init__(self, parent, ID, pos, size, style)
            listmix.ListCtrlAutoWidthMixin.__init__(self)
            



    def __init__(self, *args, **kwargs):
        """ Constructor. Will probably be completely replaced once this is
            integrated with the rest of the tabs.
        """
        super(WifiSelectionTab, self).__init__(*args, **kwargs)
        self.initUI()
        
    
    def getInfo(self):
        """ Get Wi-Fi information from the device.
        """
        # XXX: HACK: Bogus data for testing
        self.info = [WifiInfo("MIDE-Corp",  .99, True,  False,  False),
                     WifiInfo("MIDE-Guest", .77, False, False,  False),
                     WifiInfo("EarthAP",    .55, False, False,  False),
                     WifiInfo("MoonAP",     .33, True,  False,  False),
                     WifiInfo("ThisAP",     .11, False, False,  False),
                     WifiInfo("ThatAP",     .08, True,  False,  False),
                     WifiInfo("PlutoAP",    -1,  True,  True,   True)]
        
    
    def loadImages(self):
        """
        """
        self.il = wx.ImageList(20,16,mask=True)
        
        # Load wifi signal strength icons. Also includes a 'not found' icon.
        filename = os.path.realpath(os.path.join(
            os.path.dirname(__file__), '..','resources','wifi-%s.png'))
        
        states = (0,25,50,75,100,None)
        files = [filename % n for n in states]
        files.extend([filename % ("secure-%s" % n) for n in states])
        
        self.icons = [self.il.Add(wx.Bitmap(f)) for f in files]
    
    
    def initUI(self):
        """ Build the user interface, populating the Tab. 
            Separated from `__init__()` for the sake of subclassing.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.loadImages()
        
        # Set up the AP list
        self.list = self.WifiListCtrl(self, -1,
            style=(wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SORT_ASCENDING |
                   wx.LC_VRULES | wx.LC_HRULES | wx.LC_SINGLE_SEL))

        sizer.Add(self.list, 1, wx.EXPAND|wx.ALL, 8)

        self.list.setResizeColumn(0)
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
        self.struckFont = font.Strikethrough()
#         self.notFoundColor = wx.Colour(127,127,127)
        
        # Rescan button (and footnote text)
        scansizer = wx.BoxSizer(wx.HORIZONTAL)
        rescanLabel = wx.StaticText(self, -1, "* Currently configured AP")
        addButton = wx.Button(self, -1, "Add...")
        rescan = wx.Button(self, -1, "Rescan")
        rescanLabel.Enable(False)
        scansizer.AddMany(((rescanLabel, 1, wx.EXPAND|wx.ALIGN_LEFT|wx.ALL, 8),
                           (addButton, 0, wx.ALIGN_RIGHT|wx.EAST|wx.SHAPED, 8),
                           (rescan, 0, wx.ALIGN_RIGHT|wx.EAST|wx.SHAPED, 8)))
        sizer.Add(scansizer, 0, wx.EXPAND)

        # Password field components
        pwsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pwCheck = wx.CheckBox(self, -1, "Change Password:")
        self.pwCheck.Enable(False)
        self.pwField = wx.TextCtrl(self, -1, style=wx.TE_PASSWORD)
        self.pwField.Enable(False)
        
        pwstyle = wx.ALIGN_CENTER_VERTICAL|wx.RESERVE_SPACE_EVEN_IF_HIDDEN
        pwsizer.AddMany(((self.pwCheck, 0, pwstyle),
                         (self.pwField, 1, pwstyle|wx.EXPAND)))
        sizer.Add(pwsizer, 0, wx.EXPAND|wx.ALL, 8)

        # For future use
        self.forgetCheck = wx.CheckBox(self, -1, "Forget this AP on exit")
        sizer.Add(self.forgetCheck, 0, wx.EXPAND|wx.WEST|wx.SOUTH, 8)

        self.SetSizer(sizer)

        # For doing per-item tool tips in the list
        self.listToolTips = []
        self.lastToolTipItem = -1

        self.deleted = []
        self.passwords = {}
        
        self.list.Bind(wx.EVT_MOTION, self.OnListMouseMotion)
        rescan.Bind(wx.EVT_BUTTON, self.OnRescan)
        addButton.Bind(wx.EVT_BUTTON, self.OnAddButton)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self.list)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected, self.list)
        self.pwField.Bind(wx.EVT_SET_FOCUS, self.OnPasswordFocus)
        self.pwField.Bind(wx.EVT_TEXT, self.OnPasswordText)
        
        # FUTURE: For use with multiple AP memory
        if self.booleanAuth:
            self.forgetCheck.Hide()
        else:
            self.forgetCheck.Bind(wx.EVT_CHECKBOX, self.OnForgetChecked)
            self.list.Bind(wx.EVT_COMMAND_RIGHT_CLICK, self.OnListRightClick)
            self.list.Bind(wx.EVT_RIGHT_UP, self.OnListRightClick) # GTK

        self.getInfo()
        self.populate()
    
    
    def makeToolTip(self, ap):
        """ Generate the tool tip string for an AP. Isolated because it's
            bulky.
        """
        if ap.strength < 0:
            tooltip = u"%s (not in range)" % (ap.ssid)
        else:
            tooltip = u"%s (signal strength: %d%%)" % (ap.ssid, 100*ap.strength)
            
        if ap.selected:
            if ap.security:
                tooltip += u"\nSaved password, currently selected."
            else:
                tooltip += u"\nCurrently selected."
        # FUTURE: For use with multiple AP memory
        elif ap.ssid in self.deleted:
            tooltip += u"\nWill be forgotten."
        elif ap.security and not ap.known:
            # AP not previously configured; mark it.
            tooltip += u"\nRequires password."
        elif ap.security:
            tooltip += u"\nPassword saved."

        return tooltip


    def makeAuthTypeString(self, ap):
        """ Turn the AP AuthType into a string.
        """
        # Currently, AuthType is boolean (any or none), but might eventually
        # be an index.
        if self.booleanAuth:
            if ap.security:
                return u"\u2713"
            else:
                return "-"
        else:
            return AUTH_TYPES[ap.security]


    def populate(self):
        """ Fill out the AP list.
        """
        self.selected = -1
        self.lastSelected = -2
        self.listToolTips = []
        
        self.forgetCheck.Enable(False)
        
        self.list.DeleteAllItems()
        
        selected = False
        
        for n, ap in enumerate(self.info):
            # TODO: Use some sort of curve to round up low values.
            if ap.strength < 0:
                icon = 5
            elif ap.strength < .1:
                icon = 0
            else:
                icon = max(1, self.icons[int(ap.strength * 5)])
            
            if ap.security:
                icon += 6
                
            idx = self.list.InsertItem(self.list.GetItemCount(), ap.ssid, icon)
            self.list.SetItem(idx, 1, self.makeAuthTypeString(ap))
            self.list.SetItemData(idx, n)
            item = self.list.GetItem(idx)
            
            if ap.selected:
                # Indicate that this is the previously selected AP
                if not selected:
                    # HACK: Make sure only one will be marked as selected.
                    state = wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED
                    item.SetState(state)
                    item.SetStateMask(state)
                    selected = True
                else:
                    logger.warning("Device reported multiple selected APs!")

                item.SetFont(self.boldFont)
                item.SetText(item.GetText() + " *")
                
            elif ap.ssid in self.deleted:
                item.SetFont(self.struckFont)
            
#             if ap.strength < 0:
#                 item.SetTextColour(self.notFoundColor)
                
            self.list.SetItem(item)
            self.listToolTips.append(self.makeToolTip(ap))


    #===========================================================================
    # 
    #===========================================================================
    
    def OnRescan(self, evt):
        """ Handle "Rescan" button press.
        """
        self.getInfo()
        self.populate()


    def OnAddButton(self, evt):
        """ Handle 'Add' button press.
        """
        dlg = AddWifiDialog(self, -1, booleanAuth=self.booleanAuth)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        
        newinfo = []
        newap, pw = dlg.getValue()
        
        if not self.storeMultiplePasswords:
            self.passwords.clear()
        self.passwords[newap.ssid] = pw

        for ap in self.info:
            if ap.selected:
                ap = WifiInfo(ap.ssid, ap.strength, ap.security, ap.known,
                              False)
            if ap.ssid != newap.ssid:
                newinfo.append(ap)
        
        newinfo.append(newap)
        self.info = newinfo
        self.populate()
        

    def OnItemSelected(self, evt): 
        """ Handle an AP list item getting selected.
        """
        self.selected = evt.GetItem().GetData()
        ap = self.info[self.selected]
        
        changedPw = ap.ssid in self.passwords
        
        if ap.known:
            self.pwCheck.SetLabelText("Change Password:")
        else:
            self.pwCheck.SetLabelText("Set Password:")

        self.pwCheck.SetValue(changedPw)
        self.forgetCheck.Enable(ap.known)
        
        self.forgetCheck.SetValue(ap.ssid in self.deleted)
        
        hasPw = ap.security > 0 # Hack, works if security is numeric or index
        self.pwCheck.Enable(hasPw)
        self.pwField.Enable(hasPw)
        self.pwField.SetValue(self.passwords.get(ap.ssid, ""))


    def OnItemDeselected(self, evt):
        """ Handle an AP list item getting deselected.
        """
        self.selected = -1


    def OnForgetChecked(self, evt):
        """ Handle the 'Forget' checkbox changing.
            For future use, when multiple passwords are stored.
        """
        ssid = self.info[self.selected].ssid
        self.deleted.remove(ssid)
        
        if self.forgetCheck.GetValue():
            self.deleted.append(ssid)
                
        self.populate()


    def OnPasswordFocus(self, evt):
        """ Handle the password field being clicked in.
        """
        # Erase the field unless the user hasn't changed selected AP
        if self.selected != self.lastSelected:
            self.pwField.SetValue('')
            self.lastSelected = self.selected
            
        evt.Skip()

    
    def OnPasswordText(self, evt):
        """ Handle typing in the password field.
        """
        ssid = self.info[self.selected].ssid
        text = evt.GetString()
        if text:
            self.pwCheck.SetValue(True)
            if not self.storeMultiplePasswords:
                self.passwords.clear()
            self.passwords[ssid] = evt.GetString()
        evt.Skip()


    def OnListMouseMotion(self, evt):
        """ Handle mouse movement, updating the tool tips, etc.
        """
        # This determines the list item under the mouse and shows the
        # appropriate tool tip, if any
        index, _ = self.list.HitTest(evt.GetPosition())
        if index != -1 and index != self.lastToolTipItem:
            try:
                item = self.list.GetItemData(index)
                if self.listToolTips[item] is not None:
                    self.list.SetToolTip(self.listToolTips[item])
                else:
                    self.list.UnsetToolTip()
            except IndexError:
                pass
            self.lastToolTipItem = index
        evt.Skip()
        

    def OnListRightClick(self, evt):
        """ Handle a list item being right-clicked.
            For future use.
        """
        selected = self.info[self.selected]
        
        menu = wx.Menu()
        mi = menu.Append(wx.ID_DELETE, 'Forget "%s"' % selected.ssid)
        self.Bind(wx.EVT_MENU, self.OnDelete, id=wx.ID_DELETE)
        
        if not (selected.known and selected.strength < 0): 
            mi.Enable(False)

        self.PopupMenu(menu)
        menu.Destroy()


    def OnDelete(self, evt):
        """ Delete (forget) a saved AP.
            For future use.
        """
        self.deleted.append(self.info[self.selected].ssid)
        self.populate()
        

    #===========================================================================
    # 
    #===========================================================================
    
    def save(self):
        """ Save Wi-Fi configuration data to the device.
        """
        # Any password changes should be written here.
        # Any SSIDs in self.deleted should be deleted here.
        logger.debug("TODO: WifiSelectionTab.save() not implemented!")


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
    
