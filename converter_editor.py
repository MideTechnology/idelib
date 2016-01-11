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
    """ Editor for unit conversion transforms. This should be launched using
        the `ConverterEditor.edit()` method.
    """
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        self.converter = kwargs.pop('converter', None)
        kwargs.setdefault('title', u'Configure Display %s as %s' % self.converter.units)
        kwargs.setdefault('style', wx.DEFAULT_DIALOG_STYLE)# | wx.RESIZE_BORDER)
        super(ConverterEditor, self).__init__(*args, **kwargs)
        
        self.prefName = self.converter.__class__.__name__.split('.')[-1]
        
        pane = self.GetContentsPane()
        pane.SetSizerType("form")

        self.fields = {}
        self.defaults = {}
        
        for pname, plabel, ptype, prange, pdefault in self.converter.parameters:
            wx.StaticText(pane, -1, plabel).SetSizerProps(valign="center")
            pval = getattr(self.converter, pname, pdefault)
            fid = wx.NewId()
            if ptype == float:
                field = wx.SpinCtrlDouble(pane, fid, value=str(pval),
                          min=prange[0], max=prange[1], inc=0.01)
            elif ptype == int:
                field = wx.SpinCtrlDouble(pane, fid, value=str(pval),
                          min=prange[0], max=prange[1])
            # FUTURE: Other types. Tuple for a list box, etc.
            else:
                field = wx.TextCtrl(pane, fid, str(pdefault))
            field.SetSizerProps(expand=True)
            self.fields[pname] = field
            self.defaults[field] = pdefault
        
        # Spacer
        wx.StaticText(pane, -1, "")
        wx.StaticText(pane, -1, "")
        
        wx.Button(pane, wx.ID_DEFAULT, "Defaults").SetSizerProps(halign="left")
        buttonpane = SC.SizedPanel(pane, -1)
        buttonpane.SetSizerType("horizontal")
        buttonpane.SetSizerProps(expand=True)
        SC.SizedPanel(buttonpane, -1).SetSizerProps(proportion=1) # Spacer
        self.Bind(wx.EVT_BUTTON, self.OnDefaultBtn, id=wx.ID_DEFAULT)
        wx.Button(buttonpane, wx.ID_OK).SetSizerProps(halign="right")
        wx.Button(buttonpane, wx.ID_CANCEL).SetSizerProps(halign="right")
        
        # a little trick to make sure that you can't resize the dialog to
        # less screen space than the controls need
        self.Fit()
        self.SetMinSize(self.GetSize())

    
    def OnDefaultBtn(self, evt):
        for f, v in self.defaults.items():
            # FUTURE: Special handing for other types (lists, etc.)
            f.SetValue(v)


    @classmethod
    def edit(cls, converter, parent=None):
        """ Create and display the unit conversion editing dialog.
        
            @param converter: The unit conversion object
            @keyword parent: The parent window
        """
        if converter is None or converter.parameters is None:
            return False
        
        dlg = cls(parent, -1, converter=converter)
        dlg.CenterOnParent()
        result = dlg.ShowModal()
        
        if result == wx.ID_OK:
            for k,f in dlg.fields.items():
                v = f.GetValue()
                setattr(converter, k, v)
                
                try:
                    wx.GetApp().setPref(k, v, section=dlg.prefName)
                except AttributeError:
                    pass
        
        dlg.Destroy()
        return result
            
#===============================================================================
# 
#===============================================================================

# FOR DEVELOPMENT TESTING. REMOVE ME!
if __name__ == '__main__':# or True:
    from mide_ebml.unit_conversion import Pressure2Meters
    
    app = wx.App()
    conv = Pressure2Meters()
    ConverterEditor.edit(conv)
    