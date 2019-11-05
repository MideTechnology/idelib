'''
Interactive Python interpreter for debugging purposes.

@author: dstokes

@todo: Refactor. This is a copy of the old debugging console as a stand-in.
'''
from __future__ import absolute_import, print_function

import wx.py

import build_info
import images
import mide_ebml

#===============================================================================
# 
#===============================================================================

class PythonConsole(wx.py.shell.ShellFrame):
    """ An interactive Python console for debugging purposes.
    """
    HELP_TEXT = '\n'.join(
        ("* Useful global variables and helper functions:",
         "\tapp               The currently running app.",
         "\tapp.lastException The last unexpected exception handled.",
         "\tviewer            The active viewer window when the console was opened.",
         "\tviewer.dataset    The active imported recording file.",
         "\tviewer.getTab()   Retrieve the foreground tab.",
         ""))

    def __init__(self, parent=None, id=-1, title=None, introText=None, 
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.DEFAULT_FRAME_STYLE, locals=None, InterpClass=None,
                 config=None, dataDir=None, focus=True, *args, **kwds):

        if title is None:
            version = '.'.join(map(str, build_info.VERSION))
            title = "%s %s (build %d) Scripting Console" % \
                (build_info.APPNAME, version, build_info.BUILD_NUMBER)
            
        wx.py.frame.Frame.__init__(self, parent, id, title, pos, size, style)
        wx.py.frame.ShellFrameMixin.__init__(self, config, dataDir)

        self.SetIcon(images.icon.GetIcon())
        
        if size == wx.DefaultSize:
            self.SetSize((750, 525))

        if introText is None:
            introText = "%s\n\n%s" % (title, self.HELP_TEXT) 
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

        if focus:
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
        """Display a Help window.
        """
        # XXX: REWRITE CONSOLE HELP!
        import  wx.lib.dialogs
        title = 'Console Help'
        
        text = ["The Debugging Console provides access to the underlying Python environment.", 
                "Proceed with caution: misuse of the Console may cause %s to crash!\n" % build_info.APPNAME, 
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
    def openConsole(cls, parent, *args, **kwargs):
        """ Show the Scripting Console.
        """
        app = wx.GetApp()
        localVars = kwargs.setdefault('locals', {})
        localVars.update({'app': app,
                          'build_info': build_info,
                          'mide_ebml': mide_ebml,
                          'viewer': parent
                          })
        con = cls(parent, **kwargs)
        
        try:
            parent.childViews[con.GetId()] = con
        except AttributeError:
            pass

        con.Show(True)
        return con


#===============================================================================
# 
#===============================================================================

# XXX: REMOVE THIS LATER. Makes running this module run the 'main' viewer.
if __name__ == "__main__":
    import viewer
    app = viewer.ViewerApp(loadLastFile=True)
    PythonConsole.openConsole()
    app.MainLoop()