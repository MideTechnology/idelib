'''
Created on Jul 25, 2014

@author: dstokes
'''

from collections import OrderedDict
import httplib
import json
import threading
import time
import urllib

import wx; wx = wx
import wx.lib.sized_controls as SC

from common import Job
from events import EvtUpdateAvailable

#===============================================================================
# 
#===============================================================================

UPDATER_URL = "http://10.0.0.166/slam_stick_lab.json"

INTERVALS = OrderedDict(enumerate(("Never check automatically",
                                   "Monthly",
                                   "Weekly",
                                   "Daily",
                                   "Every time the app is launched")))

#===============================================================================
# 
#===============================================================================

class VersionChecker(Job):
    """
    """
    intervals = {0: "Never check automatically",
                 1: "Monthly",
                 2: "Weekly",
                 3: "Daily",
                 4: "Every time the app is launched"}
    
    def __init__(self, root, url=UPDATER_URL, numUpdates=100, 
                 updateInterval=1.0):
        self.root = root
        self.url = url
        super(VersionChecker, self).__init__(root, numUpdates=numUpdates, 
                                             updateInterval=updateInterval)

    
    @classmethod
    def isTimeToCheck(cls, lastUpdate, interval=3):
        """ Determine if it is time to check for updates.
        """
        if interval == 0:
            return False
        if interval == 4:
            return True

        now = time.localtime()
        now = (now.tm_year, now._tm_mon, 6-now.tm_wday, now.tm_yday)
        last = time.localtime(lastUpdate)
        last = (last.tm_year, last._tm_mon, 6-last.tm_wday, last.tm_yday)

        return any(map(lambda x: x[0] > x[1], zip(now, last)[:interval+1]))


    @classmethod
    def checkUpdates(cls, url, version, quiet=True):
        """ Get the latest version number from the update URL and see if it
            is greater than the current version.
        """
        try:
            x = json.load(urllib.urlopen(url))
            for v,u in zip(version,x):
                if v < u:
                    return x
        except Exception as err:
            if not quiet:
                raise err
        
        return False


    def run(self):
        newVers = self.checkUpdates(self.url, self.root._versionNumbers)
        if newVers:
            wx.PostEvent(self.root, EvtUpdateAvailable(info=newVers))
    
    
#===============================================================================
# 
#===============================================================================

class UpdateDialog(SC.SizedDialog):
    """
    """
    
    def __init__(self, *args, **kwargs):
        self.url = kwargs.pop('url')
        self.root = kwargs.pop('root')
        kwargs.setdefault('style', wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        super(UpdateDialog, self).__init__(*args, **kwargs)
        
        pane = self.GetContentsPane()
        pane.SetSizerType("vertical")
        
        appname = getattr(self.root, '_appname', u"Slam\u2022Stick Lab")
        wx.StaticText(self, -1, "A new version of %s is available!" % appname)
        
        buttonpane = SC.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        skipBtn = wx.Button(buttonpane, -1, "Skip this version")
        skipBtn.SetSizerProps(halign="right")
        downloadBtn = wx.Button(buttonpane, -1, "Go to download page")
        downloadBtn.SetSizerProps(halign="right")
        wx.Button(buttonpane, wx.ID_CANCEL).SetSizerProps(halign="right")
        
        skipBtn.Bind(wx.EVT_BUTTON, self.OnSkip)
        downloadBtn.Bind(wx.EVT_BUTTON, self.OnDownload)

        self.Fit()

    def OnSkip(self, evt):
        pass
    
    def OnDownload(self, evt):
        pass
    
#===============================================================================
# 
#===============================================================================

def isTimeToCheck(lastUpdate, interval=3):
    """ Determine if it is time to check for updates.
    """
    if interval == 0:
        return False
    if interval == 4:
        return True

    now = time.localtime()
    now = (now.tm_year, now._tm_mon, 6-now.tm_wday, now.tm_yday)
    last = time.localtime(lastUpdate)
    last = (last.tm_year, last._tm_mon, 6-last.tm_wday, last.tm_yday)

    return any(map(lambda x: x[0] > x[1], zip(now, last)[:interval+1]))


def isNewer(v1, v2):
    """ Compare two sets of version numbers `(major, minor, [build])`.
    """
    for v,u in zip(v1,v2):
        if v < u:
            return False
    return True


def getLatestVersion(url=UPDATER_URL):
    x = urllib.urlopen(url)
    if int(x.getcode()) / 400 == 1:
        # error
        return x.getcode(), None
    vers = json.load(x)
    x.close()
    return x.getcode(), vers


def checkUpdates(app, force=False, url=UPDATER_URL):
#         'updater.interval': 4,
#         'updater.lastCheck': 0, 
#         'update.version': VERSION,
    lastUpdate = app.getPref('updater.lastCheck', 0)
    interval = app.getPref('updater.interval', 3)
    currentVersion = app.getPref('updater.version', None)
    if force or currentVersion is None or isNewer(app.version, currentVersion):
        currentVersion = app.version
    if force or isTimeToCheck(lastUpdate, interval):
        response, newVersion = getLatestVersion(url)
        if response:
            if isNewer(newVersion, currentVersion):
                wx.PostEvent(app, EvtUpdateAvailable(info=newVersion))
            else:
                app.setPref('updater.lastCheck', time.time())

