"""
"""

import os.path
import string

import  wx
import wx.aui as aui
import  wx.stc  as  stc

from base import MenuMixin

from python_stc import PythonSTC, faces

#===============================================================================
# 
#===============================================================================

def uniqueName(basename, existingNames):
    """ Produce a version of a name not already in a set of existing names.
        This is done by appending a number, or if the name ends with a number, 
        incrementing that number. If the name is already unique, it is 
        returned unchanged.
        
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
    newname = "%s %s" % (name, str(num).rjust(numLen, '0'))
    while newname in existingNames:
        num += 1
        newname = "%s %s" % (name, str(num).rjust(numLen, '0'))
    return newname


#===============================================================================
# 
#===============================================================================

# XXX: hack, get rid of bad demo fonts!
faces['times'] = faces['mono']
faces['helv'] = faces['mono']
faces['other'] = faces['mono']

class ScriptEditorCtrl(PythonSTC):
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
        
        PythonSTC.__init__(self, *args, **kwargs)
        self.updateOptions()

        self.Bind(stc.EVT_STC_MODIFIED, self.OnModified)

        self.LoadFile(self.filename)



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
    
    
    def LoadFile(self, filename):
        """ Load a script into the editor. Will also update the parent
            notebook's tab.
        """
        self.modTime = None
        if not filename:
            return False
        try:
            result = PythonSTC.LoadFile(self, filename)
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
            result = PythonSTC.SaveFile(self, filename)
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

    # XXX: Copied from demo. They were there for TextCtrl compatibility.
    # Probably not needed.
    def SetInsertionPoint(self, pos):
        self.SetCurrentPos(pos)
        self.SetAnchor(pos)

    def ShowPosition(self, pos):
        line = self.LineFromPosition(pos)
        #self.EnsureVisible(line)
        self.GotoLine(line)

    def GetLastPosition(self):
        return self.GetLength()

    def GetPositionFromLine(self, line):
        return self.PositionFromLine(line)

    def GetRange(self, start, end):
        return self.GetTextRange(start, end)

    def GetSelection(self):
        return self.GetAnchor(), self.GetCurrentPos()

    def SetSelection(self, start, end):
        self.SetSelectionStart(start)
        self.SetSelectionEnd(end)

    def SelectLine(self, line):
        start = self.PositionFromLine(line)
        end = self.GetLineEndPosition(line)
        self.SetSelection(start, end)
        

    #===========================================================================
    # 
    #===========================================================================
    
    def OnKeyPressed(self, event):
        """
        """
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

class ScriptEditor(wx.Frame, MenuMixin):
    """
    """
    
    ID_NEWTAB = wx.NewId()
    ID_FINDNEXT = wx.NewId()
    
    ID_MENU_SAVEALL = wx.NewId()
    ID_MENU_CLOSE_WINDOW = wx.NewId()
    ID_MENU_SCRIPT_RUN = wx.NewId()
    
    
    def __init__(self, *args, **kwargs):
        """
        """
        super(ScriptEditor, self).__init__(*args, **kwargs)
        
        sizer = wx.BoxSizer()
        self.nb = aui.AuiNotebook(self, -1, style=aui.AUI_NB_TOP  
                                   | aui.AUI_NB_TAB_SPLIT 
                                   | aui.AUI_NB_TAB_MOVE  
                                   | aui.AUI_NB_SCROLL_BUTTONS 
                                   | aui.AUI_NB_WINDOWLIST_BUTTON
                                   | aui.AUI_NB_CLOSE_ON_ACTIVE_TAB)
        sizer.Add(self.nb, 1, wx.EXPAND)

        self.editors = []
        self.findDlg = None
        self.isReplace = False
        self.finddata = wx.FindReplaceData()
        self.finddata.SetFlags(wx.FR_DOWN)

        self.changeCheckTimer = wx.Timer(self)

        self.buildMenus()
        self.loadPrefs()

        # Should be EVT_AUINOTEBOOK_TAB_RIGHT_DOWN in wxPython 4?
        self.nb.Bind(aui.EVT__AUINOTEBOOK_TAB_RIGHT_DOWN, self.OnNotebookRightClick)
        self.nb.Bind(aui.EVT_AUINOTEBOOK_PAGE_CLOSE, self.OnCloseTab)
        self.nb.Bind(aui.EVT_AUINOTEBOOK_PAGE_CHANGED, self.OnTabChanged)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_TIMER, self.OnChangeCheck)
        
        # XXX: Test
        self.addTab(filename=__file__)



    def loadPrefs(self):
        """
        """
        self.changeCheckTimer.Stop()
        
        # TODO: Read from viewer preferences
        self.checkForChanges = True
        self.changeCheckInterval = 500
        self.defaultDir = ""
        self.showWhitespace = True
        self.showGuides = True
        self.showLineNumbers = True
        
        for n in xrange(self.nb.GetPageCount()):
            self.nb.GetPage(n).updateOptions()

        if self.checkForChanges:
            self.changeCheckTimer.Start(self.changeCheckInterval)


    def buildMenus(self):
        """
        """
        menu = wx.MenuBar()

        # "File" menu
        #=======================================================================
        fileMenu = self.addMenu(menu,  '&File')
        self.addMenuItem(fileMenu, self.ID_NEWTAB, 
                         "&New Tab\tCtrl+N", "",
                         self.addTab)
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
                         "&Close Tab\tCtrl+W", "", self.OnCloseTab)
        self.addMenuItem(fileMenu, self.ID_MENU_CLOSE_WINDOW, 
                         "&Close Window\tCtrl+Shift+W", "", self.OnClose)
        
        
        
        # "Edit" menu
        #=======================================================================
        editMenu = self.addMenu(menu, '&Edit')
        editMenu.Append(wx.ID_CUT)
        editMenu.Append(wx.ID_COPY)
        editMenu.Append(wx.ID_PASTE)
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

        # "Script" menu
        #=======================================================================
        scriptMenu = self.addMenu(menu, '&Script')
        self.addMenuItem(scriptMenu, self.ID_MENU_SCRIPT_RUN, 
                         "Run Script\tCtrl+R", '',
                         self.OnScriptRun)

        self.SetMenuBar(menu)


    def updateMenus(self):
        """ Update the script editor's main menu bar.
        """
        editor = self.nb.GetCurrentPage()
        saveEnabled = editor is not None and editor.IsModified()
        self.setMenuItem(self.MenuBar, wx.ID_SAVE, enabled=saveEnabled)

        if not saveEnabled:
            saveEnabled = any(e.IsModified() for e in self.editors)

        self.setMenuItem(self.MenuBar, self.ID_MENU_SAVEALL, enabled=saveEnabled)
        

    def addTab(self, evt=None, filename=None, focus=True):
        """ Add a tab, optionally loading a script.
        
            @keyword evt: A menu event, if called in response to a menu item.
            @keyword filename: The name of a script to load, or `None`.
            @keyword focus: If `True`, select the new tab.
        """
        editor = ScriptEditorCtrl(self.nb, -1, root=self)
        if not filename:
            names = [self.nb.GetPageText(n) for n in xrange(self.nb.GetPageCount())]
            name = uniqueName(editor.DEFAULT_NAME, names)
        else:
            name = os.path.basename(filename)
            
        self.nb.AddPage(editor, name)
        
        editor.LoadFile(filename)
        
        if focus:
            self.nb.SetSelection(self.nb.GetPageIndex(editor))
        
        self.editors.append(editor)
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
        for editor in self.editors:
            if editor.wasModifiedExternally():
                if not editor.IsModified():
                    editor.LoadFile(editor.filename)
                else:
                    print("XXX: prompt to revert changed file")

    
    #===========================================================================
    # 
    #===========================================================================
    
    def OnNotebookRightClick(self, evt):
        """ Handle a right-click on an editor tab: show a context manu.
        """
        page = self.nb.GetPage(evt.GetEventObject().GetActivePage())

        menu = wx.Menu()
        self.addMenuItem(menu, wx.ID_SAVE, u"Save File", u"", 
                         self.OnFileSaveMenu, enabled=page.IsModified())
        self.addMenuItem(menu, wx.ID_SAVEAS, u"Save As...", u"", 
                         self.OnFileSaveMenu)
        menu.AppendSeparator()
        
        self.addMenuItem(menu, wx.ID_CLOSE, 
                         "&Close Tab", "", 
                         self.OnCloseTab)

        self.nb.PopupMenu(menu)
    
    
    def OnTabChanged(self, evt):
        """ Handle selecting another tab. Also called when tabs added/removed.
        """
        self.updateMenus()
        evt.Skip()
    
    
    #===========================================================================
    # 
    #===========================================================================
    
    def OnCloseTab(self, evt):
        """ Handle a tab closing. Confirm if editor has unsaved changes.
        """
        page = self.nb.GetCurrentPage()
        
        if page.IsModified():
            q = wx.MessageBox("Save changes before closing?", 
                              "Save Changes?", wx.YES|wx.NO|wx.CANCEL|wx.YES_DEFAULT, self)
            if q == wx.CANCEL:
                evt.Veto()
                return
            elif q == wx.YES:
                page.SaveFile()
        
        self.editors.remove(page)
        evt.Skip()
        

    def OnClose(self, evt):
        """ Handle the closing of the entire scripting window. Confirm if any
            editor has unsaved changes.
        """
        pages = [p for p in self.editors if p.IsModified()]

        if not pages:
            evt.Skip()
            return

        q = wx.MessageBox("Some scripts have been modified but not saved. Save changes before closing?", 
                          "Save Changes?", wx.YES|wx.NO|wx.CANCEL|wx.YES_DEFAULT, self)
        if q == wx.CANCEL:
            evt.Veto()
            return
        elif q == wx.YES:
            for page in pages:
                page.SaveFile()
        
        evt.Skip()
        

    def OnFileNewMenu(self, evt):
        """ Handle File-New Window menu events. Create a new scripting window.
        """
        print("XXX: Implement OnFileNewMenu()!")
        evt.Skip()
        
    
    def OnFileOpenMenu(self, evt):
        """ Handle File->Open menu events. Create a new tab with a file.
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
        for p in self.editors:
            if p.IsModified():
                p.SaveFile()
        self.updateMenus()
                
        

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

    def OnScriptRun(self, evt):
        """ Handle 'Script->Run Script' menu event.
        """
        print("XXX: Implement OnScriptRun()!")


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    dlg = ScriptEditor(None, size=(800,600))
    dlg.Show()
    app.MainLoop()