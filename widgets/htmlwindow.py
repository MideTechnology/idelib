'''
A somewhat safer subclass of HTML display, filtering potentially harmful URLs.

Created on Sep 8, 2015

@author: dstokes
'''

import urllib

import wx #@UnusedImport
import wx.html

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

