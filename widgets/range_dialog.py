'''
Created on May 6, 2014

@author: dstokes
'''
import wx; wx = wx;
from wx.lib.agw.floatspin import FloatSpin


class RangeDialog(wx.Dialog):
    """ A modal dialog for manually entering X and Y ranges for the active
        plot. This class also implements a method for creating and displaying
        the dialog, making it self-contained.
    """
    
    labelAtts = {'size': (30,-1),
                 'style': wx.ALIGN_RIGHT | wx.ALIGN_BOTTOM}
    unitAtts = {'style': wx.ALIGN_LEFT}
    
        
    def addRangeBox(self, sizer, title, units, val=[-100.0,100.0], 
                    minmax=[-100.0,100.0], digits=4):
        """ Helper method for adding a Start/End box. Used internally.
        """
        
        def _addField(label, v):
            ll = wx.StaticText(self,-1,label, **self.labelAtts)
            lf = FloatSpin(self, -1, value=v, increment=precision,
                              min_val=minmax[0], max_val=minmax[1])
            lf.SetDigits(digits)
            lu = wx.StaticText(self, -1, units[1], **self.unitAtts)
            lf.Bind(wx.EVT_TEXT_ENTER, self.OnEnter)
            return ll, lf, lu 
            
        precision = 1.0/(10**digits)

        box = wx.StaticBox(self, -1, "%s (%s)" % (title, units[0]))
        bsizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        gsizer = wx.FlexGridSizer(2,3, hgap=4, vgap=4)
        
        startLabel, startField, startUnits = _addField("Start:", val[0])
        endLabel, endField, endUnits = _addField("End:", val[1])

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
        """ Constructor. Takes the standard `wx.Window` parameters, plus:
            @keyword root: The parent `View` window.
        """
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
        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)
        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()
        
        outersizer.Add(btnsizer, 0, 
                       wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT|wx.ALL, 5)
        self.SetSizerAndFit(outersizer)


    def OnEnter(self, evt):
        """ Handler for 'enter' being typed; equivalent to OK.
        """ 
        self.EndModal(wx.ID_OK)


    def getValues(self):
        """ Get the entered start and end values for the X and Y axes.
        """
        return (sorted((self.xStartField.GetValue()/self.root.timeScalar, 
                        self.xEndField.GetValue()/self.root.timeScalar)),
                sorted((self.yStartField.GetValue(), 
                        self.yEndField.GetValue()))) 


    @classmethod
    def display(cls, parent, root=None):
        """ Display the Enter Range dialog modally and return the values
            entered. This function is the preferred way to create the dialog.
            
            @param parent: The parent window.
            @keyword root: The creator `Viewer` window. Defaults to `parent`.
            @return: A tuple of tuples: the start and end values, X and Y.
                `None` is returned if the dialog is cancelled.
        """
        root = parent if root is None else root
        try:
            p = root.plotarea.getActivePage()
            title = "Select Ranges for %s" % p.GetName()
        except AttributeError:
            title = "Select Ranges"
        dlg = cls(parent, -1, title, root=root)
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
    val = RangeDialog.display(None, root=FakeViewer())
    print "ranges: %r" % (val,)
