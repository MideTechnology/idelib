'''
Created on Dec 31, 2013

@author: dstokes
'''
import wx.lib.sized_controls as sc

import wx; wx = wx


from math import ceil, sqrt

class ColorMenu(wx.PopupTransientWindow):
    """
    """
    def __init__(self, parent, colors, default=None, style=wx.SIMPLE_BORDER,
                 swatchSize=16):
        self.colors = colors
        super(ColorMenu, self).__init__(parent, style)
        
        squares = int(ceil(sqrt(len(colors))))
        print squares
        sizer = wx.GridSizer(squares, squares, 4, 4)
        outerSizer = wx.BoxSizer(wx.HORIZONTAL)
        
        swatchSize = wx.Size(swatchSize, swatchSize)
        for c in colors:
            print c
            swatch = wx.Panel(self, -1, size=swatchSize)
            swatch.SetBackgroundColour(c)
            sizer.Add(swatch, 0, wx.EXPAND).SetBorder(wx.RAISED_BORDER)
        
        outerSizer.Add(sizer, 1, wx.EXPAND | wx.ALL, 4)
        self.SetSizerAndFit(outerSizer)
        self.Layout()
#         self.SetInitialSize()


    def OnRollover(self, evt):
        """
        """
        obj = evt.GetEventObject()
        pass
        
        
    def OnMouseLeftUp(self, evt):
        pass



#===============================================================================
# 
#===============================================================================

class MultiDialog(sc.SizedDialog):
    """
    """
    def __init__(self, *args, **kwargs):
        """
        """
        style = wx.DEFAULT_DIALOG_STYLE

        self.root = kwargs.pop('root', None)
        kwargs.setdefault('style', style)

        super(MultiDialog, self).__init__(*args, **kwargs)
        
        pane = self.GetContentsPane()
        pane.SetSizerType("vertical")
        msgPane = sc.SizedPanel(pane, -1)

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__" or True:
    from random import randint
    
    def randColor():
        return wx.Color(*[randint(0,255) for _ in range(3)])
        
    class TestDlg(wx.Dialog):
        def __init__(self, *args, **kwargs):
            super(TestDlg, self).__init__(*args, **kwargs)
            b = wx.Button(self, -1, "Menu")
            b.Bind(wx.EVT_BUTTON, self.OnBtn)
        
        def OnBtn(self, evt):
#             colors = [randColor() for _ in range(16)]
            colors = [wx.Color(x,x,0) for x in range(0,255,16)]
            win = ColorMenu(self, colors)
            btn = evt.GetEventObject()
            pos = btn.ClientToScreen( (0,0) )
            sz =  btn.GetSize()
            win.Position(pos, (0, sz[1]))

            win.Popup()

    app = wx.App()
#     dlg = TestDlg(None, -1, "Test")
    dlg = MultiDialog(None, -1, "Test")
    dlg.ShowModal()
