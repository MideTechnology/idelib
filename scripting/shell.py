'''
Interactive Python interpreter for debugging purposes.

@author: dstokes

@todo: Make errors apply focus to the console (for main view's "Run Script").
    Tried an excepthook and a replacement for stderr which called `Focus()`,
    but neither worked.
'''
from __future__ import absolute_import, print_function

from datetime import datetime
import os
import sys
import tempfile
from threading import RLock

import wx.adv
import wx.py

import images
import mide_ebml
from widgets import htmlwindow

#===============================================================================
# 
#===============================================================================

HELP_HTML = """<html>
<h1>Scripting Console Help</h1>
<p>The Scripting Console provides access to the underlying Python environment.
Proceed with caution: misuse of the Console may cause enDAQ Lab to crash!</p>

<h2>Useful global variables and helper functions</h2>
<table>
<tr><td><tt>app</tt></td>
    <td>The currently running app.</td></tr>
<tr><td><tt>viewer</tt></td>
    <td>The active viewer window when the console was opened.</td></tr>
<tr><td><tt>viewer.dataset</tt></td>
    <td>The active imported recording file.</td></tr>
<tr><td><tt>viewer.getTab()</tt></td>
    <td>Retrieve the foreground tab.</td></tr>
</table>
<H2>Key bindings</H2>
<table>
<tr><td>Home</td>
    <td>Go to the beginning of the command or line.</td></tr>
<tr><td>Shift+Home</td>
    <td>Select to the beginning of the command or line.</td></tr>
<tr><td>Shift+End</td>
    <td>Select to the end of the line.</td></tr>
<tr><td>End</td>
    <td>Go to the end of the line.</td></tr>
<tr><td>Ctrl+C</td>
    <td>Copy selected text, removing prompts.</td></tr>
<tr><td>Ctrl+Shift+C</td>
    <td>Copy selected text, retaining prompts.</td></tr>
<tr><td>Alt+C</td>
    <td>Copy to the clipboard, including prefixed prompts.</td></tr>
<tr><td>Ctrl+X</td>
    <td>Cut selected text.</td></tr>
<tr><td>Ctrl+V</td>
    <td>Paste from clipboard.</td></tr>
<tr><td>Ctrl+Shift+V</td>
    <td>Paste and run multiple commands from clipboard.</td></tr>
<tr><td>Ctrl+Up Arrow<br/><i>or</i> Alt+P</td>
    <td>Retrieve Previous History item.</td></tr>
<tr><td>Ctrl+Down Arrow<br/><i>or</i> Alt+N</td>
    <td>Retrieve Next History item.</td></tr>
<tr><td>Ctrl+]</td>
    <td>Increase font size.</td></tr>
<tr><td>Ctrl+[</td>
    <td>Decrease font size.</td></tr>
<tr><td>Ctrl+=</td>
    <td>Default font size.</td></tr>
<tr><td>Ctrl+F</td>
    <td>Find (search).</td></tr>
<tr><td>Ctrl+G<br/><i>or</i> F3</td>
    <td>Find next.</td></tr>
<tr><td>Ctrl+Shift+G<br/><i>or</i> Shift+F3</td>
    <td>Find previous.</td></tr>
<tr><td>F12</td>
    <td>Toggle "free-edit" mode.</td></tr>
<tr><td>Ctrl+Tab</td>
    <td>Change to console's associated viewer window.</td></tr>
</table>
</html>"""


#===============================================================================
# 
#===============================================================================

class PythonConsole(wx.py.shell.ShellFrame):
    """ An interactive Python console for scripting and debugging purposes.
    """
    ID_RESET = wx.NewIdRef()
    ID_SHOW_VIEW = wx.NewIdRef()
    ID_EDIT_PATHS = wx.NewIdRef()
    
    ORIG_PATHS = sys.path[:]
    
    BASE_TITLE = "Scripting Console"
    INTRO_TEXT = '\n'.join(
        ("Welcome to the %s Python Scripting Console!",
         "",
         "* Useful global variables and helper functions:",
         "\tapp               The currently running app.",
         "\tviewer            The active viewer window when the console was opened.",
         "\tviewer.dataset    The active imported recording file.",
         "\tviewer.getTab()   Retrieve the foreground tab.",
         ""))

    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.py.shell.ShellFrame` arguments,
            plus:
        
            @keyword title: The 'prefix' for the window title. The rest gets
                set by the parent Viewer (IDE filename, etc.).
            @keyword focus: If `True`, the new window will have focus. 
            @keyword introText: Introductory text, shown when the shell starts.
            @keyword statusText: Initial text for the status bar.
            @keyword locals: A dictionary of local variables (like `exec` uses)
        """
        name = getattr(wx.GetApp(), 'fullAppName', '')
        
        self.baseTitle = kwargs.setdefault('title', self.BASE_TITLE)
        self.config = kwargs.pop('config', None)
        self.dataDir = kwargs.pop('dataDir', None)
        introText = kwargs.pop('introText', self.INTRO_TEXT % name)
        statusText = kwargs.pop('statusText', None)
        localvars = kwargs.pop('locals', {})
        interpClass = kwargs.pop('InterpClass', None)
        focus = kwargs.pop('focus', True)
        self.startupScript = kwargs.pop('startupScript', None)
        self.paths = kwargs.pop('path', None)
        kwargs.setdefault('size', (750, 525))
                
        self.busy = RLock()
        self.loadPrefs()

        self.execStartupScript = kwargs.pop('execStartupScript', 
                                            (bool(self.startupScript)
                                             and self.execStartupScript))

        # The `Viewer` window is (or should be) in the local variables.
        self.viewer = localvars.get('viewer', None)
        
        # Do only the relevant stuff in `Frame.__init__()`.
        # Note: May need to be refactored if `wx.py.frame.Frame` changes! 
#         wx.py.frame.Frame.__init__(self, *args, **kwargs)
        wx.Frame.__init__(self, *args, **kwargs)
        self.CreateStatusBar()
        self.shellName=self.BASE_TITLE
        self.__createMenus()
 
        self.iconized = False
        self.findDlg = None
        self.findData = wx.FindReplaceData()
        self.findData.SetFlags(wx.FR_DOWN)
 
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_ICONIZE, self.OnIconize)
        
        # Do only the relevant stuff in `ShellFrameMixin.__init__()`.
        # Note: May need to be refactored if the mixin class changes! 
#         wx.py.frame.ShellFrameMixin.__init__(self, config, dataDir)
        self.autoSaveSettings = False
        self.autoSaveHistory = False
        self.showPySlicesTutorial = False
        self.enableShellMode = False
        self.enableAutoSympy = True
        self.hideFoldingMargin = False

        self.shell = wx.py.shell.Shell(self,
                                       introText=introText,
                                       locals=localvars,
                                       startupScript=self.startupScript,
                                       execStartupScript=self.execStartupScript,
                                       InterpClass=interpClass
                                       )

        self.SetIcon(images.icon.GetIcon())
        self.SetStatusText(statusText or '')
        
        # Override the shell so that status messages go to the status bar.
        self.shell.setStatusText = self.SetStatusText

        self.setPythonPath(self.paths)
        self.parentUpdated()

        if focus:
            self.shell.SetFocus()
            
#         self.LoadSettings()
    
    
    #===========================================================================
    # 
    #===========================================================================

    def __createMenus(self):
        """ Build the menubar. Override of `Frame.__createMenus()`.
        """
        #======================================================================
        # File Menu
        m = self.fileMenu = wx.Menu()
        m.Append(wx.ID_CLOSE, '&Close Console\tCtrl+W',
                 'Close the console window')
        m.AppendSeparator()
#         m.Append(wx.ID_SAVE, '&Save... \tCtrl+S',
#                  'Save file')
#         m.Append(wx.ID_SAVEAS, 'Save &As \tCtrl+Shift+S',
#                  'Save file with new name')
#         m.AppendSeparator()
#         m.Append(wx.ID_PRINT, '&Print... \tCtrl+P',
#                  'Print file')
#         m.AppendSeparator()
#         m.Append(wx.py.frame.ID_NAMESPACE, '&Update Namespace \tCtrl+Shift+N',
#                  'Update namespace for autocompletion and calltips')
#         m.AppendSeparator()
        m.Append(self.ID_RESET, 
                 "Reset Interpreter\tCtrl+Shift+R",
                 "Restart the interpreter, clearing local variables, etc.")

        #======================================================================
        # Edit
        m = self.editMenu = wx.Menu()
        m.Append(wx.ID_UNDO)
        m.Append(wx.ID_REDO)
        m.AppendSeparator()
        m.Append(wx.ID_CUT)
        m.Append(wx.ID_COPY)
        m.Append(wx.py.frame.ID_COPY_PLUS, 'Cop&y Plus \tCtrl+Shift+C',
                 'Copy the selection - retaining prompts')
        m.Append(wx.ID_PASTE)
        m.Append(wx.py.frame.ID_PASTE_PLUS, 'Past&e Plus \tCtrl+Shift+V',
                 'Paste and run commands')
        m.AppendSeparator()
        m.Append(wx.ID_CLEAR, 'Cle&ar',
                 'Delete the selection')
        m.Append(wx.ID_SELECTALL, 'Select A&ll \tCtrl+A',
                 'Select all text')
        m.AppendSeparator()
        m.Append(wx.ID_FIND, '&Find Text... \tCtrl+F',
                 'Search for text in the edit buffer')
        findNext = m.Append(wx.py.frame.ID_FINDNEXT,
                            'Find &Next \tCtrl+G',
                            'Find next instance of the search text')
        findPrev = m.Append(wx.py.frame.ID_FINDPREVIOUS,
                            'Find Pre&vious \tCtrl+Shift+G',
                            'Find previous instance of the search text')
        
        #======================================================================
        # View
        m = self.viewMenu = wx.Menu()
        m.Append(wx.py.frame.ID_WRAP, '&Wrap Lines\tCtrl+Shift+W',
                 'Wrap lines at right edge', wx.ITEM_CHECK)
        m.Append(wx.py.frame.ID_SHOW_LINENUMBERS,
                 '&Show Line Numbers\tCtrl+Shift+L',
                 'Show Line Numbers', wx.ITEM_CHECK)
        m.Append(wx.py.frame.ID_TOGGLE_MAXIMIZE, '&Toggle Maximize\tF11',
                 'Maximize/Restore Application')
        m.AppendSeparator()
        # Lab changes:
        m.Append(self.ID_SHOW_VIEW,
                 "Show console's associated view\tCtrl+Tab",
                 "Bring the associated viewer window to the front.",
                 wx.ITEM_NORMAL)

        #======================================================================
        # Options
        m = self.autocompMenu = wx.Menu()
        m.Append(wx.py.frame.ID_AUTOCOMP_SHOW,
                 'Show &Auto Completion\tCtrl+Shift+A',
                 'Show auto completion list', wx.ITEM_CHECK)
        m.Append(wx.py.frame.ID_AUTOCOMP_MAGIC, 
                 'Include &Magic Attributes\tCtrl+Shift+M',
                 'Include attributes visible to __getattr__ and __setattr__',
                 wx.ITEM_CHECK)
        m.Append(wx.py.frame.ID_AUTOCOMP_SINGLE, 
                 'Include Single &Underscores\tCtrl+Shift+U',
                 'Include attributes prefixed by a single underscore', 
                 wx.ITEM_CHECK)
        m.Append(wx.py.frame.ID_AUTOCOMP_DOUBLE, 
                 'Include &Double Underscores\tCtrl+Shift+D',
                 'Include attributes prefixed by a double underscore',
                 wx.ITEM_CHECK)
        m = self.calltipsMenu = wx.Menu()
        m.Append(wx.py.frame.ID_CALLTIPS_SHOW, 
                 'Show Call &Tips\tCtrl+Shift+T',
                 'Show call tips with argument signature and docstring', 
                 wx.ITEM_CHECK)
        m.Append(wx.py.frame.ID_CALLTIPS_INSERT, 
                 '&Insert Call Tips\tCtrl+Shift+I',
                 '&Insert Call Tips', wx.ITEM_CHECK)

        m = self.optionsMenu = wx.Menu()
        m.AppendSubMenu(self.autocompMenu, '&Auto Completion',
                        'Auto Completion Options')
        m.AppendSubMenu(self.calltipsMenu, '&Call Tips', 'Call Tip Options')
        m.AppendSeparator()
        # Lab changes:
        m.Append(self.ID_EDIT_PATHS,
                 "Edit Module Import Paths...",
                 "Set the paths used to find modules to import "
                 "(sys.path/PYTHONPATH).")

        m = self.helpMenu = wx.Menu()
        name = getattr(wx.GetApp(), 'fullAppName', '')
        m.Append(wx.ID_HELP, '&Help\tF1', 'Help!')
        m.AppendSeparator()
        m.Append(wx.ID_ABOUT, '&About %s...' % name, '&About %s...' % name)

        b = self.menuBar = wx.MenuBar()
        b.Append(self.fileMenu, '&File')
        b.Append(self.editMenu, '&Edit')
        b.Append(self.viewMenu, '&View')
        b.Append(self.optionsMenu, '&Options')
        b.Append(self.helpMenu, '&Help')
        self.SetMenuBar(b)

        self.Bind(wx.EVT_MENU, self.OnFileClose, id=wx.ID_CLOSE)
#         self.Bind(wx.EVT_MENU, self.OnFileSave, id=wx.ID_SAVE)
#         self.Bind(wx.EVT_MENU, self.OnFileSaveAs, id=wx.ID_SAVEAS)
#         self.Bind(wx.EVT_MENU, self.OnFileSaveACopy, id=wx.py.frame.ID_SAVEACOPY)
#         self.Bind(wx.EVT_MENU, self.OnFileUpdateNamespace, id=wx.py.frame.ID_NAMESPACE)
#         self.Bind(wx.EVT_MENU, self.OnFilePrint, id=wx.ID_PRINT)
        self.Bind(wx.EVT_MENU, self.OnUndo, id=wx.ID_UNDO)
        self.Bind(wx.EVT_MENU, self.OnRedo, id=wx.ID_REDO)
        self.Bind(wx.EVT_MENU, self.OnCut, id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, self.OnCopy, id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, self.OnCopyPlus, id=wx.py.frame.ID_COPY_PLUS)
        self.Bind(wx.EVT_MENU, self.OnPaste, id=wx.ID_PASTE)
        self.Bind(wx.EVT_MENU, self.OnPastePlus, id=wx.py.frame.ID_PASTE_PLUS)
        self.Bind(wx.EVT_MENU, self.OnClear, id=wx.ID_CLEAR)
        self.Bind(wx.EVT_MENU, self.OnSelectAll, id=wx.ID_SELECTALL)
        self.Bind(wx.EVT_MENU, self.OnAbout, id=wx.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self.OnHelp, id=wx.ID_HELP)
        self.Bind(wx.EVT_MENU, self.OnAutoCompleteShow, id=wx.py.frame.ID_AUTOCOMP_SHOW)
        self.Bind(wx.EVT_MENU, self.OnAutoCompleteMagic, id=wx.py.frame.ID_AUTOCOMP_MAGIC)
        self.Bind(wx.EVT_MENU, self.OnAutoCompleteSingle, id=wx.py.frame.ID_AUTOCOMP_SINGLE)
        self.Bind(wx.EVT_MENU, self.OnAutoCompleteDouble, id=wx.py.frame.ID_AUTOCOMP_DOUBLE)
        self.Bind(wx.EVT_MENU, self.OnCallTipsShow, id=wx.py.frame.ID_CALLTIPS_SHOW)
        self.Bind(wx.EVT_MENU, self.OnCallTipsInsert, id=wx.py.frame.ID_CALLTIPS_INSERT)
        self.Bind(wx.EVT_MENU, self.OnWrap, id=wx.py.frame.ID_WRAP)
        self.Bind(wx.EVT_MENU, self.OnToggleMaximize, id=wx.py.frame.ID_TOGGLE_MAXIMIZE)
        self.Bind(wx.EVT_MENU, self.OnShowLineNumbers, id=wx.py.frame.ID_SHOW_LINENUMBERS)
        self.Bind(wx.EVT_MENU, self.OnFindText, id=wx.ID_FIND)
        self.Bind(wx.EVT_MENU, self.OnFindNext, id=wx.py.frame.ID_FINDNEXT)
        self.Bind(wx.EVT_MENU, self.OnFindPrevious, id=wx.py.frame.ID_FINDPREVIOUS)
        self.Bind(wx.EVT_MENU, self.OnToggleTools, id=wx.py.frame.ID_SHOWTOOLS)
        self.Bind(wx.EVT_MENU, self.OnHideFoldingMargin, id=wx.py.frame.ID_HIDEFOLDINGMARGIN)

        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_NEW)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_OPEN)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_REVERT)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_CLOSE)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_SAVE)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_SAVEAS)
#         self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_NAMESPACE)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_PRINT)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_UNDO)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_REDO)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_CUT)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_COPY)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_COPY_PLUS)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_PASTE)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_PASTE_PLUS)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_CLEAR)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_SELECTALL)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_AUTOCOMP_SHOW)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_AUTOCOMP_MAGIC)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_AUTOCOMP_SINGLE)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_AUTOCOMP_DOUBLE)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_CALLTIPS_SHOW)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_CALLTIPS_INSERT)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_WRAP)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_SHOW_LINENUMBERS)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.ID_FIND)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_FINDNEXT)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_FINDPREVIOUS)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_SHOWTOOLS)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, id=wx.py.frame.ID_HIDEFOLDINGMARGIN)

        self.Bind(wx.EVT_ACTIVATE, self.OnActivate)
        self.Bind(wx.EVT_FIND, self.OnFindNext)
        self.Bind(wx.EVT_FIND_NEXT, self.OnFindNext)
        self.Bind(wx.EVT_FIND_CLOSE, self.OnFindClose)

        self.Bind(wx.EVT_MENU, self.reset, id=self.ID_RESET)
        self.Bind(wx.EVT_MENU, self.OnShowView, id=self.ID_SHOW_VIEW)
        self.Bind(wx.EVT_MENU, self.OnEditPaths, id=self.ID_EDIT_PATHS)
        
        # Add F3/Shift+F3 accelerators to Find/Find Next
        accel = wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, wx.WXK_F3, findNext.GetId()),
            (wx.ACCEL_SHIFT, wx.WXK_F3, findPrev.GetId())])
        self.SetAcceleratorTable(accel)


    #===========================================================================
    # 
    #===========================================================================
    
    def loadPrefs(self):
        """ Load Python paths from the parent application's preferences.
        """
        app = wx.GetApp()
        if not hasattr(app, 'getPref'):
            return
        if not self.paths:
            self.paths = app.getPref('scripting.pythonpath', self.ORIG_PATHS)
        if not self.startupScript:
            self.startupScript = app.getPref('scripting.startupScript', None)
        self.execStartupScript = app.getPref('scripting.execStartupScript', False)
    
    
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

    
    def setPythonPath(self, paths, replace=False, quiet=True):
        """ Set the shell's `sys.path`.
        
            @param paths: A list of Python library paths.
            @keyword replace: If `True`, the existing `sys.path` will be
                replaced. If `False` (default), the new paths will be added to
                the end of the existing `sys.path`.
            @keyword quiet: If `False`, the console will display a message
                indicating `sys.path` was changed.
            @return: The console's new `sys.path`
        """
        with self.busy:
            if not replace:
                paths = self.ORIG_PATHS + [p for p in paths if p not in self.ORIG_PATHS]
                
            cmd = "import sys; sys.path=%r" % paths
            if not quiet:
                now = str(datetime.now()).rsplit('.',1)[0]
                cmd += ";print('### sys.path updated at %s')" % now
            self.shell.push(cmd, silent=quiet)
            del self.shell.history[0]
            
            return paths
   
    
    def reset(self, *args):
        """ Reset the console: clear local variables, etc. Really just
            destroys the current console and creates another. Accepts but
            does not use arguments, so it can be used as an event handler.
        """
        with self.busy:
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
    
    def execute(self, filename=None, code=None, globalScope=True, start=None,
                finish=None, focus=True):
        """ Run a file or a string of code. Executes multi-line scripts, 
            either in the editor's scope (modifying editor's global values)
            or its own local scope.
        """
        # Used when executing in local scope, so script containing the 
        # `if __name__=` pattern will run as expected.
        evLocals = {'__name__': '__main__'}
        
        if not filename and not code:
            return
        
        if focus:
            self.Show()
            self.SetFocus()
        
        if code:
            filename = tempfile.mkstemp(suffix=".py")[1]
            with open(filename, 'wb') as f:
                f.write(code)
        
        if globalScope:
            cmd = ("execfile(%r,globals())" % (filename))
        else:
            cmd = ("execfile(%r,globals().copy(),%r)" % (filename,evLocals))
        
        if start:
            cmd = ("print(%r);" % start) + cmd
        if finish:
            cmd += (";print(%r)" % finish)
        
        try:
            with self.busy:
                self.shell.push(cmd)
                del self.shell.history[0]
        finally:
            if code:
                try:
                    os.remove(filename)
                except (IOError, WindowsError):
                    pass
    
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
        text = HELP_HTML
        if wx.Platform == "__WXMAC__":
            # For future use, here now lest we forget.
            text = (text.replace("Ctrl+", "Command-")
                        .replace("Alt+", "Option-")
                        .replace("Shift+", "Shift-"))

        dlg = htmlwindow.HtmlDialog(self, text, 'Scripting Console Help',
                                    setBgColor=False)
        dlg.ShowModal()
        dlg.Destroy()

    
    def OnEditPaths(self, evt):
        """ Handle "Options->Edit Paths" menu events.
        """
        paths = PythonPathEditor.editPaths(self)
        if paths is None:
            return

        app = wx.GetApp()
        if hasattr(app, 'setPref'):
            app.setPref('scripting.pythonpath', paths)
        
        self.paths = paths
        self.setPythonPath(self.paths, quiet=False)


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
#                           'build_info': build_info,
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
        self.paths = kwargs.pop('paths', None)
        
        if not self.paths:
            if hasattr(self.app, 'getPref'):
                self.paths = self.app.getPref('scripting.pythonpath', self.ORIG_PATHS)
            else:
                self.paths = self.ORIG_PATHS
        
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
        """ Handle text exit completion.
        """
        path = os.path.normpath(evt.GetLabel())
        # XXX: Trying to set the changed string doesn't seem to work.
        evt.SetString(path)
        evt.Skip()


    def OnBrowse(self, _evt):
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
        

    def OnImport(self, _evt):
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
    
    @classmethod
    def editPaths(cls, parent, **kwargs):
        """ Launch the Python path editor. Keyword arguments other than those
            shown below are passed to the dialog's constructor.
        
            @param parent: The parent window (or `None`)
            @keyword paths: A list of module paths. Defaults to `sys.path`.
            @return: A list of paths or `None` if the dialog is cancelled.
        """
        dlg = cls(parent, **kwargs)
        q = dlg.ShowModal()
        paths = dlg.pathList.GetStrings()
        dlg.Destroy()
        
        if q != wx.ID_OK:
            return None
        
        return paths


#===============================================================================
# 
#===============================================================================

# XXX: REMOVE THIS LATER. Makes running this module run the 'main' viewer.
if __name__ == "__main__":
#     import viewer
#     app = viewer.ViewerApp(loadLastFile=True)
#     PythonConsole.openConsole(None)
#     app.MainLoop()

    class DummyApp(wx.App):
        prefs = {'scripting.pythonpath': ['fakey', 'blah']}
        
        def setPref(self, name, val, section=None):
            """ Set the value of a preference. Returns the value set as a
                convenience.
            """
            if section is not None:
                name = "%s.%s" % (section, name)
            self.prefs[name] = val
            return val

    
        def getPref(self, name, default=None, section=None):
            """ Retrieve a value from the preferences.
            """
            print("getpref %r" % name)
            if section is not None:
                name = "%s.%s" % (section, name)
            return self.prefs.get(name, default)

        
    app = DummyApp()
    print(PythonPathEditor.editPaths(None))
