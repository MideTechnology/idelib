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
    
    def __init__(self, *args, **kwargs):
        """
        """
        super(ScriptEditor, self).__init__(*args, **kwargs)
        
        sizer = wx.BoxSizer()
        self.editor = ScriptEditorCtrl(self, -1)
        sizer.Add(self.editor, 1, wx.EXPAND)


    def buildMenus(self):
        """
        """
        menu = wx.MenuBar()

        # "File" menu
        #=======================================================================
        fileMenu = self.addMenu(self.menubar,  '&File')
        self.addMenuItem(fileMenu, wx.ID_NEW, "&New Script Editor\tCtrl+N", "",
                         self.OnFileNewMenu)
        self.addMenuItem(fileMenu, wx.ID_CLOSE, 
                         "Close Script Editor\tCtrl+W", "", self.OnClose)
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_OPEN, u"", u"", 
                         self.OnFileOpenMenu)
        fileMenu.AppendSeparator()
        
        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_PRINT, u"", u"", enabled=False)
        self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, u"", u"", enabled=False)
        
#         fileMenu.AppendSeparator()
#         self.recentFilesMenu = self.app.recentFilesMenu #wx.Menu()
#         fileMenu.AppendMenu(self.ID_RECENTFILES, "Recent Files", 
#                             self.recentFilesMenu)
#         fileMenu.AppendSeparator()

        
        # "Edit" menu
        #=======================================================================
        editMenu = self.addMenu(self.menubar, '&Edit')
        editMenu.Append(wx.ID_CUT)
        editMenu.Append(wx.ID_COPY)
        editMenu.Append(wx.ID_PASTE)
#         editMenu.AppendSeparator()
#         self.addMenuItem(editMenu, wx.ID_PREFERENCES, "Preferences...", "",
#                          self.app.editPrefs)



#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    dlg = ScriptEditor(None)
    dlg.Show()
    app.MainLoop()