'''
Created on Jul 1, 2014

@author: dstokes
'''
import cgi
from datetime import datetime
from glob import glob
import os.path
import sys

# import wx
import wx.lib.sized_controls as SC
import wx.html
from wx.lib.wordwrap import wordwrap
from wx.html import HtmlWindow
wx = wx

#===============================================================================
# 
#===============================================================================

LICENSES = u"""<html><body>
<a name='top'><h1>Third-Party Licenses</h1></a>
%s
</body></html>"""


TRACKING = "?utm_source=Slam-Stick-X-Data-Logger&utm_medium=Device&utm_content=Link-to-Slam-Stick-X-web-page-from-Device-About-Us&utm_campaign=Slam-Stick-X"


#===============================================================================
# 
#===============================================================================

class HtmlWindow(wx.html.HtmlWindow):
    """
    """
    
    def __init__(self, *args, **kwargs):
        self.tracking = kwargs.pop('tracking', '')
        super(HtmlWindow, self).__init__(*args, **kwargs)
    
    
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
            if 'mide.com' in href:
                href += self.tracking
                
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
    RELEASE_NOTES = os.path.join('ABOUT', "slam_stick_lab_changelog.html")

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
        # For the wx.lib.wordwrap to wrap the monospaced text correctly:
        oldFont = self.GetFont()
        font = self.GetFont()
        font.SetFamily(wx.FONTFAMILY_TELETYPE)
        self.SetFont(font)
        
        result = [None]
        links = ["<ul>"]
        files = glob(os.path.join(self.rootDir, 'LICENSES/*.txt'))
        for filename in files:
            name = os.path.splitext(os.path.basename(filename))[0]
            links.append('<li><a href="#%s">%s</a></li>' % (name, name))
            lic = u"<a name='%s'><h2>%s</h2></a>" % (name, name)
            with open(filename, 'rb') as f:
                text = f.read()
                longest = max([len(x) for x in text.split('\n')])
                if longest > 80:
                    text = wordwrap(text, 500, wx.ClientDC(self))
                lic = u"%s<pre>%s</pre>" % (lic, text)
            result.append(lic)
        links.append("</ul>")
        result[0] = ''.join(links)

        # Restore the old font, just in case:        
        self.SetFont(oldFont)
        return LICENSES %  '<hr/>'.join(result)


    def getPlugins(self):
        """ Retrieve info from all plug-ins that have info.
        """
        try:
            app = wx.GetApp()
            plugins = app.plugins.values()
        except AttributeError:
            return
        
        result = []
        plugins.sort(key=lambda x: x.name)
        for p in plugins:
            plug = []
            info = p.info.copy()
            if 'author' not in info or 'copyright' not in info:
                continue
            url = info.pop('url', None)
            cr = info.get('copyright', None)
            desc = info.pop('description', None)
            vers = info.pop('version', '')
            info['file location'] = p.path
            
            plug.append('<h3>%s %s</h3>' % (p.name, vers))
            if cr is not None:
                if url is not None:
                    info['copyright'] = u'%s [<a href="%s">Link</a>]' % (cr, url)
                
            plug.append(u"<table width='100%'>")
            for k,v in sorted(info.items()):
                if k.startswith('_'):
                    continue
                if k in ('name','type','module','minVersion','maxVersion'):
                    continue
                plug.append(u'<tr><td width="20%%"><i>%s</i></td><td>%s</td></tr>' % (k.title(),v))
            plug.append('</table>')
            
            if desc is not None:
                plug.append(u"<blockquote>%s</blockquote>" % desc)
                
            result.append(u' '.join(plug))
        if len(result) == 0:
            return
        return u'<html>%s</html>' % u"<hr/>".join(result)


    def __init__(self, *args, **kwargs):
        self.strings = kwargs.pop('strings', None)
        tracking = kwargs.pop('tracking', TRACKING)
        
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        kwargs.setdefault("size", (640, 480))
        
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
        
        about = HtmlWindow(notebook, -1, tracking=tracking)
        notebook.AddPage(about, self.strings.get('appName'))
        about.LoadFile(self.makeAboutFile())
        
        if os.path.exists(self.RELEASE_NOTES):
            notes = HtmlWindow(notebook, -1)
            notebook.AddPage(notes, "Release Notes")
            notes.LoadPage(self.RELEASE_NOTES)
        
        licenses = HtmlWindow(notebook, -1)
        notebook.AddPage(licenses, "Licenses")
        licenses.SetPage(self.getLicenses())
        
        pluginInfo = self.getPlugins()
        if pluginInfo:
            plugins = HtmlWindow(notebook, -1)
            notebook.AddPage(plugins, "Plug-Ins")
            plugins.SetPage(pluginInfo)
        
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
    from viewer import APPNAME
    from build_info import VERSION, BUILD_TIME, BUILD_NUMBER
    app = wx.App()
    AboutBox.showDialog(None, strings={
           'appName': APPNAME, #"Slam Stick About Box",
           'version': '.'.join(map(str,VERSION)), 
           'buildNumber': BUILD_NUMBER, 
           'buildTime': datetime.fromtimestamp(BUILD_TIME),
        })