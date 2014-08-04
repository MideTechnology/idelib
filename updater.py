'''
System for retrieving the latest version number from the web and prompting the
user to update if a newer version is available.

The latest version information is provided in JSON, either as a feed or as a
static file.

    {
        "version": [1, 2, 3],
        "changelog": "http://example.mide.com/change_log.html",
        "date": 1406815444
    }

`version` is a list of version numbers: major, minor, and micro (build). It
can be longer or shorter, but two is the expected minimum length. When compared
to the app's `version` attribute, the shorter form takes precedence (the extra
digits are ignored).

`changelog` is the URL of the release notes for the new version. It is displayed
in the new version announcement dialog. Optional.

`date` is the Unix epoch timestamp of when the last update was created. 
Currently unused by the viewer. Optional.

@todo: Use `httplib.HTTPException` raising for bad web server responses, making
    the connection error handling more uniform.

Created on Jul 25, 2014

@author: dstokes
'''

from collections import OrderedDict
# import httplib
import json
import os.path
import threading
import time
import urllib

import wx; wx = wx
import wx.lib.sized_controls as SC
import wx.html

from logger import logger
from mide_ebml.dataset import __DEBUG__

from events import EvtUpdateAvailable

#===============================================================================
# 
#===============================================================================

# UPDATER_BASE = "http://10.0.0.166/"
UPDATER_BASE = "http://www.mide.com/software/updates/"
UPDATER_URL = os.path.join(UPDATER_BASE, "slam_stick_lab.json")
CHANGELOG_URL = os.path.join(UPDATER_BASE, "slam_stick_lab_changelog.html")
DOWNLOAD_URL = "http://www.mide.com/products/slamstick/slam-stick-lab-software.php?utm_source=Slam-Stick-X-Data-Logger&utm_medium=Device&utm_content=Link-to-software-page-from-Device-About-Us&utm_campaign=Slam-Stick-X"

INTERVALS = OrderedDict(enumerate(("Never check automatically",
                                   "Monthly",
                                   "Weekly",
                                   "Daily",
                                   "Every time the app is launched")))

#===============================================================================
# 
#===============================================================================

def isSafeUrl(url):
    """ Simple function to determine if a URL is (moderately) safe, i.e. is
        at mide.com. 
    """
    if not url:
        return False
    
    if __DEBUG__:
        return True
    
    prot, addr = urllib.splittype(url)
    if not prot.lower().startswith(('http','ftp')):
        return False
    host, _path = urllib.splithost(addr)
    if not host.lower().endswith('mide.com'):
        return False
    return True


def hijackWarning(parent, url):
    """ Display a warning message if a URL doesn't point to a Mide server.
    """
    if url and len(url) > 40:
        url = urllib.splitquery(url)[0]
    d = wx.MessageBox(
        "The link's URL does not appear to direct to a Mid\xe9 website.\n\n"
        "This is likely intentional, but it could be an indication that the "
        "update server has been compromised.\n\nURL: %s\n\n"
        "Open the link anyway?" % url, "Possible Link Hijack", parent=parent,
        style=wx.YES_NO|wx.NO_DEFAULT|wx.ICON_EXCLAMATION)
    return d == wx.YES

#===============================================================================
# 
#===============================================================================

class SaferHtmlWindow(wx.html.HtmlWindow):
    """ A slightly safer HTML window, which checks all URLs before opening
        them. File and relative named anchor links open in the same window,
        all others in the default browser.
    """
        
    def OnLinkClicked(self, linkinfo):
        """ Handle a link click. Does not permit outgoing links (for security).
        """
        href = linkinfo.GetHref()
        if href.startswith(('file:', '#')):
            super(SaferHtmlWindow, self).OnLinkClicked(linkinfo)
            return
        
        if not isSafeUrl(href):
            if not hijackWarning(self, href):
                return
            
        # Launch external web browser
        logger.info('Updater HTML window opened %s' % href)
        wx.LaunchDefaultBrowser(href)


#===============================================================================
# 
#===============================================================================
class UpdateDialog(SC.SizedDialog):
    """ Dialog that appears when there is a new version of the software
        available to download. It handles getting and displaying the a change
        list and launching the user's default web browser (if the user opts to
        download the new version).
    """
    ID_SKIP = wx.NewId()
    ID_DOWNLOAD = wx.NewId()
    
    DEFAULT_CHANGELIST = ("<html><body>"
                          "See the Download Page for more information."
                          "</body></html>")
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `SizedDialog` arguments, plus:
            @keyword updaterEvent: The `EvtUpdateAvailable` event sent to the
                app that lead to this dialog being displayed.
        """
        self.root = kwargs.pop('root', wx.GetApp())
        self.updaterEvent = kwargs.pop('updaterEvent', None)
        
        kwargs.setdefault('style', wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        super(UpdateDialog, self).__init__(*args, **kwargs)
        
        vers = self.updaterEvent.newVersion
        if len(vers) > 2 and isinstance(vers[-1], (float, int)):
            vers = vers[:-1] + [str(vers[-1]).rjust(4,'0')]
        self.newVersion = '.'.join(map(str,vers))
        self.changeUrl = self.updaterEvent.changelog
        self.downloadUrl = self.updaterEvent.url
        
        title = self.GetTitle()
        if not title:
            self.SetTitle("Update Check")
        
        appname = getattr(self.root, 'AppDisplayName', u"(Slam\u2022Stick Lab)")
        headerText = ("A new version of %s (%s) is available!" % 
                      (appname, self.newVersion))

        pane = self.GetContentsPane()
        pane.SetSizerType("vertical")
        
        header = wx.StaticText(pane, -1, headerText)
        header.SetFont(self.GetFont().Bold().Scaled(1.5))
        minWidth = header.GetSize()[0] + 40
        
        # The headline and the current version display
        boldFont = self.GetFont().Bold()
        s1 = SC.SizedPanel(pane, -1)
        s1.SetSizerType("horizontal", {'hgap':10, 'vgap':10})
        wx.StaticText(s1, -1, "Your version:")
        wx.StaticText(s1, -1, self.root.versionString).SetFont(boldFont)
        
        # The changelog display
        self.html = SaferHtmlWindow(pane, -1)
        self.html.SetSizerProps(expand=True, proportion=-1)
        if isSafeUrl(self.changeUrl):
            self.html.LoadPage(self.changeUrl)
        else:
            self.html.SetPage(self.DEFAULT_CHANGELIST)
        
        # Little link to the preferences dialog, for convenience.
        s2 = SC.SizedPanel(pane, -1)
        s2.SetSizerType('horizontal')
        wx.StaticText(s2, -1, "You can change the frequency "
                      "of update checks in the")
        prefTxt = wx.StaticText(s2, -1, "Preferences Dialog.")
        prefTxt.SetForegroundColour("BLUE")
        prefTxt.Bind(wx.EVT_LEFT_UP, self.OnPrefClick)
        
        # Bottom button pane
        buttonpane = SC.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        skipBtn = wx.Button(buttonpane, self.ID_SKIP, "Skip this version")
        skipBtn.SetSizerProps(halign="right")
        downloadBtn = wx.Button(buttonpane, self.ID_DOWNLOAD, 
                                "Go to download page")
        downloadBtn.SetSizerProps(halign="right")
        cancelBtn = wx.Button(buttonpane, wx.ID_CANCEL)
        cancelBtn.SetSizerProps(halign="right")
        
        cancelBtn.SetToolTipString(
            "Ignore this update for now. You will be notified again the next "
            "time the update check is run.")
        skipBtn.SetToolTipString(
            'Do not receive further automatic notifications for version %s. '
            'It will still appear in user-initiated version checks '
            '(Help menu, Check for Updates sub-menu).' % self.newVersion)
        downloadBtn.SetToolTipString('Open "%s" in your default browser' % \
                                     urllib.splitquery(self.downloadUrl)[0])
        
        skipBtn.Bind(wx.EVT_BUTTON, self.OnSkip)
        downloadBtn.Bind(wx.EVT_BUTTON, self.OnDownload)

        self.SetMinSize((minWidth,300))
        self.Fit()
        self.SetFocus()


    def OnPrefClick(self, evt):
        self.root.editPrefs()

    def OnSkip(self, evt):
        self.EndModal(self.ID_SKIP)
    
    def OnDownload(self, evt):
        if not isSafeUrl(self.downloadUrl):
            if not hijackWarning(self, self.downloadUrl):
                self.EndModal(wx.ID_CANCEL)
                return
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
    try:
        for v,u in zip(v1,v2):
            if v == u:
                continue
            else:
                return v > u
    except TypeError:
        return False


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
    except IOError as err:
        return err, None


def checkUpdates(app, force=False, quiet=True, url=UPDATER_URL):
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
    
    # Helper function to create and post the event.
    def sendUpdateEvt(vers=None, date=None, cl=None, err=None, response=None):
        evt = EvtUpdateAvailable(newVersion=vers, changelog=cl, url=url, 
                                 error=err, response=response, quiet=quiet)
        wx.PostEvent(app, evt)
    
    if force or currentVersion is None or isNewer(app.version, currentVersion):
        currentVersion = app.version
        
    if force or isTimeToCheck(lastUpdate, interval):
        responseCode, responseContent = getLatestVersion(url)
        if responseContent:
            newVersion= responseContent['version']
            changelog = responseContent.get('changelog', CHANGELOG_URL)
            updateDate = responseContent.get('date', None)
            if isNewer(newVersion, currentVersion):
                sendUpdateEvt(newVersion, updateDate, changelog)
            else:
                sendUpdateEvt(False, updateDate)
        else:
            sendUpdateEvt(False, err=True, response=responseCode)


def startCheckUpdatesThread(*args, **kwargs):
    """ Thread wrapper for the `checkUpdates` function. Simply creates and
        starts the function in a thread.
    
        @param app: The main `ViewerApp` (`wx.App`) instance.
        @keyword force: If `True`, the version check will be performed
            regardless of the update interval and the `updater.version`
            preference. The viewer will also be prompted to display a message if
            the software is up to date.
        @keyword url: The URL of the JSON file/feed containing the latest
            version number
    """
    t = threading.Thread(target=checkUpdates, name="Update Check", 
                         args=args, kwargs=kwargs)
    t.start()


#===============================================================================
# 
#===============================================================================

# if __name__ == '__main__':
#      
#     class FakeApp(wx.App):
#         PREFS = {
#                  }
#         version = (9,9,10)
#         versionString = '.'.join(map(str, version))
#         def getPref(self, v, default):
#             return self.PREFS.get(v, default)
#         def setPref(self, v, val):
#             self.PREFS[v] = val
#         def editPrefs(self, evt=None):
#             print "edit prefs"
#      
#     app = FakeApp()
#      
#     code, response = getLatestVersion()
#     print "app.version = %r" % (app.version,)
#     print "getLatestVersion returned code %r, version %r" % (code, response)
#     if response is None:
#         print "Error occurred; aborting"
#         exit(1)
#  
#     vers = response.get('version', None)
#     changeUrl = response.get('changelog', None)
#     print "zipped: %r" % (zip(app.version, vers),)
#     t = 1406471411.0
#     print "isTimeToCheck(%r): %r" % (t, isTimeToCheck(t,2))
#     t = time.time()
#     print "isTimeToCheck(%r): %r" % (t, isTimeToCheck(t))
#     print "isNewer(%r, %r): %r" % (app.version, vers, isNewer(app.version, vers))
#      
#     evt = EvtUpdateAvailable(newVersion=vers, changelog=changeUrl, url=DOWNLOAD_URL)
#      
# #     dlg = UpdateDialog(None, -1, root=app, newVersion=vers, changelog=changeUrl)
#     dlg = UpdateDialog(None, -1, updaterEvent=evt)
#     dlg.ShowModal()
#     dlg.Destroy()