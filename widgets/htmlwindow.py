'''
Functions and widgets for HTML display.

Created on Sep 8, 2015

@author: dstokes
'''
from __future__ import absolute_import, print_function

import urllib

import wx #@UnusedImport
import wx.html
import wx.lib.sized_controls as SC

from logger import logger
from build_info import DEBUG

if DEBUG:
    import logging
    logger.setLevel(logging.INFO)


#===============================================================================
# 
#===============================================================================

def isSafeUrl(url, allowExternal=False):
    """ Simple function to determine if a URL is (moderately) safe, i.e. is
        to a Mide-owned site. 
    """
    if not url:
        return False
    
    prot, addr = urllib.splittype(url)
    if not (prot and addr):
        logger.warning("Bad URL: %r" % url)
        return False
    if not prot.lower().startswith(('http','ftp')):
        logger.warning("Rejected URL protocol: %r" % url)
        return False
    
    if allowExternal:
        return True

    host, _path = urllib.splithost(addr)
    safe = host.lower().endswith(('endaq.com',
                                  'mide.com',
                                  'mide.services', 
                                  'mide.technology',
                                  'midemarine.com',
                                  'piezo.com',
                                  'slamstick.com'))

    if not safe:
        logger.warning("Potentially unsafe URL detected: %r" % url)

    return DEBUG or safe


def hijackWarning(parent, url):
    """ Display a warning message if a URL doesn't point to a Mide server.
    """
    if url and len(url) > 40:
        url = urllib.splitquery(url)[0]
    d = wx.MessageBox(
        u"The link's URL does not appear to direct to a Mid\xe9 website.\n\n"
        u"This is likely intentional, but it could be an indication that the "
        u"update server has been compromised.\n\nURL: %s\n\n"
        u"Open the link anyway?" % url, "Possible Link Hijack", parent=parent,
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
    def __init__(self, *args, **kwargs):
        self.tracking = kwargs.pop('tracking', '')
        self.allowExternalLinks = kwargs.pop('allowExternalLinks', False)
        super(SaferHtmlWindow, self).__init__(*args, **kwargs)

    
    def OnLinkClicked(self, linkinfo):
        """ Handle a link click. Does not permit outgoing links (for security).
        """
        href = linkinfo.GetHref()
        if href.startswith(('file:', '#')):
            super(SaferHtmlWindow, self).OnLinkClicked(linkinfo)
            return
        
        if not isSafeUrl(href, self.allowExternalLinks):
            if not hijackWarning(self, href):
                return

        if 'mide.com' in href:
            href += self.tracking
            
        # Launch external web browser
        logger.info('HTML window opened %s' % href)
        wx.LaunchDefaultBrowser(href)


#===============================================================================
# 
#===============================================================================

class HtmlDialog(SC.SizedDialog):
    """
    """
    
    DEFAULT_SIZE = (620,460)
    DEFAULT_STYLE = (wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | \
                     wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX | \
                     wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
    DEFAULT_BUTTONS = wx.OK

    def __init__(self, parent, content, title, buttons=DEFAULT_BUTTONS,
                 size=DEFAULT_SIZE, pos=wx.DefaultPosition, style=DEFAULT_STYLE, 
                 wxid=-1, setBgColor=True, plaintext=False):
        """
        """
        if style & 0b1111:
            buttons = style & 0b1111
        style = style & (2**32-1 ^ 0b111)
        
        super(HtmlDialog, self).__init__(parent, wxid, title, style=style)

        if plaintext:
            content = u'<pre>%s</pre>' % content

        if setBgColor:
            bg = "#%02x%02x%02x" % self.GetBackgroundColour()[:3]
            content = u'<body bgcolor="%s">%s</body>' % (bg, content)
        
        pane = self.GetContentsPane()
        html = SaferHtmlWindow(pane, -1, style=wx.BORDER_THEME)
        html.SetSizerProps(expand=True, proportion=1)
        html.SetPage(content)
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(buttons))

        self.Bind(wx.EVT_BUTTON, self.OnButton)

        self.Fit()
        self.SetSize(size)


    def OnButton(self, evt):
        self.EndModal(evt.GetEventObject().GetId())


#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    responses = {getattr(wx, x): x for x in ('ID_OK','ID_CANCEL','ID_YES','ID_NO')}
    app = wx.App()
    dlg = HtmlDialog(None, 
                     "<h1>Test</h1><p>This is the body.</p>", 
                     "Test Title", 
#                     style=wx.DEFAULT_DIALOG_STYLE|wx.YES_NO,
#                     buttons=wx.YES_NO|wx.CANCEL, 
                     setBgColor=False)
    r = dlg.ShowModal()
    print("Returned %r (%s)" % (r, responses.get(r, 'Unknown')))
    dlg.Destroy()
    