'''
Functions and widgets for HTML display.

Created on Sep 8, 2015

@author: dstokes
'''

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
        at mide.com. 
    """
    if not url:
        return False
    
    if DEBUG:
        return True
    
    prot, addr = urllib.splittype(url)
    if not (prot and addr):
        return False
    if not prot.lower().startswith(('http','ftp')):
        return False
    host, _path = urllib.splithost(addr)
    return allowExternal or host.lower().endswith('mide.com')


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
    allowExternalLinks = False
        
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
            
        # Launch external web browser
        logger.info('Updater HTML window opened %s' % href)
        wx.LaunchDefaultBrowser(href)


#===============================================================================
# 
#===============================================================================

class HtmlDialog(SC.SizedDialog):
    """ A simple dialog box containing HTML content. Intended to be a
        replacement for the standard wxPython scrolled message dialog (for
        certain purposes, anyway).
    """
    
    DEFAULT_SIZE = (400,200)
    DEFAULT_STYLE = (wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | \
                     wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX | \
                     wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
    DEFAULT_BUTTONS = wx.OK

    def __init__(self, parent, content, title, buttons=DEFAULT_BUTTONS,
                 size=DEFAULT_SIZE, pos=wx.DefaultPosition, style=DEFAULT_STYLE, 
                 ID=-1, setBgColor=True):
        """
        """
        if style & 0b1111:
            buttons = style & 0b1111
        style = style & (2**32-1 ^ 0b111)
        
        super(HtmlDialog, self).__init__(parent, ID, title, style=style)

        if setBgColor:
            bg = "#%02x%02x%02x" % self.GetBackgroundColour()[:3]
            content = '<body bgcolor="%s">%s</body>' % (bg, content)
        
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
    print "Returned %r (%s)" % (r, responses.get(r, 'Unknown'))
    dlg.Destroy()
    