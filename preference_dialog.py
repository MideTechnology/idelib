'''
Viewer Preferences editor.

Created on May 8, 2014

@author: dstokes
'''

import fnmatch
import json
import os.path
import time

import wx; wx=wx
import wx.propgrid as PG
import wx.lib.sized_controls as SC

from updater import INTERVALS
from build_info import VERSION, DEBUG
from logger import logger

#===============================================================================
# 
#===============================================================================

class Preferences(object):
    
    # Preferences format version: change if a change renders old ones unusable.
    PREFS_VERSION = 0
    defaultPrefsFile = 'ss_lab.cfg'
    
    # Default settings. Any user-changed preferences override these.
    defaultPrefs = {
        'defaultFilename': '', #'data.dat',
        'fileHistory': {},
        'fileHistorySize': 10,
        
        # Precision display of numbers
        'precisionX': 4,
        'precisionY': 4,
        
        # Data modifications
        'removeMean': True,
        'removeRollingMean': False,
        'rollingMeanSpan': 5.0, # In seconds
        
        # Rendering
        'antialiasing': False,
        'antialiasingMultiplier': 3.33,
        'resamplingJitter': False,
        'resamplingJitterAmount': 0.125,
        'drawMajorHLines': True,
        'drawMinorHLines': True, #False,
        'drawMinMax': False,
        'drawMean': False,
        'drawPoints': True,
        'plotLineWidth': 1,
        'originHLineColor': wx.Colour(200,200,200),
        'majorHLineColor': wx.Colour(240,240,240),
        'minorHLineColor': wx.Colour(240,240,240),
        'minRangeColor': wx.Colour(190,190,255),
        'maxRangeColor': wx.Colour(255,190,190),
        'meanRangeColor': wx.Colour(255,255,150),
        'plotBgColor': wx.Colour(255,255,255),
        # Plot colors, stored by channel:subchannel IDs.
        'plotColors': {"00.0": "BLUE",
                       "00.1": "GREEN",
                       "00.2": "RED",
                       "01.0": "DARK GREEN",
                       "01.1": "VIOLET"
        },
        # default colors: used for subchannel plots not in plotColors
        'defaultColors': ["DARK GREEN",
                          "VIOLET",
                          "GREY",
                          "YELLOW",
                          "MAGENTA",
                          "NAVY",
                          "PINK",
                          "SKY BLUE",
                          "BROWN",
                          "CYAN",
                          "DARK GREY",
                          "GOLD",
                          "BLACK",
                          "BLUE VIOLET"],

#         'locale': 'English_United States.1252', # Python's locale name string
        'locale': 'LANGUAGE_ENGLISH_US', # wxPython constant name (wx.*)
        'loader': dict(numUpdates=100, updateInterval=1.0),
        'openOnStart': True,
        'showDebugChannels': DEBUG,
        'showFullPath': True,#False,
        'showUtcTime': True,
        'titleLength': 80,

        # Automatic update checking
        'updater.interval': 3, # see updater.INTERVALS
        'updater.lastCheck': 0, # Unix timestamp of the last version check
        'updater.version': VERSION, # The last version check

        # WVR/SSX-specific parameters: the hard-coded warning range.        
        'wvr.tempMin': -20.0,
        'wvr.tempMax': 60.0,
    }


    def __init__(self, filename=None):
        self.prefsFile = filename or self.defaultPrefsFile
        self.loadPrefs()


    def loadPrefs(self, filename=None):
        """ Load saved preferences from file.
        """
        def tuple2color(c):
            if isinstance(c, list):
                return wx.Colour(*c)
            return c
        
#         self.fileHistory = wx.FileHistory()
        filename = filename or self.prefsFile
        if not filename:
            return {}
        
        filename = os.path.realpath(os.path.expanduser(filename))
        logger.debug(u"Loading preferences from %r" % filename)

        prefs = {}
        if not os.path.exists(filename):
            # No preferences file; probably the first run for this machine/user
            return {}
        try:
            with open(filename) as f:
                prefs = json.load(f)
                if isinstance(prefs, dict):
                    vers = prefs.get('prefsVersion', self.PREFS_VERSION)
                    if vers != self.PREFS_VERSION:
                        # Mismatched preferences version!
                        # FUTURE: Possibly translate old prefs to new format
                        n = "n older" if vers < self.PREFS_VERSION else " newer"
                        wx.MessageBox("The preferences file appears to use a%s "
                            "format than expected;\ndefaults will be used." % n,
                            "Preferences Version Mismatch")
                        return {}
                    # De-serialize *Color attributes (single colors)
                    for k in fnmatch.filter(prefs.keys(), "*Color"):
                        prefs[k] = tuple2color(prefs[k])
                    # De-serialize *Colors attributes (lists of colors)
                    for k in fnmatch.filter(prefs.keys(), "*Colors"):
                        if isinstance(prefs[k], list):
                            for i in xrange(len(prefs[k])):
                                prefs[k][i] = tuple2color(prefs[k][i])
        except (ValueError, IOError):# as err:
            # Import problem. Bad file will raise IOError; bad JSON, ValueError.
            wx.MessageBox("An error occurred while trying to read the "
                          "preferences file.\nDefault settings will be used.",
                          "Preferences File Error")
            return {}
        
        # Load recent file history
#         hist = prefs.setdefault('fileHistory', {}).setdefault('import', [])
#         map(self.fileHistory.AddFileToHistory, hist)
#         self.fileHistory.UseMenu(self.recentFilesMenu)
#         self.fileHistory.AddFilesToMenu()
            
        return prefs


    def savePrefs(self, filename=None):
        """ Write custom preferences to a file.
        """
        def _fix(d):
            if isinstance(d, (list,tuple)):
                d = [_fix(x) for x in d]
            elif isinstance(d, dict):
                for k,v in d.iteritems():
                    d[k] = _fix(v)
            elif isinstance(d, wx.Colour):
                d = tuple(d)
            return d
        
        prefs = self.prefs.copy()
        prefs['prefsVersion'] = self.PREFS_VERSION
        filename = filename or self.prefsFile
        
        try:
            path = os.path.split(filename)[0]
            if not os.path.exists(path):
                os.makedirs(path)
            with open(filename, 'w') as f:
                json.dump(_fix(prefs), f, indent=2, sort_keys=True)
        except IOError:# as err:
            # TODO: Report a problem, or just ignore?
            pass
        
    
    def saveAllPrefs(self, filename=None, hideFile=None):
        """ Save all preferences, including defaults, to the config file.
            Primarily for debugging.
        """
        prefs = self.defaultPrefs.copy()
        prefs.update(self.prefs)
        self.prefs = prefs
        self.savePrefs(filename, hideFile)

    
    def addRecentFile(self, filename, category="import"):
        """ Add a file to a history list. If the list is at capacity, the
            oldest file is removed.
        """
        self.changedFiles = True
        allFiles = self.prefs.setdefault('fileHistory', {})
        files = allFiles.setdefault(category, [])
        if filename:
            if filename in files:
                files.remove(filename)
            files.insert(0,filename)
        allFiles[category] = files[:(self.getPref('fileHistorySize'))]


    def getRecentFiles(self, category="import"):
        """ Retrieve the list of recent files within a category.
        """
        hist = self.prefs.setdefault('fileHistory', {})
        return hist.setdefault(category, [])


    def getPref(self, name, default=None, section=None):
        """ Retrieve a value from the preferences.
            @param prefName: The name of the preference to retrieve.
            @keyword default: An optional default value to return if the
                preference is not found.
            @keyword section: An optional "section" name from which to
                delete. Currently a prefix in this implementation.
        """
        if section is not None:
            name = "%s.%s" % (section, name)
        return self.prefs.get(name, self.defaultPrefs.get(name, default))


    def setPref(self, name, val, section=None, persistent=True):
        """ Set the value of a preference. Returns the value set as a
            convenience.
        """
        if section is not None:
            name = "%s.%s" % (section, name)
        prefs = self.prefs if persistent else self.defaultPrefs
        prefs[name] = val
        return val


    def hasPref(self, name, section=None, defaults=False):
        """ Check to see if a preference exists, in either the user-defined
            preferences or the defaults.
        """
        if section is not None:
            name = "%s.%s" % (section, name)
        if defaults:
            return (name in self.prefs) or (name in self.defaultPrefs)
        return name in self.prefs
    
    
    def deletePref(self, name=None, section=None):
        """ Delete one or more preferences. Glob-style wildcards are allowed.
        
            @keyword name: The name of the preference to delete. Optional if
                `section` is supplied
            @keyword section: An optional section name, limiting the scope.
            @return: The number of deleted preferences.
        """
        if section is not None:
            name = name if name is not None else "*"
            name = "%s.%s" % (section, name)
        if name is None:
            return
        keys = fnmatch.filter(self.prefs.keys(), name)
        for k in keys:
            self.prefs.pop(k, None)
        return len(keys)


    def editPrefs(self, evt=None):
        """ Launch the Preferences editor.
            
            @param evt: Unused; a placeholder to allow this method to be used
                as an event handler.
        """
        newPrefs = PrefsDialog.editPrefs(None, self.prefs, self.defaultPrefs)
        if newPrefs is not None:
            self.prefs = newPrefs
            self.savePrefs()
            
            for v in self.viewers:
                v.loadPrefs()
    
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