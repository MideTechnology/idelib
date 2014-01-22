'''
Created on Nov 25, 2013

@author: dstokes
'''

from wx.lib.agw.genericmessagedialog import GenericMessageDialog
import wx; wx = wx


class CheckboxMessageDialog(GenericMessageDialog):
    """ Extended version of the standard GenericMessageDialog with an
        optional checkbox (e.g. to suppress the dialog from coming up again).
        Can be used as a (more-or-less) drop-in replacement for its
        superclass (`GenericMessageDialog`).
        
        The constructor takes an extra keyword argument: `check`. This should
        be either `None` or a 1 or 2 element list. The first element is the
        value of the checkbox and gets changed in place. The optional second
        element is a message string to display with the checkbox. If `check`
        is `None`, no checkbox appears.
    """

    def __init__(self, parent, message, caption, agwStyle,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.DEFAULT_DIALOG_STYLE|wx.WANTS_CHARS,
                 wrap=-1, check=None):
        """
        Default class constructor. See `wx.lib.agw.genericmessagedialog` for
        more info.

        :param `parent`: the L{GenericMessageDialog} parent (if any);
        :param `message`: the message in the main body of the dialog;
        :param `caption`: the dialog title;
        :param `agwStyle`: the AGW-specific dialog style; it can be one of the
         following bits:

         =========================== =========== ==================================================
         Window Styles               Hex Value   Description
         =========================== =========== ==================================================
         0                                     0 Uses normal generic buttons
         ``GMD_USE_AQUABUTTONS``            0x20 Uses L{AquaButton} buttons instead of generic buttons.
         ``GMD_USE_GRADIENTBUTTONS``        0x40 Uses L{GradientButton} buttons instead of generic buttons.
         =========================== =========== ==================================================

        :param `pos`: the dialog position on screen;
        :param `size`: the dialog size;
        :param `style`: the underlying `wx.Dialog` style;
        :param `wrap`: if set greater than zero, wraps the string in `message` so that
         every line is at most `wrap` pixels long.
        :param `check`: a 1 or 2 element list containing the checkbox value
            and (optionally) the message to display with the checkbox. The
            value of the first element gets changed in place.
        """

        self.check = check
        
        super(CheckboxMessageDialog, self).__init__(parent, message, caption,
                                                    agwStyle, pos=pos, 
                                                    size=size, style=style,
                                                    wrap=wrap)
        

    def CreateSeparatedButtonSizer(self, flags):
        """ Create a sizer for the standard buttons; also add the checkbox
            (if any). of the dialog contents by a horizontal `wx.StaticLine`.
            
            @see `CreateButtonSizer` for a list of valid flags.

            @param flags: the button sizer flags.
        """

        sizer = self.CreateButtonSizer(flags)
        
        if self.check is None:
            return sizer
            
        checkSizer = wx.BoxSizer(wx.VERTICAL)
        if len(self.check) == 1:
            checkMsg = "Don't show this message again"
        else:
            checkMsg = self.check[1]
        self.checkbox = wx.CheckBox(self, -1, checkMsg)
        self.checkbox.SetValue(self.check[0])
        checkSizer.AddF(self.checkbox, 
                        wx.SizerFlags().Expand().DoubleBorder(wx.BOTTOM).Right())

        self.checkbox.Bind(wx.EVT_CHECKBOX, self.OnCheckboxChange)
        checkSizer.AddF(sizer, wx.SizerFlags().Expand())
            
        return checkSizer


    def OnCheckboxChange(self, evt):
        self.check[0] = evt.IsChecked()



if True or __name__ == '__main__':
    # XXX: FOR DEV TESTING. REMOVE ME!
    app = wx.App()
    frame = wx.Frame(None, title="Test")
    foo = [False, "Don't show this message again"]
    print "check list before:",foo
    
    msg = "This is a test of the checkbox dialog.\n\n%s" %\
        " ".join((l.strip() for l in CheckboxMessageDialog.__doc__.split('\n')))
    dlg = CheckboxMessageDialog(frame, msg, "Confirm", 
                                wx.ICON_INFORMATION|wx.YES|wx.NO, 
                                style=wx.CAPTION, wrap=300, 
                                check=foo).ShowModal()
    print "Dialog returned %r" % dlg
    print "check list after:",foo
