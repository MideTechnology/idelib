"""
"""
from __future__ import absolute_import, print_function

import wx
import wx.lib.agw.genericmessagedialog as GMD
from wx.lib.wordwrap import wordwrap


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
        if len(args) > 3:
            style = args[3]
        else:
            style = kwargs.get('style', 0)
        if style & (wx.YES_NO):
            defaultMsg = "Don't Ask Again"
        else:
            defaultMsg = "Don't show this message again"
        self.remember = kwargs.pop('remember', False)
        self.rememberMsg = kwargs.pop('rememberMsg', None) or defaultMsg
        self.rememberDefault = kwargs.pop('rememberDefault', False)
        super(MemoryDialog, self).__init__(*args, **kwargs)
        
        if 'size' in kwargs:
            self.SetMinSize(kwargs.get('size'))


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
        Creates a sizer with standard buttons using 
        :meth:`~GenericMessageDialog.CreateButtonSizer` separated from the rest
        of the dialog contents by a horizontal :class:`StaticLine`.

        :param `flags`: the button sizer flags.

        :see: :meth:`~GenericMessageDialog.CreateButtonSizer` for a list of
            valid flags.
        """
        sizer = self.CreateButtonSizer(flags)
        topsizer = wx.BoxSizer(wx.VERTICAL)
        
        if self.remember:
            margin = self.Children[0].GetSize()
            checkSizer = wx.BoxSizer(wx.HORIZONTAL)
            checkSizer.Add((margin[0]+10, margin[1]), 0, wx.EXPAND, 10)
            self.rememberCheck = wx.CheckBox(self, -1, self.rememberMsg, 
                                             pos=(100,-1))
            checkSizer.Add(self.rememberCheck, wx.SizerFlags().Expand())
            topsizer.Add(checkSizer, wx.SizerFlags().Expand())
            self.rememberCheck.SetValue(self.rememberDefault)
        
        # Mac Human Interface Guidelines recommend not to use static lines as
        # grouping elements
        if wx.Platform != "__WXMAC__":
            topsizer.Add(wx.StaticLine(self), 
                         wx.SizerFlags().Expand().DoubleBorder(wx.BOTTOM))
            
        topsizer.Add(sizer, wx.SizerFlags().Expand())
            
        return topsizer


    def getRememberCheck(self):
        """ Get the value of the 'remember' checkbox, if one was added. Call
            before destroying the dialog!
        """
        if not self.remember:
            return None
        return self.rememberCheck.GetValue()
    

#===============================================================================
# 
#===============================================================================

def ask(parent, message, title="Confirm", style=wx.YES_NO | wx.NO_DEFAULT,
        icon=wx.ICON_QUESTION, prefs=None, pref=None, saveNo=True,
        extendedMessage=None, rememberMsg=None, persistent=True,
        textwrap=400):
    """ Generate a message box to notify or prompt the user, allowing for
        a simple means of turning off such warnings and prompts. If a
        preference name is supplied and that preference exists, the user
        will not be prompted and the remembered value will be returned. If
        the preference doesn't exist, the dialog will contain a 'remember'
        checkbox that, if checked, will save the user's response as the
        preference. "Cancel" (if the dialog has the button) will never be
        saved.

        @param parent: The dialog's parent.
        @param message: The main message/prompt to display
        @keyword title: The dialog's title
        @keyword style: Standard wxWindows style flags
        @keyword icon: The wxWindows style flag for the icon to display.
            Separated from `style` because `MemoryDialog` always needs an
            icon, making it behave differently than normal dialogs.
        @keyword prefs: The `Preferences` object containing the preferences.
        @keyword pref: The name of the preference to load and/or save
        @keyword extendedMessage: A longer, more detailed message.
        @keyword rememberMessage: The prompt next to the 'remember'
            checkbox (if shown).
        @keyword persistent: If `False` and 'remember' is checked, the
            result is saved in memory but not written to disk.
    """
    style = (style | icon) if icon else style
    if prefs is None:
        prefs = getattr(parent, 'prefs', None)

    if prefs is not None:
        if pref is not None and prefs.hasPref(pref, section="ask"):
            return prefs.getPref(pref, section="ask")
    else:
        pref = None
        
    remember = pref is not None

    if "\n\n" in message:
        message, ext = message.split('\n\n', 1)
        if extendedMessage:
            extendedMessage = '\n'.join((ext,extendedMessage))
        else:
            extendedMessage = ext

    dlg = MemoryDialog(parent, message, title, style, remember=remember,
                       rememberMsg=rememberMsg)
    if extendedMessage:
        if textwrap:
            extendedMessage = wordwrap(extendedMessage, textwrap,
                                       wx.ClientDC(dlg))
        dlg.SetExtendedMessage(extendedMessage)

    result = dlg.ShowModal()
    savePref = result != wx.ID_CANCEL or (result == wx.ID_NO and saveNo)
    if pref is not None and savePref:
        if dlg.getRememberCheck():
            prefs.setPref(pref, result, "ask", persistent)
    dlg.Destroy()
    return result


#===============================================================================
# 
#===============================================================================

# # XXX: FOR DEVELOPMENT TESTING. REMOVE ME!
# if __name__ == '__main__':# or True:
#     app = wx.App()
#     dlg = MemoryDialog(None,
#                        "Are you sure you want to overwrite\n"
#                        "the existing file?",
#                        "Testing", wx.YES|wx.CANCEL|wx.HELP|wx.ICON_QUESTION,
#                        size=(800,-1), remember=True)
#     dlg.SetExtendedMessage("This is the extended message.")
#     v = dlg.ShowModal()
#     print("size: {}".format(dlg.GetSize()))
#     r = dlg.getRememberCheck()
#     print("Dialog returned: %r" % v)
#     print("Remember check: %r" % r)
# #     app.MainLoop()