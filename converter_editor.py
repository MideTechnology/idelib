'''
Created on Mar 24, 2015

@author: dstokes
'''

import wx; wx=wx
import wx.lib.sized_controls as SC


#===============================================================================
# 
#===============================================================================

class ConverterEditor(SC.SizedDialog):
    """
    """
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        self.converter = kwargs.pop('converter', None)
        kwargs.setdefault('title', u'Configure Display %s as %s' % self.converter.units)
        kwargs.setdefault('style', wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        super(ConverterEditor, self).__init__(*args, **kwargs)
        
        pane = self.GetContentsPane()
        pane.SetSizerType("form")

        fields = {}
        
        for pname, plabel, ptype, prange, pdefault in self.converter.parameters:
            wx.StaticText(pane, -1, plabel).SetSizerProps(valign="center")
            fid = wx.NewId()
            if ptype == float:
                field = wx.SpinCtrlDouble(pane, fid, value=str(pdefault),
                          min=prange[0], max=prange[1], inc=0.01)
            elif ptype == int:
                field = wx.SpinCtrlDouble(pane, fid, value=str(pdefault),
                          min=prange[0], max=prange[1])
            # TODO: Other types. Tuple for a list box, etc.
            else:
                field = wx.TextCtrl(pane, fid, str(pdefault))
            field.SetSizerProps(expand=True)
            fields[pname] = field
            
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        
        # a little trick to make sure that you can't resize the dialog to
        # less screen space than the controls need
        self.Fit()
        self.SetMinSize(self.GetSize())
    
    @classmethod
    def getDefaults(cls, converter):
        pass


# XXX: FOR DEVELOPMENT TESTING. REMOVE ME!
if __name__ == '__main__':# or True:
    from mide_ebml.unit_conversion import Pressure2Meters
    
    app = wx.App()
    
    conv = Pressure2Meters()
    
    dlg = ConverterEditor(None, -1, converter=conv)
    dlg.CenterOnScreen()
    dlg.ShowModal()
    