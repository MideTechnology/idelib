'''
Created on Jul 1, 2014

@author: dstokes
'''
import cgi
from datetime import datetime
from glob import glob
import os.path
import sys

import wx
import wx.lib.sized_controls as SC
import wx.html
from wx.lib.wordwrap import wordwrap
wx = wx

#===============================================================================
# 
#===============================================================================

LICENSES = u"""<html><body>
<a name='top'><h1>Third-Party Licenses</h1></a>
%s
</body></html>"""

#===============================================================================
# 
#===============================================================================

class HtmlWindow(wx.html.HtmlWindow):
    """
    """
    def OnLinkClicked(self, linkinfo):
        """ Handle a link click. Relative links and file links open in the
            same window. All others launch the default app (browser, email,
            etc.)
        """
        href = linkinfo.GetHref()
        if href.startswith(('file:', '#')):
            super(HtmlWindow, self).OnLinkClicked(linkinfo)
        else:
            # Launch external web browser
            wx.LaunchDefaultBrowser(href)

#===============================================================================
# 
#===============================================================================

class AboutBox(SC.SizedDialog):
    """ Dialog showing the recorder info from a recording file. Self-contained;
        show the dialog via the `showRecorderInfo()` method.
    """
    TEMPLATE = os.path.join('ABOUT', 'about.html')
    TEMPFILE = os.path.join('ABOUT', 'about_tmp.html')

    def makeAboutFile(self):
        escapedStrings = self.strings.copy()
        for k in escapedStrings:
            escapedStrings[k] = cgi.escape(unicode(escapedStrings[k]))
        filename = os.path.join(self.rootDir, self.TEMPFILE)
        if True:#not os.path.exists(filename):
            with open(os.path.join(self.rootDir, self.TEMPLATE), 'rb') as f:
                with open(filename, 'wb') as out:
                    # A bit of gymnastics to convert the HTML to a formatting
                    # template. This is to leverage existing, standard HTML
                    # tools. Variable names are stored Django template style.
                    template = f.read().replace('%', '%%')
                    template = template.replace('{ ', '{').replace(' }', '}')
                    template = template.replace('{{','%(').replace('}}',')s')
                    out.write(template % escapedStrings)
        return filename
            

    def getLicenses(self):
        """ Retrieve and collate all license documents.
        """
        result = [None]
        links = ["<ul>"]
        files = glob(os.path.join(self.rootDir, 'LICENSES/*.txt'))
        for filename in files:
            name = os.path.splitext(os.path.basename(filename))[0]
            links.append('<li><a href="#%s">%s</a></li>' % (name, name))
            lic = u"<a name='%s'><h2>%s</h2></a>" % (name, name)
            with open(filename, 'rb') as f:
                text = f.read()
                longest = len(sorted(text.split('\n'), key=lambda x: len(x))[-1])
                if longest > 80:
                    text = wordwrap(text, 400, wx.ClientDC(self))
                lic = u"%s<pre>%s</pre>" % (lic, text)
            result.append(lic)
        links.append("</ul>")
        result[0] = ''.join(links)
        return LICENSES %  '<hr/>'.join(result)


    def __init__(self, *args, **kwargs):
        self.strings = kwargs.pop('strings', None)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        super(AboutBox, self).__init__(*args, **kwargs)
        
        self.rootDir = os.path.split(__file__)[0]
        self.strings['rootDir'] = os.path.join(self.rootDir, 'ABOUT')
        self.strings.setdefault('lastUpdateCheck', 'Never')
        
        # Add note if this is the 64 bit version. Only relevant in Windows. 
        if sys.platform.startswith("win") and "64 bit" in sys.version:
            self.strings['version'] += " (64 bit)"
        
        pane = self.GetContentsPane()
        notebook = wx.Notebook(pane, -1)#, style=wx.NB_BOTTOM)
        notebook.SetSizerProps(expand=True, proportion=-1)
        
        about = HtmlWindow(notebook, -1)
        notebook.AddPage(about, self.strings.get('appName'))
        about.LoadFile(self.makeAboutFile())
        
        licenses = HtmlWindow(notebook, -1)
        notebook.AddPage(licenses, "Licenses")
        licenses.SetPage(self.getLicenses())
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK))
        self.SetMinSize((640, 480))
        self.Fit()
        self.SetSize((700,500))
        self.Center()

    @classmethod
    def showDialog(cls, *args, **kwargs):
        appname = kwargs.setdefault('strings', {}).setdefault('appName', u"Slam\u2022Stick Lab")
        dlg = cls(*args, **kwargs)
        dlg.SetTitle(u"About %s" % appname)
        dlg.ShowModal()
        dlg.Destroy()

#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    import time
    from viewer import APPNAME
    app = wx.App()
    AboutBox.showDialog(None, strings={
           'appName': APPNAME, #"Slam Stick About Box",
           'version': "1.0", 
           'buildNumber': 999, 
           'buildTime': datetime.fromtimestamp(int(time.time())),
        })