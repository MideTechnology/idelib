'''
System for retrieving the latest version number from the web and prompting the
user to update if a newer version is available.

Created on Jul 25, 2014

@author: dstokes
'''

from collections import OrderedDict
# import httplib
import json
import threading
import time
import urllib

import wx; wx = wx
import wx.lib.sized_controls as SC
import wx.html

from events import EvtUpdateAvailable

#===============================================================================
# 
#===============================================================================

UPDATER_URL = "http://10.0.0.166/slam_stick_lab.json"
CHANGELOG_URL = "http://10.0.0.166/slam_stick_lab_changelog.html"
DOWNLOAD_URL = "http://www.mide.com/products/slamstick/slam-stick-lab-software.php?utm_source=Slam-Stick-X-Data-Logger&utm_medium=Device&utm_content=Link-to-software-page-from-Device-About-Us&utm_campaign=Slam-Stick-X"

INTERVALS = OrderedDict(enumerate(("Never check automatically",
                                   "Monthly",
                                   "Weekly",
                                   "Daily",
                                   "Every time the app is launched")))

    
#===============================================================================
# 
#===============================================================================

class SaferHtmlWindow(wx.html.HtmlWindow):
    """
    """
#     def isValidURL(self, url):
#         """
#         """
#         scheme, url = urllib.splittype(url)
#         if scheme is None:
#             return False
#         host, _path = urllib.splithost(url)
#         return host.endswith('mide.com')
    
        
    def OnLinkClicked(self, linkinfo):
        """ Handle a link click. Does not permit outgoing links (for security).
        """
        href = linkinfo.GetHref()
        if href.startswith(('file:', '#')):
            super(SaferHtmlWindow, self).OnLinkClicked(linkinfo)
#         elif self.isValidURL(href):
#             # Launch external web browser
#             wx.LaunchDefaultBrowser(href)


#===============================================================================
# 
#===============================================================================
class UpdateDialog(SC.SizedDialog):
    """
    """
    ID_SKIP = wx.NewId()
    ID_DOWNLOAD = wx.NewId()
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        self.newVersion = kwargs.pop('newVersion')
        newVers = '.'.join(map(str,self.newVersion))
        self.changeUrl = kwargs.pop('changelog', '')
        self.downloadUrl = kwargs.pop('url', DOWNLOAD_URL)
        kwargs.setdefault('style', wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        super(UpdateDialog, self).__init__(*args, **kwargs)
        
        title = self.GetTitle()
        if not title:
            self.SetTitle("Update Check")
        
        pane = self.GetContentsPane()
        pane.SetSizerType("vertical")
        
        titleFont = self.GetFont().Bold()
        titleFont.SetPointSize(int(titleFont.GetPointSize() * 1.5))
        appname = getattr(self.root, 'AppDisplayName', u"(Slam\u2022Stick Lab)")
        headerText = "A new version of %s (%s) is available!" % (appname, 
                                                                 newVers)
        header = wx.StaticText(pane, -1, headerText)
        header.SetFont(titleFont)
        
        boldFont = self.GetFont().Bold()
        s1 = SC.SizedPanel(pane, -1)
        s1.SetSizerType("horizontal", {'hgap':10, 'vgap':10})
        wx.StaticText(s1, -1, "Your version:")
        wx.StaticText(s1, -1, self.root.versionString).SetFont(boldFont)
        
        self.html = SaferHtmlWindow(pane, -1)
        self.html.SetSizerProps(expand=True, proportion=-1)
        if self.changeUrl:
            self.html.LoadPage(self.changeUrl)
        else:
            self.html.SetPage("See the Download Page for more information.")
        
#         wx.StaticText(pane, -1, "You can change the frequency of update checks in the Preferences Dialog.")
        
        buttonpane = SC.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        skipBtn = wx.Button(buttonpane, self.ID_SKIP, "Skip this version")
        skipBtn.SetSizerProps(halign="right")
        downloadBtn = wx.Button(buttonpane, self.ID_DOWNLOAD, 
                                "Go to download page")
        downloadBtn.SetSizerProps(halign="right")
        wx.Button(buttonpane, wx.ID_CANCEL).SetSizerProps(halign="right")
        
        downloadBtn.SetToolTipString('Open "%s" in your default browser' % \
                                     urllib.splitquery(self.downloadUrl)[0])
        
        skipBtn.Bind(wx.EVT_BUTTON, self.OnSkip)
        downloadBtn.Bind(wx.EVT_BUTTON, self.OnDownload)

        minWidth = header.GetSize()[0] + 40
        minHeight = 300 if self.changeUrl else -1
        self.SetMinSize((minWidth,300))

        self.Fit()
        self.SetFocus()

    def OnSkip(self, evt):
        self.EndModal(self.ID_SKIP)
    
    def OnDownload(self, evt):
        wx.LaunchDefaultBrowser(self.downloadUrl)
        self.EndModal(self.ID_DOWNLOAD)
    
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
    now = (now.tm_year, now.tm_mon, 6-now.tm_wday, now.tm_yday)
    last = time.localtime(lastUpdate)
    last = (last.tm_year, last.tm_mon, 6-last.tm_wday, last.tm_yday)
    
    return any(map(lambda x: x[0] > x[1], zip(now, last)[:interval+1]))


def isNewer(v1, v2):
    """ Compare two sets of version numbers `(major, minor, [build])`.
    """
    for v,u in zip(v1,v2):
        if v == u:
            continue
        else:
            return v > u


def getLatestVersion(url=UPDATER_URL):
    """ Retrieve the latest version from a JSON feed (or static JSON file).
        @keyword url: 
        @return: A tuple containing the HTTP response code and the data (a
            list of version number components).
    """
    try:
        x = urllib.urlopen(url)
        if int(x.getcode()) / 400 == 1:
            # error
            return x.getcode(), None
        vers = json.load(x)
        x.close()
        return x.getcode(), vers
    except IOError:
        return None, None
    

def checkUpdates(app, force=False, url=UPDATER_URL):
    """ Wrapper for the whole version checking system, to be called by the 
        main app instance.
        
        @param app: The main `ViewerApp` (`wx.App`) instance.
        @keyword force: If `True`, the version check will be performed
            regardless of the update interval and the `updater.version`
            preference. The viewer will also be prompted to display a message if
            the software is up to date.
        @keyword url: The URL of the JSON file/feed containing the latest
            version number
    """
    lastUpdate = app.getPref('updater.lastCheck', 0)
    interval = app.getPref('updater.interval', 3)
    currentVersion = app.getPref('updater.version', None)
    
    if force or currentVersion is None or isNewer(app.version, currentVersion):
        currentVersion = app.version
    if force or isTimeToCheck(lastUpdate, interval):
        _responseCode, response = getLatestVersion(url)
        if response:
            newVersion= response['version']
            changelog = response.get('changelog', '')
            if isNewer(newVersion, currentVersion):
                wx.PostEvent(app, EvtUpdateAvailable(version=newVersion,
                                                     changelog=changelog,
                                                     url=url))
            else:
                wx.PostEvent(app, EvtUpdateAvailable(version=False, 
                                                     showNoUpdate=force))


def startCheckUpdatesThread(*args, **kwargs):
    """ Thread wrapper for the `checkUpdates` function.
    
        @param app: The main `ViewerApp` (`wx.App`) instance.
        @keyword force: If `True`, the version check will be performed
            regardless of the update interval and the `updater.version`
            preference.
        @keyword url: 
    """
    t = threading.Thread(target=checkUpdates, name="Update Check", 
                         args=args, kwargs=kwargs)
    t.start()


#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    
    class FakeApp(wx.App):
        PREFS = {
                 }
        version = (9,9,10)
        versionString = '.'.join(map(str, version))
        def getPref(self, v, default):
            return self.PREFS.get(v, default)
        def setPref(self, v, val):
            self.PREFS[v] = val
    
    app = FakeApp()
    
    code, response = getLatestVersion()
    print "app.version = %r" % (app.version,)
    print "getLatestVersion returned code %r, version %r" % (code, response)
    if response is None:
        print "Error occurred; aborting"
        exit(1)

    vers = response.get('version', None)
    changeUrl = response.get('changelog', None)
    print "zipped: %r" % (zip(app.version, vers),)
    t = 1406471411.0
    print "isTimeToCheck(%r): %r" % (t, isTimeToCheck(t,2))
    t = time.time()
    print "isTimeToCheck(%r): %r" % (t, isTimeToCheck(t))
    print "isNewer(%r, %r): %r" % (app.version, vers, isNewer(app.version, vers))
    
    dlg = UpdateDialog(None, -1, root=app, newVersion=vers, changelog=changeUrl)
    dlg.ShowModal()
    dlg.Destroy()