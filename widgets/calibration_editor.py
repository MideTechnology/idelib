"""
"""

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
    """ Validator for a text field containing polynomial coefficients.
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
        self.polyName = ("%s polynomial" % self.polyType).strip().capitalize()
        self.varName = self.NAME
        self.num = 0
        
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

        self.num = num
        
        if vals is None:
            err = "Invalid characters in %s!" % self.varName
        elif self.min == self.max and self.min != num:
            err = "%(polyName)s must have exactly %(min)d %(varName)s, %(num)d given!" % self.__dict__
        elif self.max is None and num < self.min:
            err = "%(polyName)s must have at least %(min)d %(varName)s, %(num)d given!" % self.__dict__
        elif num < self.min or num > self.max:
            err = "%(polyName)s must have %(min)d to %(max)d %(varName)s, %(num)d given!" % self.__dict__
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
    """ Validator for a text field containing polynomial references.
    """
    NAME = "reference value(s)"


#===============================================================================
# 
#===============================================================================

class PolyEditDialog(SC.SizedDialog):
    """ Dialog for editing Univariate and Bivariate polynomials.
    """
    
    ID_UNIVARIATE = wx.NewId()
    ID_BIVARIATE = wx.NewId()
    
    DEFAULT_TITLE = "Edit Polynomial"
    DEFAULT_COEFFS = (1,0)
    DEFAULT_REFS = (1,)
    
    FIELD_PAD = 8 # Padding for use when calculating field height
    
    #===========================================================================
    # Helper methods. Does the busywork associated with adding controls with
    # labels and warning icons.
    #===========================================================================
    
    def _addsubpane(self):
        # Helper helper. Don't use directly.
        subpane = SC.SizedPanel(self.pane, -1)
        subpane.SetSizerType("horizontal")
        subpane.SetSizerProps(expand=True)
        return subpane
        
        
    def _addfield(self, label, default=None, lines=1, **kwargs):
        """ Helper method to add a text field. """
        if isinstance(default, (list, tuple)):
#             lines = lines if lines == 1 else len(default)
            default = '\n'.join(map(str, default))
        else:
            default = str(default)
            
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
        t.txt = txt
        return txt, t
    
    
    def _addchoice(self, label, items, selected=None, enabled=True, **kwargs):
        """ Helper method to add a 'choice' widget (e.g. dropdown menu). """
        # Very possibly overkill, since there's only one Choice field (for now)
        txt = wx.StaticText(self.pane, -1, label)
        txt.SetSizerProps(valign="center")
        subpane = self._addsubpane()
        c = wx.Choice(subpane, -1, choices=items, **kwargs)
        c.SetSizerProps(expand=True, proportion=1)
        if selected is not None:
            c.SetSelection(selected)
        icon = wx.StaticBitmap(subpane, -1, self.noBmp)
        icon.SetSizerProps(proportion=0, expand=False, valign="center")
        c.errIcon = icon
        c.txt = txt
        c.Enable(enabled)
        return c


    def _enableField(self, field, enable=True):
        """ Helper method to enable/disable all widgets associated with a field.
        """
        field.Enable(enable)
        if hasattr(field, 'errIcon'):
            field.errIcon.Enable(enable)
        if hasattr(field, 'txt'):
            field.txt.Enable(enable)


    def _showField(self, field, show=True):
        """ Helper method to show/hide all widgets associated with a field.
        """
        field.Show(show)
        if hasattr(field, 'errIcon'):
            field.errIcon.Show(show)
        if hasattr(field, 'txt'):
            field.txt.Show(show)


    def _uses(self, t):
        """ Helper method to determine if a (Sub)Channel uses the current cal.
        """
        if t.transform is None:
            return False
        return t.transform == self.cal.id or t.transform == self.cal


    #===========================================================================
    # 
    #===========================================================================
    
    def __init__(self, parent, wxId, cal=None, channels=[], transforms={},
                 polyType=None, changeType=True, changeSource=True, 
                 savedCal=None, **kwargs):
        """ Constructor. Standard SizedDialog arguments, plus:
        
            @keyword cal: The transform to edit.
            @keyword channels: A list of Channels, for determining users and
                bivariate references.
            @keyword transforms: A dictionary of other transforms, mainly to
                detect and prevent circular references.
            @keyword polyType: The polynomial type, if creating a new one. 
            @keyword changeType: If `True`, the polynomial type can be changed.
            @keyword changeSource: If `True`, the bivariate channel/subchannel
                can be changed.
            @keyword savedCal: The original transform from the original 
                recording or factory calibration.
        """
        self.cal = cal
        self.channels = channels
        self.polyType = polyType
        self.changeType = changeType
        self.prevType = None
        self.originalCal = None
        self.savedCal = savedCal
        
        self.calSubchannel = None

        if isinstance(self.cal, Transform):
            self.originalCal = cal
            self.cal = self.cal.copy()
            if self.polyType is None:
                self.polyType = self.cal.__class__
            if isinstance(self.cal, Bivariate) and self.channels:
                try:
                    self.calSubchannel = self.channels[self.cal.channelId][self.cal.subchannelId]
                except (IndexError, KeyError):
                    pass
        
        title = 'Edit %s Polynomial' % self.polyType.__name__
        if getattr(cal, 'id', None):
            title += " (ID %r)" % cal.id
        kwargs.setdefault('title', title)
            
        kwargs.setdefault('style', wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        super(PolyEditDialog, self).__init__(parent, wxId, **kwargs)

        # Error icons and window background color.
        self.noBmp = wx.EmptyBitmapRGBA(16,16,0,0,0,1.0)
        self.errBmp = wx.ArtProvider.GetBitmap(wx.ART_ERROR, wx.ART_CMN_DIALOG, (16,16))
        self.bgColor = wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW)
        self.errColor = "pink"

        self.buildUI()
        
        if not self.changeType:
            self.typeTxt.Show(False)
            self.uniBtn.Show(False)
            self.biBtn.Show(False)
            
        if self.polyType == Bivariate:
            self.biBtn.SetValue(True)
            self.sourceList.Enable(changeSource)
        else:
            self.uniBtn.SetValue(True)
            self._showField(self.sourceList, False)
        
#         self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))

        # This stuff is just to create non-standard buttons, right aligned,
        # with a gap. It really should not be this hard to do. This approach is
        # probably not optimal or properly cross-platform.
        SC.SizedPanel(self.GetContentsPane(), -1, size=(8,8))
        buttonpane = SC.SizedPanel(self.GetContentsPane(), -1)
        buttonpane.SetSizerType("horizontal")
        SC.SizedPanel(buttonpane, -1).SetSizerProps(expand=True, halign='right', proportion=1)
        revertBtn = wx.Button(buttonpane, wx.ID_REVERT, "Revert")
        wx.Button(buttonpane, wx.ID_OK)
        wx.Button(buttonpane, wx.ID_CANCEL)
        buttonpane.SetSizerProps(expand=True, halign='right')
        
        if self.savedCal is None:
            revertBtn.Hide()
        
        self.Fit()
        s = self.GetSize()
        self.SetMinSize(s)
        self.SetSize((400,s[1]))
        self.SetMaxSize((-1, s[1]))
        
        self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self.onRevert, id=wx.ID_REVERT)


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
            if len(self.transforms) > 0:
                self.calId = max(self.transforms) + 1
            else:
                self.calId = 0
            self.calLabel = '%d (New)' % self.calId
        else:
            self.calId = self.cal.id
            self.calLabel = '%d' % self.calId
        
#         self.pane = self.GetContentsPane()
        cp = self.GetContentsPane()
        self.pane = SC.SizedPanel(cp, -1)
        self.pane.SetSizerProps(expand=True)
        self.pane.SetSizerType("form")
        
        self.typeTxt = wx.StaticText(self.pane, -1, "Polynomial Type:")
        self.lineHeight = self.typeTxt.GetTextExtent("yY")[1] 
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
        """ Handle updating the UI for the current type of polynomial being
            edited.
        """
        if self.polyType == Univariate:
            self.numCoeffs = (2,2)
            self.numRefs = (1,1)
            self.sourceList.Enable(False)
        else:
            self.numCoeffs = (4,4)
            self.numRefs = (2,2)
            self.sourceList.Enable(True)
            if self.calSubchannel in self.sources:
                self.sourceList.SetSelection(self.sources.index(self.calSubchannel))
            
        if self.polyType != self.prevType:
            ptype = self.polyType.__name__
            coeffVal = CoeffValidator(*self.numCoeffs, root=self, polyType=ptype)
            refVal = RefValidator(*self.numRefs, root=self, polyType=ptype)
            self.coeffField.SetValidator(coeffVal)
            self.refField.SetValidator(refVal)
            self.prevType = self.polyType

        if self.numCoeffs[0] == self.numCoeffs[1]:
            clabel = "Coefficients (%d)" % self.numCoeffs[0]
        else:
            clabel = "Coefficients (%d-%d)" % self.numCoeffs
        if self.numRefs[0] == self.numRefs[1]:
            if self.numRefs == 1:
                rlabel = "Reference" 
            else: 
                rlabel = "References (%d)" % self.numRefs[0]
        else:
            rlabel = "References (%d-%d)" % self.numRefs
        self.coeffLbl.SetLabelText(clabel)
        self.refLbl.SetLabelText(rlabel)

        self.prevType = self.polyType
        for field in (self.coeffField, self.refField):
            self.updatePoly(field.GetValidator().manualValidate(field, quiet=True))
        

    def onCancel(self, evt):
        """ Handle dialog cancel.
        """
        # Reset `self.cal` to the original (no changes)
        self.cal = self.originalCal
        evt.Skip()

    
    def onRevert(self, evt):
        """ Handle reverting to saved.
        """
        if self.savedCal is None:
            return
        self.cal = self.savedCal.copy()
        self.coeffField.SetValue('\n'.join(map(str, self.cal.coefficients)))
        self.refField.SetValue('\n'.join(map(str, self.cal.references)))
        self.updateUI()
        

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
        """ Get a list of all Channels/SubChannels that can be used as the 
            source for the polynomial being edited. Channels/SubChannels that
            use the current polynomial are excluded to prevent circular 
            references.
        """
        self.sources = []
        self.sourceNames = []
        if not hasattr(self.cal, "channelId"):
            # Probably shouldn't happen.
            return
        
        if self.channels:
            for c in self.channels.values():
                if self._uses(c):
                    # Exclude all subchannels of parent uses the current cal.
                    continue
                for source in c.subchannels:
                    if self._uses(source):
                        continue
                        
                    self.sources.append(source)
                    self.sourceNames.append("%d:%d %s" % (source.parent.id,
                                                          source.id,
                                                          source.displayName))
            

    def OnTypeChanged(self, evt):
        """ Handle polynomial type change.
        """
        if evt.GetEventObject().GetId() == self.ID_UNIVARIATE:
            self.polyType = Univariate
        else:
            self.polyType = Bivariate
        self.updateUI()


#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    from mide_ebml import importer
    doc = importer.importFile()
    transforms = doc.transforms
    channels = doc.channels
    print "loaded %r" % doc.filename
    
    app = wx.App()
   
    def show(d, title="Edit Polynomial", cal=1, **kwargs):
        title = "%s (ID %d)" % (title, cal)
        d = d(None, -1, title=title, transforms=transforms, channels=channels, cal=transforms[cal], **kwargs)
        d.ShowModal()
        cal = d.cal
        d.Destroy()
        if hasattr(cal, 'channelId'):
            print "%r, refs channel %r.%r" % (cal, cal.channelId, cal.subchannelId)
        else:
            print "%r" % cal
        return cal
    
    show(PolyEditDialog, cal=1)
    show(PolyEditDialog, cal=2, changeType=False)
    show(PolyEditDialog, cal=3, changeType=False, changeSource=False)
    show(PolyEditDialog, cal=0, changeType=False)
    
    app.MainLoop()
