""" A tabbed, fairly fully featured script editing window.
"""

from datetime import datetime
import os.path
import string
import tempfile

import  wx
import wx.aui as aui
import  wx.stc  as  stc

from base import MenuMixin

# TODO: Get rid of `python_stc.py` (copied from demo) and implement it here.
import python_stc
# TODO: Refactor/replace `DebugConsole` (a hack) with a good one.
from shell import DebugConsole 


#===============================================================================
# 
#===============================================================================

def uniqueName(basename, existingNames, sep=""):
    """ Produce a version of a name not already in a set of existing names.
        This is done by appending a number, or if the name ends with a number, 
        incrementing that number. If the name is already unique, it is 
        returned unchanged.
        
        @todo: This is generally useful. Move to shared module. 
        
        @param basename: The name to make unique.
        @param existingNames: A collection of existing names to avoid. It can
            be anything that implements the `__contains__` method.
        @return: A unique string.
    """
    if basename not in existingNames:
        return basename
    name = basename.rstrip(string.digits)
    num = basename[len(name):].strip()
    numLen = max(len(num), 1)
    try:
        num = int(num)+1
    except ValueError:
        num = 1
        
    while True:
        newname = "%s %s" % (name, str(num).rjust(numLen, '0'))
        if newname not in existingNames:
            return newname
        num += 1


#===============================================================================
# 
#===============================================================================

# XXX: hack, get rid of bad demo fonts!
python_stc.faces['times'] = python_stc.faces['mono']
python_stc.faces['helv'] = python_stc.faces['mono']
python_stc.faces['other'] = python_stc.faces['mono']


class ScriptEditorCtrl(python_stc.PythonSTC):
    """ A syntax-highlighting Python script editing control. Part of
        `ScriptEditor`; it assumes it is a tab in a AUINotebook.
    """
    
    DEFAULT_NAME = "Untitled"

    def __init__(self, *args, **kwargs):
        """ Constructor. Standard `stc.StyledTextCtrl()` arguments, plus:
        
            @keyword root: The containing `ScriptEditor`.
            @keyword filename: The full path and name of a file to load
                immediately after creation.
        """
        self.filename = kwargs.pop('filename', None)
        self.root = kwargs.pop('root', None)
        
        super(ScriptEditorCtrl, self).__init__(*args, **kwargs)
        self.updateOptions()

        self.Bind(stc.EVT_STC_MODIFIED, self.OnModified)

        self.LoadFile(self.filename)        

        self.lastSelection = None
        self.Bind(wx.EVT_UPDATE_UI, self.OnUIUpdate)
        
    
    def OnUIUpdate(self, evt):
        """ Handle a UI update event: Update parent window's selection-dependent
            menu items (run selection, copy, etc.).
        """
        # Note: this gets called extremely frequently. Do as little as possible.
        newSel = self.GetSelection()
        if newSel != self.lastSelection:
            hasSelection = newSel[0] != newSel[1]
            self.root.cutMI.Enable(hasSelection)
            self.root.copyMI.Enable(hasSelection)
            self.root.runSelectedMI.Enable(hasSelection)
            self.lastSelection = newSel
        evt.Skip()

    
    def __repr__(self): 
        """ x.__repr__() <==> repr(x)
            
            More human-readable, since user may access editors from the shell.
        """
        filename = self.filename or "not saved"
        return "<%s %r (%s)>" % (self.__class__.__name__, self.GetName(),
                                 filename)


    def updateOptions(self):
        """ Update the editor's display options using values from the root
            scripting window.
        """
        self.SetIndent(4)
        self.SetTabWidth(4)
        self.SetUseTabs(False)
        self.SetBackSpaceUnIndents(True)
        self.SetMarginType(1, stc.STC_MARGIN_NUMBER)
        
        self.SetIndentationGuides(self.root.showGuides)
        self.SetViewWhiteSpace(self.root.showWhitespace)

        self.SetEdgeColumn(self.root.edgeColumn)
        self.SetEdgeMode(int(self.root.showEdge))
        self.showEdge = True
        
        if self.root.showLineNumbers:
            self.SetMarginWidth(1, 25)
        else:
            self.SetMarginWidth(1, 0)
        

    def updateTab(self):
        """ Update the parent notebook's tab label, showing the name of the
            loaded file and a marker if the file has been modified.
        """
        try:
            parent = self.GetParent()
            idx = parent.GetPageIndex(self)
            
            if self.filename is None:
                txt = parent.GetPageText(idx).lstrip("*")
            else:
                txt = os.path.basename(self.filename)
            
            if self.IsModified():
                txt = "*" + txt
            
            parent.SetPageText(idx, txt)
            parent.SetPageToolTip(idx, self.filename or "")
            
        except (AttributeError, ValueError):
            # probably okay
            raise
        
    
    def wasModifiedExternally(self):
        """ Check to see if the loaded file has been modified by another
            program (e.g. an external editor).
        """
        if self.modTime is None:
            return False
        elif not self.filename:
            return False
        elif not os.path.isfile(self.filename):
            return False
        return os.path.getmtime(self.filename) != self.modTime
    
    
    def executeInShell(self, selected=False):
        """
        """
        if not self.filename or selected:
            filename = tempfile.mkstemp(suffix=".py")[1]
            code = self.GetSelectedText() if selected else self.GetText()
            if not code:
                return
            with open(filename, 'wb') as f:
                f.write(code)
            istemp = True
        else:
            filename = self.filename
            istemp = False

        if selected:
            numLines = (code.rstrip('\n').count('\n')+1)
            if numLines == 1:
                what = "selected text (1 line)"
            else:
                what = "selected text (%d lines)" % numLines
        else:
            what = "script"
            
        name = self.GetName()
        now = str(datetime.now()).rsplit('.',1)[0]
        start = "### Running %s from tab '%s' at %s" % (what, name, now)
        finish = "### Finished running %s from tab '%s'" % (what, name)
        
        try:
            shell = self.root.getShell()
            shell.shell.push("print(%r);execfile(%r);print(%r)" % (start,filename,finish))
        except Exception:
            print("XXX: Handle ScriptEditorCtrl.executeInShell() error!")
            raise
        finally:
            if istemp:
                try:
                    os.remove(filename)
                except (IOError, WindowsError):
                    pass
        
    
    def LoadFile(self, filename):
        """ Load a script into the editor. Will also update the parent
            notebook's tab.
        """
        self.modTime = None
        if not filename:
            return False
        try:
            result = super(ScriptEditorCtrl, self).LoadFile(filename)
            self.filename = filename
            self.SetModified(False)
            self.modTime = os.path.getmtime(filename)
        except (IOError, ValueError):
            # XXX: Handle error
            raise
        
        self.updateTab()
        return result
        
    
    
    def SaveFile(self, filename=None, saveAs=False):
        """ Save the current editor's contents. Will prompt for a name if
            the editor has no filename, or `saveAs` is `True`. Will also
            update the parent notebook's tab.
            
            @keyword filename: The filename to which to save. `None` will
                keep the existing filename.
            @keyword saveAs: If `True`, prompt to save the file with a
                different name.
        """
        filename = self.filename or filename
        
        if not saveAs and not self.IsModified():
            return False
        
        if saveAs or filename is None:
            dlg = wx.FileDialog(
                self, message="Save Script",
                defaultDir=self.root.defaultDir, 
                defaultFile=filename or "",
                wildcard=("Python source (*.py)|*.py|"
                          "All files (*.*)|*.*"),
                style=wx.SAVE | wx.CHANGE_DIR | wx.FD_OVERWRITE_PROMPT)
            if dlg.ShowModal() == wx.ID_OK:
                filename = dlg.GetPath()
            else:
                filename = None
            dlg.Destroy()
        
        if filename is None:
            return False
        
        try:
            result = super(ScriptEditorCtrl, self).SaveFile(filename)
            self.SetModified(False)
            self.filename = filename
            self.modTime = os.path.getmtime(filename)
            self.updateTab()
            return result
        except IOError:
            # XXX: handle error. Other exception types?
            raise
    

    #===========================================================================
    # 
    #===========================================================================
    
    def OnKeyPressed(self, event):
        """ Handle key press event: hide 'call tip' menu.
        """
        # Note: 'call tips' not currently implemented
        if self.CallTipActive():
            self.CallTipCancel()
            
        event.Skip()


    def OnModified(self, evt):
        """
        """
        if evt.GetModificationType() & (stc.STC_MOD_DELETETEXT|stc.STC_MOD_INSERTTEXT):
            self.updateTab()
            self.root.updateMenus()


#===============================================================================
# 
#===============================================================================

class ScriptEditorStatusBar(wx.StatusBar):
    """ 
    """
    # TODO: Implement status bar


#===============================================================================
# 
#===============================================================================

class ScriptEditor(wx.Frame, MenuMixin):
    """
    """
    ID_NEWTAB = wx.NewId()
    ID_FINDNEXT = wx.NewId()
    
    ID_MENU_OPEN_IN_NEW = wx.NewId()
    ID_MENU_SAVEALL = wx.NewId()
    ID_MENU_CLOSE_WINDOW = wx.NewId()
    ID_MENU_VIEW_WHITESPACE = wx.NewId()
    ID_MENU_VIEW_LINENUMBERS = wx.NewId()
    ID_MENU_VIEW_GUIDES = wx.NewId()
    ID_MENU_SCRIPT_RUN = wx.NewId()
    ID_MENU_SCRIPT_RUN_SEL = wx.NewId()
    
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Standard `wx.Frame` arguments, plus:
            
            @keyword files: A list of filenames to load on launch.
            @keyword contents: 
        """
        # Keep the launch arguments for creating new windows
        self.launchArgs = (args, kwargs.copy())
        
        files = kwargs.pop('files', None)
        contents = kwargs.pop('contents', None)
        
        super(ScriptEditor, self).__init__(*args, **kwargs)

        if not self.GetTitle():
            self.SetTitle("Script Editor")
        
        sizer = wx.BoxSizer()
        self.nb = aui.AuiNotebook(self, -1, style=aui.AUI_NB_TOP  
                                   | aui.AUI_NB_TAB_SPLIT 
                                   | aui.AUI_NB_TAB_MOVE  
                                   | aui.AUI_NB_SCROLL_BUTTONS 
                                   | aui.AUI_NB_WINDOWLIST_BUTTON
                                   | aui.AUI_NB_CLOSE_ON_ACTIVE_TAB)
        sizer.Add(self.nb, 1, wx.EXPAND)

        self.SetStatusBar(ScriptEditorStatusBar(self, -1))

        self.tabs = []
        self.findDlg = None
        self.isReplace = False
        self.finddata = wx.FindReplaceData()
        self.finddata.SetFlags(wx.FR_DOWN)

        self.changeCheckTimer = wx.Timer(self)

        self.loadPrefs()
        self.buildMenus()

        # Should be EVT_AUINOTEBOOK_TAB_RIGHT_DOWN in wxPython 4?
        self.nb.Bind(aui.EVT__AUINOTEBOOK_TAB_RIGHT_DOWN, self.OnNotebookRightClick)
        self.nb.Bind(aui.EVT_AUINOTEBOOK_PAGE_CLOSE, self.OnCloseTab)
        self.nb.Bind(aui.EVT_AUINOTEBOOK_PAGE_CHANGED, self.OnTabChanged)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_TIMER, self.OnChangeCheck)
        
        if files:
            for filename in files:
                self.addTab(filename=filename)

        if contents:
            for filename, src, modified in contents:
                self.addTab(filename=filename, text=src, modified=modified)


    def OnMenuTest(self, evt):
        print("menu event")


    def loadPrefs(self):
        """ Load/reload editor configuration from the main app.
        """
        self.changeCheckTimer.Stop()
        
        # TODO: Read from viewer preferences
        self.checkForChanges = True
        self.changeCheckInterval = 500
        self.defaultDir = ""
        self.showWhitespace = True
        self.showGuides = True
        self.showLineNumbers = True
        self.edgeColumn = 78
        self.showEdge = True
        
        for n in xrange(self.nb.GetPageCount()):
            self.nb.GetPage(n).updateOptions()

        if self.checkForChanges:
            self.changeCheckTimer.Start(self.changeCheckInterval)


    def buildMenus(self):
        """ Construct the main menu bar.
        """
        menu = wx.MenuBar()

        # "File" menu
        #=======================================================================
        fileMenu = self.addMenu(menu,  '&File')
        self.addMenuItem(fileMenu, self.ID_NEWTAB, 
                         "&New Tab\tCtrl+N", "",
                         self.OnFileNewTabMenu)
        self.addMenuItem(fileMenu, wx.ID_NEW, 
                         "New &Window\tCtrl+Shift+N", "",
                         self.OnFileNewMenu)
        self.addMenuItem(fileMenu, wx.ID_OPEN, u"", u"", 
                         self.OnFileOpenMenu)       
        fileMenu.AppendSeparator()
        
        self.addMenuItem(fileMenu, wx.ID_SAVE, u"", u"", 
                         self.OnFileSaveMenu)
        self.addMenuItem(fileMenu, wx.ID_SAVEAS, u"Save As...", u"", 
                         self.OnFileSaveMenu)
        self.addMenuItem(fileMenu, self.ID_MENU_SAVEALL,
                         u"Save All Changes", u"", 
                         self.OnFileSaveAllMenu)
        fileMenu.AppendSeparator()
        
        self.addMenuItem(fileMenu, wx.ID_PRINT, 
                         u"&Print...\tCtrl+P", u"", enabled=False)
        self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, 
                         u"Print Setup...", u"", enabled=False)
        fileMenu.AppendSeparator()
        
        self.addMenuItem(fileMenu, wx.ID_CLOSE, 
                         "&Close Tab\tCtrl+W", "", self.OnFileCloseTabMenu)
        self.addMenuItem(fileMenu, self.ID_MENU_CLOSE_WINDOW, 
                         "&Close Window\tCtrl+Shift+W", "", self.OnClose)
        
        # "Edit" menu
        #=======================================================================
        editMenu = self.addMenu(menu, '&Edit')
        self.cutMI = editMenu.Append(wx.ID_CUT)
        self.copyMI = editMenu.Append(wx.ID_COPY)
        self.pasteMI = editMenu.Append(wx.ID_PASTE)
        editMenu.AppendSeparator()
        
        self.addMenuItem(editMenu, wx.ID_FIND, 
                         '&Find...\tCtrl-F', '', 
                         self.OnEditFindMenu)
        # Note: in future, make this "Ctrl-G" if 'wxMax' in wx.PlatformInfo
        self.addMenuItem(editMenu, self.ID_FINDNEXT, 
                         'Find &Next\tF3', "", 
                         self.OnFindNext)
        self.addMenuItem(editMenu, wx.ID_REPLACE, 
                         'Find and &Replace...\tCtrl+Shift+F', '',
                         self.OnEditReplaceMenu)

        # "View" menu
        #=======================================================================
        viewMenu = self.addMenu(menu, '&View')
        self.addMenuItem(viewMenu, self.ID_MENU_VIEW_WHITESPACE,
                         'Show Whitespace', '',
                         self.OnViewMenuItem, 
                         kind=wx.ITEM_CHECK, checked=self.showWhitespace)
        self.addMenuItem(viewMenu, self.ID_MENU_VIEW_LINENUMBERS,
                         'Show Line Numbers', '',
                         self.OnViewMenuItem, 
                         kind=wx.ITEM_CHECK, checked=self.showLineNumbers)
        self.addMenuItem(viewMenu, self.ID_MENU_VIEW_GUIDES,
                         'Show Indentation Guides', '',
                         self.OnViewMenuItem, 
                         kind=wx.ITEM_CHECK, checked=self.showLineNumbers)


        # "Script" menu
        #=======================================================================
        scriptMenu = self.addMenu(menu, '&Script')
        self.runScriptMI = self.addMenuItem(scriptMenu, self.ID_MENU_SCRIPT_RUN, 
                         "&Run Script\tCtrl+R", '',
                         self.OnScriptRun)
        self.runSelectedMI = self.addMenuItem(scriptMenu, self.ID_MENU_SCRIPT_RUN_SEL, 
                         "&Execute Selected Lines\tCtrl+E", '',
                         self.OnScriptRunSelected)

        scriptMenu.AppendSeparator()
        self.addMenuItem(scriptMenu, -1, '&Show Python Interpreter\tCtrl+I', '', 
                         lambda x:self.getShell())

        # debugging
        debugMenu = self.addMenu(menu, "&Debug")
        self.addMenuItem(debugMenu, -1, 'getShell(focus=False)', '', lambda x:self.getShell(focus=False))

        self.SetMenuBar(menu)


    def updateMenus(self):
        """ Update the script editor's main menu bar.
        """
        editor = self.nb.GetCurrentPage()
        if not editor:
            saveEnabled = False
            saveAsEnabled = False
            saveAllEnabled = False
            closeEnabled = False
            pasteEnabled = False
            findEnabled = False
            runEnabled = False
            runSelEnabled = False
        else:
            saveEnabled = editor.IsModified()
            saveAsEnabled = True
            saveAllEnabled = any(t.IsModified() for t in self.tabs)
            closeEnabled = True
            pasteEnabled = editor.CanPaste()
            findEnabled = True
            runEnabled = True
            runSelEnabled = editor.CanCopy()
                        
        mb = self.GetMenuBar()
        self.setMenuItem(mb, wx.ID_SAVE, enabled=saveEnabled)
        self.setMenuItem(mb, wx.ID_SAVEAS, enabled=saveAsEnabled)
        self.setMenuItem(mb, self.ID_MENU_SAVEALL, enabled=saveAllEnabled)
        self.setMenuItem(mb, wx.ID_CLOSE, enabled=closeEnabled)
        self.setMenuItem(mb, wx.ID_CUT, enabled=runSelEnabled)
        self.setMenuItem(mb, wx.ID_COPY, enabled=runSelEnabled)
        self.setMenuItem(mb, wx.ID_PASTE, enabled=pasteEnabled)
        self.setMenuItem(mb, wx.ID_FIND, enabled=findEnabled)
        self.setMenuItem(mb, self.ID_FINDNEXT, enabled=findEnabled)
        self.setMenuItem(mb, wx.ID_REPLACE, enabled=findEnabled)
        self.setMenuItem(mb, self.ID_MENU_SCRIPT_RUN, enabled=runEnabled)
        self.setMenuItem(mb, self.ID_MENU_SCRIPT_RUN_SEL, enabled=runSelEnabled)
        
    
    
    def getShell(self, focus=True):
        """ Get the Python shell window.
        """
        # XXX: TODO: Get the shell from the parent.
        try:
            if self.shell.IsIconized(): # will fail if shell closed
                self.shell.Iconize(False)
        except (AttributeError, wx.PyDeadObjectError) as err:
            # Shell window isn't open (not shown yet, or previously closed)
            localVars = locals() # use provided locals?
            localVars['editor'] = self # for testing
            self.shell = DebugConsole.openConsole(locals=localVars, focus=False)
        
        if focus:
            self.shell.Raise()
        else:
            self.Raise()
        
        return self.shell
    

    def addTab(self, filename=None, name=None, text=None, modified=False,
               focus=True):
        """ Add a tab, optionally loading a script.
        
            @keyword filename: The name of a script to load, or `None`.
            @keyword text: The new tab's raw contents. If `text` is provided,
                the file specified by `filename` will not be loaded. Primarily
                for use when moving a tab from one window to another.
            @keyword modified: Explicitly set the new tab's 'modified' flag.
                Intended for use with `text`.
            @keyword focus: If `True`, select the new tab.
        """
        editor = ScriptEditorCtrl(self.nb, -1, root=self)
        if not filename:
            names = [self.nb.GetPageText(n) for n in xrange(self.nb.GetPageCount())]
            tabname = uniqueName(editor.DEFAULT_NAME, names)
        else:
            tabname = os.path.basename(filename)
        
        name = name or tabname
        self.nb.AddPage(editor, name)
        editor.SetName(name)
        
        if not text:
            editor.LoadFile(filename)
        else:
            editor.SetText(text)
            
        editor.SetModified(modified)
        
        if focus:
            self.nb.SetSelection(self.nb.GetPageIndex(editor))
        
        self.tabs.append(editor)
        self.updateMenus()
        return editor

        

    #===========================================================================
    # 
    #===========================================================================

    def _makeFindDialog(self, title, replace=False):
        """ Helper method to create a `wx.FindReplaceDialog`, bind its events,
            and show it. Same method for both "Find" and "Find and Replace".
        """
        if self.findDlg is not None:
            if replace == self.isReplace:
                return
            else:
                self.findDlg.Destroy()
        
        style = 0
        if replace:
            style |= wx.FR_REPLACEDIALOG
        
        self.isReplace = replace
        self.findDlg = wx.FindReplaceDialog(self, self.finddata, title, style)
        self.findDlg.Bind(wx.EVT_FIND, self.OnFind)
        self.findDlg.Bind(wx.EVT_FIND_NEXT, self.OnFindNext)
        self.findDlg.Bind(wx.EVT_FIND_REPLACE, self.OnFindReplace)
        self.findDlg.Bind(wx.EVT_FIND_REPLACE_ALL, self.OnFindReplaceAll)
        self.findDlg.Bind(wx.EVT_FIND_CLOSE, self.OnFindClose)
        self.findDlg.Show()
        
    
    #===========================================================================
    # 
    #===========================================================================


    def OnFind(self, event):
        """ Handle find dialog 'find' button click. 
        """
        editor = self.nb.GetCurrentPage()
        if not editor:
            return
        
        # Copied (mostly) from demo
        end = editor.GetLastPosition()
        textstring = editor.GetRange(0, end).lower()
        findstring = self.finddata.GetFindString().lower()
        backward = not (self.finddata.GetFlags() & wx.FR_DOWN)
        if backward:
            start = editor.GetSelection()[0]
            loc = textstring.rfind(findstring, 0, start)
        else:
            start = editor.GetSelection()[1]
            loc = textstring.find(findstring, start)
        if loc == -1 and start != 0:
            # string not found, start at beginning
            if backward:
                start = end
                loc = textstring.rfind(findstring, 0, start)
            else:
                start = 0
                loc = textstring.find(findstring, start)
        if loc == -1:
            dlg = wx.MessageDialog(self, 'Find String Not Found',
                          'Find String Not Found in Demo File',
                          wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
        if self.findDlg:
            if loc == -1:
                self.findDlg.SetFocus()
                return
            # NOTE: From demo. Not sure what it was for.
#             else:
#                 self.findDlg.Destroy()
#                 self.findDlg = None
        if loc != -1:
            editor.ShowPosition(loc)
            editor.SetSelection(loc, loc + len(findstring))


    def OnFindNext(self, evt):
        """ Handle find dialog 'find next' button click. 
        """
        if self.finddata.GetFindString():
            self.OnFind(evt)
        else:
            self.OnEditFindMenu(evt)
    
    
    def OnFindReplace(self, evt):
        """ Handle find dialog 'replace' button click. 
        """
        editor = self.nb.GetCurrentPage()
        if not editor:
            return
        
        if self.finddata.GetFindString():
            replacestring = self.finddata.GetReplaceString()
            selStart, selEnd = editor.GetSelection()
            if selStart != selEnd:
                editor.ReplaceSelection(replacestring)
                editor.SetSelectionStart(selStart)
                editor.SetSelectionEnd(selStart + len(replacestring))
            self.OnFind(evt)
        
        
        
    def OnFindReplaceAll(self, evt):
        """ Handle find dialog 'replace all' button click. 
        """
        print("XXX: Implement OnFindReplaceAll()!")
        evt.Skip()
        
    
    def OnFindClose(self, evt):
        """ Handle Find/Replace dialog close (cancel, escape, etc.).
        """
        evt.GetDialog().Destroy()
        self.findDlg = None


    #===========================================================================
    # 
    #===========================================================================
    
    def OnChangeCheck(self, evt):
        """ Timer handler to check if files have been edited externally. 
            Modified files will be reloaded.
        """
        self.changeCheckTimer.Stop()
        for editor in self.tabs:
            if not editor.wasModifiedExternally():
                continue
            doSave = True
            if editor.IsModified():
                q = wx.MessageBox(
                  "A file was modified outside of the Script Editor\n\n%s\n\n"
                  "Do you want to reload the file and lose changes?" % editor.filename, 
                  "Reload File?", wx.YES|wx.NO|wx.YES_DEFAULT|wx.ICON_WARNING, self)
                
                doSave = q == wx.YES
                
            if doSave:
                editor.LoadFile(editor.filename)
                
        self.changeCheckTimer.Start(self.changeCheckInterval)

    
    #===========================================================================
    # 
    #===========================================================================
    
    def OnNotebookRightClick(self, evt):
        """ Handle a right-click on an editor tab: show a context menu.
        """
        page = self.nb.GetPage(evt.GetEventObject().GetActivePage())

        menu = wx.Menu()
        self.addMenuItem(menu, wx.ID_SAVE, u"Save File", u"", 
                         self.OnFileSaveMenu, enabled=page.IsModified())
        self.addMenuItem(menu, wx.ID_SAVEAS, u"Save As...", u"", 
                         self.OnFileSaveMenu)
        menu.AppendSeparator()
        
        self.addMenuItem(menu, self.ID_MENU_OPEN_IN_NEW,
                         u"Open Script in New Window", u"",
                         self.OnOpenInEditor)
        
        self.nb.PopupMenu(menu)
    
    
    def OnTabChanged(self, evt):
        """ Handle selecting another tab. Also called when tabs added/removed.
        """
        self.updateMenus()
        evt.Skip()
    
    
    def OnOpenInEditor(self, evt):
        """ Open a new editor window containing the selected tab.
        """
        args, kwargs = self.launchArgs
        kwargs = kwargs.copy()
        kwargs['files'] = None
        kwargs.pop('contents', None)
        
        tab = self.nb.GetCurrentPage()
        if tab:
            kwargs['contents'] = [(tab.filename, tab.GetText(), tab.IsModified())]
        
        # TODO: Any additional prep?
        dlg = self.__class__(*args, **kwargs)
        dlg.Show()
        
        self.OnCloseTab(evt, savePrompt=False)
        
        # Actually remove the page (needed if not called by the notebook)
        self.nb.DeletePage(self.nb.GetSelection())
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    def OnCloseTab(self, evt, savePrompt=True):
        """ Handle a tab closing. Confirm if editor has unsaved changes.
        """
        tab = self.nb.GetCurrentPage()
        
        if savePrompt and tab.IsModified():
            q = wx.MessageBox("Save changes before closing?", 
                              "Save Changes?", wx.YES|wx.NO|wx.CANCEL|wx.YES_DEFAULT, self)
            if q == wx.CANCEL:
                evt.Veto()
                return
            elif q == wx.YES:
                tab.SaveFile()

        if tab in self.tabs:
            self.tabs.remove(tab)

        evt.Skip()
        wx.CallAfter(self.updateMenus)
    
    
    def OnClose(self, evt):
        """ Handle the closing of the entire scripting window. Confirm if any
            editor has unsaved changes.
        """
        changed = [t for t in self.tabs if t.IsModified()]

        if not changed:
            evt.Skip()
            return

        q = wx.MessageBox("Some scripts have been modified but not saved. Save changes before closing?", 
                          "Save Changes?", wx.YES|wx.NO|wx.CANCEL|wx.YES_DEFAULT, self)
        if q == wx.CANCEL:
            evt.Veto()
            return
        elif q == wx.YES:
            for tab in changed:
                tab.SaveFile()
        
        evt.Skip()
        

    def OnFileNewTabMenu(self, evt):
        """ Handle 'File->New Tab' menu events. Self-explanatory.
        """
        self.addTab()


    def OnFileNewMenu(self, evt):
        """ Handle 'File->New Window' menu events. Create a new scripting 
            window.
        """
        args, kwargs = self.launchArgs
        kwargs = kwargs.copy()
        kwargs.pop('files', None)
        kwargs.pop('contents', None)
        
        # TODO: Any additional prep?
        dlg = self.__class__(*args, **kwargs)
        dlg.Show()
        
    
    def OnFileOpenMenu(self, evt):
        """ Handle 'File->Open' menu events. Create a new tab with a file.
        """
        dlg = wx.FileDialog(
            self, message="Open Script",
            defaultDir=os.getcwd(), 
            defaultFile=self.defaultDir,
            wildcard=("Python source (*.py)|*.py|"
                      "All files (*.*)|*.*"),
            style=wx.OPEN | wx.CHANGE_DIR | wx.FILE_MUST_EXIST)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            # TODO: See if file already open, error handling?
            self.addTab(filename = filename)
        
        dlg.Destroy()
   

    def OnFileSaveMenu(self, evt):
        """ Handle 'File->Save' and 'File->Save All' menu events.
        """
        saveAs = evt.GetId() == wx.ID_SAVEAS
        editor = self.nb.GetCurrentPage()
        if not editor:
            return
        
        editor.SaveFile(saveAs=saveAs)
        self.updateMenus()


    def OnFileSaveAllMenu(self, evt):
        """ Handle 'File->Save All' menu events.
        """
        for t in self.tabs:
            if t.IsModified():
                t.SaveFile()
        self.updateMenus()
                

    def OnFileCloseTabMenu(self, evt):
        """ Handle a tab closing from 'File->Close Tab'. Confirm if editor has
            unsaved changes.
        """
        self.OnCloseTab(evt)
        
        # Actually remove the page (needed if not called by the notebook)
        self.nb.DeletePage(self.nb.GetSelection())


    #===========================================================================

    def OnEditFindMenu(self, evt):
        """ Handle 'Edit->Find' menu event.
        """
        self._makeFindDialog("Find", replace=False)


    def OnEditReplaceMenu(self, evt):
        """ Handle 'Edit->Find and Replace' menu event.
        """
        self._makeFindDialog("Find and Replace", replace=True)
    

    #===========================================================================

    def OnViewMenuItem(self, evt):
        """ Handle one of the 'View' menu check items. They're individually
            simple, so this method handles them all.
        """
        mid = evt.GetId()
        if mid == self.ID_MENU_VIEW_WHITESPACE:
            self.showWhitespace = evt.Checked()
        elif mid == self.ID_MENU_VIEW_LINENUMBERS:
            self.showLineNumbers = evt.Checked()
        elif mid == self.ID_MENU_VIEW_GUIDES:
            self.showGuides = evt.Checked()

        for n in xrange(self.nb.GetPageCount()):
            self.nb.GetPage(n).updateOptions()


    #===========================================================================

    def OnScriptRun(self, evt):
        """ Handle 'Script->Run Script' menu event.
        """
        tab = self.nb.GetCurrentPage()
        if tab:
            tab.executeInShell()


    def OnScriptRunSelected(self, evt):
        """ Handle 'Script->Execute Selected' menu event.
        """
        tab = self.nb.GetCurrentPage()
        if tab:
            if tab.CanCopy():
                tab.executeInShell(selected=True)
            else:
                print("TODO: tell user to select text first")



            

#===============================================================================
# 
#===============================================================================

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    dlg = ScriptEditor(None, size=(800,600), files=[__file__])
    dlg.Show()
    app.MainLoop()