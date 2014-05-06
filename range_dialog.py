'''
Created on May 6, 2014

@author: dstokes
'''
import wx; wx = wx;
import wx.lib.agw.floatspin as FS


class RangeDialog(wx.Dialog):
    """
    """
    
    fieldAtts = {'size': (56,-1),
                 'style': wx.TE_PROCESS_ENTER | wx.TE_PROCESS_TAB}
    labelAtts = {'size': (30,-1),
                 'style': wx.ALIGN_RIGHT | wx.ALIGN_BOTTOM}
    unitAtts = {'style': wx.ALIGN_LEFT}
    
        
    def addRangeBox(self, sizer, title, units, val=[-100.0,100.0], 
                    minmax=[-100.0,100.0], digits=4):
        """
        """
        precision = 1.0/(10**digits)

        box = wx.StaticBox(self, -1, "%s (%s)" % (title, units[0]))
        bsizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        gsizer = wx.FlexGridSizer(2,3, hgap=4, vgap=4)
        
        startLabel = wx.StaticText(self,-1,"Start:", **self.labelAtts)
        startField = FS.FloatSpin(self, -1, min_val=minmax[0], max_val=minmax[1],
                                  increment=precision, value=val[0])
        startField.SetDigits(digits)
        startUnits = wx.StaticText(self, -1, units[1], **self.unitAtts)
        startField.Bind(wx.EVT_TEXT_ENTER, self.OnEnter)

        endLabel = wx.StaticText(self,-1,"End:", **self.labelAtts)
        endField = FS.FloatSpin(self, -1, min_val=minmax[0], max_val=minmax[1],
                                  increment=precision, value=val[1])
        endField.SetDigits(digits)
        endUnits = wx.StaticText(self, -1, units[1], **self.unitAtts)
        endField.Bind(wx.EVT_TEXT_ENTER, self.OnEnter)

        gsizer.AddGrowableCol(0,-2)
        gsizer.AddGrowableCol(1,-4)
        gsizer.AddGrowableCol(2,-1)
        
        gsizer.AddMany([
            (startLabel,-1, wx.ALIGN_CENTER|wx.ALIGN_RIGHT),
            (startField, 1),
            (startUnits, -1, wx.ALIGN_CENTER),
            (endLabel,-1, wx.ALIGN_CENTER|wx.ALIGN_RIGHT),
            (endField,1),
            (endUnits,0, wx.EXPAND|wx.ALIGN_CENTER),
         ])
         
        bsizer.Add(gsizer, 1, wx.EXPAND|wx.ALL)
        sizer.Add(bsizer, 1, wx.EXPAND|wx.ALL, 4)
        return startField, endField


    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop("root", None)
        super(RangeDialog, self).__init__(*args, **kwargs)

        outersizer = wx.BoxSizer(wx.VERTICAL)
        mainsizer = wx.BoxSizer(wx.HORIZONTAL)

        xUnits = ("seconds", "s")
        xRange = self.root.getTimeRange()
        xRange = (xRange[0] * self.root.timeScalar,
                  xRange[1] * self.root.timeScalar)
        xVis = self.root.getVisibleRange()
        xVis = (xVis[0] * self.root.timeScalar,
                xVis[1] * self.root.timeScalar)
 
        try:
            xDigits = self.root.app.getPref('precisionX', 4)
            yDigits = self.root.app.getPref('precisionY', 4)
            p = self.root.plotarea.getActivePage()
            yVis = p.getValueRange()
            yRange = p.source.displayRange
            yUnits = p.source.units
        except AttributeError:
            xDigits = 4
            yDigits = 4
            yUnits = ("g", "g")
            yRange = [-100,100]
            yVis = [-10,10]
        
        self.xStartField, self.xEndField = \
            self.addRangeBox(mainsizer, "X Axis", xUnits, xVis, xRange, xDigits)
            
        self.yStartField, self.yEndField = \
            self.addRangeBox(mainsizer, "Y Axis", yUnits, yVis, yRange, yDigits)

        outersizer.Add(mainsizer, 1, wx.EXPAND|wx.ALL, 2,4)
        
        btnsizer = wx.StdDialogButtonSizer()
        
        if wx.Platform != "__WXMSW__":
            btn = wx.ContextHelpButton(self)
            btnsizer.AddButton(btn)
        
        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)

        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()

        outersizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT|wx.ALL, 5)

        self.SetSizerAndFit(outersizer)
        print dir(self)


    def OnEnter(self, evt):
        # TODO: Validation? 
        self.EndModal(wx.ID_OK)


    def getValues(self):
        """
        """
        return ((self.xStartField.GetValue()/self.root.timeScalar, 
                 self.xEndField.GetValue()/self.root.timeScalar),
                (self.yStartField.GetValue(), 
                 self.yEndField.GetValue())) 


    @classmethod
    def display(cls, parent, root=None):
        """
        """
        root = parent if root is None else root
        dlg = cls(parent, -1, "Select Ranges", root=root)
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
    class Fake(object):
        timeScalar = 0.00001
        units = ("Things", "t")
        def getTimeRange(self):
            return [0.0, 9999.09]
        def getVisibleRange(self):
            return [0.0, 9999.09]

    app = wx.App()
    val = RangeDialog.display(None, root=Fake())
    print "ranges: %r" % (val,)
