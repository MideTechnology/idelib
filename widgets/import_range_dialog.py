'''
Created on May 6, 2014

@author: dstokes
'''
import locale

import wx; wx = wx;
from wx.lib.agw.floatspin import FloatSpin

from mide_ebml import importer
from timeline import TimeNavigatorCtrl


class ImportRangeDialog(wx.Dialog):
    """ A modal dialog for selecting a time range to import from a recording. 
        This class also implements a method for creating and displaying the 
        dialog, making it self-contained.
    """
    
    def addRangeBox(self, sizer, val=[-100.0,100.0], 
                    minmax=[-100.0,100.0], digits=4):
        """ Helper method for adding a Start/End box. Used internally.
        """
        
        labelAtts = {'size': (self.GetTextExtent(" Start: ")[0]+16,-1),
                     'style': wx.ALIGN_LEFT | wx.ALIGN_BOTTOM}
        unitAtts = {'style': wx.ALIGN_LEFT}
         
        def _addField(label, v, checked):
            lc = wx.CheckBox(self, -1, label, **labelAtts)
            lc.SetValue(checked)
            lf = FloatSpin(self, -1, value=v, increment=precision,
                              min_val=minmax[0], max_val=minmax[1])
            lf.SetDigits(digits)
            lf.Enable(checked)
            lu = wx.StaticText(self, -1, "s", **unitAtts)
            lc.Bind(wx.EVT_CHECKBOX, self.OnCheck)
            lf.Bind(wx.EVT_TEXT_ENTER, self.OnEnter)
            self.fields[lc] = lf
            return lc, lf, lu 
            
        precision = 1.0/(10**digits)

        gsizer = wx.FlexGridSizer(2,3, hgap=4, vgap=4)
        
        startLabel, startField, startUnits = _addField("Start:", val[0], True)
        endLabel, endField, endUnits = _addField("End:", val[1], False)

        gsizer.AddMany([
            (startLabel,-1, wx.ALIGN_CENTER|wx.ALIGN_RIGHT),
            (startField, 1),
            (startUnits, -1, wx.ALIGN_CENTER),
            (endLabel,-1, wx.ALIGN_CENTER|wx.ALIGN_RIGHT),
            (endField,1),
            (endUnits,0, wx.EXPAND|wx.ALIGN_CENTER),
         ])
         
        sizer.Add(gsizer)#, 1, wx.EXPAND|wx.ALL, 4)
        return startField, endField


    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard `wx.Window` parameters, plus:
            @keyword root: The parent `View` window.
        """
        self.root = kwargs.pop("root", None)
        self.filename = kwargs.pop("filename", None)
        kwargs.setdefault("style", 
            wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | \
            wx.MINIMIZE_BOX | wx.DIALOG_EX_CONTEXTHELP | wx.SYSTEM_MENU)
        super(ImportRangeDialog, self).__init__(*args, **kwargs)
        self.SetMinSize((400,100))
        self.SetSizeWH(800,100)
        
        start, end, self.samplesPerSec = importer.estimateLength(self.filename)
        self.samplesPerSec /= self.root.timeScalar
        xRange = (start * self.root.timeScalar, end * self.root.timeScalar)
        xVis = xRange
        
        self.fields = {}
        
        rightsizer = wx.BoxSizer(wx.VERTICAL)
        outersizer = wx.BoxSizer(wx.VERTICAL)
        mainsizer = wx.BoxSizer(wx.HORIZONTAL)

#         xVis = self.root.getVisibleRange()
#         xVis = (xVis[0] * self.root.timeScalar,
#                 xVis[1] * self.root.timeScalar)
#  
        xDigits = self.root.app.getPref('precisionX', 4)
        
        self.xStartField, self.xEndField = \
            self.addRangeBox(mainsizer, xVis, xRange, xDigits)
            
        self.timeline = TimeNavigatorCtrl(self, -1)
        self.timeline.SetRange(*xRange)
        self.timeline.setVisibleRange(*xVis)
        self.sampleCount = wx.StaticText(self, 1, "Range contains ~ 999,999,999 samples")
        rightsizer.Add(self.timeline, 1, wx.EXPAND|wx.ALIGN_RIGHT|wx.HORIZONTAL, 8)
        rightsizer.Add(self.sampleCount, 0, wx.ALIGN_CENTER)
    
        mainsizer.Add(rightsizer, 1, wx.EXPAND|wx.ALL, 2,4)
        outersizer.Add(mainsizer, 1, wx.EXPAND|wx.ALL, 2,4)
        outersizer.Add(wx.StaticText(self, -1, "\nNote: End time and sample count are only estimates. Actual values may vary."), 0, wx.ALIGN_CENTER, 16, 16)
        
        btnsizer = wx.StdDialogButtonSizer()
        btn = wx.Button(self, wx.ID_OK)
        btn.SetLabel("Import") # wxPython won't let me add arbitrary button IDs
        btn.SetDefault()
        btnsizer.AddButton(btn)
        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()
        
        outersizer.Add(btnsizer, 0, 
                       wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT|wx.ALL, 5)
        self.SetSizerAndFit(outersizer)
        s = self.GetSizeTuple()
        self.SetSizeWH(450,s[1])
        self.SetMinSize((400, s[1]))
        self.SetMaxSize((-1,s[1]))
        
        self.Bind(TimeNavigatorCtrl.EVT_INDICATOR_CHANGED, self.OnMarkChanged)
        self.OnMarkChanged(None)


    def OnMarkChanged(self, evt):
        if evt is not None:
            evt.Skip()
        v1, v2 = self.timeline.getVisibleRange()
        self.xStartField.SetValue(v1)
        self.xEndField.SetValue(v2)
        num = int((v2 - v1) * self.samplesPerSec)
        self.sampleCount.SetLabel("Range contains ~ %s samples" % \
                                  locale.format("%d", num, grouping=True))
        

    def OnCheck(self, evt):
        obj = evt.GetEventObject()
        self.fields[obj].Enable(obj.GetValue())


    def OnEnter(self, evt):
        """ Handler for 'enter' being typed; equivalent to OK.
        """ 
        self.EndModal(wx.ID_OK)


    def getValues(self):
        """ Get the entered start and end values for the X and Y axes.
        """
        return sorted((self.xStartField.GetValue()/self.root.timeScalar, 
                        self.xEndField.GetValue()/self.root.timeScalar))


    @classmethod
    def display(cls, parent, filename, root=None):
        """ Display the Enter Range dialog modally and return the values
            entered. This function is the preferred way to create the dialog.
            
            @param parent: The parent window.
            @keyword root: The creator `Viewer` window. Defaults to `parent`.
            @return: A tuple of tuples: the start and end values, X and Y.
                `None` is returned if the dialog is cancelled.
        """
        root = parent if root is None else root
        try:
            title = "Import Range..."
        except AttributeError:
            title = "Select Ranges"
        dlg = cls(parent, -1, title, filename=filename, root=root)
        d = dlg.ShowModal()
        if d != wx.ID_CANCEL:
            result = dlg.getValues()
        else:
            result = None
        dlg.Destroy()
        return result


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, 'English_United States.1252')

    # An ugly test fixture
    class FakePlot:
        class source:
            displayRange = [-100,100]
            units = ("g", "g")
            class parent:
                name = "Fake Channel"
        @staticmethod
        def getValueRange():
            return [-10,10]
        @staticmethod
        def GetName():
            return "Fake Channel"
    class FakeViewer(object):
        timeScalar = 0.00001
        units = ("Things", "t")
        def getTimeRange(self):
            return [0.0, 9999.09]
        def getVisibleRange(self):
            return [0.0, 9999.09]
        class plotarea:
            @staticmethod
            def getActivePage():
                return FakePlot()
        class app:
            @staticmethod
            def getPref(k, d):
                return d

    app = wx.App()
    val = ImportRangeDialog.display(None, "test_recordings/Garmin_temp.IDE", root=FakeViewer())
    print "ranges: %r" % (val,)
