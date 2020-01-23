'''
Interactive Python interpreter for debugging purposes.

@author: dstokes

@todo: Refactor. This is a copy of the old debugging console as a stand-in.
'''
from __future__ import absolute_import, print_function

import os
import sys

import wx.adv
import  wx.lib.dialogs
import wx.py

import build_info
import images
import mide_ebml

#===============================================================================
# 
#===============================================================================

class PythonConsole(wx.py.shell.ShellFrame):
    """ An interactive Python console for scripting and debugging purposes.
    """
    TITLE = "Scripting Console"
    
    ORIG_PATHS = sys.path[:]
    
    HELP_TEXT = '\n'.join(
        ("* Useful global variables and helper functions:",
         "\tapp               The currently running app.",
         "\tviewer            The active viewer window when the console was opened.",
         "\tviewer.dataset    The active imported recording file.",
         "\tviewer.getTab()   Retrieve the foreground tab.",
         ""))

    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.py.shell.ShellFrame` arguments,
            plus:
        
            @keyword focus: If `True`, the new window will have focus. 
            @keyword introText: Introductory text, shown when the shell starts.
            @keyword statusText: Initial text for the status bar.
            @keyword locals: A dictionary of local variables (like `exec` uses)
            @keyword startupScript: A script to run at start (Python in string)
            @keyword execStartupScript: 
            @keyword dataDir: 
        """
        title = kwargs.setdefault('title', self.TITLE)
        config = kwargs.pop('config', None)
        dataDir = kwargs.pop('dataDir', None)
        introText = kwargs.pop('introText', "%s\n\n%s" % (title, self.HELP_TEXT))
        statusText = kwargs.pop('statusText', None)
        self.startupScript = kwargs.pop('startupScript', None)
        self.execStartupScript = kwargs.pop('execStartupScript', True)
        localvars = kwargs.pop('locals', None)
        interpClass = kwargs.pop('InterpClass', None)
        focus = kwargs.pop('focus', True)
    
        kwargs.setdefault('size', (750, 525))

        # The 'prefix' for the window title. The rest gets set by its Viewer.
        self.baseTitle = title
        
        # The `Viewer` window is (or should be) in the local variables.
        self.viewer = localvars.get('viewer', None)
        
        wx.py.frame.Frame.__init__(self, *args, **kwargs)
        wx.py.frame.ShellFrameMixin.__init__(self, config, dataDir)

        self.SetIcon(images.icon.GetIcon())
            
        self.shell = wx.py.shell.Shell(self,
                                       introText=introText,
                                       locals=localvars,
                                       startupScript=self.startupScript,
                                       execStartupScript=self.execStartupScript,
                                       InterpClass=interpClass
                                       )

        self.SetStatusText(statusText or '')
        
        self.addMenuItems()
        self.parentUpdated()

        # Override the shell so that status messages go to the status bar.
        self.shell.setStatusText = self.SetStatusText

        if focus:
            self.shell.SetFocus()
        self.LoadSettings()

        self.Bind(wx.EVT_CLOSE, self.OnClose)
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    def addMenuItems(self):
        """ Do some post-initialization modifications to the menus. To work
            around wx.py.shell.ShellFrame obfuscation.
        """
        menubar = self.GetMenuBar()
        fileMenu = menubar.GetMenu(0)
        numItems = fileMenu.GetMenuItemCount()
        idx = numItems - 2
        mi = wx.MenuItem(fileMenu, wx.ID_ANY, 
                     "Reset Interpreter\tCtrl+Shift+R",
                     "Restart the interpreter, clearing local variables, etc.",
                     wx.ITEM_NORMAL)
        fileMenu.InsertSeparator(idx)
        fileMenu.Insert(idx+1, mi)
        
        self.Bind(wx.EVT_MENU, self.reset, id=mi.GetId())
        
        viewMenu = menubar.GetMenu(2)
        viewMenu.AppendSeparator()
        mi = viewMenu.Append(wx.ID_ANY,
                             "Show console's associated view\tCtrl+Space",
                             "",
                             wx.ITEM_NORMAL)
        
        self.Bind(wx.EVT_MENU, self.OnShowView, id=mi.GetId())
    
        optMenu = menubar.GetMenu(3)
        for _i in range(3):
            optMenu.Remove(optMenu.GetMenuItems()[-1])
        mi = optMenu.Append(wx.ID_ANY,
                            "Edit Module Import Paths (PYTHONPATH)",
                            "",
                            wx.ITEM_NORMAL)
        self.Bind(wx.EVT_MENU, self.OnEditPaths, id=mi.GetId())
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    def parentUpdated(self):
        """ Method called when the parent `Viewer` changes in such a way that
            the editor needs updating (e.g. a file was imported).
        """
        title = self.baseTitle
        
        if self.viewer:
            name = self.viewer.app.getWindowTitle(self.viewer, showApp=False)
            if name:
                title = "%s: %s" % (self.baseTitle, name)
        
        self.SetTitle(title)

    
    def reset(self, *args):
        """ Reset the console: clear local variables, etc. Really just
            destroys the current console and creates another. Accepts but
            does not use arguments, so it can be used as an event handler.
        """
        if self.viewer:
            args, kwargs = self.launchArgs
            kwargs['pos'] = self.GetPosition()
            kwargs['size'] = self.GetSize()
            kwargs['focus'] = True
            
            viewer = self.viewer
            viewer.childViews.pop(self.GetId(), None)
            viewer.console = None
            self.Destroy()
            viewer.showConsole(*args, **kwargs)

        else:
            wx.Bell()
            

    #===========================================================================
    # 
    #===========================================================================
    
    def SetFocus(self):
        """ This sets the window to receive keyboard input.
        """
        # The console proper is a child of the window; set focus appropriately.
        focus = super(PythonConsole, self).SetFocus()
        self.shell.SetFocus()
        return focus
    
    
    def OnShowView(self, evt):
        """ Handle 'show view' menu event: bring the linked Viewer to the
            foreground.
        """
        if self.viewer:
            self.viewer.SetFocus()
        else:
            wx.Bell()

    
    def OnClose(self, evt):
        """ Handle Window Close events. Actually just hides it.
        """
        if self.viewer and self.viewer.console == self:
            self.Hide()
            evt.Veto()
        else:
            evt.Skip()
    
    
    def OnAbout(self, evt):
        """ Handle "Help->About" menu events.
        """
        try:
            self.viewer.OnHelpAboutMenu(evt)
        except AttributeError:
            pass


    def OnHelp(self, evt):
        """ Display a Help window.
        """
        # XXX: REWRITE CONSOLE HELP!
        title = 'Scripting Console Help'
        
        text = ["The Scripting Console provides access to the underlying "
                "Python environment.", "Proceed with caution: misuse of the "
                "Console may cause %s to crash!\n" % build_info.APPNAME, 
                self.HELP_TEXT, 
                wx.py.shell.HELP_TEXT]
        text = '\n'.join(text)

        dlg = wx.lib.dialogs.ScrolledMessageDialog(self, text, title,
                                                   size=(700, 600))
        fnt = wx.Font(10, wx.TELETYPE, wx.NORMAL, wx.NORMAL)
        dlg.GetChildren()[0].SetFont(fnt)
        dlg.GetChildren()[0].SetInsertionPoint(0)
        dlg.ShowModal()
        dlg.Destroy()

    
    def OnEditPaths(self, evt):
        """ Handle "Options->Edit Paths" menu events.
        """
        paths = PythonPathEditor.editPaths(self)
        if paths is None:
            return

        sys.path = paths

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
        
        # Keep a copy of the initial arguments for 
        launchArgs = (args[:], kwargs.copy())
        launchArgs[1]['locals'] = localVars.copy()
        
        con = cls(parent, **kwargs)
        con.launchArgs = launchArgs
        
        try:
            parent.childViews[con.GetId()] = con
        except AttributeError:
            pass

        con.Show(True)
        return con


#===============================================================================
# 
#===============================================================================

class PythonPathEditor(wx.Dialog):
    """ A dialog for editing module import paths (i.e. `sys.path`).
    """
    ORIG_PATHS = sys.path[:]
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Dialog` arguments, plus:
        
            @keyword root: The 'root' viewer window.
            @keyword paths: A list of module paths.
        """
        self.app = wx.GetApp()
        self.root = kwargs.pop('root', None)
        self.paths = kwargs.pop('paths', sys.path)
        
        kwargs.setdefault('title', "Edit Import Paths")
        kwargs.setdefault('style', wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        kwargs.setdefault('size', (500,400))

        super(PythonPathEditor, self).__init__(*args, **kwargs)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        
        self.pathList = wx.adv.EditableListBox(self, -1,
                                       "Edit Module Import Paths (sys.path)")
        self.pathList.SetStrings(self.paths)
        sizer.Add(self.pathList, 1, wx.EXPAND|wx.ALL, 8)

        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.browseBtn = wx.Button(self, -1, "Select Directory...")
        self.browseBtn.SetToolTip("Browse for a directory to add to the list")
        self.browseBtn.Bind(wx.EVT_BUTTON, self.OnBrowse)
        hsizer.Add(self.browseBtn, 1, wx.EXPAND)
        
        self.importBtn = wx.Button(self, -1, "Import PYTHONPATH")
        self.importBtn.SetToolTip("Include paths defined in the PYTHONPATH "
                                  "environment variable."
                                  "\nNote: Must be Python 2.7!")
        self.importBtn.Bind(wx.EVT_BUTTON, self.OnImport)
        hsizer.Add(self.importBtn, 1, wx.EXPAND|wx.WEST, 8)
        
        sizer.Add(hsizer, 0, wx.EXPAND|wx.EAST|wx.SOUTH|wx.WEST, 8)
        
        line = wx.StaticLine(self, -1, style=wx.LI_HORIZONTAL)
        sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        
        bsizer = wx.StdDialogButtonSizer()
        bsizer.Add((0,0), 1)
        
        self.OkBtn = wx.Button(self, wx.ID_OK)
        self.OkBtn.SetDefault()
        bsizer.AddButton(self.OkBtn)
        self.CancelBtn = wx.Button(self, wx.ID_CANCEL)
        bsizer.AddButton(self.CancelBtn)
        bsizer.Realize()

        sizer.Add(bsizer, 0, wx.EXPAND|wx.EAST|wx.SOUTH|wx.WEST, 8)

        self.pathList.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEndEdit)


    #===========================================================================
    # 
    #===========================================================================

    def OnEndEdit(self, evt):
        """
        """
        path = os.path.normpath(evt.GetLabel())
        # XXX: Trying to set the changed string doesn't seem to work.
        evt.SetString(path)
        evt.Skip()


    def OnBrowse(self, evt):
        """ Handle the "Select Directory" button.
        """
        dlg = wx.DirDialog(self, "Choose a Python module directory:")
        if dlg.ShowModal() == wx.ID_OK:
            paths = self.pathList.GetStrings()
            p = dlg.GetPath()
            if p not in paths:
                paths.append(p)
            self.pathList.SetStrings(paths)
        dlg.Destroy()
        

    def OnImport(self, evt):
        """ Handle the "Import PYTHONPATH" button.
        """
        paths = self.pathList.GetStrings()
        newPaths = os.environ.get('PYTHONPATH', "").split(';')
        newPaths = [os.path.normpath(p.strip()) for p in newPaths]
        for p in newPaths:
            if p and p not in paths:
                paths.append(p)
        self.pathList.SetStrings(paths)

    #===========================================================================
    # 
    #===========================================================================
    
    def getEditedPaths(self):
        """
        """
        return [p for p in sys.path if p not in self.ORIG_PATHS]

    
    @classmethod
    def editPaths(cls, parent, **kwargs):
        """ Launch the Python path editor. Keyword arguments other than those
            shown below are passed to the dialog's constructor.
        
            @param parent: The parent window (or `None`)
            @keyword paths: A list of module paths. Defaults to `sys.path`.
            @return: A list of paths or `None` if the dialog is cancelled.
        """
        kwargs.setdefault('paths', sys.path[:])
        
        dlg = cls(parent, **kwargs)
        q = dlg.ShowModal()
        result = dlg.pathList.GetStrings()
        dlg.Destroy()
        
        if q == wx.ID_OK:
            return result
        
        return None
        


#===============================================================================
# 
#===============================================================================

# XXX: REMOVE THIS LATER. Makes running this module run the 'main' viewer.
if __name__ == "__main__":
#     import viewer
#     app = viewer.ViewerApp(loadLastFile=True)
#     PythonConsole.openConsole(None)
#     app.MainLoop()

    app = wx.App()
    print(PythonPathEditor.editPaths(None))
