'''
System for retrieving the latest version number from the web and prompting the
user to update if a newer version is available.

The latest version information is provided in JSON, either as a feed or as a
static file.

    {
        "version": [1, 2, 3],
        "changelog": "http://example.mide.com/change_log.html",
        "date": 1406815444,
        "downloadUrl": "http://example.mide.com/download.html"
    }

`version` is a list of version numbers: major, minor, and micro (build). It
can be longer or shorter, but two is the expected minimum length. When compared
to the app's `version` attribute, the shorter form takes precedence (the extra
digits are ignored). This is the only required item.

`changelog` is the URL of the release notes for the new version. It is displayed
in the new version announcement dialog. Optional.

`date` is the Unix epoch timestamp of when the last update was created. 
Currently unused by the viewer. Optional.

`downloadUrl` is the URL of the download page. Defaults to `DOWNLOAD_URL` if
absent. Optional.

@todo: Use `httplib.HTTPException` raising for bad web server responses, making
    the connection error handling more uniform.

Created on Jul 25, 2014

@author: dstokes
'''

from collections import OrderedDict
import json
import os.path
import threading
import time
import urllib

import wx #@UnusedImport
import wx.lib.sized_controls as SC

from logger import logger
from build_info import DEBUG, BETA, VERSION
from events import EvtUpdateAvailable
from widgets.htmlwindow import SaferHtmlWindow, isSafeUrl, hijackWarning

if DEBUG:
    import logging
    logger.setLevel(logging.INFO)


#===============================================================================
# 
#===============================================================================

# UPDATER_BASE = "http://10.0.0.166/"
UPDATER_BASE = "http://mide.services/software/"
UPDATER_URL = os.path.join(UPDATER_BASE, "slam_stick_lab.json")
CHANGELOG_URL = os.path.join(UPDATER_BASE, "slam_stick_lab_changelog.html")
DOWNLOAD_URL = "http://info.mide.com/data-loggers/slam-stick-lab-software?utm_campaign=Slam-Stick-X&utm_content=Link-to-software-page-from-Device-About-Us&utm_medium=Device&utm_source=Slam-Stick-X-Data-Logger"

# BETA_UPDATER_URL = os.path.join(UPDATER_BASE, "slam_stick_lab_beta.json")
# BETA_CHANGELOG_URL = os.path.join(UPDATER_BASE, "slam_stick_lab_beta_changelog.html")
# BETA_DOWNLOAD_URL = DOWNLOAD_URL

BETA_UPDATER_URL = os.path.join(UPDATER_BASE, "slam_stick_lab_beta.json")
BETA_CHANGELOG_URL = CHANGELOG_URL
BETA_DOWNLOAD_URL = DOWNLOAD_URL

INTERVALS = OrderedDict(enumerate(("Never check automatically",
                                   "Monthly",
                                   "Weekly",
                                   "Daily",
                                   "Every time the app is launched")))

#===============================================================================
# 
#===============================================================================

class UpdateDialog(SC.SizedDialog):
    """ Dialog that appears when there is a new version of the software
        available to download. It handles getting and displaying the a change
        list and launching the user's default web browser (if the user opts to
        download the new version).
    """
    ID_SKIP = wx.NewIdRef()
    ID_DOWNLOAD = wx.NewIdRef()
    
    DEFAULT_CHANGELIST = ("<html><body>"
                          "See the Download Page for more information."
                          "</body></html>")
    
    FIELD_PAD = 8 # Padding for use when calculating field height
    
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
        if len(vers) > 3 and isinstance(vers[-1], (float, int)):
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
        
        # The headline and the current version display
        boldFont = self.GetFont().Bold()
        s1 = SC.SizedPanel(pane, -1)
        s1.SetSizerType("horizontal", {'hgap':10, 'vgap':10})
        wx.StaticText(s1, -1, "Your version:")
        wx.StaticText(s1, -1, self.root.versionString).SetFont(boldFont)
        
        # The changelog display
        self.html = SaferHtmlWindow(pane, -1, style=wx.BORDER_THEME)
        self.html.SetSizerProps(expand=True, proportion=-1)
        if isSafeUrl(self.changeUrl):
            self.html.LoadPage(self.changeUrl)
        else:
            self.html.SetPage(self.DEFAULT_CHANGELIST)
        
        # Little link to the preferences dialog, for convenience.
        s2 = SC.SizedPanel(pane, -1)
        s2.SetSizerType('horizontal')
        freqTxt = wx.StaticText(s2, -1, ("You can change the frequency "
                                         "of update checks in the"))
        prefTxt = wx.StaticText(s2, -1, "Preferences Dialog.")
        prefTxt.SetForegroundColour("BLUE")
        prefTxt.Bind(wx.EVT_LEFT_UP, self.OnPrefClick)
        
        minWidth = max(header.GetSize()[0], freqTxt.GetSize()[0] + prefTxt.GetSize()[0])
        minWidth += self.FIELD_PAD * 8
        
        # Bottom button pane
        
        # This stuff is just to create non-standard buttons, right aligned,
        # with a gap. It really should not be this hard to do. This approach is
        # probably not optimal or properly cross-platform.
        SC.SizedPanel(pane, -1, size=(8,self.FIELD_PAD))
        
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
        
        cancelBtn.SetToolTip(
            "Ignore this update for now. You will be notified again the next "
            "time the update check is run.")
        skipBtn.SetToolTip(
            'Do not receive further automatic notifications for version %s. '
            'It will still appear in user-initiated version checks '
            '(Help menu, Check for Updates sub-menu).' % self.newVersion)
        downloadBtn.SetToolTip('Open "%s" in your default browser' % \
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
        
        @param lastUpdate: The *NIX epoch time of the last update check.
        @keyword interval: The check frequency, as specified in `INTERVALS`.
    """
    if interval == 0: # "Never check automatically"
        return False
    if interval == 4: # "Every time the app is launched"
        return True

    now = time.localtime()
    now = (now.tm_year, now.tm_mon, 6-now.tm_wday, now.tm_yday)
    last = time.localtime(lastUpdate)
    last = (last.tm_year, last.tm_mon, 6-last.tm_wday, last.tm_yday)
    
    return any(map(lambda x: x[0] > x[1], zip(now, last)[:interval+1]))


def isNewer(v1, v2):
    """ Compare two sets of version numbers `(major, minor, micro, [build])`.
    """
    try:
        for v,u in zip(v1,v2):
            if v == u:
                continue
            else:
                return v > u
    except TypeError:
        return False
    
    # Numbers are equal, but the release version trumps the debug version
    # since the debug versions have the same number. The JSON will not be
    # updated until release.
    return DEBUG


def getLatestVersion(url=UPDATER_URL):
    """ Retrieve the latest version from a JSON feed (or static JSON file).
        @keyword url: 
        @return: A tuple containing the HTTP response code and the data (a
            list of version number components).
    """
    try:
        x = urllib.urlopen(url)
        code = int(x.getcode())
        if code / 400 == 1:
            # error
            return code, None
        vers = json.load(x)
        if BETA and 'beta' in vers:
            # Beta update info overrides defaults.
            vers.update(vers.pop('beta'))
        x.close()
        return code, vers
    except IOError as err:
        return err, None


def checkUpdates(app, force=False, quiet=True, url=UPDATER_URL, 
                 downloadUrl=None, checkBeta=BETA):
    """ Wrapper for the whole version checking system, to be called by the 
        main app instance.
        
        @param app: The main `ViewerApp` (`wx.App`) instance.
        @keyword force: If `True`, the version check will be performed
            regardless of the update interval and the `updater.version`
            preference. The viewer will also be prompted to display a message if
            the software is up to date.
        @keyword quiet: If `True`, the recipient of the update event will
            show a message box. This is just passed verbatim; this function
            doesn't actually do anything with it.
        @keyword url: The URL of the JSON file/feed containing the latest
            version number
        @keyword downloadUrl: The URL of the download page. If not `None`, 
            overrides the download URL in the JSON data (or the default 
            DOWNLOAD_URL if `downloadURL` is not in the JSON).
        @keyword checkBeta: If `True`, the default beta updater URLs are
            checked if the main one. Beta software will be a later version than
            the official release. 
    """
    lastUpdate = app.getPref('updater.lastCheck', 0)
    interval = app.getPref('updater.interval', 3)
    currentVersion = app.getPref('updater.version', None)
    
    # Add version as GET parameter to the URL
#     url = url + "?version=%s" % ('.'.join(map(str,app.buildVersion)))
    
    # Helper function to create and post the event.
    def sendUpdateEvt(vers=None, date=None, cl=None, err=None, response=None,
                      downloadUrl=DOWNLOAD_URL):
        evt = EvtUpdateAvailable(newVersion=vers, changelog=cl, url=downloadUrl, 
                                 error=err, response=response, quiet=quiet)
        wx.PostEvent(app, evt)
    
    if force or currentVersion is None or isNewer(app.buildVersion, currentVersion):
        currentVersion = app.buildVersion

    if force or isTimeToCheck(lastUpdate, interval):
        logger.info("Checking %r for updates to version %r..." % (url, currentVersion,))
        responseCode, responseContent = getLatestVersion(url)
        if responseContent:
            newVersion = responseContent.get('version', VERSION)
            changelog = responseContent.get('changelog', CHANGELOG_URL)
            updateDate = responseContent.get('date', None)
            if downloadUrl is None:
                downloadUrl = responseContent.get('downloadUrl', DOWNLOAD_URL)
            if isNewer(newVersion, currentVersion):
                logger.info("Updater found new version %r" % (newVersion,))
                sendUpdateEvt(newVersion, updateDate, changelog, downloadUrl=downloadUrl)
            elif checkBeta:
                checkUpdates(app, force, quiet, BETA_UPDATER_URL,
                             BETA_DOWNLOAD_URL, checkBeta=False)
            else:
                logger.info("App is up to date.")
                sendUpdateEvt(False, updateDate)
        else:
            logger.warning("Update check failed (code %r)!" % (responseCode,))
            if not BETA or DEBUG:
                # updater failure suppressed in beta versions
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
  
if __name__ == '__main__':

    class FakeApp(wx.App):
        PREFS = {
                 }
        version = (0,1,10)
        versionString = '.'.join(map(str, version))
        buildVersion = version + (1234,)
        def getPref(self, v, default):
            return self.PREFS.get(v, default)
        def setPref(self, v, val):
            self.PREFS[v] = val
        def editPrefs(self, evt=None):
            print "edit prefs"

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

    evt = EvtUpdateAvailable(newVersion=vers, changelog=changeUrl, url=DOWNLOAD_URL)

#     dlg = UpdateDialog(None, -1, root=app, newVersion=vers, changelog=changeUrl)
    dlg = UpdateDialog(None, -1, updaterEvent=evt)
    dlg.ShowModal()
    dlg.Destroy()