
import wx
import wx.lib.sized_controls as SC

from mide_ebml import calibration
from mide_ebml.dataset import Channel, SubChannel

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
    
    def __init__(self, minItems=1, maxItems=2, root=None):
        """ Standard constructor.
        """
        self.min = minItems
        self.max = maxItems
        self.root = root
        self.msg = ""
        wx.PyValidator.__init__(self)


    def Clone(self):
        """ Standard cloner. Note that every validator must implement the 
            Clone() method.
        """
        return self.__class__(self.min, self.max, self.root)


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

        if vals is None:
            err = "Invalid characters in %s!" % self.NAME
        elif self.min == self.max and self.min != num:
            err = "Polynomial must have exactly %d %s, %d given!" % (self.min, self.NAME, num)
        elif self.max is None and num < self.min:
            err = "Polynomial must have at least %d %s, %d given!" % (self.min, self.NAME, num)
        elif num < self.min or num > self.max:
            err = "Polynomial must have %d to %d %s, %d given!" % (self.min, self.max, self.NAME, num)
        else:
            err = None
        
        self.msg = err
        
        if err is not None:
            textCtrl.errIcon.SetBitmap(self.root.errBmp)
            textCtrl.errIcon.SetToolTipString(err)
            textCtrl.SetBackgroundColour(self.root.errColor)

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


class RefValidator(CoeffValidator):
    NAME = "reference value(s)"
    
#===============================================================================
# 
#===============================================================================

class UnivariateDialog(SC.SizedDialog):
    """
    """
    CAL_TYPE = calibration.Univariate
    DEFAULT_TITLE = "Edit Univariate Polynomial"
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
        
    def _addicon(self, subpane, ctrl):
        # Helper helper. Adds icon next to fields. Don't use directly.
        icon = wx.StaticBitmap(subpane, -1, self.noBmp)
        icon.SetSizerProps(proportion=0, expand=False, valign="center")
        ctrl.errIcon = icon
        return icon
        
    def _addfield(self, label, default=None, lines=1, **kwargs):
        """ Helper method to add a text field. """
        if isinstance(default, (list, tuple)) and lines == 1:
            lines = len(default)
            default = self._tostr(default)
        if lines > 1:
            kwargs['style'] = kwargs.get('style', 0) | wx.TE_MULTILINE | wx.TE_PROCESS_ENTER
            kwargs['size'] = (-1, (self.lineHeight * lines)+self.FIELD_PAD)
        wx.StaticText(self.pane, -1, label)
        subpane = self._addsubpane()
        t = wx.TextCtrl(subpane, -1, unicode(default), **kwargs)
        t.SetSizerProps(expand=True, proportion=1)
        self._addicon(subpane, t)
        return t
    
    def _addlist(self, label, items, single=True, selected=None, **kwargs):
        """ Helper method to add a listbox. """
        style = wx.LB_SINGLE if single else wx.LB_EXTENDED
        wx.StaticText(self.pane, -1, label)
        subpane = self._addsubpane()
        l = wx.ListBox(subpane, -1, choices=items, style=style, **kwargs)
        l.SetSizerProps(expand=True, proportion=1)
        if selected is not None:
            if isinstance(selected, int):
                selected = (selected,)
            map(l.SetSelection, selected)
        self._addicon(subpane, l)
        return l
    
    def _addchoice(self, label, items, selected=None, **kwargs):
        """ Helper method to add a 'choice' widget (e.g. dropdown menu). """
        wx.StaticText(self.pane, -1, label)
        subpane = self._addsubpane()
        c = wx.Choice(subpane, -1, choices=items, **kwargs)
        c.SetSizerProps(expand=True, proportion=1)
        if selected is not None:
            c.SetSelection(selected)
        self._addicon(subpane, c)
        return c

    def _channelstr(self, c):
        """ Helper method to create nice string for a (sub)channel's name. """
        if isinstance(c, SubChannel):
            return "%d.%d: %s" % (c.parent.id, c.id, c.name)
        else:
            return "%d: %s" % (c.id, c.name)
        
    #===========================================================================
    # 
    #===========================================================================
    
    def __init__(self, *args, **kwargs):
        self.ebmldoc = kwargs.pop('ebmldoc', None)
        self.cal = kwargs.pop('cal', None)
        showChannels = kwargs.pop('showChannels', False)
        
        kwargs['title'] = kwargs.get('title', None) or self.DEFAULT_TITLE
        super(UnivariateDialog, self).__init__(*args, **kwargs)

        # Error icons and window background color.
        self.noBmp = wx.EmptyBitmapRGBA(16,16,0,0,0,1.0)
        self.errBmp = wx.ArtProvider.GetBitmap(wx.ART_ERROR, wx.ART_CMN_DIALOG, (16,16))
        self.bgColor = wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW)
        self.errColor = "pink"

        # Build list of channel names, and map back to the channel.
        self.channels = {}
        for c in self.ebmldoc.getPlots():
            self.channels[self._channelstr(c)] = c
        if showChannels:
            for c in self.ebmldoc.channels.values():
                self.channels[self._channelstr(c)] = c
        self.channelNames = sorted(self.channels.keys(), key=lambda x: x.replace(':',' '))
        
        if self.cal is None:
            if len(self.ebmldoc.transforms) > 0:
                self.calId = max(self.ebmldoc.transforms) + 1
            else:
                self.calId = 0
            self.calLabel = '%d (New)' % self.calId
        else:
            self.calId = self.cal.id
            self.calLabel = '%d' % self.calId
        
        self.pane = self.GetContentsPane()
        self.pane.SetSizerType("form")
        
        self.idField = self._addfield("Calibration ID", default=self.calLabel, style=wx.TE_READONLY)
        self.channelList = self._addlist("Used By", self.channelNames, selected=self.getChannelsUsing(), single=False)
        self.lineHeight = self.idField.GetTextExtent("yY")[1] 
        
        self.buildUI()
        
        self.polyText = self._addfield("Polynomial", style=wx.TE_READONLY)
        self.updatePoly()
        
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        s = self.GetSize()
        self.SetMinSize(self.GetSize())
        self.SetSize((400,s[1]))


    def buildUI(self):
        """ Subclass-specific UI stuff goes here.
        """
        if self.cal is not None:
            coeffs = self.cal.coefficients
            ref = self.cal.references
        else:
            coeffs = self.DEFAULT_COEFFS
            ref = self.DEFAULT_REFS
        
        # Make the labels nice and informative.
        if self.NUM_COEFFS[0] == self.NUM_COEFFS[1]:
            clabel = "Coefficients (%d)" % self.NUM_COEFFS[0]
        else:
            clabel = "Coefficients (%d-%d)" % self.NUM_COEFFS
        if self.NUM_REFS[0] == self.NUM_REFS[1]:
            rlabel = "Reference" if len(ref) == 1 else "References (%d)" % len(ref)
        else:
            rlabel = "References (%d-%d)" % self.NUM_REFS
            
        coeffVal = CoeffValidator(*self.NUM_COEFFS, root=self)
        refVal = RefValidator(*self.NUM_REFS, root=self)
        self.coeffField = self._addfield(clabel, coeffs, validator=coeffVal)
        self.refField = self._addfield(rlabel, ref, validator=refVal)

        # Bind loss of focus to auto-validate fields on the fly.
        self.coeffField.Bind(wx.EVT_KILL_FOCUS, self.OnLoseFocus)
        self.refField.Bind(wx.EVT_KILL_FOCUS, self.OnLoseFocus)


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
            print coeffs
            refs = cleanSplit(self.refField.GetValue())
            self.cal.coefficients = coeffs
            self.cal.references = refs
            self.polyText.SetValue(str(self.cal))
            return True
        except (ValueError, TypeError):
            self.polyText.SetValue("")
            return False


    def getChannelsUsing(self):
        """ Get a list of all Channels using the current calibration polynomial.
        """
        result = []
        for n, c in enumerate(self.channels.values()):
            if c.transform is not None:
                try:
                    if c.transform.id == self.calId:
                        result.append(n)
                except AttributeError:
                    if self.calId in [getattr(x,'id',None) for x in filter(None, c.transform)]:
                        result.append(n)
        return result
            
        

#===============================================================================
# 
#===============================================================================

class BivariateDialog(UnivariateDialog):
    """
    """
    CAL_TYPE = calibration.Univariate
    DEFAULT_TITLE = "Edit Bivariate Polynomial"
    DEFAULT_COEFFS = (1-.003, 1, 0, 0)
    DEFAULT_REFS = (0, 50)
    NUM_COEFFS = (4,4) # (min, max)
    NUM_REFS = (2,2) # (min. max)
    
    def buildUI(self):
        chIdx = None
        if self.ebmldoc is not None and self.cal is not None:
            ch = self.ebmldoc.channels[self.cal.channelId][self.cal.subchannelId]
            try:
                chIdx = self.channelNames.index(self._channelstr(ch))
            except ValueError:
                pass
        self.sourceList = self._addchoice("Source", self.channelNames, selected=chIdx)
        super(BivariateDialog, self).buildUI()
        
        
    def updatePoly(self, valid=True):
        if not super(BivariateDialog, self).updatePoly(valid):
            return False
        
        source = self.channels.get(self.sourceList.GetStringSelection(), None)
        if isinstance(source, SubChannel):
            self.cal.channelId = source.parent.id
            self.cal.subchannelId = source.id
        else:
            self.cal.channelId = source.id
            self.cal.subchannelId = 0
                
        
#===============================================================================
# 
#===============================================================================

if __name__ == '__main__':
    from mide_ebml import importer
    doc = importer.importFile()
#     print doc.transforms
    
    app = wx.App()
    
    def show(d, title="Edit Polynomial", cal=1):
        d = d(None, -1, title=title, ebmldoc=doc, cal=doc.transforms[cal])
        d.ShowModal()
        d.Destroy()
    
    show(UnivariateDialog, title=None, cal=0)
    show(BivariateDialog, title=None)
    
    app.MainLoop()
