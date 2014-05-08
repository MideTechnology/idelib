'''
Created on May 8, 2014

@author: dstokes
'''

import wx; wx=wx
import wx.propgrid as wxpg
import wx.lib.dialogs as wxd
import wx.lib.sized_controls as sc


#===============================================================================
# 
#===============================================================================

class PrefsDialog(sc.SizedDialog):
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

        self.pg = pg = wxpg.PropertyGrid(pane, 
                                         style=(wxpg.PG_SPLITTER_AUTO_CENTER |
                                                wxpg.PG_AUTO_SORT |
                                                wxpg.PG_TOOLBAR))
        pg.SetExtraStyle(wxpg.PG_EX_HELP_AS_TOOLTIPS)
        pg.SetSizerProps(expand=True, proportion=1)
        
        self.resetHiddenCheck = wx.CheckBox(pane, -1, "Reset Hidden Dialogs and Warnings")
        self.resetHiddenCheck.SetSizerProps(proportion=0)
        
        buttons = sc.SizedPanel(pane,-1)
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
        pg = self.pg
        pg.Append(wxpg.PropertyCategory("UI Colors") )
        pg.Append(wxpg.ColourProperty("Major Gridline", "majorHLineColor"))
        pg.Append(wxpg.ColourProperty("Minor Gridlines", "minorHLineColor"))
        pg.Append(wxpg.ColourProperty("Buffer Maximum", "maxRangeColor"))
        pg.Append(wxpg.ColourProperty("Buffer Mean", "meanRangeColor"))
        pg.Append(wxpg.ColourProperty("Buffer Minimum", "minRangeColor"))
        
        pg.Append(wxpg.PropertyCategory("Drawing"))
        pg.Append(wxpg.FloatProperty("Antialiasing Scaling Factor","antialiasingMultiplier",value=3.33) )
        pg.Append(wxpg.FloatProperty("Noisy Resampling Jitter", "resamplingJitterAmount", value=0.125))
        pg.SetPropertyHelpString("resamplingJitterAmount", "XXX: THIS IS HOW HELP TEXT IS DONE?")
        
        pg.Append(wxpg.PropertyCategory("Miscellaneous"))
        pg.Append(wxpg.BoolProperty("Display 'Open' Dialog on Startup", "openOnStart",value=True) )
        pg.SetPropertyAttribute("openOnStart", "UseCheckbox", True)
        pg.Append(wxpg.IntProperty("X Axis Value Precision", "precisionX", value=4) )
        pg.Append(wxpg.IntProperty("Y Axis Value Precision", "precisionY", value=4) )
        pg.Append(wxpg.EnumProperty("Locale", "locale", self.LANG_LABELS))
        
        self.populateGrid(self.prefs)


    def populateGrid(self, prefs):
        """ Puts the contents of preferences dict into the grid after doing
            any data modifications for display.
        """
        locale = prefs.get('locale', 'LANGUAGE_ENGLISH_US')
        print "locale: %r" % locale
        if isinstance(locale, basestring):
            if locale not in self.LANGUAGES:
                locale = 'LANGUAGE_ENGLISH_US'
            localeIdx = self.LANGUAGES.index(locale)
        else:
            localeIdx = locale
            
        self.prefs['locale'] = localeIdx
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
        for k in self.prefs:
            if resetHidden and k.startswith("ask."):
                continue
            if k not in self.defaultPrefs or self.prefs[k] != self.defaultPrefs[k]:
                result[k] = self.prefs[k]
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