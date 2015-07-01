'''
Interactive Python interpreter for debugging purposes.

Created on Jul 1, 2015

@author: dstokes
'''

import wx.py

import build_info
import images
import mide_ebml

#===============================================================================
# 
#===============================================================================

class DebugConsole(wx.py.shell.ShellFrame):
    """ An interactive Python console for debugging purposes.
    """
    HELP_TEXT = '\n'.join(
        ("* Useful global variables and helper functions:",
         "app               The currently running app.",
         "app.lastException The last unexpected exception handled.",
         "viewer            The active viewer window when the console was opened.",
         "viewer.dataset    The active imported recording file.",
         "viewer.getTab()   Retrieve the foreground tab.",
         ""))

    def __init__(self, parent=None, id=-1, title=None, introText=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.DEFAULT_FRAME_STYLE, locals=None, InterpClass=None,
                 config=None, dataDir=None, *args, **kwds):

        if title is None:
            version = '.'.join(map(str, build_info.VERSION))
            title = "Slam Stick Lab version %s (build %d) Debugging Console" % \
                (version, build_info.BUILD_NUMBER)
            
        wx.py.frame.Frame.__init__(self, parent, id, title, pos, size, style)
        wx.py.frame.ShellFrameMixin.__init__(self, config, dataDir)

        self.SetIcon(images.icon.GetIcon())
        
        if size == wx.DefaultSize:
            self.SetSize((750, 525))

        if introText is None:
            introText = "%s - Use at your own risk!\n\n%s" % (title, self.HELP_TEXT) 
        self.startupScript="print 'hello'"
        self.SetStatusText(title)
        self.shell = wx.py.shell.Shell(parent=self, id=-1, 
                                       introText=introText,
                                       locals=locals, InterpClass=InterpClass,
                                       startupScript=self.startupScript,
                                       execStartupScript=self.execStartupScript,
                                       *args, **kwds)

        # Override the shell so that status messages go to the status bar.
        self.shell.setStatusText = self.SetStatusText

        self.shell.SetFocus()
        self.LoadSettings()
    
    #===========================================================================
    # 
    #===========================================================================
    
    def OnAbout(self, evt):
        try:
            self.Parent.OnHelpAboutMenu(evt)
        except AttributeError:
            pass
    
    def OnHelp(self, event):
        """Display a Help window."""
        import  wx.lib.dialogs
        title = 'Console Help'
        
        text = ["The Debugging Console provides access to the underlying Python environment.", 
                "Proceed with caution: misuse of the Console may cause Slam Stick Lab to crash!\n", 
                self.HELP_TEXT, 
                wx.py.shell.HELP_TEXT]
        text = '\n'.join(text)

        dlg = wx.lib.dialogs.ScrolledMessageDialog(self, text, title,
                                                   size = ((700, 600)))
        fnt = wx.Font(10, wx.TELETYPE, wx.NORMAL, wx.NORMAL)
        dlg.GetChildren()[0].SetFont(fnt)
        dlg.GetChildren()[0].SetInsertionPoint(0)
        dlg.ShowModal()
        dlg.Destroy()
        
    #===========================================================================
    # 
    #===========================================================================
    
    @classmethod
    def openConsole(cls, *args, **kwargs):
        """ Show the Debugging Console.
        """
        app = wx.GetApp()
        viewer = wx.GetActiveWindow()
        localVars = kwargs.setdefault('locals', {})
        localVars.update({'app': app,
                          'build_info': build_info,
                          'mide_ebml': mide_ebml,
                          'viewer': viewer})
        con = cls(viewer, **kwargs)
        viewer.childViews[con.GetId()] = con
        con.Show(True)
        return con


#===============================================================================
# 
#===============================================================================

# XXX: REMOVE THIS LATER. Makes running this module run the 'main' viewer.
if __name__ == "__main__":
    import viewer
    app = viewer.ViewerApp(loadLastFile=True)
    DebugConsole.openConsole()
    app.MainLoop()