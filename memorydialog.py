import wx.lib.agw.genericmessagedialog as GMD
import wx; wx = wx

class MemoryDialog(GMD.GenericMessageDialog):
    """ A variant of the `GenericMessageDialog` that optionally includes a
        checkbox, intended for allowing the user to remember their choice
        and/or suppress future appearances of the dialog.
    """

    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the same arguments as `GenericMessageDialog`
            plus the following keywords:
            
            @keyword remember: If `True`, the checkbox will be added.
            @keyword rememberMsg: A custom label for the checkbox.
            @keyword rememberDefault: The default value of the checkbox.
        """
        style = args[3]
        if style & (wx.YES_NO):
            defaultMsg = "Don't Ask Again"
        else:
            defaultMsg = "Don't show this message again"
        self.remember = kwargs.pop('remember', False)
        self.rememberMsg = kwargs.pop('rememberMsg', defaultMsg)
        self.rememberDefault = kwargs.pop('rememberDefault', False)
        super(MemoryDialog, self).__init__(*args, **kwargs)


    def SetRememberCheck(self, message=None, default=False):
        """ Add a 'remember' checkbox to a dialog, if the `remember` arguments
            weren't used when the dialog was instantiated. Implemented for
            compatibility with the dialog's existing `SetExtendedMessage`
            method. Call this before displaying the dialog. 
        """
        self.remember = True
        self.rememberMsg = message if message is not None else self.rememberMsg
        self.rememberDefault = default


    def CreateSeparatedButtonSizer(self, flags):
        """
        Creates a sizer with standard buttons using :meth:`~GenericMessageDialog.CreateButtonSizer` separated
        from the rest of the dialog contents by a horizontal :class:`StaticLine`.

        :param `flags`: the button sizer flags.

        :see: :meth:`~GenericMessageDialog.CreateButtonSizer` for a list of valid flags.
        """
        sizer = self.CreateButtonSizer(flags)
        topsizer = wx.BoxSizer(wx.VERTICAL)
        
        if self.remember:
            margin = self.Children[0].GetSize()
            checkSizer = wx.BoxSizer(wx.HORIZONTAL)
            checkSizer.Add((margin[0]+10, margin[1]), 0, wx.EXPAND, 10)
            self.rememberCheck = wx.CheckBox(self, -1, self.rememberMsg, pos=(100,-1))
            checkSizer.AddF(self.rememberCheck, wx.SizerFlags().Expand())
            topsizer.AddF(checkSizer, wx.SizerFlags().Expand())
            self.rememberCheck.SetValue(self.rememberDefault)
        
        # Mac Human Interface Guidelines recommend not to use static lines as
        # grouping elements
        if wx.Platform != "__WXMAC__":
            topsizer.AddF(wx.StaticLine(self), wx.SizerFlags().Expand().DoubleBorder(wx.BOTTOM))
            
        topsizer.AddF(sizer, wx.SizerFlags().Expand())
            
        return topsizer


    def getRememberCheck(self):
        """ Get the value of the 'remember' checkbox, if one was added. Call
            before destroying the dialog!
        """
        if not self.remember:
            return None
        return self.rememberCheck.GetValue()
    

# XXX: FOR DEVELOPMENT TESTING. REMOVE ME!
if __name__ == '__main__':# or True:
    app = wx.App()
    dlg = MemoryDialog(None, "Are you sure you want to overwrite the existing file?", "Testing", wx.YES|wx.CANCEL|wx.HELP|wx.ICON_QUESTION, remember=True)
    dlg.SetExtendedMessage("This is the extended message.")
    v = dlg.ShowModal()
    r = dlg.getRememberCheck()
    print "Dialog returned: %r" % v
    print "Remember check: %r" % r
#     app.MainLoop()