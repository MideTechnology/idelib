'''
Created on Sep 15, 2015

@author: dstokes
'''
import wx
import wx.lib.sized_controls as SC

from widgets.htmlwindow import SaferHtmlWindow

#===============================================================================
# 
#===============================================================================

class HtmlDialog(SC.SizedDialog):
    """
    """
    
    DEFAULT_SIZE = (620,460)
    DEFAULT_STYLE = (wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | \
                     wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX | \
                     wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
    DEFAULT_BUTTONS = wx.OK

    def __init__(self, parent, content, title, buttons=DEFAULT_BUTTONS,
                 size=DEFAULT_SIZE, pos=wx.DefaultPosition, style=DEFAULT_STYLE, 
                 wxid=-1, setBgColor=True, plaintext=False):
        """
        """
        if style & 0b1111:
            buttons = style & 0b1111
        style = style & (2**32-1 ^ 0b111)
        
        super(HtmlDialog, self).__init__(parent, wxid, title, style=style)

        if plaintext:
            content = u'<pre>%s</pre>' % content

        if setBgColor:
            bg = "#%02x%02x%02x" % self.GetBackgroundColour()[:3]
            content = u'<body bgcolor="%s">%s</body>' % (bg, content)
        
        pane = self.GetContentsPane()
        html = SaferHtmlWindow(pane, -1, style=wx.BORDER_THEME)
        html.SetSizerProps(expand=True, proportion=1)
        html.SetPage(content)
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(buttons))

        self.Bind(wx.EVT_BUTTON, self.OnButton)

        self.Fit()
        self.SetSize(size)


    def OnButton(self, evt):
        self.EndModal(evt.GetEventObject().GetId())


#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    responses = {getattr(wx, x): x for x in ('ID_OK','ID_CANCEL','ID_YES','ID_NO')}
    with open('../updater files/slam_stick_lab_changelog.html', 'rb') as f:
        contents = f.read()
    app = wx.App()
    dlg = HtmlDialog(None, 
                     contents, #"<h1>Test</h1><p>This is the body.</p>", 
                     "Test Title", 
#                     style=wx.DEFAULT_DIALOG_STYLE|wx.YES_NO,
#                     buttons=wx.YES_NO|wx.CANCEL, 
                     setBgColor=False,
                     plaintext=False)
    r = dlg.ShowModal()
    print "Returned %r (%s)" % (r, responses.get(r, 'Unknown'))
    dlg.Destroy()
    