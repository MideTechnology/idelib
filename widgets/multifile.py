'''
Created on Aug 12, 2015

@author: dstokes
'''

import os

import wx


class MultiFileSelect(wx.Panel):
    """ A multiple file selection widget. 
    """
    
    FULL_PATHS = 0
    NAME_ONLY = 1
    SHORTEN_PATHS = 2
        
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.Panel` arguments, plus:
        
            @keyword label: The widget's label text. `None` for no label.
            @keyword items: A set of files with which to pre-populate the list.
            @keyword display: How to display the files.
            @keyword wildcard: File types string. See `wx.FileDialog`
            @keyword message: The Add dialog's message. See `wx.FileDialog`
            @keyword defaultDir: See `wx.FileDialog`
            @keyword defaultFile: See `wx.FileDialog`
        """
        self.labelText = kwargs.pop("label", "Files to Process:")
        self.files = kwargs.pop('items', [])
        self.display = kwargs.pop('display', self.FULL_PATHS)
        self.wildcard = kwargs.pop("wildcard", "All Files (*.*)|*.*")
        self.message = kwargs.pop("message", "Select Files")
        self.defaultDir = kwargs.pop("defaultDir", os.getcwd())
        self.defaultFile = kwargs.pop("defaultFile", "")
        super(MultiFileSelect, self).__init__(*args, **kwargs)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        rsizer = wx.BoxSizer(wx.HORIZONTAL)
        bsizer = wx.BoxSizer(wx.VERTICAL)

        if self.labelText is not None:
            label = wx.StaticText(self, -1, self.labelText)
            rsizer.Add(label,  0, wx.ALIGN_TOP, 5)

        self.listbox = wx.ListBox(self, -1, style=wx.LB_MULTIPLE)
        self.addBtn = wx.Button(self, wx.ID_ADD)
        self.removeBtn = wx.Button(self, wx.ID_REMOVE)
        self.clearBtn = wx.Button(self, wx.ID_CLEAR)
        
        rsizer.Add(self.listbox, 1, wx.LEFT|wx.CENTER|wx.EXPAND|wx.ALL, 5)
        rsizer.Add(bsizer)
        bsizer.Add(self.addBtn, 1, wx.ALIGN_RIGHT|wx.ALIGN_TOP)
        bsizer.Add(self.removeBtn, 1, wx.ALIGN_RIGHT|wx.ALIGN_TOP)
        bsizer.Add(self.clearBtn, 1, wx.ALIGN_RIGHT|wx.ALIGN_TOP)
        
        sizer.Add(rsizer, 1, wx.EXPAND|wx.ALL)
        
        outersizer = wx.BoxSizer()
        outersizer.Add(sizer, 1, wx.EXPAND|wx.ALL, 3)
        outersizer.Fit(self)
        
        self.SetSizer(outersizer)
        self.Layout()
        self.Fit()
        
        self.listItems = []
        self.lastIndex = -1
        
        self.listbox.Bind(wx.EVT_LISTBOX, self.OnListbox)
        self.listbox.Bind(wx.EVT_MOTION, self.OnListMotion)
        self.addBtn.Bind(wx.EVT_BUTTON, self.OnAdd)
        self.removeBtn.Bind(wx.EVT_BUTTON, self.OnRemove)
        self.clearBtn.Bind(wx.EVT_BUTTON, self.OnClear)
        
        self.OnListbox(None)


    def makeListItems(self):
        """ Used internally. Updates the items in the list, potentially
            modifying the strings.
        """
        if self.display == self.NAME_ONLY:
            self.listItems = map(os.path.basename, self.files)
        else:
            self.listItems = self.files[:]
        self.listbox.SetItems(self.listItems)
        self.OnListbox(None)


    def OnListMotion(self, evt):
        index = self.listbox.HitTest(evt.GetPosition())
        if index != self.lastIndex:
            if index >= 0:
                self.listbox.SetToolTipString(self.files[index])
            else:
                self.listbox.SetToolTipString('')
        self.lastIndex = index
        evt.Skip()
        

    def OnAdd(self, evt):
        """ Handle 'Add' button press.
        """
        self.dlg = wx.FileDialog(self, message=self.message, 
                                 defaultDir=self.defaultDir,
                                 defaultFile=self.defaultFile,
                                 wildcard=self.wildcard,
                                 style=wx.OPEN | wx.MULTIPLE | wx.CHANGE_DIR)
        if self.dlg.ShowModal() == wx.ID_OK:
            for f in self.dlg.GetPaths():
                if f not in self.files:
                    self.files.append(f)
            self.makeListItems()
            
        self.dlg.Destroy()


    def OnListbox(self, evt):
        """ Handle listbox selection change.
        """
        self.removeBtn.Enable(len(self.listbox.GetSelections()) > 0)
        self.clearBtn.Enable(len(self.listItems) > 0)
        if evt is not None:
            evt.Skip()


    def OnRemove(self, evt):
        """ Handle 'Remove' button press.
        """
        for i in reversed(self.listbox.GetSelections()):
            del self.files[i]
        self.makeListItems()
        
    
    def OnClear(self, evt):
        self.files = []
        self.makeListItems()
        
    
    def GetPaths(self):
        """ Get the widget's selected files.
        """
        return self.files[:]
