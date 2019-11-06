'''
"Splash Page" - Shown in a viewer before a file is opened. This should probably
get moved into `plots.py` later.

Created on Oct 28, 2019

@author: dstokes
'''

import os

import wx
# import wx.html as html

#===============================================================================
# 
#===============================================================================

class SplashPageContents(wx.Panel):
    """ The actual contents of the splash page, with graphics, quick links,
        etc.
    """
    BITMAP = os.path.realpath(os.path.join(os.path.dirname(__file__), 'ABOUT', 'splash.png'))
    
    def __init__(self, *args, **kwargs):
        """
        """
        print (self.BITMAP)
        self.root = kwargs.pop('root', None)
        kwargs.setdefault('style', wx.NO_BORDER)
        kwargs.setdefault('size', wx.Size(640,480))
        super(SplashPageContents, self).__init__(*args, **kwargs)
        
        self.SetBackgroundColour(self.Parent.GetBackgroundColour())
        
        self.bmp = wx.Image(self.BITMAP, wx.BITMAP_TYPE_PNG).ConvertToBitmap()
        self.bgbrush = wx.Brush(self.GetBackgroundColour())
        
        self.openBtn = wx.Button(self, -1, "Open a Recording",
                                   pos=(200,400), size=(240,-1))
        self.configBtn = wx.Button(self, -1, "Configure a Recording Device",
                                   pos=(200,432), size=(240,-1))

#         openIcon = wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_CMN_DIALOG, (16,16))
#         self.openBtn.SetBitmap(openIcon)
#         configIcon = wx.ArtProvider.GetBitmap(wx.ART_EXECUTABLE_FILE, wx.ART_CMN_DIALOG, (16,16))
#         self.configBtn.SetBitmap(configIcon)

        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.openBtn.Bind(wx.EVT_BUTTON, self.root.OnFileOpenMenu)
        self.configBtn.Bind(wx.EVT_BUTTON, self.root.OnDeviceConfigMenu)


    def OnEraseBackground(self, evt):
        """
        """
        dc = evt.GetDC()
        
        if not dc:
            dc = wx.ClientDC(self)
            rect = self.GetUpdateRegion().GetBox()
            dc.SetClippingRect(rect)
        
        dc.SetBackground(self.bgbrush)
        dc.Clear()
        dc.DrawBitmap(self.bmp, 0, 0, useMask=True)
        
        

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
        self.contents = SplashPageContents(self, root=self.root)
#         self.contents = HtmlSplash(self, root=self.root)
        sizer.Add(self.contents, 0, wx.ALIGN_CENTER)
        sizer.Add((0,0), 1) # Bottom padding, to center contents

        self.SetSizer(sizer)
    
    
    def enableMenus(self, *args, **kwargs):
        return
    
    
    def setVisibleRange(self, *args, **kwargs):
        return
    
    
    def setTimeRange(self, *args, **kwargs):
        return
