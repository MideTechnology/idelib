'''
Created on Jul 1, 2014

@author: dstokes
'''
from datetime import datetime
from glob import glob
import os.path

import wx; wx = wx
import wx.lib.sized_controls as SC
import wx.html
from wx.lib.wordwrap import wordwrap


ABOUT = u"""<html><body><a name="top"/><center>
<b><font size=15> %(appName)s </font></b><br/>
Version %(version)s (build %(buildNumber)s), %(buildTime)s<br/>
<p>Copyright (c) 2014 <a href="http://www.mide.com/">Mid\xe9 Technology</a></p>
</center>
<p>
This is the about box. It is here that the software should be described in 
detail. There's a lot of room for whatever. Even images and <a href="#below">relative links</a>: this is a basic HTML
renderer (nothing fancy). Party like it's 1997!
</p><hr/>
<center><img src="%(rootDir)s/ssx.jpg"/><br/><a href="http://www.mide.com/products/slamstick/slam-stick-lab-software.php">Slam Stick Lab Home</a></center>
<a name="below">Kind of cool, yeah?</a><br/><a href="#top">Go to Top</a>
</html></body>""" 
 

class HtmlWindow(wx.html.HtmlWindow):
    """
    """
    def OnLinkClicked(self, linkinfo):
        """ Handle a link click. Relative links and file links open in the
            same window. All others launch the default app (browser, email,
            etc.)
        """
        href = linkinfo.GetHref()
        if href.startswith('file:') or href.startswith('#'):
            super(HtmlWindow, self).OnLinkClicked(linkinfo)
        else:
            # Launch external web browser
            wx.LaunchDefaultBrowser(href)


class AboutBox(SC.SizedDialog):
    """ Dialog showing the recorder info from a recording file. Self-contained;
        show the dialog via the `showRecorderInfo()` method.
    """

    def getAboutText(self):
        return ABOUT % self.strings
#         with open(os.path.join(self.rootDir, 'ABOUT/about.html'), 'rb') as f:
#             text = f.read() % self.strings
#         return text
    
    def getLicenses(self):
        """
        """
        result = []
        files = glob(os.path.join(self.rootDir, 'LICENSES/*.txt'))
        for filename in files:
            lic = u"<h2>%s</h2>" % os.path.splitext(os.path.basename(filename))[0]
            with open(filename, 'rb') as f:
                text = f.read()
                text = wordwrap(text, 450, wx.ClientDC(self))
                lic = u"%s<pre>%s</pre>" % (lic, text)
            result.append(lic)
        return u"<html><font size=-1>%s</font></html>" % '<hr/>'.join(result)


    def __init__(self, *args, **kwargs):
        self.strings = kwargs.pop('strings', None)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        super(AboutBox, self).__init__(*args, **kwargs)
        
        self.rootDir = os.path.split(__file__)[0]
        self.strings['rootDir'] = os.path.join(self.rootDir, 'ABOUT')
        
        pane = self.GetContentsPane()
        notebook = wx.Notebook(pane, -1)#, style=wx.NB_BOTTOM)
        notebook.SetSizerProps(expand=True, proportion=-1)
        
        about = HtmlWindow(notebook, -1)
        notebook.AddPage(about, "Slam Stick Lab")
        about.SetPage(self.getAboutText())
        
        licenses = HtmlWindow(notebook, -1)
        notebook.AddPage(licenses, "Licenses")
        licenses.SetPage(self.getLicenses())
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK))
        self.SetMinSize((640, 480))
        self.Fit()
        self.Center()
        print self.strings

    @classmethod
    def showDialog(cls, *args, **kwargs):
        appname = kwargs.get('strings', {}).get('appName', 'Slam Stick Lab')
        dlg = cls(*args, **kwargs)
        dlg.SetTitle(u"About %s" % appname)
        dlg.ShowModal()
        dlg.Destroy()

#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    app = wx.App()
    AboutBox.showDialog(None, strings={
           'appName': "App Name",
           'version': 1.0, 
           'buildNumber': 999, 
           'buildTime': datetime.now(),
        })