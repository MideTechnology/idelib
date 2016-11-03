"""
Stand-alone clock auto-updater.
"""
from datetime import datetime
import importlib
import sys
import time

import wx

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
        super(HubDialog, self).__init__(*args, **kwargs)
        
        self.baseTitle = self.GetTitle()
        self.nextClockSet = 0
        
        w,h = self.GetSizeTuple()
        w = max(w, 600)
        self.SetSizeWH(w, h)
        
        self.okButton.Hide()
        self.cancelButton.SetLabel("Close")
        self.setClockButton.SetLabel("Set Clocks Now")
        
        self.TimerHandler(None)


    def TimerHandler(self, evt):
        super(HubDialog, self).TimerHandler(evt)
        if time.time() > self.nextClockSet:
            self.setClocks()


    def OnItemDoubleClick(self, evt):
        evt.Skip()


    def setClocks(self, evt=None):
        if not self.recorders:
            return 
        super(HubDialog, self).setClocks(evt)
        ts = str(datetime.now()).rsplit('.',1)[0]
        self.SetTitle("%s (last set at %s)" % (self.baseTitle, ts))
        self.nextClockSet = time.time() + self.SET_INTERVAL


    def _thing2string(self, dev, col):
        try:
            # Special case: clock drift from when the recorder was first found
            if col.propName == 'clockDrift':
                d = getattr(dev, 'clockDrift', None)
                if d is None:
                    sysTime, devTime = dev.getTime()
                    dev.clockDrift = sysTime - devTime
            return col.formatter(getattr(dev, col.propName, col.default))
        except TypeError:
            return col.default




#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    app = wx.App()
    dlg = HubDialog(None, -1, "Slam Stick Time Hub")
    dlg.ShowModal()
    dlg.Destroy()

    
