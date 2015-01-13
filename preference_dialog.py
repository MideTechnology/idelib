'''
Viewer Preferences editor.

Created on May 8, 2014

@author: dstokes
'''

import time

import wx; wx=wx
import wx.propgrid as PG
import wx.lib.sized_controls as SC

from updater import INTERVALS

#===============================================================================
# 
#===============================================================================

class PrefsDialog(SC.SizedDialog):
    """ The viewer preferences editor. This is a self-contained unit; instead
        of instantiating it, use the `editPrefs` method directly from the
        class. That handles all the setup and teardown.
    """

    LANGUAGES = [s for s in dir(wx) if s.startswith("LANGUAGE")]
    LANG_LABELS = [s[9:].title(
       ).replace("_"," "
                 ).replace(" Us", " US"
                           ).replace(" Uk", " UK"
                                     ).replace(" Uae", " UAE"
                                               ) for s in LANGUAGES]
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Standard dialog arguments plus:
            @keyword prefs: A dictionary of preferences.
            @keyword defaultPrefs: A dictionary of default preference settings.
        """
        userPrefs = kwargs.pop("prefs", {})
        self.defaultPrefs = kwargs.pop("defaultPrefs", {})
        self.prefs = self.defaultPrefs.copy()
        self.prefs.update(userPrefs)

        style = ( wx.DEFAULT_DIALOG_STYLE
                | wx.RESIZE_BORDER 
                | wx.MAXIMIZE_BOX 
                | wx.MINIMIZE_BOX 
                | wx.DIALOG_EX_CONTEXTHELP 
                | wx.SYSTEM_MENU
                )

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
        wx.Button(buttons, wx.ID_SAVE)
        wx.Button(buttons, wx.ID_CANCEL)
        buttons.SetSizerProps(halign='right')

        self.buildGrid()

        self.defaultsBtn.Bind(wx.EVT_BUTTON, self.OnDefaultsButton)
        self.SetAffirmativeId(wx.ID_SAVE)
        self.SetEscapeId(wx.ID_CANCEL)
        
        self.SetSize((500,586))
        self.SetMinSize((300,200))
        self.SetMaxSize((1000,1000))


    def buildGrid(self):
        """ Build the display.
        """
        def _add(prop, tooltip=None, **atts):
            # Helper to add properties to the list.
            self.pg.Append(prop)
            if tooltip:
                self.pg.SetPropertyHelpString(prop, tooltip)
            for att, val in atts.iteritems():
                self.pg.SetPropertyAttribute(prop, att, val)
            return prop
        
        self.pg.Append(PG.PropertyCategory("UI Colors"))
        _add(PG.ColourProperty("Plot Background", "plotBgColor"))
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
        _add(PG.IntProperty("Plot Line Width", "plotLineWidth"),
             "The base width of the plot lines. This width will scale with "
             "the antialiasing settings.")
        _add(PG.BoolProperty("Draw Points", "drawPoints"), 
             "If the number of samples shown is fewer than the number "
             "of pixels, draw individual samples as larger points.",
             UseCheckbox=True)
        _add(PG.FloatProperty("Antialiasing Scaling", "antialiasingMultiplier"),
             "A multiplier of screen resolution used when drawing antialiased "
             "graphics.")
        _add(PG.FloatProperty("Noisy Resampling Jitter", 
                              "resamplingJitterAmount"), 
             "The size of X axis variation when 'Noise Resampling' is on, "
             "as a normalized percent.")
        
        _add(PG.PropertyCategory("Miscellaneous"))
        _add(PG.BoolProperty("Show Full Path in Title Bar", "showFullPath"),
             UseCheckbox=True)
        _add(PG.BoolProperty("Display 'Open' Dialog on Startup", "openOnStart"), 
             UseCheckbox=True )
        _add(PG.IntProperty("X Axis Value Precision", "precisionX", value=4))
        _add(PG.IntProperty("Y Axis Value Precision", "precisionY", value=4))
        _add(PG.EnumProperty("Locale", "locale", self.LANG_LABELS))
        _add(PG.EnumProperty("Automatic Update Check Interval", "updater.interval", 
                             INTERVALS.values()))
        _add(PG.BoolProperty("Show Advanced Options", "showAdvancedOptions"),
             "Show advanced/experimental features. These are not required for "
             "general use of the app and may cause problems. Use with caution!",
             UseCheckbox=True)
        
        _add(PG.PropertyCategory("Slam Stick X/WVR Special Preferences"))
        temphelp = ("Accelerometer readings when the temperature (Channel "
                    "01.1) is %s this value may not be accurate; used for "
                    "accelerometer display.") 
        _add(PG.FloatProperty("Temperature Warning, Low", 
                              "wvr.tempMin"), tooltop=temphelp % "below")
        _add(PG.FloatProperty("Temperature Warning, High", 
                              "wvr.tempMax"), tooltip=temphelp % "above")
        
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
        """ Restore the default settings. """
        # Keep the file history, though
        hist = self.prefs.get('fileHistory', None)
        self.prefs = self.defaultPrefs.copy()
        if hist is not None:
            self.prefs['fileHistory'] = hist
        self.populateGrid(self.prefs)


    def getChangedPrefs(self):
        """ Get all of the preferences that differ from the default. Also does
            any conversion from the display version to usable data (e.g.
            the 'locale').
        """
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
        """ Display the Preferences Editor. Use this method directly from the
            class rather than instantiating and displaying the dialog manually.
            
            @param parent: The dialog parent.
            @param prefs: A dictionary of preferences to edit. This does not
                get modified.
            @param defaultPrefs: A dictionary of default values, for applying
                when the user clicks 'restore defaults.'
            @return: A new dictionary of preferences that differ from the
                defaults.
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
    d = PrefsDialog(None, -1, "Prefs Test", defaultPrefs={'updater.lastCheck': time.time()})
    d.ShowModal()
    app.MainLoop()