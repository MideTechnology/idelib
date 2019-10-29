'''
"Splash Page" - Shown in a viewer before a file is opened. This should probably
get moved into `plots.py` later.

Created on Oct 28, 2019

@author: dstokes
'''

import wx
import wx.html as html

#===============================================================================
# 
#===============================================================================

class SplashPageContents(wx.Panel):
    """ The actual contents of the splash page, with graphics, quick links,
        etc.
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.root = kwargs.pop('root', None)
        kwargs.setdefault('style', wx.SIMPLE_BORDER)
        kwargs.setdefault('size', wx.Size(640,480))
        super(SplashPageContents, self).__init__(*args, **kwargs)
        
        
        self.SetBackgroundColour(wx.BLUE)


class HtmlSplash(html.HtmlWindow):
    """ Temporary contents for the splash page.
    """
    
    SPLASH_TEMP = """<html><body bgcolor="#%02x%02x%02x">
                     <center><FONT SIZE=+4><h1>enDAQ Lab</h1></font>
                     This is a stand-in splash page.
                     </body></html>"""
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        kwargs.setdefault('style', wx.NO_BORDER|wx.NO_FULL_REPAINT_ON_RESIZE)
        kwargs.setdefault('size', wx.Size(640,480))
        super(HtmlSplash, self).__init__(*args, **kwargs)
        
        if "gtk2" in wx.PlatformInfo or "gtk3" in wx.PlatformInfo:
            self.SetStandardFonts()

        bgcolor = (255,255,255) # self.Parent.GetBackgroundColour()[:3]
        self.SetPage(self.SPLASH_TEMP % (bgcolor))


class SplashPage(wx.Panel):
    """ The Lab 'splash page,' shown in the plot area when the app launches.
        The actual contents are shown in a smaller, centered box.
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.root = kwargs.pop('root', None)
        super(SplashPage, self).__init__(*args, **kwargs)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add((0,0), 1) # Top padding, to center contents
#         self.contents = SplashPageContents(self, root=self.root)
        self.contents = HtmlSplash(self, root=self.root)
        sizer.Add(self.contents, 0, wx.ALIGN_CENTER)
        sizer.Add((0,0), 1) # Bottom padding, to center contents

        self.SetSizer(sizer)
    
    
    def enableMenus(self, *args, **kwargs):
        return
    
    
    def setVisibleRange(self, *args, **kwargs):
        return
    
    
    def setTimeRange(self, *args, **kwargs):
        return
