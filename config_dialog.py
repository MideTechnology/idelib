'''
Created on Dec 16, 2013

@author: dstokes
'''

import string
import time

import wx.lib.sized_controls as sc
from wx.lib.masked import TimeCtrl

import wx; wx = wx


#===============================================================================
# 
#===============================================================================

class BaseConfigPanel(sc.SizedPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """

    def addField(self, labelText, fieldText="" ,fieldSize=(-1,-1), 
                 fieldStyle=None):
        """ Helper method to create and configure a labeled text field. 
        """
        txt = unicode(fieldText)
        c = wx.StaticText(self, -1, labelText)
        c.SetSizerProps(valign="center")
        if fieldStyle is None:
            t = wx.TextCtrl(self, -1, txt, size=fieldSize)
        else:
            t = wx.TextCtrl(self, -1, txt, size=fieldSize, style=fieldStyle)
        
        return t
    

    def addCheckField(self, checkText, fieldText="", fieldSize=(-1,-1), 
                      fieldStyle=None):
        """ Helper method to create and configure checkbox/field pairs, and add
            them to the set of controls.
        """
        txt = unicode(fieldText)
        c = wx.CheckBox(self, -1, checkText)
        c.SetSizerProps(valign="center")
        if fieldStyle is None:
            t = wx.TextCtrl(self, -1, txt, size=fieldSize)
        else:
            t = wx.TextCtrl(self, -1, txt, size=fieldSize, style=fieldStyle)
        self.controls[c] = [t]
        return c, t
    
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.root = kwargs.pop('root', None)
        super(BaseConfigPanel, self).__init__(*args, **kwargs)
        
        self.SetSizerType("form", {'hgap':10, 'vgap':10})
        self.controls = {}
        self.buildUI()
        self.initUI()
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckChanged)


    def buildUI(self):
        """ Create the UI elements within the page. Every subclass should
            implement this. Called after __init__() and before initUI().
        """
        pass


    def initUI(self):
        """ Do any setup work on the page. Most subclasses should override
            this.
        """
        for c in self.controls:
            self.enableAll(c)


    def enableAll(self, checkbox, state=True):
        """ Enable (or disable) all the other controls associated with a
            checkbox.
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


    def OnCheckChanged(self, evt):
        cb = evt.EventObject
        if cb in self.controls:
            self.enableAll(cb)

#===============================================================================
# 
#===============================================================================

class TriggerConfigPanel(BaseConfigPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """

    def buildUI(self):
        self.wakeCheck = wx.CheckBox(self, -1, "Wake at specific time:")
        self.wakeCheck.SetSizerProps(valign='center')
        wakePane = sc.SizedPanel(self, -1)
        wakePane.SetSizerType("horizontal")
        self.wakeDateField = wx.DatePickerCtrl(wakePane, style=wx.DP_DROPDOWN)
        self.wakeTimeField = TimeCtrl(wakePane, -1, fmt24hr=True)
        fieldSize = self.wakeDateField.GetSize()
        self.wakeTimeSpin = wx.SpinButton(wakePane, -1, 
            size=(-1,fieldSize.height), style=wx.SP_VERTICAL)
        self.wakeTimeField.BindSpinButton(self.wakeTimeSpin)
        
        self.controls[self.wakeCheck] = [self.wakeDateField, self.wakeTimeField,
                                         self.wakeTimeSpin]
        
        self.delayCheck, self.delayField = \
            self.addCheckField("Wake After Delay:", fieldSize=fieldSize)

        self.timeCheck, self.timeField = \
            self.addCheckField("Limit recording time to:", fieldSize=fieldSize)
        
        self.rearmCheck = wx.CheckBox(self, -1, "Re-triggerable")
        sc.SizedPanel(self, -1)
        
        self.controls[self.timeCheck].append(self.rearmCheck)
        
        self.accelTriggerCheck, self.accelTriggerField = \
            self.addCheckField("Accelerometer Trigger (High):", "", fieldSize)
        self.pressLoTrigger, self.pressLoTrigger = \
            self.addCheckField("Pressure Trigger (Low)", "", fieldSize)
        self.pressHiTrigger, self.pressHiTrigger = \
            self.addCheckField("Pressure Trigger (High)", "", fieldSize)
        self.tempLoTrigger, self.tempLoTrigger = \
            self.addCheckField("Temperature Trigger (Low)", "", fieldSize)
        self.tempHiTrigger, self.tempHiTrigger = \
            self.addCheckField("Temperature Trigger (High)", "", fieldSize)

        self.Bind(wx.EVT_DATE_CHANGED, self.OnDateChanged, self.wakeDateField)


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

class OptionsPanel(BaseConfigPanel):
    """ A configuration dialog page with miscellaneous editable recorder
        properties.
    """
    
    def buildUI(self):
        self.nameField = self.addField("Device Name:")
        self.nameField.SetSizerProps(expand=True)

        self.noteField = self.addField("Device Notes:", 
                                       fieldStyle=wx.TE_MULTILINE)
        noteSize = self.noteField.GetSize()
        self.noteField.SetSize((noteSize[0], noteSize[1]*3))
        self.noteField.SetSizerProps(expand=True)
      
        self.samplingCheck, self.samplingField = \
            self.addCheckField("Sampling Rate:",)
        
        self.oversamplingCheck = wx.CheckBox(self, -1, "Oversampling")
        sc.SizedPanel(self, -1) # Spacer
 
        self.timeBtn = wx.Button(self, -1, "Set Device Time")
        self.timeBtn.SetSizerProps(expand=True)
        timeFieldPane = sc.SizedPanel(self,-1)
        timeFieldPane.SetSizerType("horizontal")
        wx.StaticText(timeFieldPane, -1, "UTC Offset:"
                      ).SetSizerProps(valign='center')
        self.utcOffsetField = wx.TextCtrl(timeFieldPane, -1, "999")
        self.localTimeBtn = wx.Button(timeFieldPane, -1, "Get Local")
        self.localTimeBtn.SetToolTipString(time.tzname[time.daylight])
        
        self.Fit()
        
        self.timeBtn.Bind(wx.EVT_BUTTON, self.OnSetTime)
        self.localTimeBtn.Bind(wx.EVT_BUTTON, self.OnSetTZ)


    def OnSetTime(self, event):
        pass
    
    def OnSetTZ(self, event):
        val = str(time.timezone / 60 / 60) 
        self.utcOffsetField.SetValue(val)

#===============================================================================
# 
#===============================================================================
        
class InfoPanel(TriggerConfigPanel):
    """ A configuration dialog page showing various read-only properties of
        a recorder.
    """
    
    def buildUI(self):
        infoColor = wx.Colour(60,60,60)
        mono = wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL, False, 
                       u'monospace')
        
        sc.SizedPanel(self, -1) # Spacer
        wx.StaticText(self, -1, "All values are read-only"
                      ).SetForegroundColour("RED")
        
        for k,v in self.root.recorderInfo.iteritems():
            if isinstance(v, int) or isinstance(v, long):
                v = "0x%08X" % v
                
            t = self.addField('%s:' % k, v, fieldStyle=wx.TE_READONLY)
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
        
        # Dummy info
        self.recorderInfo = {"RecorderTypeUID": 0x000DEFEC,
                             "RecorderSerial": 0xD1DAC71C,
                             "SchemaID": 0x01,
                             "ProductName": "Slam Stick X",
                             "HwRev": 0x01,
                             "FwRev": 0x01
                             }
        
        pane = self.GetContentsPane()
        
        self.notebook = wx.Notebook(pane, -1)
        
        t = TriggerConfigPanel(self.notebook, -1, root=self)
        p = OptionsPanel(self.notebook, -1, root=self)
        info = InfoPanel(self.notebook, -1, root=self)

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

def configureRecorder(path):
    """
    """
    dlg = ConfigDialog(None, -1, "Configure Device (%s)" % path)
    dlg.ShowModal()    


#===============================================================================
# 
#===============================================================================

if True or __name__ == "__main__":
    app = wx.App()
    configureRecorder("e:\\")
