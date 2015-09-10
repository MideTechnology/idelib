
import wx
import wx.lib.sized_controls as SC

from mide_ebml.calibration import Transform, Univariate, Bivariate

#===============================================================================
# 
#===============================================================================

def cleanSplit(s, dtype=float):
    return tuple(map(dtype, [x for x in s.strip().split() if len(x) > 0]))

#===============================================================================
# 
#===============================================================================

class CoeffValidator(wx.PyValidator):
    """ Validator for a text field containing coefficients.
    """
    NAME = "coefficients"
    
    def __init__(self, minItems=1, maxItems=2, root=None, polyType=''):
        """ Standard constructor.
        """
        self.min = minItems
        self.max = maxItems
        self.root = root
        self.msg = ""
        self.polyType = polyType
        wx.PyValidator.__init__(self)


    def Clone(self):
        """ Standard cloner. Note that every validator must implement the 
            Clone() method.
        """
        return self.__class__(self.min, self.max, self.root, self.polyType)


    def Validate(self, win):
        return self.manualValidate(self.GetWindow(), quiet=False)


    def manualValidate(self, textCtrl, quiet=True):
        """ Validate the contents of the given text control. This Validator is
            also serving as a 'live' check of field contents, so it can be
            called apart from the wxWindows validation mechanism.
        """
        try:
            vals = cleanSplit(textCtrl.GetValue())
            num = len(vals)
        except ValueError:
            vals = None
            num = 0

        ptype = ("%s polynomial" % self.polyType).strip().capitalize()
        if vals is None:
            err = "Invalid characters in %s!" % self.NAME
        elif self.min == self.max and self.min != num:
            err = "%s must have exactly %d %s, %d given!" % (ptype, self.min, self.NAME, num)
        elif self.max is None and num < self.min:
            err = "%s must have at least %d %s, %d given!" % (ptype, self.min, self.NAME, num)
        elif num < self.min or num > self.max:
            err = "%s must have %d to %d %s, %d given!" % (ptype, self.min, self.max, self.NAME, num)
        else:
            err = None
        
        self.msg = err
        
        if err is not None:
            textCtrl.errIcon.SetBitmap(self.root.errBmp)
            textCtrl.errIcon.SetToolTipString(err)
#             textCtrl.SetBackgroundColour(self.root.errColor)

            if not quiet:
                wx.MessageBox(err, "Error")
                textCtrl.SetFocus()
            textCtrl.Refresh()
            return False
        else:
            textCtrl.SetBackgroundColour(self.root.bgColor)
            textCtrl.errIcon.SetBitmap(self.root.noBmp)
            textCtrl.errIcon.UnsetToolTip()
            textCtrl.Refresh()
            return True


    def TransferToWindow(self):
        """ Transfer data from validator to window.

            The default implementation returns False, indicating that an error
            occurred.  We simply return True, as we don't do any data transfer.
        """
        return True # Prevent wxDialog from complaining.


    def TransferFromWindow(self):
        """ Transfer data from window to validator.

            The default implementation returns False, indicating that an error
            occurred.  We simply return True, as we don't do any data transfer.
        """
        return True # Prevent wxDialog from complaining.

#===============================================================================

class RefValidator(CoeffValidator):
    NAME = "reference value(s)"
    
#===============================================================================
# 
#===============================================================================

class PolyEditDialog(SC.SizedDialog):
    """
    """
    ID_UNIVARIATE = wx.NewId()
    ID_BIVARIATE = wx.NewId()
    
    CAL_TYPE = Univariate
    DEFAULT_TITLE = "Edit Polynomial"
    DEFAULT_COEFFS = (1,0)
    DEFAULT_REFS = (1,)
    NUM_COEFFS = (2,2)
    NUM_REFS = (1,1)
    
    FIELD_PAD = 8 # Padding for use when calculating field height
    
    #===========================================================================
    # Helper methods. Does the busywork associated with adding controls with
    # labels and warning icons.
    #===========================================================================
    
    def _tostr(self, l):
        if isinstance(l, (list, tuple)):
            return '\n'.join(map(str, l))
        return str(l)
    
    def _addsubpane(self):
        # Helper helper. Don't use directly.
        subpane = SC.SizedPanel(self.pane, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)
        return subpane
        
    def _addfield(self, label, default=None, lines=1, **kwargs):
        """ Helper method to add a text field. """
#         if isinstance(default, (list, tuple)) and lines == 1:
#             lines = len(default)
        default = self._tostr(default)
        if lines > 1:
            kwargs['style'] = (kwargs.get('style', 0) 
                               | wx.TE_MULTILINE | wx.TE_PROCESS_ENTER)
            kwargs['size'] = (-1, (self.lineHeight * lines)+self.FIELD_PAD)
        txt = wx.StaticText(self.pane, -1, label)
        subpane = self._addsubpane()
        t = wx.TextCtrl(subpane, -1, unicode(default), **kwargs)
        t.SetSizerProps(expand=True, proportion=1)
        icon = wx.StaticBitmap(subpane, -1, self.noBmp)
        icon.SetSizerProps(proportion=0, expand=False, valign="center")
        t.errIcon = icon
        return txt, t
    
    def _addchoice(self, label, items, selected=None, enabled=True, **kwargs):
        """ Helper method to add a 'choice' widget (e.g. dropdown menu). """
        wx.StaticText(self.pane, -1, label).SetSizerProps(valign="center")
        subpane = self._addsubpane()
        c = wx.Choice(subpane, -1, choices=items, **kwargs)
        c.SetSizerProps(expand=True, proportion=1)
        if selected is not None:
            c.SetSelection(selected)
        icon = wx.StaticBitmap(subpane, -1, self.noBmp)
        icon.SetSizerProps(proportion=0, expand=False, valign="center")
        c.errIcon = icon
        c.Enable(enabled)
        return c

    #===========================================================================
    # 
    #===========================================================================
    
    def __init__(self, parent, wxId, cal=None, channel=None, dataset=None, 
                 polyType=None, changeType=True, **kwargs):
        """
        """
        self.dataset = dataset
        self.cal = cal
        self.channel = channel
        self.polyType = polyType
        self.changeType = changeType
        self.prevType = None
        self.originalCal = None
        
        self.calSubchannel = None

        if isinstance(self.cal, Transform):
            self.originalCal = cal
            self.cal = self.cal.copy()
            if self.polyType is None:
                self.polyType = self.cal.__class__
            if isinstance(self.cal, Bivariate) and self.dataset is not None:
                try:
                    self.calSubchannel = self.dataset.channels[self.cal.channelId][self.cal.subchannelId]
                except (IndexError, KeyError):
                    pass
                
        
        kwargs.setdefault('style', wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        super(PolyEditDialog, self).__init__(parent, wxId, **kwargs)

        # Error icons and window background color.
        self.noBmp = wx.EmptyBitmapRGBA(16,16,0,0,0,1.0)
        self.errBmp = wx.ArtProvider.GetBitmap(wx.ART_ERROR, wx.ART_CMN_DIALOG, (16,16))
        self.bgColor = wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW)
        self.errColor = "pink"

        self.buildUI()
        
        if not self.changeType:
            self.uniBtn.Enable(False)
            self.biBtn.Enable(False)
            
        if self.polyType == Bivariate:
            self.biBtn.SetValue(True)
            self.sourceList.Enable(True)
        else:
            self.uniBtn.SetValue(True)
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        s = self.GetSize()
        self.SetMinSize(s)
        self.SetSize((400,s[1]))
        self.SetMaxSize((-1, s[1]))
        
        self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)


    def onCancel(self, evt):
        """ Handle dialog cancel.
        """
        # Reset `self.cal` to the original (no changes)
        self.cal = self.originalCal
        evt.Skip()


    def buildUI(self):
        """ Subclass-specific UI stuff goes here.
        """
        if self.cal is not None:
            coeffs = self.cal.coefficients
            ref = self.cal.references
        else:
            coeffs = self.DEFAULT_COEFFS
            ref = self.DEFAULT_REFS
        
        if self.cal is None:
            if len(self.dataset.transforms) > 0:
                self.calId = max(self.dataset.transforms) + 1
            else:
                self.calId = 0
            self.calLabel = '%d (New)' % self.calId
        else:
            self.calId = self.cal.id
            self.calLabel = '%d' % self.calId
        
        self.pane = self.GetContentsPane()
        self.pane.SetSizerType("form")
        
        typeTxt = wx.StaticText(self.pane, -1, "Polynomial Type:")
        self.lineHeight = typeTxt.GetTextExtent("yY")[1] 
        subpane = self._addsubpane()
        self.uniBtn = wx.RadioButton(subpane, self.ID_UNIVARIATE, "Univariate")
        self.biBtn = wx.RadioButton(subpane, self.ID_BIVARIATE, "Bivariate")
        
        self.buildSourceList()
        self.sourceList = self._addchoice("Source", self.sourceNames, enabled=False)
        
        # If the type can't be changed, size fields appropriately
        if not self.changeType:
            clines = len(coeffs)
            rlines = len(ref)
        else:
            clines = 4
            rlines = 2
        
        self.coeffLbl, self.coeffField = self._addfield("Coefficients", coeffs, 
                                                        lines=clines)
        self.refLbl, self.refField = self._addfield("References", ref, 
                                                    lines=rlines)

        pLbl, self.polyText = self._addfield("Polynomial", style=wx.TE_READONLY)
        pLbl.SetSizerProps(valign="center")

        # Bind loss of focus to auto-validate fields on the fly.
        self.coeffField.Bind(wx.EVT_KILL_FOCUS, self.OnLoseFocus)
        self.refField.Bind(wx.EVT_KILL_FOCUS, self.OnLoseFocus)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnTypeChanged)
        
        self.updateUI()


    def updateUI(self):
        """
        """
        if self.polyType == Univariate:
            self.NUM_COEFFS = (2,2)
            self.NUM_REFS = (1,1)
            self.sourceList.Enable(False)
        else:
            self.NUM_COEFFS = (4,4)
            self.NUM_REFS = (2,2)
            self.sourceList.Enable(True)
            if self.calSubchannel in self.sources:
                self.sourceList.SetSelection(self.sources.index(self.calSubchannel))
            
        if self.polyType != self.prevType:
            ptype = self.polyType.__name__
            coeffVal = CoeffValidator(*self.NUM_COEFFS, root=self, polyType=ptype)
            refVal = RefValidator(*self.NUM_REFS, root=self, polyType=ptype)
            self.coeffField.SetValidator(coeffVal)
            self.refField.SetValidator(refVal)
            self.prevType = self.polyType

        if self.NUM_COEFFS[0] == self.NUM_COEFFS[1]:
            clabel = "Coefficients (%d)" % self.NUM_COEFFS[0]
        else:
            clabel = "Coefficients (%d-%d)" % self.NUM_COEFFS
        if self.NUM_REFS[0] == self.NUM_REFS[1]:
            if self.NUM_REFS == 1:
                rlabel = "Reference" 
            else: 
                rlabel = "References (%d)" % self.NUM_REFS[0]
        else:
            rlabel = "References (%d-%d)" % self.NUM_REFS
        self.coeffLbl.SetLabelText(clabel)
        self.refLbl.SetLabelText(rlabel)

        self.prevType = self.polyType
        for field in (self.coeffField, self.refField):
            self.updatePoly(field.GetValidator().manualValidate(field, quiet=True))
        

    def OnLoseFocus(self, evt):
        """ Auto-validate fields when moving from one to another. 
        """
        obj = evt.GetEventObject()
        self.updatePoly(obj.GetValidator().manualValidate(obj, quiet=True))
        evt.Skip()


    def updatePoly(self, valid=True):
        """ Get data from the dialog and update the polynomial. Also draws it.
        """
        if not valid or self.cal is None:
            self.polyText.SetValue("")
            return
        
        try:
            coeffs = cleanSplit(self.coeffField.GetValue())
            refs = cleanSplit(self.refField.GetValue())
            self.cal.coefficients = coeffs
            self.cal.references = refs
            self.polyText.SetValue(str(self.cal))
            if self.polyType == Bivariate:
                idx = self.sourceList.GetSelection()
                if idx != wx.NOT_FOUND:
                    source = self.sources[idx]
                    self.cal.channelId = source.parent.id
                    self.cal.subchannelId = source.id
            return True
        except (ValueError, TypeError):
            self.polyText.SetValue("")
            return False


    def buildSourceList(self):
        """ Get a list of all Channels using the current calibration polynomial.
        """
        self.sources = []
        self.sourceNames = []
        if self.dataset is not None:
            for source in self.dataset.getPlots(plots=False, sort=False):
                if self.channel is not None:
                    if source == self.channel or source == self.channel.parent:
                        continue
                self.sources.append(source)
                self.sourceNames.append("%d:%d %s" % (source.parent.id,
                                                      source.id,
                                                      source.displayName))
            

    def OnTypeChanged(self, evt):
        """
        """
        if evt.GetEventObject().GetId() == self.ID_UNIVARIATE:
            self.polyType = Univariate
        else:
            self.polyType = Bivariate
        self.updateUI()


    #===========================================================================
    # 
    #===========================================================================
    
#     def editPolynomial(self, cal, dataset=None):

#===============================================================================
# 
#===============================================================================



#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    from mide_ebml import importer
    doc = importer.importFile()
#     print doc.transforms
    
    app = wx.App()
    
    def show(d, title="Edit Polynomial", cal=1, **kwargs):
        d = d(None, -1, title=title, dataset=doc, cal=doc.transforms[cal], **kwargs)
        d.ShowModal()
        cal = d.cal
        d.Destroy()
        return cal
    
    print "%r" % show(PolyEditDialog)
    print "%r" % show(PolyEditDialog, changeType=False)
    print "%r" % show(PolyEditDialog, cal=0, changeType=False)
    
    app.MainLoop()
