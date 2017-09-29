"""
Stand-alone clock auto-updater.
"""
from datetime import datetime
import importlib
import sys
import time

import os.path

import wx

import hub_icons

# Song and dance to find libraries in sibling folder.
# Should not matter after PyInstaller builds it.
try:
    _ = importlib.import_module('devices')
except ImportError:
    sys.path.append('..')

from widgets.device_dialog import DeviceSelectionDialog as DevSelDlg

#===============================================================================
# 
#===============================================================================

class HidingTaskBarIcon(wx.TaskBarIcon):
    """
    """
    
    def __init__(self, frame, label="Restore"):
        self.label = label
        self.frame = frame
        super(HidingTaskBarIcon, self).__init__()
        
        # XXX: Icon needs to be somewhere else for a 'real' version.
        img = wx.Image('hub_tray_icon.png', wx.BITMAP_TYPE_ANY)
        bmp = wx.BitmapFromImage(img)
        self.icon = wx.EmptyIcon()
        self.icon.CopyFromBitmap(bmp)

        self.hidden = True

        self.icon = hub_icons.hub_tray_icon.GetIcon()
        self.busyIcon = hub_icons.hub_tray_icon_active.GetIcon()
        
        self.Bind(wx.EVT_TASKBAR_LEFT_DOWN, self.OnTaskBarLeftClick)

    
    def setActive(self, active=True):
        if self.hidden:
            return
        if active:
            self.SetIcon(self.busyIcon, self.label)
        else:
            self.SetIcon(self.icon, self.label)

    
    def Hide(self):
        self.hidden = True
        self.RemoveIcon()
    
    
    def Show(self):
        self.hidden = False
        self.SetIcon(self.icon, self.label)
    
    
    def OnTaskBarActivate(self, evt):
        pass
    
    
    def OnTaskBarClose(self, evt):
        self.frame.Close()
        

    def OnTaskBarLeftClick(self, evt):
            """
            Create the right-click menu
            """
            self.frame.Show()
            self.frame.Restore()
            self.Hide()
    

#===============================================================================
# 
#===============================================================================

class HubDialog(DevSelDlg):
    """ Stand-alone clock auto-updater.
    """

    # Extra column: clock drift
    COLUMNS = (DevSelDlg.COLUMNS +
               (DevSelDlg.ColumnInfo("Clock Drift", "clockDrift", str, ''),))

    SET_INTERVAL = 60*60
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.drifts = {}
        self.tbIcon = HidingTaskBarIcon(self)
        
        super(HubDialog, self).__init__(*args, **kwargs)
        
        self.Bind(wx.EVT_ICONIZE, self.OnMinimize)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        
        self.baseTitle = self.GetTitle()
        self.nextClockSet = 0
        
        w,h = self.GetSizeTuple()
        w = max(w, 600)
        self.SetSizeWH(w, h)
        
        self.okButton.Hide()
        self.cancelButton.SetLabel("Close")
        self.setClockButton.SetLabel("Set Clocks Now")
        
        self.TimerHandler(None)

    
    def OnMinimize(self, evt):
        if self.IsIconized():
            self.tbIcon.Show()
            self.Hide()
        
    
    def OnClose(self, evt):
        self.tbIcon.RemoveIcon()
        self.tbIcon.Destroy()
        self.Destroy()
        wx.GetApp().Exit()
        

    def TimerHandler(self, evt):
        super(HubDialog, self).TimerHandler(evt)
        if time.time() > self.nextClockSet:
            self.setClocks()


    def OnItemDoubleClick(self, evt):
        evt.Skip()


    def setClocks(self, evt=None):
        if not self.recorders:
            return
         
        self.tbIcon.setActive()
            
        super(HubDialog, self).setClocks(evt)
        ts = str(datetime.now()).rsplit('.',1)[0]
        self.SetTitle("%s (last set at %s)" % (self.baseTitle, ts))
        self.nextClockSet = time.time() + self.SET_INTERVAL

        self.tbIcon.setActive(False)
            

    def _thing2string(self, dev, col):
        try:
            # Special case: clock drift from when the recorder was first found
            if col.propName == 'clockDrift':
                if dev.serial not in self.drifts:
                    self.drifts[dev.serial] = dev.getClockDrift()
                return col.formatter(self.drifts[dev.serial])
            return col.formatter(getattr(dev, col.propName, col.default))
        except TypeError:
            return col.default


    def populateList(self):
        self.tbIcon.setActive()
        DevSelDlg.populateList(self)
        
        # Remove time drift for unplugged devices
        serials = [d.serial for d in self.recorders.values()]
        for d in self.drifts.keys():
            if d not in serials:
                self.drifts.pop(d)
                
        self.tbIcon.setActive(False)



#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    app = wx.App()
    dlg = HubDialog(None, -1, "Slam Stick Time Hub")
    dlg.Show()
    app.MainLoop()
#     dlg.Destroy()

    
