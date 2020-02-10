'''
Viewer Preferences editor.

Created on May 8, 2014

@author: dstokes
'''

import fnmatch
import json
import os.path
from threading import RLock
import time

import wx; wx=wx
import wx.propgrid as PG
import wx.lib.sized_controls as SC

from common import multiReplace
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
    
    LEGEND_POSITIONS = ('Upper Left', 'Upper Right', 
                        'Lower Left', 'Lower Right')
    INITIAL_DISPLAY = ('One Channel Per Tab', 
                       'One Tab per Sensor', 
                       'One Tab per Type')
    
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
        'removeRollingMean': True,
        'rollingMeanSpan': 5.0, # In seconds
        'noBivariates': False,
        
        # Rendering
        'initialDisplayMode': 1,
        'antialiasing': False,
        'antialiasingMultiplier': 3.33,
        'resamplingJitter': False,
        'resamplingJitterAmount': 0.125,
        'oversampling': 25.0,
        'condensedPlotThreshold': 1.0,
        'fillCondensedPlot': True,
        'drawMajorHLines': True,
        'drawMinorHLines': True, #False,
        'drawMinMax': True,
        'drawMean': False,
        'drawPoints': True,
        'plotLineWidth': 1,
        'originHLineColor': wx.Colour(200,200,200),
        'majorHLineColor': wx.Colour(240,240,240),
        'minorHLineColor': wx.Colour(240,240,240),
        'minRangeColor': wx.Colour(190,190,255),
        'maxRangeColor': wx.Colour(255,190,190),
        'meanRangeColor': wx.Colour(255,255,150),
        'outOfRangeColor': wx.Colour(250,250,250),
        'warningColor': wx.Colour(255, 192, 203),
        'plotBgColor': wx.Colour(255,255,255),
        
        # Plot colors, stored by channel:subchannel IDs.
        'plotColors': {# SSX v1
                       "00.0": "BLUE",       # Acceleration Z
                       "00.1": "GREEN",      # Acceleration Y
                       "00.2": "RED",        # Acceleration X
                       "01.0": "DARK GREEN", # Pressure
                       "01.1": "VIOLET",     # Temperature
                       
                       # SSX v2
                       "08.0": "RED",                  # Acceleration X
                       "08.1": "GREEN",                # Acceleration Y
                       "08.2": "BLUE",                 # Acceleration Z
                       "20.0": wx.Colour(255,100,100), # Acceleration X (DC)
                       "20.1": wx.Colour(100,255,100), # Acceleration Y (DC)
                       "20.2": wx.Colour(100,100,255), # Acceleration Z (DC)
                       "24.0": "DARK GREEN",           # Pressure
                       "24.1": "VIOLET",               # Temperature
    
                       # IMU Accelerometer (channel 0x2b, 43 decimal)
                       "2b.0": wx.Colour(225,100,100), # Acceleration X (IMU)
                       "2b.1": wx.Colour(100,225,100), # Acceleration Y (IMU)
                       "2b.2": wx.Colour(100,100,225), # Acceleration Z (IMU)
    
                       # IMU gyroscope (channel 0x2f, 47 decimal)
                       # Same colors as main accelerometer axes
                       "2f.0": "RED",   # IMU gyroscope X
                       "2f.1": "GREEN", # IMU gyroscope Y
                       "2f.2": "BLUE",  # IMU gyroscope Z
                       
                       # IMU Magnetometer (channel 0x33, 51 decimal)
                       # Same colors as main accelerometer axes
                       "33.0": "RED",   # IMU Magnetometer X
                       "33.1": "GREEN", # IMU Magnetometer Y
                       "33.2": "BLUE",  # IMU Magnetometer Z
                       
                       # Control Pad/Fast pressure/temperature (channel 59)
                       "3b.0": wx.Colour(91,181,148),
                       "3b.1": wx.Colour(92,95,180),
                       
                       # IMU Quaternion data (channel 0x41, 65 decimal)
                       # X/Y/Z components same as accelerometer axes
                       "41.0": "RED",
                       "41.1": "GREEN",
                       "41.2": "BLUE",
                       "41.3": "GOLD",
                       "41.4": "BLUE VIOLET",
                       
                       # IMU Quaternion data (channel 0x46, 70 decimal)
                       "46.0": "RED",   # Quaternion X
                       "46.1": "GREEN", # Quaternion Y
                       "46.2": "BLUE",  # Quaternion Z
                       "46.3": "GOLD",  # Quaternion W
                       
                       # 40/200g digital accelerometer
                       "50.0": "RED",   # Acceleration X
                       "50.1": "GREEN", # Acceleration Y
                       "50.2": "BLUE",  # Acceleration Z
    
                       # BMG250 gyroscope (channel 0x54, 84 decimal)
                       "54.0": "RED",   # gyroscope X
                       "54.1": "GREEN", # gyroscope Y
                       "54.2": "BLUE",  # gyroscope Z
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
        'showLegend': True,
        'legendPosition': 2,
        'legendOpacity': .95,
        'drawHollowPlot': True,
#         'locale': 'English_United States.1252', # Python's locale name string
        'locale': 'LANGUAGE_ENGLISH_US', # wxPython constant name (wx.*)
        'loader': dict(numUpdates=100, updateInterval=1.0, minCount=10000000),
        'openOnStart': False,
        'showDebugChannels': DEBUG,
        'showFullPath': True,#False,
        'showUtcTime': True,
        'titleLength': 80,

        # Automatic update checking
        'updater.interval': 3, # see updater.INTERVALS
        'updater.lastCheck': 0, # Unix timestamp of the last version check
        'updater.version': VERSION, # The last version check

        # WVR/SSX-specific parameters: the hard-coded warning range. 
        # Obsolete, but used for old firmware.      
        'wvr.tempMin': -20.0,
        'wvr.tempMax': 60.0,
        
        # Plug-ins
        'plugins.loadUserPlugins': True,
        'plugins.searchPaths': [],
    }


    def __init__(self, filename=None, clean=False):
        """ Constructor.
        
            @keyword filename: The name of the preferences file to load, or
                `None` to import the default file.
            @keyword clean: If `True`, do not read preferences.
        """
        self.busy = RLock()
        self.prefsFile = filename
        self.prefs = {}
        
        if not clean:
            if os.path.exists(self.prefsFile):
                self.loadPrefs()
            else:
                # To be removed later
                self.loadLegacy()


    @property
    def prefsFile(self):
        """ Get the name of the preferences file. Returns the default if not
            previously set.
        """
        if getattr(self, '_prefsFile', None) is not None:
            return self._prefsFile
        
        if wx.GetApp() is not None:
            # wx.StandardPaths fails if called outside of an App.
            prefPath = wx.StandardPaths.Get().GetUserDataDir()
        else:
            prefPath = ''
            
        self._prefsFile = os.path.join(prefPath, self.defaultPrefsFile)
        return self._prefsFile
        
        
    @prefsFile.setter
    def prefsFile(self, filename):
        """ Set the name of the preferences file. `None` will set it to the
            default.
        """
        self._prefsFile = filename


    def loadLegacy(self):
        """ Import legacy Slam Stick Lab preferences.
        
            @todo: Remove this after a few versions of enDAQ Lab.
        """
        with self.busy:
            filename = os.path.join(self.prefsFile, '../..', 
                                    u"Slam\u2022Stick Lab", "ss_lab.cfg")
            
            prefs = self.loadPrefs(os.path.abspath(filename))
            prefs.pop('openOnStart', None)
            return prefs
        

    def loadPrefs(self, filename=None):
        """ Load saved preferences from file.
        """
        def tuple2color(c):
            if isinstance(c, list):
                return wx.Colour(*c)
            return c
        
        with self.busy:
            self.prefs = {}
            filename = filename or self.prefsFile
            logger.info("Loading prefs file %r (exists=%r)" % 
                        (filename,os.path.exists(filename)))
            if not filename:
                return self.prefs
            
            filename = os.path.realpath(os.path.expanduser(filename))
    
            prefs = {}
            if not os.path.exists(filename):
                # No preferences file; probably the first run for this machine/user
                return self.prefs
            try:
                with open(filename) as f:
                    prefs = json.load(f)
                    if not isinstance(prefs, dict):
                        raise ValueError
                    
                    vers = prefs.get('prefsVersion', self.PREFS_VERSION)
                    if vers != self.PREFS_VERSION:
                        # Mismatched preferences version!
                        # FUTURE: Possibly translate old prefs to new format
                        n = "an older" if vers < self.PREFS_VERSION else "a newer"
                        wx.MessageBox("The preferences file appears to use %s "
                            "format than expected;\ndefaults will be used." % n,
                            "Preferences Version Mismatch")
                        return self.prefs
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
            
            self.prefs = prefs
            return self.prefs


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
        
        with self.busy:
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
        with self.busy:
            prefs = self.defaultPrefs.copy()
            prefs.update(self.prefs)
            self.prefs = prefs
            self.savePrefs(filename, hideFile)

    
    def addRecentFile(self, filename, category="import"):
        """ Add a file to a history list. If the list is at capacity, the
            oldest file is removed.
        """
        with self.busy:
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
        with self.busy:
            hist = self.prefs.setdefault('fileHistory', {})
            return hist.setdefault(category, [])


    def clearRecentFiles(self, category="import"):
        """ Clear the list of recent files within a category.
        """
        with self.busy:
            hist = self.prefs.setdefault('fileHistory', {})
            del hist.setdefault(category, [])[:]


    def getPref(self, name, default=None, section=None):
        """ Retrieve a value from the preferences.
            @param prefName: The name of the preference to retrieve.
            @keyword default: An optional default value to return if the
                preference is not found.
            @keyword section: An optional "section" name from which to
                delete. Currently a prefix in this implementation.
        """
        with self.busy:
            if section is not None:
                name = "%s.%s" % (section, name)
            return self.prefs.get(name, self.defaultPrefs.get(name, default))


    def setPref(self, name, val, section=None, persistent=True):
        """ Set the value of a preference. Returns the value set as a
            convenience.
        """
        with self.busy:
            if section is not None:
                name = "%s.%s" % (section, name)
            prefs = self.prefs if persistent else self.defaultPrefs
            prefs[name] = val
            return val


    def hasPref(self, name, section=None, defaults=False):
        """ Check to see if a preference exists, in either the user-defined
            preferences or the defaults.
        """
        with self.busy:
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
        with self.busy:
            if section is not None:
                name = name if name is not None else "*"
                name = "%s.%s" % (section, name)
            if name is None:
                return
            keys = fnmatch.filter(self.prefs.keys(), name)
            for k in keys:
                self.prefs.pop(k, None)
            return len(keys)

    
    def editPrefs(self, parent=None):
        """ Launch the Preferences editor.

        """
        newPrefs = PrefsDialog.editPrefs(parent, self.prefs, self.defaultPrefs)
        if newPrefs is not None:
            self.prefs = newPrefs
            self.savePrefs()
            return True
        return False
    

    #===========================================================================
    # Dictionary work-alike methods 
    #===========================================================================
    
    def __contains__(self, k):
        return self.hasPref(k)

    def __delitem__(self, k):
        if self.hasPref(k):
            return self.deletePref(k)
        raise KeyError(k)

    def __getitem__(self, k):
        if self.hasPref(k):
            return self.getPref(k)
        raise KeyError(k)
    
    def __setitem__(self, k, v):
        return self.setPref(k,v)
    
    def __iter__(self, *args, **kwargs):
        return self.prefs.__iter__(*args, **kwargs)
    
    def get(self, *args, **kwargs):
        return self.getPref(*args, **kwargs)
    
    def items(self):
        return self.prefs.items()
    
    def iteritems(self):
        return self.prefs.iteritems()
    
    def iterkeys(self):
        return self.prefs.iterkeys()
    
    def itervalues(self):
        return self.prefs.itervalues()
    
    def keys(self):
        return self.prefs.keys()
    
    def pop(self, *args):
        if len(args) == 0:
            raise TypeError("pop expected at least 1 arguments, got 0")
        elif len(args) > 2:
            raise TypeError("pop expected at most 2 arguments, got %d" % len(args))
        elif len(args) == 1:
            if not self.hasPref(args[0]):
                raise KeyError(args[0])
        p = self.getPref(*args)
        self.deletePref(args[0])
        return p
    
    def popitem(self, *args, **kwargs):
        return self.prefs.popitem(*args, **kwargs)
    
    def setdefault(self, k, v):
        return self.prefs.setdefault(k,v)

    def values(self):
        return self.prefs.values()
    
        
#===============================================================================
# 
#===============================================================================

class PrefsDialog(SC.SizedDialog):
    """ The viewer preferences editor. This is a self-contained unit; instead
        of instantiating it, use the `editPrefs` method directly from the
        class. That handles all the setup and teardown.
    """

    LANGUAGES = [s for s in dir(wx) if s.startswith("LANGUAGE")]
    LANG_LABELS = [multiReplace(s[9:].title(), 
                                ('_',' '), (' Us',' US'), (' Uk',' UK'),
                                (' Uae',' UAE'), ('UKrain', 'Ukrain'))
                   for s in LANGUAGES]
    
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

        self.pg = pg = PG.PropertyGrid(pane, style=(PG.PG_SPLITTER_AUTO_CENTER |
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
        self.defaultColorsBtn = wx.Button(buttons, -1, "Reset Plot Colors")
        self.defaultsBtn = wx.Button(buttons, -1, "Reset to Defaults")
        wx.Button(buttons, wx.ID_SAVE)
        wx.Button(buttons, wx.ID_CANCEL)
        buttons.SetSizerProps(halign='right')

        self.buildGrid()

        self.defaultColorsBtn.Bind(wx.EVT_BUTTON, self.OnDefaultColorsButton)
        self.defaultsBtn.Bind(wx.EVT_BUTTON, self.OnDefaultsButton)
        self.SetAffirmativeId(wx.ID_SAVE)
        self.SetEscapeId(wx.ID_CANCEL)
        
        self.SetSize((500,688))
        self.SetMinSize((300,200))
        self.SetMaxSize((1000,1000))


    def buildGrid(self):
        """ Build the display.
        """
        showAdvancedOptions = self.prefs.get("showAdvancedOptions", False)
        
        def _add(prop, tooltip=None, advanced=False, **atts):
            # Helper to add properties to the list.
            if advanced and not showAdvancedOptions:
                return
            self.pg.Append(prop)
            if tooltip:
                self.pg.SetPropertyHelpString(prop, tooltip)
            for att, val in atts.iteritems():
                self.pg.SetPropertyAttribute(prop, att, val)
            return prop
        
        self.pg.Append(PG.PropertyCategory("UI Colors"))
        _add(PG.ColourProperty("Plot Background", "plotBgColor"))
        _add(PG.ColourProperty("Major Grid Lines", "majorHLineColor"))
        _add(PG.ColourProperty("Minor Grid Lines", "minorHLineColor"))
        _add(PG.ColourProperty("Buffer Maximum", "maxRangeColor"),
             "The color of the buffer maximum envelope line, when plotting "
             "one source. This color is set automatically when plotting "
             "multiple sources simultaneously.")
        _add(PG.ColourProperty("Buffer Mean", "meanRangeColor"),
             "The color of the buffer mean envelope line, when plotting "
             "one source. This color is set automatically when plotting "
             "multiple sources simultaneously.")
        _add(PG.ColourProperty("Buffer Minimum", "minRangeColor"),
             "The color of the buffer minimum envelope line, when plotting "
             "one source. This color is set automatically when plotting "
             "multiple sources simultaneously.")
        _add(PG.ColourProperty("Warning Range Highlight Color", "warningColor"),
             "The color of the shading over the plot where extreme conditions "
             "may have adversely affected the data (e.g. extreme temperatures "
             "that affect accelerometer accuracy on a Slam Stick X).")
        _add(PG.ColourProperty("Out-of-Range Highlight Color", "outOfRangeColor"),
             "The color of the shading of time before and/or after the "
             "first/last sample in the dataset.")
        _add(PG.FloatProperty("Legend Opacity", "legendOpacity"),
             "The opacity of the legend background; 0 is transparent, "
             "1 is solid", advanced=True)
        
        _add(PG.PropertyCategory("Data"))
        _add(PG.BoolProperty("Remove Total Mean by Default", "removeMean"), 
             "By default, remove the total median of buffer means from the "
             "data (if the data contains buffer mean data).",
             UseCheckbox=True)
        _add(PG.FloatProperty("Rolling Mean Span (seconds)", "rollingMeanSpan"),
             "The width of the time span used to compute the 'rolling mean' "
             "used when \"Remove Rolling Mean from Data\" is enabled.")
        _add(PG.BoolProperty("Disable Bivariate References by Default", "noBivariates"), 
             "By default, prevent bivariate calibration polynomials from "
             "referencing other channels (e.g. accelerometer temperature "
             "compensation). Disabling references improves performance.",
             UseCheckbox=True)
        
        _add(PG.PropertyCategory("Drawing"))
        _add(PG.EnumProperty("Initial Display Layout", "initialDisplayMode",
                             Preferences.INITIAL_DISPLAY))
        _add(PG.IntProperty("Plot Line Width", "plotLineWidth"),
             "The base width of the plot lines. This width will scale with "
             "the antialiasing settings.")
        _add(PG.BoolProperty("Draw Points", "drawPoints"), 
             "If the number of samples shown is significantly fewer than the "
             "number of pixels, draw individual samples as larger points.",
             UseCheckbox=True)
        _add(PG.FloatProperty("Antialiasing Scaling", "antialiasingMultiplier"),
             "A multiplier of screen resolution used when drawing antialiased "
             "graphics.")
        _add(PG.FloatProperty("Noisy Resampling Jitter", "resamplingJitterAmount"), 
             "The size of X axis variation when 'Noise Resampling' is on, "
             "as a normalized percent.")
        _add(PG.FloatProperty("Oversampling Multiplier", 'oversampling'),
             "The maximum number of points sampled for plotting; a multiple of "
             "the width of the plot in pixels.")
        _add(PG.FloatProperty("Condensed Plot Threshold", 'condensedPlotThreshold'),
             "When the number of points on screen exceeds the number of pixels "
             "by this multiple, use the 'condensed' drawing mode. A multiple "
             "of the Oversampling Multiplier.")
        _add(PG.EnumProperty("Legend Position (main view)", "legendPosition",
                             Preferences.LEGEND_POSITIONS))
        
        _add(PG.PropertyCategory("Importing"))
        _add(PG.IntProperty("Pre-Plotting Samples", 'loader_minCount'), 
             "The number of samples to import before doing the first plot. "
             "Note: a very large number may cause performance issues when "
             "importing extremely large recordings.",
             Min=0, Max=25000000, Step=50000)
        self.pg.SetPropertyEditor("loader_minCount","SpinCtrl")
        _add(PG.EnumProperty("When opening another file:", "openAnotherFile",
                             ("Close previous file","Open in new window", "Ask")),
             "The application's behavior when opening a file while another "
             "is already open.")

        _add(PG.PropertyCategory("Scripting"))
        _add(PG.BoolProperty("Enable Scripting", "scriptingEnabled"),
             "Enable Python scripting functionality. Warning: Downloaded "
             "scripts may pose a security risk to your computer. "
             "Use with caution!", UseCheckbox=True)
        
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
        
#         _add(PG.PropertyCategory("Slam Stick X/WVR Special Preferences"))
#         temphelp = ("Accelerometer readings when the temperature (Channel "
#                     "01.1) is %s this value may not be accurate; used for "
#                     "accelerometer display.") 
#         _add(PG.FloatProperty("Temperature Warning, Low", 
#                               "wvr.tempMin"), tooltop=temphelp % "below")
#         _add(PG.FloatProperty("Temperature Warning, High", 
#                               "wvr.tempMax"), tooltip=temphelp % "above")
        
        self.populateGrid(self.prefs)


    def populateGrid(self, prefs):
        """ Puts the contents of preferences dict into the grid after doing
            any data modifications for display.
        """
        # Special case: turn the locale into an index into the list of locales.
        locale = prefs.get('locale', 'LANGUAGE_ENGLISH_US')
        if isinstance(locale, basestring):
            if locale not in self.LANGUAGES:
                locale = 'LANGUAGE_ENGLISH_US'
            localeIdx = self.LANGUAGES.index(locale)
        else:
            localeIdx = locale    
        prefs['locale'] = localeIdx
        
        # Another special case: the open in same window dialog. The user may
        # want to change this without clearing all other 'ask' settings.
        openAnother = prefs.get("ask.openInSameWindow", 2)
        prefs['openAnotherFile'] = {wx.ID_YES: 0, wx.ID_NO: 1}.get(openAnother, 2)
        
        # YA special case: loader prefs
        loaderPrefs = prefs.get('loader', {})
        prefs['loader_minCount'] = loaderPrefs.get('minCount', 500000)
        
        self.pg.SetPropertyValues(prefs)

    #===========================================================================
    # 
    #===========================================================================

    def OnDefaultColorsButton(self, evt):
        """ Restore the default plotting colors.
        """
        self.prefs.pop('plotColors', None)


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

        openAnother = result.pop('openAnotherFile', 2)
        if openAnother == 2:
            result.pop("ask.openInSameWindow", None)
        else:
            result["ask.openInSameWindow"] = (wx.ID_YES, wx.ID_NO)[openAnother]

        loaderMinCount = result.pop('loader_minCount', None)
        if loaderMinCount is not None:
            result.setdefault('loader', {})['minCount'] = loaderMinCount

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
    print d.getChangedPrefs()
#     app.MainLoop()