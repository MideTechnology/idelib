'''
"Splash Page" - Shown in a viewer before a file is opened. This should probably
get moved into `plots.py` later.

Created on Oct 28, 2019

@author: dstokes
'''
from __future__ import absolute_import, print_function

import os
import wx

from build_info import DEBUG, BETA

#===============================================================================
# 
#===============================================================================

class SplashPageContents(wx.Panel):
    """ The actual contents of the splash page, with graphics, quick links,
        etc. Drawn in the center of the parent viewer window's plot area.
    """
    
    BGIMAGE = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                            'ABOUT', 'splash.jpg'))
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` methods, plus:
        
            @keyword root: The parent viewer window. 
        """
        image = wx.Image(self.BGIMAGE, wx.BITMAP_TYPE_ANY)

        self.root = kwargs.pop('root', None)
        self.showWarning = kwargs.pop('warning', True)
        kwargs.setdefault('style', wx.NO_BORDER)
        kwargs.setdefault('size', image.GetSize())
        super(SplashPageContents, self).__init__(*args, **kwargs)
        
        # For background image, drawn in `OnEraseBackground()`: the bitmap,
        # and the 'brush' for making the background match the window.
        bgcolor = self.Parent.GetBackgroundColour()
        self.bmp = image.ConvertToBitmap()
        self.bgbrush = wx.Brush(bgcolor)
        self.SetBackgroundColour(bgcolor)
        
        # The recent files popup menu, generated once.
        self.recentFilesMenu = None

        # Getting size in `OnEraseBackground()` has issues when resizing,
        # so get it now.
        self.fullsize = self.GetSize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        
        openBtn = wx.Button(self, -1, "Open a Recording", size=(240,-1))
        confBtn = wx.Button(self, -1, "Configure a Recording Device",
                            size=(240,-1))
        resBtn = wx.Button(self, -1, "enDAQ Recorder Resources", size=(240,-1))
        
        openBtn.SetToolTip("Import a recording file (IDE, DAT)")
        confBtn.SetToolTip("Configure an enDAQ or Slam Stick data recorder")
        resBtn.SetToolTip("Visit enDAQ support (opens in browser)")
        
#         bcolor = wx.Colour(230,112,37)
#         for b in (openBtn, confBtn, resBtn):
#             b.SetBackgroundColour(bcolor)
#             b.SetForegroundColour(wx.WHITE)
#             b.Set(bcolor)
        
        sizer.Add((0,0), 1)
        sizer.Add(openBtn, 0, wx.ALIGN_BOTTOM|wx.ALIGN_CENTER, 8)
        sizer.AddSpacer(8)
        sizer.Add(confBtn, 0, wx.ALIGN_BOTTOM|wx.ALIGN_CENTER, 8)
        sizer.AddSpacer(24)
        sizer.Add(resBtn, 0, wx.ALIGN_BOTTOM|wx.ALIGN_CENTER, 8)
        sizer.AddSpacer(80)

        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        openBtn.Bind(wx.EVT_BUTTON, self.root.OnFileOpenMenu)
        confBtn.Bind(wx.EVT_BUTTON, self.root.OnDeviceConfigMenu)
        openBtn.Bind(wx.EVT_RIGHT_DOWN, self.OnFileRightClick)
        resBtn.Bind(wx.EVT_BUTTON, self.root.OnHelpResources)

        # Remove focus from buttons. Primarily cosmetic.
        self.SetFocus()


    def OnEraseBackground(self, evt):
        """ Draw the background image.
        """
        dc = evt.GetDC()
        
        if not dc:
            dc = wx.ClientDC(self)
            rect = self.GetUpdateRegion().GetBox()
            dc.SetClippingRect(rect)
        
        dc.SetBackground(self.bgbrush)
        dc.Clear()
        dc.DrawBitmap(self.bmp, 0, 0, useMask=True)
        
        # NOTE: Some of these numbers may need tweaking if image size changes.
        if self.showWarning and self.root and self.root.app:
            vers = "Version %s" % self.root.app.versionString
            dc.SetTextForeground(wx.WHITE)
            dc.SetFont(self.GetFont())
            tsize = dc.GetTextExtent(vers)
            p = self.fullsize - tsize - (8,4)
            dc.DrawText(vers, *p)

            if DEBUG or BETA:
                msg = "PRE-RELEASE VERSION: USE WITH CAUTION!"
                dc.SetFont(self.GetFont().Bold().Scaled(2))
                pos = wx.Point(*((self.fullsize - dc.GetTextExtent(msg))/2))
                dc.SetTextForeground(wx.RED)
                dc.DrawText(msg, pos[0],8)
                    
    
    def OnFileRightClick(self, evt):
        """
        """
        filenames = self.root.app.prefs.getRecentFiles()
        if not filenames:
            return
        
        if self.recentFilesMenu is None:
            self.recentFilesMenu = wx.Menu()
            mi = self.recentFilesMenu.Append(-1, 'Recent Files:', '')
            mi.Enable(False)
        
            for i, f in enumerate(filenames):
                self.recentFilesMenu.Append(i+wx.ID_FILE1, f, '')
            
        self.PopupMenu(self.recentFilesMenu)


#===============================================================================
# 
#===============================================================================

class SplashPage(wx.Panel):
    """ The Lab 'splash page,' shown in the plot area when the app launches.
        The actual contents are shown in a smaller, centered box.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` methods, plus:
        
            @keyword root: The parent viewer window. 
        """
        self.root = kwargs.pop('root', None)
        showWarning = kwargs.pop('warning', True)
        kwargs.setdefault('style', wx.CLIP_CHILDREN)
        super(SplashPage, self).__init__(*args, **kwargs)

#         self.SetBackgroundColour(wx.Colour(2,24,38))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add((0,0), 1) # Top padding, to center contents
        contents = SplashPageContents(self, root=self.root, warning=showWarning)
        sizer.Add(contents, 0, wx.ALIGN_CENTER)
        sizer.Add((0,0), 1) # Bottom padding, to center contents

        self.SetSizer(sizer)
    
    
    def enableMenus(self, *args, **kwargs):
        # For compatibility with `Plot`, the usual contents.
        return
    
    
    def setVisibleRange(self, *args, **kwargs):
        # For compatibility with `Plot`, the usual contents.
        return
    
    
    def setTimeRange(self, *args, **kwargs):
        # For compatibility with `Plot`, the usual contents.
        return


    def loadPrefs(self, *args, **kwargs):
        # For compatibility with `Plot`, the usual contents.
        return
    