""" A tabbed, fairly fully featured script editing window.
"""
from __future__ import absolute_import, print_function

from datetime import datetime
import os.path
import string

import wx
import wx.aui as AUI
import wx.stc as STC

from base import MenuMixin
# from build_info import DEBUG
import images
from logger import logger


# TODO: Get rid of `python_stc.py` (copied from demo) and implement it here.
from scripting import python_stc


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
        
            @keyword frame: The containing `ScriptEditor`.
            @keyword filename: The full path and name of a file to load
                immediately after creation.
        """
        self.filename = kwargs.pop('filename', None)
        self.frame = kwargs.pop('frame', None)
        self.root = kwargs.pop('root', None)
        
        super(ScriptEditorCtrl, self).__init__(*args, **kwargs)
        self.updateOptions()

        self.Bind(STC.EVT_STC_MODIFIED, self.OnModified)

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
            self.frame.cutMI.Enable(hasSelection)
            self.frame.copyMI.Enable(hasSelection)
            self.frame.runSelectedMI.Enable(hasSelection)
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
        """ Update the editor's display options using values from the parent
            scripting window.
        """
        self.SetIndent(4)
        self.SetTabWidth(4)
        self.SetUseTabs(False)
        self.SetBackSpaceUnIndents(True)
        self.SetMarginType(1, STC.STC_MARGIN_NUMBER)
        
        self.SetIndentationGuides(self.frame.showGuides)
        self.SetViewWhiteSpace(self.frame.showWhitespace)

        self.SetEdgeColumn(self.frame.edgeColumn)
        self.SetEdgeMode(int(self.frame.showEdge))
        self.showEdge = True
        
        if self.frame.showLineNumbers:
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
    

    def executeInShell(self, selected=False, globalScope=True):
        """ Run the tab's contents in the Python console. Running selected
            text is done in the editor's current scope.
        """
        evGlobals = {}
        
        if not self.filename or selected:
            filename = None
            code = self.GetSelectedText() if selected else self.GetText()
            if not code:
                logger.debug("ScriptEditorCtrl.executeInShell(): No code!")
                return
        else:
            filename = self.filename
            code=None

        if selected:
            whatEnd = "selected text"
            numLines = (code.rstrip('\n').count('\n')+1)
            if numLines == 1:
                what = whatEnd + " (1 line)"
            else:
                what = whatEnd + " (%d lines)" % numLines
        else:
            what = whatEnd = "script"
            evGlobals['__name__'] = "__main__"

        name = self.GetName()
        now = str(datetime.now()).rsplit('.',1)[0]
        start = "### Running %s from tab '%s' at %s" % (what, name, now)
        finish = "### Finished running %s from tab '%s'" % (whatEnd, name)

        try:
            self.frame.getShell().execute(filename=filename, code=code,
                                          globalScope=globalScope,
                                          start=start, finish=finish)
        except Exception as err:
            # Error trying to execute the script (not the script itself)
            logger.error("ScriptEditorCtrl.executeInShell() error: %r" % err)
            raise


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
                defaultDir=self.frame.defaultDir, 
                defaultFile=filename or "",
                wildcard=("Python source (*.py)|*.py|"
                          "All files (*.*)|*.*"),
                style=wx.FD_SAVE | wx.FD_CHANGE_DIR | wx.FD_OVERWRITE_PROMPT)
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
        """ Handle editor contents change.
        """
        if evt.GetModificationType() & (STC.STC_MOD_DELETETEXT|STC.STC_MOD_INSERTTEXT):
            self.updateTab()
            self.frame.updateMenus()


#===============================================================================
# 
#===============================================================================

# class ScriptEditorStatusBar(wx.StatusBar):
#     """ The script editor window's status bar.
#     """
#     # FUTURE: Implement status bar, if needed. With cursor position, etc.


#===============================================================================
# 
#===============================================================================

class ScriptEditor(wx.Frame, MenuMixin):
    """
    """
    TITLE = "Script Editor"
    
    ID_NEWTAB = wx.NewIdRef()
    ID_FINDNEXT = wx.NewIdRef()
    
    ID_MENU_OPEN_IN_NEW = wx.NewIdRef()
    ID_MENU_SAVEALL = wx.NewIdRef()
    ID_MENU_CLOSE_WINDOW = wx.NewIdRef()
    ID_MENU_DETECT_CHANGES = wx.NewIdRef()
    ID_MENU_VIEW_WHITESPACE = wx.NewIdRef()
    ID_MENU_VIEW_LINENUMBERS = wx.NewIdRef()
    ID_MENU_VIEW_GUIDES = wx.NewIdRef()
    ID_MENU_SCRIPT_RUN = wx.NewIdRef()
    ID_MENU_SCRIPT_RUN_SEL = wx.NewIdRef()
    
    PREFS = {'checkForChanges': True,
            'changeCheckInterval': 500,
            'defaultDir': "",
            'showWhitespace': True,
            'showGuides': True,
            'showLineNumbers': True,
            'edgeColumn': 78,
            'showEdge': True
            }
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Standard `wx.Frame` arguments, plus:
            
            @keyword files: A list of filenames to load on launch.
            @keyword contents: 
        """
        # Keep the launch arguments for creating new windows
        self.launchArgs = (args, kwargs.copy())
        
        self.root = kwargs.pop('root', args[0] if args else None)
        files = kwargs.pop('files', None)
        contents = kwargs.pop('contents', None)
        self.baseTitle = kwargs.setdefault('title', self.TITLE)
        
        super(ScriptEditor, self).__init__(*args, **kwargs)
        self.parentUpdated()
        
        sizer = wx.BoxSizer()
        self.nb = AUI.AuiNotebook(self, -1, style=AUI.AUI_NB_TOP  
                                   | AUI.AUI_NB_TAB_SPLIT 
                                   | AUI.AUI_NB_TAB_MOVE  
                                   | AUI.AUI_NB_SCROLL_BUTTONS 
                                   | AUI.AUI_NB_WINDOWLIST_BUTTON
                                   | AUI.AUI_NB_CLOSE_ON_ACTIVE_TAB)
        sizer.Add(self.nb, 1, wx.EXPAND)

#         self.SetStatusBar(ScriptEditorStatusBar(self, -1))
        self.SetStatusBar(wx.StatusBar(self, -1))
        
        self.SetIcon(images.icon.GetIcon())
        
        self.changeCheckTimer = wx.Timer(self)

        self.tabs = []
        self.findDlg = None
        self.isReplace = False
        self.finddata = wx.FindReplaceData()
        self.finddata.SetFlags(wx.FR_DOWN)

        self.checkForChanges = True
        self.changeCheckInterval = 500
        self.defaultDir = ""
        self.showWhitespace = True
        self.showGuides = True
        self.showLineNumbers = True
        self.edgeColumn = 78
        self.showEdge = True

        self.loadPrefs()
        self.buildMenus()

        self.nb.Bind(AUI.EVT_AUINOTEBOOK_TAB_RIGHT_DOWN, self.OnNotebookRightClick)
        self.nb.Bind(AUI.EVT_AUINOTEBOOK_PAGE_CLOSE, self.OnCloseTab)
        self.nb.Bind(AUI.EVT_AUINOTEBOOK_PAGE_CHANGED, self.OnTabChanged)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_TIMER, self.OnChangeCheck)
        
        if files:
            for filename in files:
                self.addTab(filename=filename)
        elif not contents:
            self.addTab()

        if contents:
            for filename, src, modified in contents:
                self.addTab(filename=filename, text=src, modified=modified)


    def loadPrefs(self):
        """ Load/reload editor configuration from the main app.
        """
        self.changeCheckTimer.Stop()
        
        app = wx.GetApp()
        if hasattr(app, 'getPref'):
            for k,v in self.PREFS.items():
                setattr(self, k, app.getPref('scripting.editor.%s' % k, v))
        
        for n in xrange(self.nb.GetPageCount()):
            self.nb.GetPage(n).updateOptions()

        if self.checkForChanges:
            self.changeCheckTimer.Start(self.changeCheckInterval)


    def savePrefs(self):
        """ Save editor configuration to the main app.
        """
        try:
            timerRunning = self.changeCheckTimer.IsRunning()
            self.changeCheckTimer.Stop()
        except RuntimeError:
            timerRunning = False

        app = wx.GetApp()
        if hasattr(app, 'setPref'):
            for k in self.PREFS.keys():
                app.setPref('scripting.editor.%s' % k, getattr(self, k))

        if timerRunning:
            self.changeCheckTimer.Start(self.changeCheckInterval)


    def buildMenus(self):
        """ Construct the main menu bar.
        """
        menu = wx.MenuBar()

        # "File" menu
        #=======================================================================
        fileMenu = self.addMenu(menu,  '&File')
        self.addMenuItem(fileMenu, self.ID_NEWTAB, 
                         "&New Tab\tCtrl+N",
                         "Create a new editor tab",
                         self.OnFileNewTabMenu)
        self.addMenuItem(fileMenu, wx.ID_NEW, 
                         "New &Window\tCtrl+Shift+N",
                         "Create a new script editor window",
                         self.OnFileNewMenu)
        self.addMenuItem(fileMenu, wx.ID_OPEN, u"", 
                         u"Open a Python script", 
                         self.OnFileOpenMenu)
        fileMenu.AppendSeparator()
        
        self.addMenuItem(fileMenu, wx.ID_SAVE, handler=self.OnFileSaveMenu)
        self.addMenuItem(fileMenu, wx.ID_SAVEAS, handler=self.OnFileSaveMenu)
        self.addMenuItem(fileMenu, self.ID_MENU_SAVEALL,
                         u"Save All Changes",
                         u"Save all modified documents", 
                         self.OnFileSaveAllMenu)
        fileMenu.AppendSeparator()

        self.addMenuItem(fileMenu, self.ID_MENU_DETECT_CHANGES,
                         "Detect External Edits",
                         "Automatically update editor contents when another "
                         "program changes the file",
                         self.OnFileDetectEdits,
                         kind=wx.ITEM_CHECK,
                         checked=self.checkForChanges)
        fileMenu.AppendSeparator()

        
        # NOTE: Printing not (yet) implemented.
#         self.addMenuItem(fileMenu, wx.ID_PRINT, enabled=False)
#         self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, u"Print Setup...", u"", 
#                          enabled=False)
#         fileMenu.AppendSeparator()
        
        # NOTE: Closing the tab this way crashes the app. Fix!
#         self.addMenuItem(fileMenu, wx.ID_CLOSE, 
#                          "&Close Tab\tCtrl+W", "", self.OnFileCloseTabMenu)
        
        self.addMenuItem(fileMenu, self.ID_MENU_CLOSE_WINDOW, 
                         "&Close Window\tCtrl+Shift+W", 
                         "Close the Script Editor window",
                         self.OnFileCloseWindow)
        
        # "Edit" menu
        #=======================================================================
        editMenu = self.addMenu(menu, '&Edit')
        self.cutMI = editMenu.Append(wx.ID_CUT)
        self.copyMI = editMenu.Append(wx.ID_COPY)
        self.pasteMI = editMenu.Append(wx.ID_PASTE)
        self.Bind(wx.EVT_MENU, self.OnCut, id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, self.OnCopy, id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, self.OnPaste, id=wx.ID_PASTE)
        editMenu.AppendSeparator()
        
        self.addMenuItem(editMenu, wx.ID_FIND, 
#                          '&Find...\tCtrl-F', '', 
                         handler=self.OnEditFindMenu)
        # Note: in future, make this "Ctrl-G" if 'wxMax' in wx.PlatformInfo
        self.addMenuItem(editMenu, self.ID_FINDNEXT, 
                        'Find &Next\tF3', 
                        "Find next occurrence in document", 
                         handler=self.OnFindNext)
        self.addMenuItem(editMenu, wx.ID_REPLACE, 
#                          'Find and &Replace...\tCtrl+Shift+F', '',
                         handler=self.OnEditReplaceMenu)

        # "View" menu
        #=======================================================================
        viewMenu = self.addMenu(menu, '&View')
        self.addMenuItem(viewMenu, self.ID_MENU_VIEW_WHITESPACE,
                         'Show Whitespace',
                         "Display 'invisible' characters (space, tab, etc.)",
                         self.OnViewMenuItem, 
                         kind=wx.ITEM_CHECK, checked=self.showWhitespace)
        self.addMenuItem(viewMenu, self.ID_MENU_VIEW_LINENUMBERS,
                         'Show Line Numbers', '',
                         self.OnViewMenuItem, 
                         kind=wx.ITEM_CHECK, checked=self.showLineNumbers)
        self.addMenuItem(viewMenu, self.ID_MENU_VIEW_GUIDES,
                         'Show Indentation Guides',
                         'Show vertical tab alignment guides',
                         self.OnViewMenuItem, 
                         kind=wx.ITEM_CHECK, checked=self.showGuides)


        # "Script" menu
        #=======================================================================
        scriptMenu = self.addMenu(menu, '&Script')
        self.runScriptMI = self.addMenuItem(scriptMenu, self.ID_MENU_SCRIPT_RUN, 
                         "&Run Script\tCtrl+R",
                         'Run the script in the current tab',
                         self.OnScriptRun)
        self.runSelectedMI = self.addMenuItem(scriptMenu, self.ID_MENU_SCRIPT_RUN_SEL, 
                         "&Execute Selected Lines\tCtrl+E",
                         'Run the selected line(s) in the current tab',
                         self.OnScriptRunSelected)

        scriptMenu.AppendSeparator()
        self.addMenuItem(scriptMenu, -1, 
                         "Open Python &Console\tCtrl+Shift+C", 
                         'Show the interactive Python console for this editor',
                         lambda _x:self.getShell())

        helpMenu = self.addMenu(menu, "&Help")
        name = getattr(wx.GetApp(), 'fullAppName', '')
        self.addMenuItem(helpMenu, wx.ID_ABOUT,
                         "About %s..." % name,
                         "About %s..." % name,
                         self.OnHelpAboutMenu)

        # debugging
        #=======================================================================
#         if DEBUG:
#             debugMenu = self.addMenu(menu, "&Debug")
#             self.addMenuItem(debugMenu, -1, 'getShell(focus=False)', '', 
#                              lambda _x:self.getShell(focus=False))

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
    

    def parentUpdated(self):
        """ Method called when the parent `Viewer` changes in such a way that
            the editor needs updating (e.g. a file was imported).
        """
        title = self.baseTitle
        
        if self.root:
            name = self.root.app.getWindowTitle(self.root, showApp=False)
            if name:
                title = "%s: %s" % (self.baseTitle, name)
        
        try:
            self.SetTitle(title)
        except RuntimeError:
            pass

    
    def getShell(self, focus=True):
        """ Get the Python shell window.
        """
        if self.root:
            console = self.root.showConsole(focus=False)
            if focus:
                console.Raise()
            else:
                self.Raise()
        
            return console
    

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
        editor = ScriptEditorCtrl(self.nb, -1, frame=self, root=self.root)
        if not filename:
            names = [self.nb.GetPageText(n).lstrip('*') \
                     for n in xrange(self.nb.GetPageCount())]
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
        
        try:
            editor.SetModified(modified)
        except wx.wxAssertionError:
            # A C++ assertion failure ("wxStyledTextCtrl::MarkDirty(): not
            # implemented") happens when opening a tab in a new window (done
            # via tab context menu). Not sure why there at not elsewhere.
            pass
        
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

    def OnCut(self, evt):
        """ Handle Edit->Cut menu event.
        """
        editor = self.nb.GetCurrentPage()
        if not editor:
            return
        editor.Cut()
        

    def OnCopy(self, evt):
        """ Handle Edit->Copy menu event.
        """
        editor = self.nb.GetCurrentPage()
        if not editor:
            return
        editor.Copy()
        

    def OnPaste(self, evt):
        """ Handle Edit->Paste menu event.
        """
        editor = self.nb.GetCurrentPage()
        if not editor:
            return
        editor.Paste()
    

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
            dlg = wx.MessageDialog(self, 
                                   'The string "%s" could not be found.' % findstring,
                                   'Not Found',
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
        editor = self.nb.GetCurrentPage()
        if not editor:
            return

        text = editor.GetText()
        if self.finddata.GetFindString():
            findstring = self.finddata.GetFindString()
            replacestring = self.finddata.GetReplaceString()
            text = text.replace(findstring, replacestring)
            editor.SetText(text)
        
        
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
                  "The file '%s' was modified outside of the Script Editor\n\n"
                  "Do you want to reload the file '%s'\nand lose changes?" % \
                  (editor.GetName(),editor.filename), 
                  "Reload File?", wx.YES|wx.NO|wx.YES_DEFAULT|wx.ICON_WARNING,
                  self)
                
                doSave = q == wx.YES
                
            if doSave:
                editor.LoadFile(editor.filename)
            else:
                editor.modTime = os.path.getmtime(editor.filename)#time.time()
                
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
                         u"Open Script in New Window",
                         u"Create a new editor window containing this tab",
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
            kwargs['contents'] = [(tab.filename,
                                   tab.GetText(),
                                   tab.IsModified())]
        
        # ???: Any additional preparation required?
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
            if tab.filename:
                msg = "The script '%s' has been modified." % tab.filename
            else:
                msg = "The script has not been saved."
            q = wx.MessageBox("Save Changes to '%s'?\n\n%s\nSave changes "
                              "before closing?" % (tab.GetName(), msg), 
                              "Script Editor", 
                              wx.YES|wx.NO|wx.CANCEL|wx.YES_DEFAULT|wx.ICON_QUESTION,
                              self)
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
        self.changeCheckTimer.Stop()
        changed = [t for t in self.tabs if t.IsModified()]

        if changed:
            q = wx.MessageBox("Save Changes?\n\nSome scripts have been "
                              "modified but not saved. Save changes before "
                              "closing?", "Script Editor",
                              wx.YES|wx.NO|wx.CANCEL|wx.YES_DEFAULT, self)
            if q == wx.CANCEL:
                if self.checkForChanges:
                    self.changeCheckTimer.Start(self.changeCheckInterval)
                evt.Veto()
                return
            elif q == wx.YES:
                for tab in changed:
                    tab.SaveFile()
        
        # Remove from parent Viewer.
        try:
            self.viewer.childViews.pop(self.GetId())
        except (AttributeError, KeyError):
            pass
        
        self.savePrefs()
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
        
        # ???: Any additional preparation required?
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
            style=wx.FD_OPEN | wx.FD_CHANGE_DIR | wx.FD_FILE_MUST_EXIST)
        
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
        # XXX: THIS IS HARD-CRASHING THE APP! FIX OR REMOVE!
        self.OnCloseTab(evt)
         
        # Actually remove the page (needed if not called by the notebook)
        page = evt.GetSelection()
        self.nb.RemovePage(page)
        self.nb.DeletePage(page)


    def OnFileCloseWindow(self, evt):
        """ Handle the 'File->Close Window' menu event.
        """
        self.Close()
        

    def OnFileDetectEdits(self, evt):
        """
        """
        self.checkForChanges = evt.IsChecked()
        if self.checkForChanges:
            self.changeCheckTimer.Start(self.changeCheckInterval)
        else:
            self.changeCheckTimer.Stop()


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
            self.showWhitespace = evt.IsChecked()
        elif mid == self.ID_MENU_VIEW_LINENUMBERS:
            self.showLineNumbers = evt.IsChecked()
        elif mid == self.ID_MENU_VIEW_GUIDES:
            self.showGuides = evt.IsChecked()

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
                wx.Bell()


    #===========================================================================

    def OnHelpAboutMenu(self, evt):
        """ Handle 'Help->About' menu event.
        """
        try:
            self.root.OnHelpAboutMenu(evt)
        except AttributeError:
            # Probably not started through a viewer
            pass


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    dlg = ScriptEditor(None, size=(800,600), files=[__file__])
    dlg.Show()
    app.MainLoop()