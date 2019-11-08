'''
Created on Jul 1, 2014

@author: dstokes
'''
from __future__ import absolute_import, print_function

import cgi
from datetime import datetime
from glob import glob
import os.path
import platform

import wx
import wx.lib.sized_controls as SC
from wx.lib.wordwrap import wordwrap
from wx.html import HtmlWindow

from build_info import APPNAME, BUILD_NUMBER, VERSION, BUILD_TIME
from widgets.htmlwindow import SaferHtmlWindow

#===============================================================================
# 
#===============================================================================

# "Licenses" tab template
LICENSES = u"""<html><body>
<a name='top'><h1>Third-Party Licenses</h1></a>
%s
</body></html>"""

# Extra tracking info to add to Mide URLs
TRACKING = "?utm_source=Slam-Stick-X-Data-Logger&utm_medium=Device&utm_content=Link-to-Slam-Stick-X-web-page-from-Device-About-Us&utm_campaign=Slam-Stick-X"

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

    DEFAULTS = {'appName': APPNAME, #"Slam Stick About Box",
                'version': '.'.join(map(str,VERSION)), 
                'buildNumber': BUILD_NUMBER, 
                'buildTime': datetime.fromtimestamp(BUILD_TIME),
                'copyright': datetime.fromtimestamp(BUILD_TIME).year,
                'lastUpdateCheck': 'Never'}


    def makeAboutFile(self):
        """ Fill out the main About Box page with current info. 
        """
        escapedStrings = {k: cgi.escape(unicode(v)) for k,v in self.strings.items()}

        with open(os.path.join(self.rootDir, self.TEMPLATE), 'rb') as f:
            template = f.read()
            
        with open(os.path.join(self.rootDir, self.TEMPFILE), 'wb') as out:
            out.write(template.format(**escapedStrings))
            return out.name
            

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
        files.extend(glob(os.path.join(self.rootDir, 'LICENSES/*.html')))
        files.sort()
        for filename in files:
            name = os.path.splitext(os.path.basename(filename))[0]
            links.append('<li><a href="#%s">%s</a></li>' % (name, name))
            lic = u"<a name='%s'><h2>%s</h2></a>" % (name, name)
            with open(filename, 'rb') as f:
                text = f.read()
                if filename.lower().endswith('.txt'):
                    longest = max([len(x) for x in text.split('\n')])
                    if longest > 80:
                        text = wordwrap(text, 500, wx.ClientDC(self))
                    lic = u"%s<pre>%s</pre>" % (lic, text)
                else:
                    lic = u"%s%s" % (lic, text)
            result.append(lic)
        links.append(u"</ul>")
        result[0] = ''.join(links)

        # Restore the old font, just in case:        
        self.SetFont(oldFont)
        return LICENSES %  u'<hr/>'.join(result)


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
        """ Constructor. Standard `wx.lib.sized_controls.SizedDialog` 
            arguments, plus:
        
            @keyword strings: A dictionary of strings to insert into the
                About HTML.
            @keyword tracking: A URL query string to append to Mide links
                for tracking.
        """
        self.strings = kwargs.pop('strings', {})
        tracking = kwargs.pop('tracking', TRACKING)
        
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        kwargs.setdefault("size", (640, 480))
        
        super(AboutBox, self).__init__(*args, **kwargs)
        
        self.rootDir = os.path.split(__file__)[0]
        self.strings['rootDir'] = os.path.join(self.rootDir, 'ABOUT')
        
        # Add note if this is the 64 bit version. Only relevant in Windows.
        bits, ops = platform.architecture()
        if ops.lower().startswith("win"):
            self.strings['version'] += " (%s)" % bits
        
        pane = self.GetContentsPane()
        notebook = wx.Notebook(pane, -1)#, style=wx.NB_BOTTOM)
        notebook.SetSizerProps(expand=True, proportion=-1)
        
        about = SaferHtmlWindow(notebook, -1, tracking=tracking)
        notebook.AddPage(about, self.strings.get('appName'))
        about.LoadFile(self.makeAboutFile())
        
        releaseNotes = os.path.join(self.rootDir, self.RELEASE_NOTES)
        if os.path.exists(releaseNotes):
            notes = HtmlWindow(notebook, -1)
            notebook.AddPage(notes, "Release Notes")
            notes.LoadPage(releaseNotes)
        
        licenses = SaferHtmlWindow(notebook, -1, allowExternalLinks=True)
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
        """ Display the About Box.
        
            @see: `AboutBox.__init__()`

            @keyword strings: A dictionary of strings to insert into the
                About HTML.
            @keyword tracking: A URL query string to append to Mide links
                for tracking.
        """
        stringsArg = kwargs.get('strings', {})
        strings = cls.DEFAULTS.copy()
        strings.update(stringsArg)
        kwargs['strings'] = strings
        
        dlg = cls(*args, **kwargs)
        dlg.SetTitle(u"About %s" % strings['appName'])
        dlg.ShowModal()
        dlg.Destroy()

#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    # Test the About Box
    app = wx.App()
    AboutBox.showDialog(None,
                         strings={
#            'appName': APPNAME, #"Slam Stick About Box",
#            'version': '.'.join(map(str,VERSION)), 
#            'buildNumber': BUILD_NUMBER, 
#            'buildTime': datetime.fromtimestamp(BUILD_TIME),
#            'copyright': datetime.fromtimestamp(BUILD_TIME).year
        })