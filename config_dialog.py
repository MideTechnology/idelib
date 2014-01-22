'''
Created on Dec 16, 2013

@author: dstokes
'''

from numbers import Number
import string

import  wx.lib.scrolledpanel as scrolled
import wx.lib.sized_controls as sc
from wx.lib.masked import TimeCtrl
import  wx.lib.rcsizer  as rcs

import wx; wx = wx

#===============================================================================
# 
#===============================================================================

class TriggerPanel(wx.Panel):
    """
    """
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        super(TriggerPanel, self,).__init__(*args, **kwargs)
        


class TriggerList(scrolled.ScrolledPanel):
    pass


class TriggerConfigPanel(wx.Panel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        super(TriggerConfigPanel, self).__init__(*args, **kwargs)

        self.controls = {}
        outerSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(outerSizer)
        sizer = wx.FlexGridSizer(3,3,8,8)
        outerSizer.Add(sizer, 1, wx.EXPAND|wx.ALL, border=10)
        
        wakeSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.wakeCheck = wx.CheckBox(self, -1, "Wake at specific time:")
        self.wakeDateField = wx.DatePickerCtrl(self, size=(120,-1),
            style = wx.DP_DROPDOWN)#|wx.DP_ALLOWNONE )
        self.wakeTimeField = TimeCtrl(self, -1, fmt24hr=True)
        self.wakeTimeSpin = wx.SpinButton(self, -1, 
            size=(-1,self.wakeTimeField.GetSize().height), style=wx.SP_VERTICAL)
        self.wakeTimeField.BindSpinButton(self.wakeTimeSpin)
        sizer.Add(self.wakeCheck, -1, wx.ALIGN_CENTRE_VERTICAL)
        sizer.Add(self.wakeDateField, -1, wx.EXPAND)
        wakeSizer.Add(self.wakeTimeField, -1, wx.EXPAND)
        wakeSizer.Add(self.wakeTimeSpin, 0, wx.EXPAND)
        sizer.Add(wakeSizer, 2,0)
        
        self.controls[self.wakeCheck] = (self.wakeDateField, self.wakeTimeField, self.wakeTimeSpin)
        
        self.delayCheck = wx.CheckBox(self, -1, "Wake after delay:")
        self.delayField = wx.TextCtrl(self, -1, size=self.wakeDateField.GetSize())
#         self.delayUnitsList = wx.Choice(self, -1, choices=['Seconds','Minutes','Hours'])
        sizer.Add(self.delayCheck, -1, wx.ALIGN_CENTRE_VERTICAL)
        sizer.Add(self.delayField, -1, wx.EXPAND)
#         sizer.Add(self.delayUnitsList, 0, wx.EXPAND)
        sizer.Add(wx.BoxSizer())

        self.controls[self.delayCheck] = (self.delayField, )#self.delayUnitsList)

        self.timeCheck = wx.CheckBox(self, -1, "Limit recording time to:")
        self.timeField = wx.TextCtrl(self, -1, size=self.wakeDateField.GetSize())
        self.rearmCheck = wx.CheckBox(self, -1, "Re-triggerable")
#         self.timeUnitsList = wx.Choice(self, -1, choices=['Seconds','Minutes','Hours'])
        sizer.Add(self.timeCheck, -1, wx.EXPAND|wx.ALIGN_CENTRE_VERTICAL)
        sizer.Add(self.timeField, -1, wx.EXPAND)
        sizer.AddStretchSpacer()
         
        
        sizer.Add(self.rearmCheck, -1, wx.EXPAND|wx.ALIGN_CENTRE_VERTICAL)
        sizer.AddStretchSpacer()
        sizer.AddStretchSpacer()
        
        self.controls[self.timeCheck] = (self.rearmCheck, )
        
        
        
        self.Bind(wx.EVT_DATE_CHANGED, self.OnDateChanged, self.wakeDateField)
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckChanged)

        self.initUI()


    def initUI(self):
        """
        """
        for c in self.controls:
            self.enableAll(c)


    def enableAll(self, checkbox, state=True):
        """
        """
        for c in self.controls[checkbox]:
            c.Enable(checkbox.GetValue())
        

    def parseTime(self, timeStr):
        """ Turn a string containing a length of time as S.s, M:S.s, or H:M:S.s
            into the corresponding number of seconds
        """
        t = map(lambda x: float(x.strip(string.letters+" ,")), 
                reversed(timeStr.strip().replace(',',':').split(':')))
        if len(t) > 4:
            raise ValueError("Time had too many columns to parse: %r" % timeStr)
        if len(t) == 4:
            total = t.pop() * (24*60*60)
        else:
            total = 0
        for i in xrange(len(t)):
            total += t[i] * (60**i)
        return total


    def OnDateChanged(self, evt):
        evt.Skip()


    def OnCheckChanged(self, evt):
        cb = evt.EventObject
        if cb in self.controls:
            self.enableAll(cb)
            if cb == self.delayCheck or cb == self.wakeCheck:
                other = self.delayCheck if cb == self.wakeCheck else self.wakeCheck
                other.SetValue(False)
                self.enableAll(other)

#===============================================================================
# 
#===============================================================================

class OptionsPanel(sc.SizedPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop("root", None)
        super(OptionsPanel,self).__init__(*args, **kwargs)
        self.SetSizerType("form")#, {'hgap':10, 'vgap':10})
        
        wx.StaticText(self, -1, "Device Name:").SetSizerProps(valign='center')
        self.nameField = wx.TextCtrl(self, -1, "Slam Stick X")
        self.nameField.SetSizerProps(expand=True)
      
        sc.SizedPanel(self, -1)
        sc.SizedPanel(self, -1)
        
        self.samplingCheck = wx.CheckBox(self, -1, "Sampling Frequency:")
        self.samplingField = wx.TextCtrl(self, -1, "5000")
        
        self.oversamplingCheck = wx.CheckBox(self, -1, "Oversampling")
        sc.SizedPanel(self, -1)
 
        self.timeBtn = wx.Button(self, -1, "Set Device Time")
        self.timeBtn.SetSizerProps(expand=True)
        timeFieldPane = sc.SizedPanel(self,-1)
        timeFieldPane.SetSizerType("horizontal")
        wx.StaticText(timeFieldPane, -1, "UTC Offset:"
                      ).SetSizerProps(valign='center')
        self.utcOffsetField = wx.TextCtrl(timeFieldPane, -1, "999")
        self.localTimeBtn = wx.Button(timeFieldPane, -1, "Get Local")
        
        self.Fit()
        
#===============================================================================
# 
#===============================================================================
        
class InfoPanel(sc.SizedPanel):
    """ A configuration dialog page showing various read-only properties of
        a recorder.
    """
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop("root", None)
        self.props = kwargs.pop("props", {})
        
        super(InfoPanel,self).__init__(*args, **kwargs)
        self.SetSizerType("form", {'hgap':10, 'vgap':10})
    
        infoColor = wx.Colour(60,60,60)
        mono = wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL, False, 
                       u'monospace')
        
        sc.SizedPanel(self, -1)
        wx.StaticText(self, -1, "All values are read-only"
                      ).SetForegroundColour("RED")
        
        for k,v in self.props.iteritems():
            wx.StaticText(self, -1, '%s:' % k).SetSizerProps(valign='center')
            
            if isinstance(v, int) or isinstance(v, long):
                v = "0x%08x" % v
            t = wx.TextCtrl(self, -1, unicode(v), style=wx.TE_READONLY)
            t.SetSizerProps(expand=True)
            t.SetFont(mono)
            t.SetForegroundColour(infoColor)
    
        self.Fit()



        
#===============================================================================
# 
#===============================================================================

class ConfigDialog(sc.SizedDialog):
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | \
            wx.MINIMIZE_BOX | wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
        
        super(ConfigDialog, self).__init__(*args, **kwargs)
        
        pane = self.GetContentsPane()
        
        self.notebook = wx.Notebook(pane, -1)
        
        t = TriggerConfigPanel(self.notebook, -1)
        p = OptionsPanel(self.notebook, -1)
        info = InfoPanel(self.notebook, -1, props={"RecorderTypeUID": 12345})

        self.notebook.AddPage(p, "General")
        self.notebook.AddPage(t, "Triggers")
        self.notebook.AddPage(info, "Device Info")
        
        self.notebook.SetSizerProps(expand=True, proportion=-1)

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.okButton = self.FindWindowById(wx.ID_OK)
        self.Fit()

#===============================================================================
# 
#===============================================================================

if True or __name__ == "__main__":
    app = wx.App()
    dlg = ConfigDialog(None, -1, "Preferences", size=(640,480))
    dlg.ShowModal()