'''
Created on May 8, 2014

@author: dstokes
'''

import wx; wx=wx
import wx.propgrid as PG
# import wx.lib.dialogs as wxd
import wx.lib.sized_controls as SC


#===============================================================================
# 
#===============================================================================

class PrefsDialog(SC.SizedDialog):
    """
    """

    LANGUAGES = [s for s in dir(wx) if s.startswith("LANGUAGE")]
    LANG_LABELS = [s[9:].title(
       ).replace("_"," "
                 ).replace(" Us", " US"
                           ).replace(" Uk", " UK"
                                     ).replace(" Uae", " UAE"
                                               ) for s in LANGUAGES]
    
    def __init__(self, *args, **kwargs):
        """
        """
        userPrefs = kwargs.pop("prefs", {})
        self.defaultPrefs = kwargs.pop("defaultPrefs", {})
        self.prefs = self.defaultPrefs.copy()
        self.prefs.update(userPrefs)

        style = wx.DEFAULT_DIALOG_STYLE \
            | wx.RESIZE_BORDER \
            | wx.MAXIMIZE_BOX \
            | wx.MINIMIZE_BOX \
            | wx.DIALOG_EX_CONTEXTHELP \
            | wx.SYSTEM_MENU

        kwargs.setdefault('style',style)

        super(PrefsDialog, self).__init__(*args, **kwargs)
        pane = self.GetContentsPane()

        self.pg = pg = PG.PropertyGrid(pane, 
                                         style=(PG.PG_SPLITTER_AUTO_CENTER |
#                                                 PG.PG_AUTO_SORT |
                                                PG.PG_TOOLBAR))
        pg.SetExtraStyle(PG.PG_EX_HELP_AS_TOOLTIPS)
        pg.SetSizerProps(expand=True, proportion=1)
        
        wx.StaticText(pane, -1, "Restarting the app may be required for "
            "some changes to take effect.").SetSizerProps(halign='centre')
        
        self.resetHiddenCheck = wx.CheckBox(pane, -1, 
                                            "Reset Hidden Dialogs and Warnings")
        self.resetHiddenCheck.SetSizerProps(proportion=0)
        
        buttons = SC.SizedPanel(pane,-1)
        buttons.SetSizerType("horizontal")
        self.defaultsBtn = wx.Button(buttons, -1, "Reset to Defaults")
        self.defaultsBtn.SetSizerProps(halign='left')
        wx.Button(buttons, wx.ID_SAVE)
        wx.Button(buttons, wx.ID_CANCEL)
        buttons.SetSizerProps(halign='right')
#         self.SetButtonSizer(buttons)

        self.buildGrid()

        self.defaultsBtn.Bind(wx.EVT_BUTTON, self.OnDefaultsButton)
        self.SetAffirmativeId(wx.ID_SAVE)
        self.SetEscapeId(wx.ID_CANCEL)
        
        self.SetSize((500,400))
        self.SetMinSize((300,200))
        self.SetMaxSize((600,1000))


    def buildGrid(self):
        """
        """
        def _add(prop, tooltip=None, **atts):
            self.pg.Append(prop)
            if tooltip:
                self.pg.SetPropertyHelpString(prop, tooltip)
            for att, val in atts.iteritems():
                self.pg.SetPropertyAttribute(prop, att, val)
            return prop
        
        self.pg.Append(PG.PropertyCategory("UI Colors"))
        _add(PG.ColourProperty("Major Gridline", "majorHLineColor"))
        _add(PG.ColourProperty("Minor Gridlines", "minorHLineColor"))
        _add(PG.ColourProperty("Buffer Maximum", "maxRangeColor"))
        _add(PG.ColourProperty("Buffer Mean", "meanRangeColor"))
        _add(PG.ColourProperty("Buffer Minimum", "minRangeColor"))
        
        _add(PG.PropertyCategory("Data"))
        _add(PG.BoolProperty("Remove Total Mean by Default", "removeMean"), 
             "By default, remove the total median of buffer means from the "
             "data (if the data contains buffer mean data).",
             UseCheckbox=True)
        _add(PG.FloatProperty("Rolling Mean Span (seconds)", "rollingMeanSpan"),
             "The width of the time span used to compute the 'rolling mean' "
             "used when \"Remove Rolling Mean from Data\" is enabled.")
        
        
        _add(PG.PropertyCategory("Drawing"))
        _add(PG.BoolProperty("Draw Points", "drawPoints"), 
             "If the number of samples shown is fewer than the number "
             "of pixels, draw individual samples as larger points.",
             UseCheckbox=True)
        _add(PG.FloatProperty("Antialiasing Scaling", "antialiasingMultiplier"),
             "A multiplier of screen resolution used when drawing antialiased"
             "graphics.")
        _add(PG.FloatProperty("Noisy Resampling Jitter", 
                              "resamplingJitterAmount"), 
             "The size of X axis variation when 'Noise Resampling' is on, "
             "as a normalized percent.")
        
        _add(PG.PropertyCategory("Miscellaneous"))
        _add(PG.BoolProperty("Display 'Open' Dialog on Startup", "openOnStart"), 
             UseCheckbox=True )
        _add(PG.IntProperty("X Axis Value Precision", "precisionX", value=4))
        _add(PG.IntProperty("Y Axis Value Precision", "precisionY", value=4))
        _add(PG.EnumProperty("Locale", "locale", self.LANG_LABELS))
        
        self.populateGrid(self.prefs)


    def populateGrid(self, prefs):
        """ Puts the contents of preferences dict into the grid after doing
            any data modifications for display.
        """
        locale = prefs.get('locale', 'LANGUAGE_ENGLISH_US')
        if isinstance(locale, basestring):
            if locale not in self.LANGUAGES:
                locale = 'LANGUAGE_ENGLISH_US'
            localeIdx = self.LANGUAGES.index(locale)
        else:
            localeIdx = locale
            
        prefs['locale'] = localeIdx
        self.pg.SetPropertyValues(prefs)

    #===========================================================================
    # 
    #===========================================================================

    def OnDefaultsButton(self, evt):
        self.populateGrid(self.defaultPrefs)


    def getChangedPrefs(self):
        result = {}
        resetHidden = self.resetHiddenCheck.GetValue()
        self.prefs.update(self.pg.GetPropertyValues(as_strings=False))
        self.prefs['locale'] = self.LANGUAGES[self.prefs['locale']]
        for k,v in self.prefs.iteritems():
            if resetHidden and k.startswith("ask."):
                continue
            if k not in self.defaultPrefs or v != self.defaultPrefs[k]:
                result[k] = v
        return result


    #===========================================================================
    # 
    #===========================================================================
    
    @classmethod
    def editPrefs(cls, parent, prefs, defaultPrefs):
        """
        """
        dlg = cls(parent, -1, "Preferences", prefs=prefs, 
                  defaultPrefs=defaultPrefs)
        result = dlg.ShowModal()
        if result == wx.ID_CANCEL:
            dlg.Destroy()
            return None

        newPrefs = dlg.getChangedPrefs()
        dlg.Destroy()
        return newPrefs

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    app = wx.App()
    d = PrefsDialog(None, -1, "Prefs Test")
    d.ShowModal()
    app.MainLoop()