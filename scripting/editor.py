import  wx
import  wx.stc  as  stc

from base import MenuMixin

from python_stc import PythonSTC, faces

# XXX: hack, get rid of bad demo fonts!
faces['times'] = faces['mono']
faces['helv'] = faces['mono']
faces['other'] = faces['mono']


class ScriptEditorCtrl(PythonSTC):
    """
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        PythonSTC.__init__(self, *args, **kwargs)

        self.SetTabWidth(4)
        self.SetUseTabs(False)
        self.SetViewWhiteSpace(True)
        self.SetMarginType(1, stc.STC_MARGIN_NUMBER)
        self.SetMarginWidth(1, 25)

        self.SetIndent(4)               # Proscribed indent size for wx
        self.SetIndentationGuides(True) # Show indent guides
        self.SetBackSpaceUnIndents(True)# Backspace unindents rather than delete 1 space


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
        


    def OnKeyPressed(self, event):
        if self.CallTipActive():
            self.CallTipCancel()
            
        event.Skip()


#===============================================================================
# 
#===============================================================================

class ScriptEditor(wx.Frame, MenuMixin):
    """
    """
    
    ID_FINDNEXT = wx.NewId()
    
    def __init__(self, *args, **kwargs):
        """
        """
        super(ScriptEditor, self).__init__(*args, **kwargs)
        
        sizer = wx.BoxSizer()
        self.editor = ScriptEditorCtrl(self, -1)
        sizer.Add(self.editor, 1, wx.EXPAND)

        self.finddlg = None
        self.finddata = wx.FindReplaceData()
        self.finddata.SetFlags(wx.FR_DOWN)

        self.buildMenus()


    def buildMenus(self):
        """
        """
        menu = wx.MenuBar()

        # "File" menu
        #=======================================================================
        fileMenu = self.addMenu(menu,  '&File')
        self.addMenuItem(fileMenu, wx.ID_NEW, "&New Script Editor\tCtrl+N", "",
                         self.OnFileNewMenu)
        self.addMenuItem(fileMenu, wx.ID_CLOSE, 
                         "Close Script Editor\tCtrl+W", "", self.OnClose)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_OPEN, u"", u"", 
                         self.OnFileOpenMenu)
        fileMenu.AppendSeparator()
        
        self.addMenuItem(fileMenu, wx.ID_PRINT, u"&Print...\tCtrl+P", u"", enabled=False)
        self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, u"Print Setup...", u"", enabled=False)
        
#         fileMenu.AppendSeparator()
#         self.recentFilesMenu = self.app.recentFilesMenu #wx.Menu()
#         fileMenu.AppendMenu(self.ID_RECENTFILES, "Recent Files", 
#                             self.recentFilesMenu)
#         fileMenu.AppendSeparator()

        
        # "Edit" menu
        #=======================================================================
        editMenu = self.addMenu(menu, '&Edit')
        editMenu.Append(wx.ID_CUT)
        editMenu.Append(wx.ID_COPY)
        editMenu.Append(wx.ID_PASTE)
        editMenu.AppendSeparator()
        
        self.addMenuItem(editMenu, wx.ID_FIND, '&Find...\tCtrl-F', '', 
                         self.OnEditFindMenu)
        # Note: in future, make this "Ctrl-G" if 'wxMax' in wx.PlatformInfo
        self.addMenuItem(editMenu, self.ID_FINDNEXT, 'Find &Next\tF3', "", 
                         self.OnEditFindNextMenu)
        self.addMenuItem(editMenu, wx.ID_REPLACE, 'Find and &Replace...\tShift+Ctrl+F', '',
                         self.OnEditReplaceMenu)
        
#         self.addMenuItem(editMenu, wx.ID_PREFERENCES, "Preferences...", "",
#                          self.app.editPrefs)

        # "Edit" menu
        #=======================================================================
        scriptMenu = self.addMenu(menu, '&Script')
        

        self.SetMenuBar(menu)


    def OnClose(self, evt):
        evt.Skip()
        

    def OnFileNewMenu(self, evt):
        evt.Skip()
        
    
    def OnFileOpenMenu(self, evt):
        evt.Skip()
   
    
    def OnEditFindMenu(self, evt):
        """
        """
        if self.finddlg is not None:
            # TODO: Focus on find dialog
            return
        
        self.finddlg = wx.FindReplaceDialog(self, self.findddata, "Find",
                                            wx.FR_NOMATCHCASE | wx.FR_NOWHOLEWORD)
        self.finddlg.Show(True)


    def OnEditFindNextMenu(self, evt):
        # XXX: implement
        evt.Skip()
    
    
    def OnEditReplaceMenu(self, evt):
        # XXX: implement
        evt.Skip()
    

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    dlg = ScriptEditor(None)
    dlg.Show()
    app.MainLoop()