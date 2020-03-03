'''
enDAQ Lab: Full-featured viewer for data recorded by enDAQ and Slam Stick data
loggers. Also does Slam Stick recorder configuration.

TODO: Remove vestigial features that haven't been fully implemented (operations)
TODO: Clean up `Viewer.ask()`, maybe make it a stand-alone function. It could
    be useful elsewhere.
TODO: Refactor and clean everything. This has grown organically since 2013.

See other TODO items in the code.
'''
from __future__ import absolute_import, print_function

#===============================================================================
#
#===============================================================================

from collections import OrderedDict
from datetime import datetime
import os
import sys
from threading import Event
import time

if (sys.hexversion & 0xffff0000) != 0x02070000:
    raise RuntimeError("This branch requires Python 2.7!")

import wx

if wx.MAJOR_VERSION < 4:
    raise RuntimeError("This branch requires wxPython 4!")

from wx.lib.rcsizer import RowColSizer
from wx.lib.wordwrap import wordwrap

# Graphics (icons, etc.)
import images

# Custom controls, events and base classes
from base import MenuMixin
from common import cleanUnicode, wordJoin
import events

# Views, dialogs and such
from aboutbox import AboutBox
import config_dialog
from converter_editor import ConverterEditor
from fileinfo import RecorderInfoDialog
from renders.fft import FFTView, SpectrogramView, PSDView
from loader import Loader
from plots import PlotSet
from preferences import Preferences
from renders.renderplot import PlotView
import scripting.editor, scripting.shell
import updater
from widgets import export_dialog as xd
from widgets import live_calibration
from widgets.shared import StatusBar
from widgets.device_dialog import selectDevice
from widgets.memorydialog import MemoryDialog
from widgets.range_dialog import RangeDialog
from widgets.timeline import Corner, Timeline, TimeNavigator

# Special helper objects and functions
import devices.efm32_firmware
from threaded_file import ThreadAwareFile

# The actual data-related stuff
from idelib import ebmlite
import idelib.classic.importer
import idelib.multi_importer
import idelib.matfile
import idelib.unit_conversion

# Plug-ins
import plugins
import tools.raw2mat
import tools.filesplit
import tools.ide2csv


#===============================================================================
#
#===============================================================================

from build_info import APPNAME, VERSION, DEBUG, BETA, BUILD_NUMBER, BUILD_TIME
from build_info import REPO_BRANCH, REPO_COMMIT_ID
from logger import logger

__version__= '.'.join(map(str, VERSION))
__copyright__=(u"Copyright (c) %s Mid\xe9 Technology" %
               (datetime.fromtimestamp(BUILD_TIME).year))

if DEBUG:
    __version__ = '%s DEBUG b%04d' % (__version__, BUILD_NUMBER)
    import socket
    if socket.gethostname() in ('HADLEY', 'DEDHAM', 'LEE'):
        try:
            # TODO: Make sure this doesn't make it into PyInstaller build
            import yappi
            yappi.start()
            logger.info('yappi profiler started.')
        except ImportError:
            logger.info('Could not import profiler (yappi), continuing...')
            pass
elif BETA:
    __version__ = '%s BETA b%04d' % (__version__, BUILD_NUMBER)


# The feedback form URL. Will show up as an item in the Help menu if provided.
FEEDBACK_URL = "https://endaq.com/pages/contact"

RESOURCES_URL = "https://support.endaq.com/?utm_source=Slam-Stick-X-Data-Logger&utm_medium=Device&utm_content=Link-to-Slam-Stick-Resources-web-page-from-Device&utm_campaign=Slam-Stick-X"


#===============================================================================
#
#===============================================================================

ANTIALIASING_MULTIPLIER = 3.33
RESAMPLING_JITTER = 0.125

FILESIZE_WARNING = 33554432


#===============================================================================
#
#===============================================================================

class Viewer(wx.Frame, MenuMixin):
    """ The main data viewer frame, wrapping all major functionality.
    """

    timeScalar = 1.0/(10**6)
    timerange = (1043273L * timeScalar*2,7672221086L * timeScalar)

    # Custom menu IDs
    # TODO: Consider using literal IDs, so they are sure to be consistent
    #     between runs of the application.
    ID_FILE_RECENT = wx.NewIdRef()
    ID_FILE_EXPORT = wx.NewIdRef()
    ID_FILE_PROPERTIES = wx.NewIdRef()
    ID_FILE_MULTI = wx.NewIdRef()
    ID_EDIT_CLEARPREFS = wx.NewIdRef()
    ID_EDIT_RANGES = wx.NewIdRef()
    ID_VIEW_ADDSOURCE = wx.NewIdRef()
    ID_VIEW_NEWTAB = wx.NewIdRef()
    ID_VIEW_ZOOM_OUT_Y = wx.NewIdRef()
    ID_VIEW_ZOOM_IN_Y = wx.NewIdRef()
    ID_VIEW_ZOOM_FIT_Y = wx.NewIdRef()
    ID_VIEW_ZOOM_FIT_ALL = wx.NewIdRef()
    ID_VIEW_ANTIALIAS = wx.NewIdRef()
    ID_VIEW_JITTER = wx.NewIdRef()
    ID_VIEW_UTCTIME = wx.NewIdRef()
    ID_VIEW_LOCALTIME = wx.NewIdRef()
    ID_VIEW_MINMAX = wx.NewIdRef()
    ID_VIEW_MEAN = wx.NewIdRef()
    ID_VIEW_LINES_MAJOR = wx.NewIdRef()
    ID_VIEW_LINES_MINOR = wx.NewIdRef()
    ID_VIEW_LEGEND = wx.NewIdRef()
    ID_VIEW_HOLLOW = wx.NewIdRef()
    ID_DEVICE_CONFIG = wx.NewIdRef()
    ID_DEVICE_UPDATE = wx.NewIdRef()
    ID_DATA_MEAN_SUBMENU = wx.NewIdRef()
    ID_DATA_NOMEAN = wx.NewIdRef()
    ID_DATA_MEAN = wx.NewIdRef()
    ID_DATA_MEAN_TOTAL = wx.NewIdRef()
    ID_DATA_WARNINGS = wx.NewIdRef()
    ID_DATA_DISPLAY = wx.NewIdRef()
    ID_DATA_DISPLAY_NATIVE = wx.NewIdRef()
    ID_DATA_DISPLAY_CONFIG = wx.NewIdRef()
    ID_DATA_EDIT_CAL = wx.NewIdRef()
    ID_DATA_DISABLE_BIVARIATES = wx.NewIdRef()
    ID_DATA_RENDER = wx.NewIdRef()
    ID_DATA_RENDER_FFT = wx.NewIdRef()
    ID_DATA_RENDER_PSD = wx.NewIdRef()
    ID_DATA_RENDER_SPEC = wx.NewIdRef()
    ID_DATA_RENDER_PLOTS = wx.NewIdRef()
    ID_SCRIPTING_RUN = wx.NewIdRef()
    ID_SCRIPTING_RECENT = wx.NewIdRef()
    ID_SCRIPTING_EDIT = wx.NewIdRef()
    ID_SCRIPTING_CONSOLE = wx.NewIdRef()
    ID_SCRIPT1 = 2000 # Recent script menu ID; other recent scripts increment.
    ID_TOOLS = wx.NewIdRef()
    ID_TOOLS_SHOW_PLUGINS = wx.NewIdRef()
    ID_HELP_CHECK_UPDATES = wx.NewIdRef()
    ID_HELP_FEEDBACK = wx.NewIdRef()
    ID_HELP_RESOURCES = wx.NewIdRef()

    ID_DEBUG_SUBMENU = wx.NewIdRef()
    ID_DEBUG_SAVEPREFS = wx.NewIdRef()
    ID_DEBUG0 = wx.NewIdRef()
    ID_DEBUG1 = wx.NewIdRef()


    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Frame/MenuMixin arguments plus:

            @keyword app: The viewer's parent application.
        """
        splash  = kwargs.pop('splash', True)
        openDialog = kwargs.pop('openDialog', False)
        self.app = kwargs.pop('app', None)
        self.units = kwargs.pop('units',('Time','s'))
        self.number = kwargs.pop('number', 1)

        self.drawingSuspended = Event()
        self.suspendDrawing()

        filename = kwargs.pop('filename', None)
        if filename:
            splash = False

        displaySize = wx.DisplaySize()
        windowSize = int(displaySize[0]*.66), int(displaySize[1]*.66)
        kwargs.setdefault('size', windowSize)
        kwargs.setdefault('title', self.app.getWindowTitle(self))

        super(Viewer, self).__init__(*args, **kwargs)

        self.root = self # for consistency with other objects
        self.dataset = None
        self.session = None
        self.dataSources = OrderedDict()
        self.tabTypes = {} # Each tab shows one type of unit
        self.cancelQueue = []
        self.plotarea = None
        self.warningRanges = {}

        self.menubar = None
        self.showAdvanced = False
        self.loadPrefs()

        self.buildUI(splash)
        self.Centre()
        self.Show()

        self._nextColor = 0
        self.setVisibleRange(self.timerange[0], self.timerange[1])

        # FUTURE: FFT views as separate windows will eventually be refactored.
        self.childViews = {}
        self.console = None

        self.Bind(events.EVT_SET_VISIBLE_RANGE, self.OnSetVisibleRange)
        self.Bind(events.EVT_SET_TIME_RANGE, self.OnSetTimeRange)
        self.Bind(events.EVT_PROGRESS_START, self.OnProgressStart)
        self.Bind(events.EVT_PROGRESS_UPDATE, self.OnProgressUpdate)
        self.Bind(events.EVT_PROGRESS_END, self.OnProgressEnd)
        self.Bind(events.EVT_INIT_PLOTS, self.initPlots)
        self.Bind(events.EVT_IMPORT_ERROR, self.handleError)

        # Note: suspend/resume drawing events not currently generated anywhere.
        self.Bind(events.EVT_SUSPEND_DRAWING, self.suspendDrawing)
        self.Bind(events.EVT_RESUME_DRAWING, self.resumeDrawing)

        self.Bind(wx.EVT_CLOSE, self.OnClose)

        if filename is not None:
            if wx.GetKeyState(wx.WXK_SHIFT):
                self.setNoBivariates(True)

            if isinstance(filename, basestring):
                self.openFile(filename)
            else:
                self.openMultiple(filename)

        elif openDialog or self.app.getPref('openOnStart', True):
            self.OnFileOpenMenu(None)


    def __repr__(self):
        """ x.__repr__() <==> repr(x), but more human-readable.
            To make scripting a little simpler.
        """
        try:
            return '<%s %s: "%s">' % (type(self).__name__, self.number,
                                  self.app.getWindowTitle(self, showApp=False,
                                                          number=False))
        except:
            return super(Viewer, self).__repr__()


    def loadPrefs(self):
        """ Get all the attributes that are read from the preferences.
            Separated from `__init__` to allow reloading after editing in the
            preferences dialog.
        """
        self.uiBgColor = wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE)
        self.xFormatter = "X: %%.%df %%s" % self.app.getPref('precisionX', 4)
        self.yFormatter = "Y: %%.%df %%s" % self.app.getPref('precisionY', 4)
        self.antialias = self.app.getPref('antialiasing', False)
        self.aaMultiplier = self.app.getPref('antialiasingMultiplier',
                                             ANTIALIASING_MULTIPLIER)
        self.noisyResample = self.app.getPref('resamplingJitter', False)
        self.showUtcTime = self.app.getPref('showUtcTime', True)
        self.showLocalTime = self.app.getPref('showLocalTime', False)
        self.drawMinMax = self.app.getPref('drawMinMax', False)
        self.drawMean = self.app.getPref('drawMean', False)
        self.drawMajorHLines = self.app.getPref('drawMajorHLines', True)
        self.drawMinorHLines = self.app.getPref('drawMinorHLines', False)
        self.showLegend = self.app.getPref('showLegend', True)
        self.legendPos = self.app.getPref('legendPosition', 1)

        self.drawHollowPlot = self.app.getPref('drawHollowPlot', False)
        self.noBivariates = self.app.getPref('noBivariates', False)

        self.showDebugChannels = self.app.getPref('showDebugChannels', True)

        adv = self.app.getPref('showAdvancedOptions', False)

        if self.plotarea is not None:
            # reload, probably
            for p in self.plotarea:
                p.loadPrefs()
            self.plotarea.redraw()

        if self.menubar is not None:
            self.OnToggleUtcTime(self.showUtcTime)
            self.OnToggleLocalTime(self.showLocalTime)
            if self.app.getPref('scriptingEnabled', False):
                self.insertScriptingMenu()
            if adv and adv!= self.showAdvanced:
                self.insertAdvancedMenus()
                self.buildToolsMenu()
        
        self.showAdvanced = adv


    def buildMenus(self):
        """ Construct and configure the view's menu bar. Called once by
            `buildUI()`. Used internally.
        """
        self.menubar = wx.MenuBar()

        #=======================================================================
        # "File" menu
        
        fileMenu = self.addMenu(self.menubar,  '&File')
        self.addMenuItem(fileMenu, wx.ID_NEW,
                         "&New Viewer Window\tCtrl+N",
                         "Create a new viewer, empty viewer window",
                         self.OnFileNewMenu)
        self.addMenuItem(fileMenu, wx.ID_CLOSE,
                         "Close Viewer Window\tCtrl+W",
                         "Close the current document", self.OnClose)

        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_OPEN,
                         "&Open...\tCtrl+O",
                         "Load and display a recording file",
                         self.OnFileOpenMenu)
#         self.addMenuItem(fileMenu, self.ID_FILE_MULTI,
#                          "Open Multiple...", "",
#                          self.OnFileOpenMulti)

        # "Recent Files" submenu. This does not use `wx.FileHistory`. Consider
        # using that later.
        self.recentFilesMenu = wx.Menu()
        fileMenu.Append(self.ID_FILE_RECENT, "Open Recent",
                            self.recentFilesMenu)
        self.Bind(wx.EVT_UPDATE_UI, self.OnShowRecentFiles, id=self.ID_FILE_RECENT)
        self.Bind(wx.EVT_MENU_RANGE, self.OnPickRecentFile, id=wx.ID_FILE1, id2=wx.ID_FILE9)

        self.addMenuItem(fileMenu, wx.ID_CANCEL, "Stop Importing\tCtrl-.",
                         "Cancel the current import",
                         self.cancelOperation, enabled=False)

        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, self.ID_FILE_EXPORT,
                         "&Export Data...\tCtrl+S",
                         "Export data to another format",
                         self.OnFileExportMenu)

        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, self.ID_FILE_PROPERTIES,
                         "Recording Properties...\tCtrl+I",
                         "Display information about this recording file",
                         self.OnFileProperties)

#         fileMenu.AppendSeparator()
#         self.addMenuItem(fileMenu, wx.ID_PRINT, "&Print...", "", enabled=False)
#         self.addMenuItem(fileMenu, wx.ID_PRINT_SETUP, "Print Setup...", "",
#                          enabled=False)

        fileMenu.AppendSeparator()
        self.addMenuItem(fileMenu, wx.ID_EXIT,
                         'E&xit\tCtrl+Q',
                         'Close all files and quit %s.' % APPNAME,
                self.OnFileExitMenu)
        wx.App.SetMacExitMenuItemId(wx.ID_EXIT)

        #=======================================================================
        # "Edit" menu

        editMenu = self.addMenu(self.menubar, '&Edit')
        self.addMenuItem(editMenu, wx.ID_CUT, "Cut", "", enabled=False)
        self.addMenuItem(editMenu, wx.ID_COPY, "Copy", "", enabled=False)
        self.addMenuItem(editMenu, wx.ID_PASTE, "Paste", "", enabled=False)
        editMenu.AppendSeparator()
        self.addMenuItem(editMenu, wx.ID_PREFERENCES, "Preferences...",
                         "Configure and customize %s" % APPNAME,
                         self.app.editPrefs)

        #=======================================================================
        # "View" menu
        
        viewMenu = self.addMenu(self.menubar, 'V&iew')
        self.addMenuItem(viewMenu, wx.ID_REFRESH, "&Redraw Plots\tCtrl+R", "",
                         self.plotarea.redraw)
        viewMenu.AppendSeparator()

        self.viewNewTabMenu = self.addSubMenu(viewMenu, self.ID_VIEW_NEWTAB,
                                              "Create New Tab")
        self.viewSourceMenu = self.addSubMenu(viewMenu, self.ID_VIEW_ADDSOURCE,
                                              "Display Channels")
        self.addMenuItem(viewMenu, self.ID_VIEW_LEGEND,
                         "Show Legend\tCtrl+L",
                         "Display the overlay listing plot names and colors",
                         self.OnLegendToggle, kind=wx.ITEM_CHECK)
        self.addMenuItem(viewMenu, self.ID_VIEW_HOLLOW,
                         "'Hollow' Envelope Drawing",
                         "Hollow mode: When zoomed out, plot only the minimum "
                         "and maximum values",
                         self.OnHollowToggle, kind=wx.ITEM_CHECK)
        viewMenu.AppendSeparator()

        self.addMenuItem(viewMenu, self.ID_EDIT_RANGES,
                         "Edit Visible Ranges...\tCtrl+E",
                         "Change the displayed ranges numerically",
                         self.OnEditRanges)
        self.addMenuItem(viewMenu, wx.ID_ZOOM_OUT, "Zoom Out X\tCtrl+-",
                         "Zoom out on the horizontal axis",
                         self.OnZoomOutX)
        self.addMenuItem(viewMenu, wx.ID_ZOOM_IN, "Zoom In X\tCtrl+=",
                         "Zoom in on the horizontal axis",
                         self.OnZoomInX)
        self.addMenuItem(viewMenu, wx.ID_ZOOM_FIT, "Zoom to Fit X\tCtrl+0",
                         "Zoom horizontally to fit the entire data set",
                         self.OnZoomFitX)
        self.addMenuItem(viewMenu, self.ID_VIEW_ZOOM_OUT_Y, "Zoom Out Y\tAlt+-",
                         'Zoom out on the vertical axis.',
                         self.OnZoomOutY)
        self.addMenuItem(viewMenu, self.ID_VIEW_ZOOM_IN_Y, "Zoom In Y\tAlt+=",
                         'Zoom in on the vertical axis',
                         self.OnZoomInY)
        self.addMenuItem(viewMenu, self.ID_VIEW_ZOOM_FIT_Y,
                         "Zoom to Fit Y\tAlt+0",
                         'Zoom vertically to fit all data in the visible interval.',
                         self.OnZoomFitY)
        self.addMenuItem(viewMenu, self.ID_VIEW_ZOOM_FIT_ALL,
                         "Zoom to Fit All\tAlt+Ctrl+0",
                         'Zoom to display the entirety of the data set.',
                         self.OnZoomFitAll)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_ANTIALIAS,
                         "Antialiased Drawing",
                         "Toggle antialiased drawing",
                         self.OnToggleAA, kind=wx.ITEM_CHECK)
        self.addMenuItem(viewMenu, self.ID_VIEW_JITTER,
                        "Noisy Resampling",
                        "Remove aliasing by slightly randomizing the sampling",
                        self.OnToggleNoise, kind=wx.ITEM_CHECK)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_MINMAX,
                         "Show Buffer Minimum/Maximum",
                         "Draw the envelop around the raw data to simplify" \
                         " the view for large data sets",
                         self.OnToggleMinMax, kind=wx.ITEM_CHECK)
        self.addMenuItem(viewMenu, self.ID_VIEW_MEAN,
                         "Show Buffer Mean",
                         "Draw the mean of the raw data across every block of"
                         " data points",
                         self.OnToggleViewMean, kind=wx.ITEM_CHECK)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_LINES_MAJOR,
                         "Show Major Horizontal Grid Lines\tCtrl+'",
                         "Toggle the display of horizontal grid lines",
                         self.OnToggleLinesMajor, kind=wx.ITEM_CHECK)
        self.addMenuItem(viewMenu, self.ID_VIEW_LINES_MINOR,
                         "Show Minor Horizontal Grid Lines\tCtrl+Shift+'",
                         "Toggle the display of minor horizontal grid lines",
                         self.OnToggleLinesMinor, kind=wx.ITEM_CHECK)
        viewMenu.AppendSeparator()
        self.addMenuItem(viewMenu, self.ID_VIEW_UTCTIME,
                         "Show Absolute UTC Time",
                         "Display the UTC time corresponding to the mouse's" \
                         " X position",
                         self.OnToggleUtcTime, kind=wx.ITEM_CHECK,
                         checked=self.showUtcTime)
        self.addMenuItem(viewMenu, self.ID_VIEW_LOCALTIME,
                         "Show Absolute Local Time",
                         "Display the local time corresponding to the mouse's" \
                         " X position",
                         self.OnToggleLocalTime, kind=wx.ITEM_CHECK,
                         checked=self.showLocalTime)

        #=======================================================================
        # "Device" menu
        
        self.deviceMenu = self.addMenu(self.menubar, 'De&vice')
        self.addMenuItem(self.deviceMenu, self.ID_DEVICE_CONFIG,
                         "Configure &Device...\tCtrl+D",
                         "Select and configure a recording device",
                         self.OnDeviceConfigMenu)
        # "Update Recorder Firmware" item added by `insertAdvancedMenus()`

        #=======================================================================
        # "Data" menu
        
        dataMenu = self.addMenu(self.menubar, "&Data")
        meanMenu = self.addSubMenu(dataMenu, self.ID_DATA_MEAN_SUBMENU,
                                   "Remove Mean")
        self.addMenuItem(meanMenu, self.ID_DATA_NOMEAN,
                         "Do Not Remove Mean",
                         "Plot data without modifying vertical axis",
                         self.OnDontRemoveMeanCheck, kind=wx.ITEM_RADIO)
        self.addMenuItem(meanMenu, self.ID_DATA_MEAN,
                         "Remove Rolling Mean from Data",
                         "Plot data with the average of a set interval removed",
                         self.OnRemoveRollingMeanCheck, kind=wx.ITEM_RADIO)
        self.addMenuItem(meanMenu, self.ID_DATA_MEAN_TOTAL,
                         "Remove Total Mean from Data",
                         "Plot data with the average of the total file removed",
                         self.OnRemoveTotalMeanCheck, kind=wx.ITEM_RADIO)

        self.displayMenu = self.addSubMenu(dataMenu, self.ID_DATA_DISPLAY,
                                           "Display Units")
        self.addMenuItem(self.displayMenu, self.ID_DATA_DISPLAY_NATIVE,
                         "Native Units",
                         "Display data in the file's original units",
                         self.OnConversionPicked, kind=wx.ITEM_RADIO)

        dataMenu.AppendSeparator()
        renderMenu = self.addSubMenu(dataMenu, self.ID_DATA_RENDER, "Render")
        self.addMenuItem(renderMenu, self.ID_DATA_RENDER_PLOTS,
                         "Render &Plots...",
                         'Generate a printable plot in a new window.',
                         self.renderPlot)
        self.addMenuItem(renderMenu, self.ID_DATA_RENDER_FFT,
                         "Render &FFT...\tCtrl+F",
                         "Generate an FFT plot in a new window",
                         self.renderPlot)
        self.addMenuItem(renderMenu, self.ID_DATA_RENDER_PSD,
                         "Render &PSD...\tCtrl+P",
                         "Generate a PSD plot in a new window",
                         self.renderPlot)
        self.addMenuItem(renderMenu, self.ID_DATA_RENDER_SPEC,
                         "Render &Spectrogram...\tCtrl+G",
                         "Generate a spectrogram (2D FFT) in a new window",
                         self.renderPlot)
        dataMenu.AppendSeparator()

        self.addMenuItem(dataMenu, self.ID_DATA_EDIT_CAL,
                         "&Edit Calibration Polynomials...",
                         "Edit the functions that convert raw data into"
                         " engineering units and calibrated",
                         self.OnEditCalibration)

        self.addMenuItem(dataMenu, self.ID_DATA_DISABLE_BIVARIATES,
                         "&Disable Bivariate References",
                         "Improve plotting speed at the expense of disabling"
                         " temperature dependent calibration",
                         self.OnDisableBivariates, kind=wx.ITEM_CHECK)

        dataMenu.AppendSeparator()
        self.viewWarningsMenu = self.addSubMenu(dataMenu, self.ID_DATA_WARNINGS,
                          "Display Range Warnings")

        #=======================================================================
        # "Scripting" menu: only shows if enabled in preferences. Inserted
        # by another method, so updating the preferences makes it appear.

        if self.app.getPref('scriptingEnabled', False):
            self.insertScriptingMenu()

        #=======================================================================
        # "Tools" menu: some items only appear if 'show advanced options'
        # preference is enabled. Built by another method, so updating the
        # preferences makes it appear.

        self.toolMenu = self.addMenu(self.menubar, "Tools")
        self.buildToolsMenu()

        #=======================================================================
        # "Help" menu

        helpMenu = self.addMenu(self.menubar, '&Help')
        self.addMenuItem(helpMenu, wx.ID_ABOUT,
                         "About %s..." % self.app.fullAppName,
                         "About %s..." % self.app.fullAppName,
                         self.OnHelpAboutMenu)
        helpMenu.AppendSeparator()
        self.addMenuItem(helpMenu, self.ID_HELP_CHECK_UPDATES,
                         "Check for Updates",
                         "Check online for a newer version of %s" % APPNAME,
                         self.OnHelpCheckUpdates)

        helpMenu.AppendSeparator()
        self.addMenuItem(helpMenu, self.ID_HELP_RESOURCES,
                         "enDAQ Recorder Resources",
                         "Documentation, downloads and other resources",
                         self.OnHelpResources)
        self.addMenuItem(helpMenu, self.ID_HELP_FEEDBACK,
                         "Send Feedback",
                         "Submit questions, comments, and suggestions for %s" \
                         % APPNAME,
                         self.OnHelpFeedback)

        if DEBUG:
            helpMenu.AppendSeparator()
            debugMenu = self.addSubMenu(helpMenu, self.ID_DEBUG_SUBMENU,
                                        "Debugging")
            self.addMenuItem(debugMenu, self.ID_DEBUG_SAVEPREFS,
                             "Save All Preferences", "",
                             lambda(_evt): self.app.saveAllPrefs())
            self.addMenuItem(debugMenu, self.ID_DEBUG0,
                             "Open Multiple...",
                             "EXPERIMENTAL: Merge multiple recordings",
                             self.OnFileOpenMulti)
            self.addMenuItem(debugMenu, self.ID_DEBUG1,
                             "Render Plots/FFTs/etc. in foreground",
                             "Do stuff in foreground for debugging",
                             self.OnForegroundRender, kind=wx.ITEM_CHECK)

        #=======================================================================
        # Finishing touches.
        
        self.SetMenuBar(self.menubar)
        self.insertAdvancedMenus()
        self.enableMenus(False)


    def buildToolsMenu(self):
        """ Construct (or empty and reconstruct) the "Tools" menu contents.
            Called in `buildMenus()` and after the preferences have been
            edited (so the menu will appear after 'show advanced options' is
            checked).
        """
        map(self.toolMenu.DestroyItem, self.toolMenu.GetMenuItems())

        self.toolPlugins = {}
        tools = self.app.plugins.find(type='tool', isModule=True)
        extTools = self.app.plugins.find(type='tool', isModule=False)

        if not self.app.getPref('showAdvancedOptions', False):
            # Remove tools marked as 'advanced'
            tools = [t for t in tools if not t.info.get('advanced', False)]
            extTools = [t for t in extTools if not t.info.get('advanced', False)]

        if tools or extTools:
            tools.sort(key=lambda x: x.name)
            for t in tools:
                # Get the tool's menu ID or generate one (one time only)
                tid = t.info.get('_wxId', None)
                if tid is None:
                    tid = t.info.setdefault('_wxId', wx.NewIdRef())
                self.toolPlugins[tid] = t
                self.addMenuItem(self.toolMenu, tid, t.name, t.desc,
                                 self.OnToolMenuSelection)
            if extTools:
                extTools.sort(key=lambda x: x.name)
                self.toolMenu.AppendSeparator()
                for t in extTools:
                    tid = t.info.get('_wxId', None)
                    if tid is None:
                        tid = t.info.setdefault('_wxId', wx.NewIdRef())
                    self.toolPlugins[tid] = t
                    self.addMenuItem(self.toolMenu, tid, t.name, t.desc,
                                     self.OnToolMenuSelection)
            self.toolMenu.AppendSeparator()
            
        self.addMenuItem(self.toolMenu, self.ID_TOOLS_SHOW_PLUGINS,
                         "Show Plug-Ins Directory",
                         "Open the plug-ins folder (%s)" % self.app.pluginsDir,
                         self.OnToolMenuShowPlugins)
        

    def insertScriptingMenu(self):
        """ Insert the 'Scripting' menu, if it isn't already present. Called
            in `buildMenus()` and after the preferences have been edited (so
            the menu will appear after 'enable scripting' is checked').
        """
        if not self.app.getPref('scriptingEnabled', False):
            return
        
        if self.menubar.FindItemById(self.ID_SCRIPTING_RUN) is None:
            scriptMenu = wx.Menu()
            self.addMenuItem(scriptMenu, self.ID_SCRIPTING_RUN,
                             "&Run Script...\tCtrl+Shift+R",
                             'Open the Python script editor.',
                             self.OnScriptRun)
            
            self.recentScriptsMenu = wx.Menu()
            scriptMenu.Append(self.ID_SCRIPTING_RECENT, "Run Recent Script",
                              self.recentScriptsMenu)
            self.Bind(wx.EVT_UPDATE_UI, self.OnShowRecentScripts, 
                      id=self.ID_SCRIPTING_RECENT)
            self.Bind(wx.EVT_MENU_RANGE, self.OnPickRecentScript,
                      id=self.ID_SCRIPT1, id2=self.ID_SCRIPT1+7)
    
            scriptMenu.AppendSeparator()
            self.addMenuItem(scriptMenu, self.ID_SCRIPTING_EDIT,
                             "Open Script &Editor\tCtrl+Shift+E",
                             'Open the Python script editor.',
                             self.OnShowScriptEditor)
            self.addMenuItem(scriptMenu, self.ID_SCRIPTING_CONSOLE,
                             "Open Python &Console\tCtrl+Shift+C",
                             "Open the Python interactive interpreter",
                             self.OnShowScriptConsole)
            self.menubar.Insert(5, scriptMenu, '&Scripting')
    
    
    def insertAdvancedMenus(self):
        """ Insert 'advanced' menu items into the menubar. Called in 
            `buildMenus()` and after the preferences have been edited (so the
            menus will appear after 'enable scripting' is checked').
        """
        if not self.app.getPref('showAdvancedOptions', False):
            return
        
        if self.menubar.FindItemById(self.ID_DEVICE_UPDATE) is None:
            self.deviceMenu.AppendSeparator()
            self.addMenuItem(self.deviceMenu, self.ID_DEVICE_UPDATE,
                             "Update Recorder Firmware...",
                             "Update the firmware on a recording device",
                             self.OnDeviceUpdateFW)
        # Other advanced options can be enabled here.
        

    def OnForegroundRender(self, evt):
        """ For debugging: handle 'render in foreground' menu item change.
        """
        from renders import fft
        fft.FOREGROUND=evt.IsChecked()


    def buildUI(self, splash=True):
        """ Construct and configure all the viewer window's panels. Called once
            by the constructor. Used internally.
        """
        self.SetIcon(images.icon.GetIcon())
        self.SetMinSize((320,240))

        self.root = self
        self.navigator = TimeNavigator(self, root=self)
        self.corner = Corner(self, root=self)
        self.plotarea = PlotSet(self, -1, root=self, splash=splash)
        self.timeline = Timeline(self, root=self)

        # List of components that display time-related data.
        # The second element is whether or no they do live updates.
        self.timeDisplays = [[self.navigator, True],
                             [self.plotarea, False],
                             [self.corner, True],
                             [self.timeline, True]]

        sizer = RowColSizer()
        sizer.Add(self.navigator, flag=wx.EXPAND, row=0, col=0, colspan=2)
        sizer.Add(self.plotarea, flag=wx.EXPAND, row=1, col=0, colspan=2)
        sizer.Add(self.corner, flag=wx.EXPAND, row=2, col=0)
        sizer.Add(self.timeline, flag=wx.EXPAND, row=2, col=1)

        sizer.AddGrowableCol(1)
        sizer.AddGrowableRow(1)

        self.SetSizer(sizer)
        self.statusBar = StatusBar(self)
        self.SetStatusBar(self.statusBar)

        self.enableChildren(False)

        if splash:
            self.plotarea.Enable()

        self.buildMenus()

        self.setMenuItem(self.menubar, self.ID_VIEW_LEGEND,
                         checked=self.showLegend)
        self.setMenuItem(self.menubar, self.ID_VIEW_HOLLOW,
                         checked=self.drawHollowPlot)


    def enableMenus(self, enabled=True):
        """ Enable (or disable) all menus applicable only when a file has
            been imported.

            @keyword enabled: `True` (default) to enable the menus, `False`
                to disable.
        """
        # These are the menus that are enabled even when there's no file open.
        # There are fewer of them than menus that are disabled.
        menus = [wx.ID_NEW, wx.ID_OPEN, wx.ID_CLOSE, wx.ID_EXIT,
                self.ID_FILE_RECENT,
                 self.ID_DEVICE_CONFIG, self.ID_DEVICE_UPDATE, wx.ID_ABOUT,
                 wx.ID_PREFERENCES,
                 self.ID_HELP_CHECK_UPDATES, self.ID_HELP_FEEDBACK,
                 self.ID_HELP_RESOURCES,
                 self.ID_FILE_MULTI, self.ID_TOOLS, self.ID_TOOLS_SHOW_PLUGINS,
                 self.ID_SCRIPTING_EDIT, self.ID_SCRIPTING_CONSOLE,
                 self.ID_SCRIPTING_RUN, self.ID_SCRIPTING_RECENT,
                 self.ID_DEBUG_SUBMENU, self.ID_DEBUG_SAVEPREFS,
                 self.ID_DEBUG0, self.ID_DEBUG1,
                 ]
        menus.extend([t.info['_wxId'] for t in self.app.plugins.find(type='tool')
                      if '_wxId' in t.info])

        if self.dataset:
            menus.append(self.ID_VIEW_NEWTAB)
            menus.extend(self.tabTypes.keys())

        if not enabled:
            self.enableMenuItems(self.menubar, menus, True, False)
        else:
            self.enableMenuItems(self.menubar, enable=True)
            if self.dataset:
                enableCal = len(self.dataset.transforms) > 0
                self.setMenuItem(self.menubar, self.ID_DATA_EDIT_CAL,
                                 enabled=enableCal)

        # Some items should always be disabled unless explicitly enabled
        alwaysDisabled = (wx.ID_CUT, wx.ID_COPY, wx.ID_PASTE,
                          wx.ID_PRINT, wx.ID_PRINT_SETUP)

        self.enableMenuItems(self.menubar, alwaysDisabled, False)
        self.setMenuItem(self.menubar, self.ID_VIEW_LEGEND,
                         checked=self.showLegend)


    def enableChildren(self, enabled=True):
        """ Enable (or disable) all child UI items.

            @keyword enabled: `True` (default) to enable the children,
                `False` to disable.
        """
        for c in self.Children:
            c.Enable(enabled)


    def buildAddChannelMenu(self, *args):
        """ Populate the View->Display Channels menu with plots in the file.
        """
        map(self.viewSourceMenu.DestroyItem, self.viewSourceMenu.GetMenuItems())
        for n,s in enumerate(self.dataSources.iteritems(),1):
            txt = s[1].parent.displayName
            if n < 10:
                # Add keyboard shortcut for first 9 sources
                txt = "%s\tCtrl+%d" % (txt, n)
            self.addMenuItem(self.viewSourceMenu, s[0], txt, "",
                             self.OnSourceChecked, kind=wx.ITEM_CHECK)


    def buildNewTabMenu(self, *args):
        """ Populate the View->New Tab menu with measurement types from the
            current dataset.
        """
        self.tabTypes.clear()
        map(self.viewNewTabMenu.DestroyItem, self.viewNewTabMenu.GetMenuItems())
        for t in sorted(set([p.parent.units for p in self.dataSources.values()])):
            tid = wx.NewIdRef()
            self.tabTypes[tid] = t
            self.addMenuItem(self.viewNewTabMenu, tid, t[0], "",
                             self.OnNewTabPicked)


    def buildWarningMenu(self, *args):
        """ Populate the Data->Display Range Warnings menu with 'idiot light'
            warning ranges from the current dataset.
        """
        self.warningRanges.clear()
        for i in self.viewWarningsMenu.GetMenuItems():
            self.viewWarningsMenu.DestroyItem(i)

        if len(self.plotarea.warningRanges) == 0:
            self.addMenuItem(self.viewWarningsMenu, -1, "None", "", None,
                             enabled=False)
            return

        for w in sorted(self.plotarea.warningRanges.values()):
            wid = w.menuId
            self.warningRanges[wid] = w
            self.addMenuItem(self.viewWarningsMenu, wid, w.source.displayName,
                             "",
                             self.OnDataWarningsCheck, kind=wx.ITEM_CHECK)


    def buildDisplayMenu(self):
        """ Populate the Data->Display menu with applicable unit converters.
            Only those that match channels in the dataset are shown.
        """
        for mi in self.displayMenu.GetMenuItems():
            if mi.GetId() == self.ID_DATA_DISPLAY_NATIVE:
                continue
            self.displayMenu.DestroyItem(mi)
        if self.dataset is None:
            self.displayMenu.Enable(False)
            return
        self.unitConverters = {self.ID_DATA_DISPLAY_NATIVE: None}
        cons = idelib.unit_conversion.getApplicableConverters(self.dataset)

        for c in sorted(cons, key=lambda x: x.units):
            params = {}
            if c.parameters is not None:
                for p in c.parameters:
                    params[p[0]] = self.app.getPref(p[0], p[-1], section=c.__name__)
            cid = wx.NewIdRef()
            self.unitConverters[cid] = c(dataset=self.dataset, **params)

            if c.units[0] is None:
                # Unit converters are generic, and can have 'None' as units[0]
                label = "Display as %s" % c.units[1]
            else:
                label = "Display %s as %s" % c.units

            self.addMenuItem(self.displayMenu, cid, label, "",
                             self.OnConversionPicked, kind=wx.ITEM_RADIO)

        self.displayMenu.AppendSeparator()
        self.addMenuItem(self.displayMenu, self.ID_DATA_DISPLAY_CONFIG,
                         "Configure Unit Conversion...", "",
                         self.OnConversionConfig)


    def promptBadTransforms(self):
        """ Inform the user that the recording has bad polynomials, e.g.
            the file is missing data for a referenced channel (i.e.
            temperature).
        """
        if not self.noBivariates:
            # XXX: HACK: This assumes the issue is bad bivariates, which it
            # probably is, but it isn't necessarily so. Handle better!
            self.setNoBivariates(True)
            self.FindItemInMenuBar(self.ID_DATA_DISABLE_BIVARIATES).Enable(False)

            wx.MessageBox("Bivariate calibration could not be applied.\n\n"
              "A calibration data source contained no data. Bivariate "
              "polynomials have been disabled.", "Calibration Error",
              wx.OK|wx.ICON_WARNING, self)

        # TODO: log other transform errors. This can get called immediately
        # after the dialog has been displayed, however, so it should be
        # ignored in those cases.
        logger.error("Bad transforms detected, but bivariates already disabled")


    #===========================================================================
    #
    #===========================================================================

    def ask(self, message, title="Confirm", style=wx.YES_NO | wx.NO_DEFAULT,
            icon=wx.ICON_QUESTION, parent=None, pref=None, saveNo=True,
            extendedMessage=None, rememberMsg=None, persistent=True,
            textwrap=400):
        """ Generate a message box to notify or prompt the user, allowing for
            a simple means of turning off such warnings and prompts. If a
            preference name is supplied and that preference exists, the user
            will not be prompted and the remembered value will be returned. If
            the preference doesn't exist, the dialog will contain a 'remember'
            checkbox that, if checked, will save the user's response as the
            preference. "Cancel" (if the dialog has the button) will never be
            saved.

            @param message: The main message/prompt to display
            @keyword title: The dialog's title
            @keyword style: Standard wxWindows style flags
            @keyword icon: The wxWindows style flag for the icon to display.
                Separated from `style` because `MemoryDialog` always needs an
                icon, making it behave differently than normal dialogs.
            @keyword parent: The dialog's parent; defaults to `self`.
            @keyword pref: The name of the preference to load and/or save
            @keyword extendedMessage: A longer, more detailed message.
            @keyword rememberMessage: The prompt next to the 'remember'
                checkbox (if shown).
            @keyword persistent: If `False` and 'remember' is checked, the
                result is saved in memory but not written to disk.
        """
        style = (style | icon) if icon else style
        parent = self or parent
        if pref is not None and self.app.hasPref(pref, section="ask"):
            return self.app.getPref(pref, section="ask")
        remember = pref is not None

        if "\n\n" in message:
            message, ext = message.split('\n\n', 1)
            if extendedMessage:
                extendedMessage = '\n'.join((ext,extendedMessage))
            else:
                extendedMessage = ext

        dlg = MemoryDialog(parent, message, title, style, remember=remember,
                           rememberMsg=rememberMsg)
        if extendedMessage:
            if textwrap:
                extendedMessage = wordwrap(extendedMessage, textwrap,
                                           wx.ClientDC(dlg))
            dlg.SetExtendedMessage(extendedMessage)

        result = dlg.ShowModal()
        savePref = result != wx.ID_CANCEL or (result == wx.ID_NO and saveNo)
        if pref is not None and savePref:
            if dlg.getRememberCheck():
                self.app.setPref(pref, result, "ask", persistent)
        dlg.Destroy()
        return result


    def getSaveFile(self, message, defaults=None, types=None,
                    style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT,
                    deviceWarning=True):
        """ Wrapper for getting the name of an output file.

            @param message: The message to be shown in the file dialog.
            @keyword defaults: A tuple with the default path and filename,
                or `None`.
            @keyword types: The "type spec" string for the file dialog.
            @keyword style: Dialog style, as per `wx.FileDialog`.
            @keyword deviceWarning: If `True`, the user will be warned before
                exporting to a recorder (it's slow). This warning can be
                overridden via a "don't show again" preference.
            @return: The name of the saved file.
        """
        exportTypes = "Comma Separated Values (*.csv)|*.csv|" \
                      "MATLAB 5.0 (*.mat)|*.mat"

        defaults = self.getDefaultExport() if defaults is None else defaults
        types = exportTypes if types is None else types

        defaultDir, defaultFile = defaults

        dlg = wx.FileDialog(self, message=message, defaultFile=defaultFile,
                            defaultDir=defaultDir, wildcard=types, style=style)

        while True:
            filename = None
            if dlg.ShowModal() == wx.ID_OK:
                filename = dlg.GetPath()
                if deviceWarning and devices.onRecorder(filename):
                    a = self.ask(
                        "You appear to be trying to export to a recording "
                        "device.\nFor best performance, you should save to a "
                        "local hard drive.\n\nContinue anyway?",
                        "Performance Warning", icon=wx.ICON_INFORMATION,
                        pref="saveOnRecorderWarning", saveNo=False)
                    if a != wx.YES:
                        continue
            break

        dlg.Destroy()

        return filename


    #===========================================================================
    #
    #===========================================================================

    def initPlots(self, evt=None):
        """ Set up the plot views specified in the dataset. Should only be
            called after the file's RecordingProperties and first data block
            have been read.

            @param evt: The event that initiated the initialization, if any.
                Not actually used; just there for compatibility with event
                handlers.
        """
        if self.dataset is None:
            return

        if self.session is None:
            if len(self.dataset.sessions) > 1:
                if not self.selectSession():
                    return
            else:
                self.session = self.dataset.lastSession

        self.plotarea.createWarningRanges()

        removeRolling = self.app.getPref('removeRollingMean', False)
        removeMean = self.app.getPref('removeMean', True)
        meanSpan = None
        if removeRolling:
            removeMean = True
            meanSpan = self.app.getPref('rollingMeanSpan', 5.0) / self.timeScalar
        else:
            meanSpan = -1

        self.dataSources.clear()
        displaymode = self.app.getPref('initialDisplayMode', 1)
        if displaymode == 0:
            # Old style: one tab per subchannel
            for d in self.dataset.getPlots(debug=self.showDebugChannels):
                el = d.getSession(self.session.sessionId)
                self.dataSources[wx.NewIdRef()] = el
                p = self.plotarea.addPlot(el, title=d.displayName)
                if p is not None:
                    p.removeMean(removeMean, meanSpan)
        else:
            # Create tabs with multiple channels
            units = None
            for ch in self.dataset.channels.values():
                if displaymode == 1:
                    # If one sensor per tab, reset units each time
                    units = None
                for subc in ch.subchannels:
                    el = subc.getSession(self.session.sessionId)
                    self.dataSources[wx.NewIdRef()] = el
                    if subc.units != units:
                        p = self.plotarea.addPlot(el, subc.displayName)
                        p.removeMean(removeMean, meanSpan)
                        units = subc.units
                    else:
                        p.addSource(el, True)

        self.setNoBivariates(self.noBivariates)
        self.enableChildren(True)
        self.buildAddChannelMenu()
        self.buildNewTabMenu()
        self.buildWarningMenu()

        # enabling plot-specific menu items happens on page select; do manually
        self.plotarea.getActivePage().enableMenus()


    def suspendDrawing(self, evt=None):
        """ Pause the plot drawing. This method can be used as an event
            handler.
        """
        self.drawingSuspended.set()


    def resumeDrawing(self, evt=None, redraw=True):
        """ Resume the plot drawing. This method can be used as an event
            handler.
            
            @keyword redraw: If `True`, force the plots to redraw. Not used
                if the method is called by an event.
        """
        if evt is not None:
            suspended = self.drawingSuspended.isSet()
            redraw = suspended and getattr(evt, "redraw", False)

        self.drawingSuspended.clear()

        if redraw:
            self.plotarea.redraw()


    def getTab(self, idx=None):
        """ Get the currently active plot tab.
        """
        if idx is None:
            return self.plotarea.getActivePage()
        else:
            return self.plotarea[idx]


    def setNoBivariates(self, disabled=True):
        """ Disable (or enable) bivariate calibration polynomials. Disabling
            them makes things faster.
        """
        self.menubar.FindItemById(self.ID_DATA_DISABLE_BIVARIATES).Check(disabled)
        self.noBivariates = disabled
        for source in self.dataSources.values():
            source.noBivariates = self.noBivariates
            if source._childLists:
                for cl in source._childLists:
                    cl.noBivariates = self.noBivariates
            if source._parentList:
                source._parentList.noBivariates = self.noBivariates


    #===========================================================================
    #
    #===========================================================================

    def setXUnits(self, name=None, symbol=None, displayScale=timeScalar):
        """ Set the horizontal units.

            @keyword name: The full name of the units used.
            @keyword symbol: The symbol or abbreviation of the unit.
            @keyword displayScale: A scaling factor for displaying the data.
        """
        if name == symbol == None:
            name = symbol = ''
        elif name is None:
            name = symbol
        else:
            symbol = name
        self.units = (name, symbol)

        if displayScale is not None:
            self.timeScalar = displayScale

        try:
            self.corner.setXUnits(symbol)
        except AttributeError:
            # Probably called before corner bit initialization; that's okay.
            pass


    #===========================================================================
    #
    #===========================================================================

    def setVisibleRange(self, start=None, end=None, instigator=None,
                        tracking=False):
        """ Set the currently visible time range. Propagates to its children.

            @keyword start: The first time in the visible range. Defaults to
                the current start.
            @keyword end: The last time in the visible range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in
                order to avoid an infinite loop of child calling parent
                calling child. The call is aborted if the instigator is the
                object itself.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return
        instigator = self if instigator is None else instigator
        for display, liveUpdate in self.timeDisplays:
            if liveUpdate or not tracking and display != instigator:
                display.setVisibleRange(start, end, instigator, tracking)


    def setTimeRange(self, start=None, end=None, instigator=None,
                     tracking=False):
        """ Set the time range for the entire session. Propagates to its
            children.

            @keyword start: The first time in the range. Defaults to
                the current start.
            @keyword end: The last time in the range. Defaults to the
                current end.
            @keyword instigator: The object that initiated the change, in
                order to avoid an infinite loop of child calling parent
                calling child. The call is aborted if the instigator is the
                object itself.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator == self:
            return
        start = start if start is not None else self.timerange[0]
        end = end if end is not None else self.timerange[1]
        self.timerange = start, end
        instigator = self if instigator is None else instigator
        for display, liveUpdate in self.timeDisplays:
            if liveUpdate or not tracking and display != instigator:
                display.setTimeRange(start, end, instigator)


    def getVisibleRange(self):
        """ Retrieve the beginning and end of the currently displayed interval
            of time.
        """
        return self.timeline.getVisibleRange()


    def getTimeRange(self):
        """ Retrieve the start and end of the current session.
        """
        return self.timerange


    #===========================================================================
    #
    #===========================================================================

    def getDefaultImport(self):
        """ Get the path and name of the default data file. If the app is
            running directly off a recorder, the recorder's data directory
            is returned.
        """
        curdir = os.path.realpath(os.path.curdir)
        name = self.app.getPref('defaultFilename', '')
        recorder = devices.onRecorder(curdir)
        if recorder:
            datadir = os.path.join(recorder, "DATA")
            if os.path.exists(datadir):
                return (datadir, name)
            return (recorder, name)
        # FUTURE: Use a path from the file history, maybe?
        return (curdir, name)


    def getDefaultExport(self):
        """ Get the path and name of the default export file.
        """
        if not self.dataset or not self.dataset.filename:
            return (os.path.realpath(os.path.curdir), "export.csv")
        filename = os.path.splitext(os.path.basename(self.dataset.filename))[0]
        return (os.path.realpath(os.path.curdir), filename + ".csv")


    def okayToExit(self):
        """ Returns `True` if the app is in a state to immediately quit.
        """
        # TODO: Prompt to veto quitting only if an export is underway.
        q = self.ask("Really quit?\n\nAll currently open recordings will be closed.",
                     "Quit %s" % APPNAME, wx.OK|wx.CANCEL, pref="promptBeforeQuit")
        return q == wx.ID_OK


    #===========================================================================
    #
    #===========================================================================

    def selectSession(self):
        """ Show a list of sessions in a recording and allow the user to choose
            one. This changes the Viewer's `session` variable.
        """
        sessions = []
        for session in self.dataset.sessions:
            s = "%d:" % session.sessionId
            if session.utcStartTime is not None:
                utcStartTime = session.utcStartTime
                if isinstance(utcStartTime, (int, float)):
                    utcStartTime = datetime.fromtimestamp(utcStartTime)
                s = "%s %s" % (s, utcStartTime)
            if session.startTime is not None and session.endTime is not None:
                length = session.endTime - session.startTime
                if length == 0:
                    continue
                s = "%s (%0.4f seconds)" % (s, length * self.timeScalar)
            sessions.append(s)

        result = False
        dlg = wx.SingleChoiceDialog(
                self, ('This file contains multiple recording sessions.\n'
                       'Please select the session to view:'),
                'Select Recording Session', sessions, wx.CHOICEDLG_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            self.session = self.dataset.sessions[dlg.GetSelection()]
            result = True
        else:
            self.closeFile()

        dlg.Destroy()
        return result


    def openFile(self, filename, prompt=True):
        """ Open a recording file. This also handles prompting the user when
            a file is loading or has already been loaded.

            @todo: Encapsulate the file type identification, so a file without
                an extension (or a different one) can still be identified and
                imported. Low priority.

            @param filename: The full path and name of the file to open.
            @keyword prompt: If `True`, the user will be warned before loading
                a new file over the old one. If `False`, the old file will
                get clobbered automatically.
        """
        if not os.path.isfile(filename):
            wx.MessageBox("File not found\n\n%s" % filename,
                          "Open File", wx.OK|wx.ICON_ERROR, self)
            return False

        name = os.path.basename(filename)
        ext = os.path.splitext(name)[-1].lower()

        badMsg = u"The file may be irretrievably damaged."

        if ext in ('.ide','.mide'):
            importer = idelib.importer.openFile
            reader = idelib.importer.readData
        else:
            importer = idelib.classic.importer.openFile
            reader = idelib.classic.importer.readData
            badMsg = (u"The file may be irretrievably damaged, "
                      "or it may not a Slam Stick Classic file.")

        if prompt and self.dataset is not None:
            if self.dataset.loading is True:
                if self.ask("Abort loading the current file?") != wx.ID_YES:
                    return False
            else:
                q = self.ask("Do you want to close the current file?\n\n"
                             "'No' will open the file in another window.",
                             "Open File",style=wx.YES_NO|wx.CANCEL,
                             pref="openInSameWindow")
                if q == wx.ID_NO:
                    self.app.createNewView(filename=filename)
                    return False
                elif q == wx.ID_CANCEL:
                    return False

        self.closeFile()
        stream = None

        try:
            stream = ThreadAwareFile(filename, 'rb')
            newDoc = importer(stream, quiet=True)
            self.app.prefs.addRecentFile(filename, 'import')

            # SSX: Check EBML schema version
            if newDoc.schemaVersion is not None and newDoc.schemaVersion < newDoc.ebmldoc.version:
                q = self.ask("The data file was created using a newer "
                  "version of the MIDE data schema.\n\nLab's version is %s, "
                  "file's version is %s; this could potentially cause problems."
                  "\n\nOpen anyway?" % (newDoc.schemaVersion,
                                        newDoc.ebmldoc.version),
                  "Schema Version Mismatch", wx.YES|wx.CANCEL, wx.ICON_WARNING,
                  pref="schemaVersionMismatch")
                if q == wx.ID_NO:
                    stream.closeAll()
                    return

            # Classic: Blank file
            if isinstance(newDoc, idelib.classic.dataset.Dataset):
                if not newDoc.sessions:
                    self.ask("This Classic file contains no data.",
                        "Import Error", wx.OK, wx.ICON_ERROR, extendedMessage=\
                        "Slam Stick Classic recorders always contain "
                        "a 'data.dat' file,\nregardless whether a recording "
                        "has been made.")
                    stream.closeAll()
                    return

        except idelib.parsers.ParsingError as err:
            self.ask("The file '%s' could not be opened" % name,
                     "Import Error", wx.OK, icon=wx.ICON_ERROR,
                     extendedMessage=badMsg)
            stream.closeAll()
            return False

        except Exception as err:
            # Catch-all for unanticipated errors
            if stream is not None:
                stream.closeAll()
            self.handleError(err, what="importing the file %s" % filename,
                             closeFile=True)
            return False

        self.dataset = newDoc
        if len(newDoc.sessions) > 1:
            if not self.selectSession():
                stream.closeAll()
                return False
        else:
            self.session = newDoc.lastSession

        # Import external calibration file, if it has the same name as the
        # recording file.
        # This might have to go before the loader is started.
        calfile = os.path.splitext(filename)[0] + '.cal'
        if os.path.exists(calfile):
            q = self.ask("Import matching calibration file?\n\n"
                         "This recording has a corresponding calibration file "
                         "(%s). Do you want to import calibration data from "
                         "this file, overriding the recording's calibration "
                         "data?" % os.path.basename(calfile),
                         title="Import Calibration Data?", pref="autoImportCal")
            if q == wx.ID_YES:
                logger.info("Importing external calibration file.")
                self.importCalibration(calfile)
            else:
                logger.info("Not importing external calibration file.")

        loader = Loader(self, newDoc, reader, **self.app.getPref('loader'))
        self.pushOperation(loader)
        self.SetTitle(self.app.getWindowTitle(self))
        loader.start()

        self.buildDisplayMenu()

        # Expired calibration warning
        try:
            recDate = self.session.startTime or self.session.utcStartTime or 0
            calDate = newDoc.recorderInfo.get('CalibrationDate')
            if calDate and recDate > calDate + 31536000:
                self.ask("This file was recorded with expired calibration.",
                         "Expired Calibration Warning",
                         wx.OK, wx.ICON_INFORMATION, pref="expiredCal",
                         extendedMessage="The display of values recorded in "
                         "this file may be inaccurate.")
        except (TypeError, KeyError, AttributeError):
            pass

#         self.app.fileHistory.AddFileToHistory(filename)
        self.enableMenus(True)
        return True


    def importCalibration(self, filename):
        """ Import an external calibration file into the current dataset.
        """
        calname = os.path.basename(filename)
        try:
            cal = live_calibration.readCal(filename)

            if not cal:
                # Either import failed, or there was no calibration data.
                self.handleError(None, "No calibration data could be read.\n\n"
                                 "The file '%s' contained no usable/readable "
                                 "calibration data." % calname)
                return
            elif sorted(cal.keys()) != sorted(self.dataset.transforms.keys()):
                # Calibration ID mismatch.
                self.handleError(None, "Calibration IDs in the file '%s'"
                               "do not match those in this recording.\n\n"
                               "The file may have been exported from a "
                               "recorder running a different version of the "
                               "firmware." % calname)
                return

            if not hasattr(self.dataset, 'originalTransforms'):
                self.dataset.originalTransforms = {c.id: c.copy() for c in self.dataset.transforms.values()}

            self.dataset.transforms = cal
            self.dataset.updateTransforms()

        except IOError as err:
            # Probably bad/damaged file
            self.handleError(err, "The file '%s' could not be read.\n\n"
                             "The file may be damaged, or it may not be a "
                             "calibration file." % calname)
        except Exception as err:
            self.handleError(err, what="importing calibration data.")


    def openMultiple(self, filenames, prompt=True):
        """ Open multiple IDE files, merging them into one view. Experimental!

            @todo: Implement this, and add all the schema version checking and
                error handling present in the normal `openFile()`.

            NOTE: The title-related stuff needs to be reworked.
        """
        title = "%s - %s (%d files)" % (os.path.basename(filenames[0]),
                                        os.path.basename(filenames[-1]),
                                        len(filenames))

        if prompt and self.dataset is not None:
            if self.dataset.loading is True:
                if self.ask("Abort loading the current file?") != wx.ID_YES:
                    return False
            else:
                q = self.ask("Do you want to close the current file?\n"
                             "'No' will open the file in another window.",
                             "Open File",style=wx.YES_NO|wx.CANCEL,
                             pref="openInSameWindow")
                if q == wx.ID_NO:
                    self.app.createNewView(filename=filenames, title=title)
                    return False
                elif q == wx.ID_CANCEL:
                    return False

        self.closeFile()

        streams = [ThreadAwareFile(filename, 'rb') for filename in filenames]
        newDoc = idelib.multi_importer.multiOpen(streams)

        self.dataset = newDoc
        if len(newDoc.sessions) > 1:
            if not self.selectSession():
                newDoc.close()
                return False
            title = "%s (Session %d)" % (title, self.session.sessionId)
        else:
            self.session = newDoc.lastSession

        loader = Loader(self, newDoc, idelib.multi_importer.multiRead,
                        **self.app.getPref('loader'))
        self.pushOperation(loader)
        self.SetTitle(self.app.getWindowTitle(self))
        loader.start()
        self.enableMenus(True)
        return True


    def closeFile(self):
        """ Close a file. Does not close the viewer window itself.
        """
        self.cancelOperation()
        self.plotarea.clearAllPlots()
        if self.dataset is not None:
            self.dataset.close()
        self.session = None
        self.dataset = None
        self.enableChildren(False)
        self.enableMenus(False)


    def OnFileExportMenu(self, evt=None):
        """ Export the active plot view's data as CSV. after getting input from
            the user (range, window size, etc.).

            @keyword evt: An event (not actually used), making this method
                compatible with event handlers.
        """
        noMean = 0
        if self.plotarea[0].removeMean:
            noMean = 2 if self.plotarea[0].rollingMeanSpan == -1 else 1

        # FUTURE: Make exporters conform to the plug-in system, and get the
        # extensions from the plugins. If more than one plugin uses the same
        # file extension, produce a dialog so the user can select (e.g. if
        # there are separate plugins for ASCII and binary UFF files).
        validTypes = ('CSV', 'MAT')

        exportType = None
        while exportType not in validTypes:
            filename = self.getSaveFile("Export Data...")
            if filename is None:
                return

            exportType = os.path.splitext(filename)[-1].upper().strip('.')
            if exportType not in validTypes:
                valids = wordJoin(validTypes)
                wx.MessageBox("Unknown export type: %s\n\n"
                  "Recognized types are %s." % (exportType, valids),
                  "Export Error", wx.OK, self)

        settings = xd.CSVExportDialog.getExport(root=self, removeMean=noMean,
                                                exportType=exportType,
                                                title='Export %s' % exportType)

        if settings is None:
            return

        source = settings.pop('source')
        subchannels = [c.id for c in settings.pop('subchannels', [])]
        settings.pop('startTime', None)
        settings.pop('endTime', None)
        numRows = settings.pop('numRows', 1)

        self.suspendDrawing()

        dlg = xd.ModalExportProgress("Exporting %s" % exportType,
                                     "Exporting %d rows" % numRows,
                                     maximum=numRows*len(subchannels),
                                     parent=self)

        settings['subchannels'] = subchannels
        settings['callback'] = dlg
        settings['raiseExceptions'] = True
        settings.setdefault('display', True)

        try:
            if exportType == 'CSV':
                with open(filename, 'w') as stream:
                    source.exportCsv(stream, **settings)

            elif exportType == 'MAT':
                idelib.matfile.exportMat(source, filename, **settings)

        except Exception as err:
            self.handleError(err, what="exporting %s" % exportType)

        dlg.Destroy()
        self.resumeDrawing()


    def renderPlot(self, evt=None, plotType=ID_DATA_RENDER_FFT, outFile=None,
                   initSettings=None):
        """ Create a plot showing multiple subchannels, an FFT, a PSD, or
            a Spectrogram after getting input from the user (range,
            window size, etc.). This method can be used as an event handler
            or called normally. If called normally, you must include the
            menu item ID for the type of plot to render.

        """
        # FUTURE: Make this conform to the plugin system, and keep a dictionary
        # mapping the dynamically added menu items to the renderer plugin,
        # rather than a chain of 'if' statements.
        kwargs = {'root': self, 'initSettings': initSettings}
        evtId = plotType if evt is None else evt.GetId()
        if evtId == self.ID_DATA_RENDER_PSD:
            viewClass = PSDView
            settings = xd.PSDExportDialog.getExport(**kwargs)
        elif evtId == self.ID_DATA_RENDER_SPEC:
            viewClass = SpectrogramView
            settings = xd.SpectrogramExportDialog.getExport(**kwargs)
        elif evtId == self.ID_DATA_RENDER_PLOTS:
            viewClass = PlotView
            settings = xd.ExportDialog.getExport(title="Render Plot",
                                                 byType=True, **kwargs)
        else:
            viewClass = FFTView
            settings = xd.FFTExportDialog.getExport(**kwargs)

        if settings is None:
            return

        if outFile:
            subchannelIds = [c.id for c in settings["subchannels"]]
            sliceSize = settings.pop("sliceSize", 2**14)
            start = settings["start"]
            stop = settings["stop"]
            source = settings["source"]
            inputData = settings["source"].itervalues(start, stop, subchannels=subchannelIds, display=True)
            renderData = viewClass.generateData(inputData, rows=stop-start, cols=len(subchannelIds),
                                                fs=source.getSampleRate(), sliceSize=sliceSize, useWelch=initSettings["useWelch"])
            import numpy as np
            np.savetxt(outFile, renderData)
            return

        viewId = wx.NewIdRef()
        size = self.GetSize()

        try:
            self.childViews[viewId] = viewClass(self, viewId, size=size,
                                                root=self, **settings)
        except Exception as e:
            # Catch no exceptions if in debug.
            if DEBUG:
                raise

            self.handleError(e, what="rendering the %s" % viewClass.FULLNAME)


    #===========================================================================
    #
    #===========================================================================

    def getPlotColor(self, source, opacity=255):
        """ Get the plotting color for a data source. If the source does not
            have a color specified in the recording, the color is retrieved
            from the preferences. Channel/subchannel combinations not known are
            assigned one of the standard default colors.

            @param source: The source, either `idelib.dataset.Channel`,
                `idelib.dataset.SubChannel`, or `idelib.dataset.EventList`
        """
        if isinstance(source, idelib.dataset.EventList):
            source = source.parent

        color = getattr(source, 'color', None)

        if color is not None:
            color = wx.Colour(color)

        else:
            try:
                sourceId = "%02x.%d" % (source.parent.id,
                                        source.id)
                color = self.root.app.getPref('plotColors')[sourceId]
            except (KeyError, AttributeError):
                defaults = self.app.getPref('defaultColors')
                color = defaults[self._nextColor % len(defaults)]
                self._nextColor += 1

            if isinstance(color, basestring):
                color = self.app.colorDb.Find(color)

        return color


    def setPlotColor(self, source, color):
        """ Writes a plot's color to the preferences.
        """
        if isinstance(source, idelib.dataset.EventList):
            source = source.parent
        sourceId = "%02x.%d" % (source.parent.id, source.id)
        colors = self.root.app.getPref('plotColors')
        colors[sourceId] = color
        self.root.app.setPref('plotColors', colors)


    #===========================================================================
    #
    #===========================================================================

    def showConsole(self, **kwargs):
        """ Show the Python scripting console (i.e. the REPL).
        """
        focus = kwargs.pop("focus", True)
        if self.console:
            self.console.Show()
            if self.console.IsIconized():
                self.console.Iconize(False)
        else:
            self.console = scripting.shell.PythonConsole.openConsole(self,
                                                                     **kwargs)
            self.childViews[self.console.GetId()] = self.console

        if focus:
            self.console.SetFocus()

        return self.console


    def runScript(self, filename, focus=False, warn=True):
        """ Execute a Python script.
            
            @param filename: The script's full path and filename.
            @keyword focus: If `True`, the console will be shown and take
                focus before the script runs.
        """
        if warn:
            warning = self.ask("Caution!\n\n"
                           "Scripts from unknown sources pose a risk to your "
                           "computer's security. They should be treated with "
                           "the same caution as any downloaded software.\n\n"
                           "Do you wish to continue?",
                           "Run Script", icon=wx.ICON_WARNING,
                           pref="scriptWarning", saveNo=False)
            if warning != wx.ID_YES:
                return
        
        if not self.console:
            self.console = scripting.shell.PythonConsole.openConsole(self)
            self.childViews[self.console.GetId()] = self.console
            if not focus:
                self.console.Hide()

        now = str(datetime.now()).rsplit('.',1)[0]
        start = "### Running %s at %s" % (filename, now)
        finish = "### Finished running %s" % (filename)
        
        try:
            self.console.execute(filename=filename, globalScope=False,
                                 start=start, finish=finish, focus=focus)
            
            # TODO: Find a way to identify when an error happens.
            # This doesn't seem to work at all.
            if getattr(self.console.shell, 'hasSyntaxError', False):
                self.console.Show()
                self.console.SetFocus()
        
        except RuntimeError:
            # Console window (probably) destroyed. Not likely, but could happen
            # in certain edge cases.
            logger.debug("Viewer.runScript(): console window destroyed?")
            return
        
        except Exception as err:
            # This *doesn't* run if the script executed had an error.
            # The console catches it all.
            logger.error("Viewer.runScript() error: %r" % err)
            raise

        self.app.prefs.addRecentFile(filename, 'scripts')


    #===========================================================================
    #
    #===========================================================================

    def SetTitle(self, title):
        """ Set the window title. Also updates possible dependencies in
            'child' windows.
        """
        super(Viewer, self).SetTitle(title)

        for c in self.childViews.values():
            if hasattr(c, 'parentUpdated'):
                c.parentUpdated()


    #===========================================================================
    #
    #===========================================================================

    def OnClose(self, evt):
        """ Close the viewer.
        """
        # CommandEvents don't have veto functionality
        canVeto = True
        if hasattr(evt, 'CanVeto'):
            canVeto = evt.CanVeto()

        # User may be prompted to before close if it's the last window and
        # the application isn't in the process of quitting (they also get
        # prompted when the exit menu event is handled).
        canVeto = (canVeto 
                   and len(self.app.viewers) < 2
                   and not self.app.quitting)

        if canVeto  and not self.okayToExit():
            if hasattr(evt, 'Veto'):
                evt.Veto()
            return False

        self.app.prefs.savePrefs()

        # Kill all background processes
        self.cancelAllOperations()

        # Close related windows
        for fft in self.childViews.itervalues():
            try:
                fft.Destroy()
            except (AttributeError, RuntimeError):#, wx.PyDeadObjectError):
                # FFT view may already have been destroyed; that's okay.
                pass

        # Remove from parent's viewer list (prevents dead object errors)
        try:
            self.app.viewers.remove(self)
        except ValueError:
            raise
            pass

        self.Destroy()
        evt.Skip()


    #===========================================================================
    # Menu Events
    #===========================================================================

    def OnFileNewMenu(self, evt):
        """ Handle File->New Viewer Window menu events.
        """
        self.app.createNewView(splash=False, openDialog=True)


    def OnFileOpenMenu(self, evt):
        """ Handle File->Open menu events.
        """
        importTypes = ("All Recording Types (*.ide, *.dat)|*.ide;*.dat|"
                        "MIDE Data File (*.ide)|*.ide|"
                        "Slam Stick Classic (*.dat)|*.dat|"
                        "All files (*.*)|*.*")

        defaultDir, defaultFile = self.getDefaultImport()
        dlg = wx.FileDialog(self,
                            message="Choose a file",
                            defaultDir=defaultDir,
                            defaultFile=defaultFile,
                            wildcard=importTypes,
                            style=wx.FD_OPEN|wx.FD_CHANGE_DIR|wx.FD_FILE_MUST_EXIST)
        dlg.SetFilterIndex(0)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            try:
                if os.path.getsize(filename) > FILESIZE_WARNING:
                    q = self.ask("You are attempting to open an extremely large file.\n\n"
                                 "This may cause the Lab to respond slowly. "
                                 "For best results, try splitting the recording "
                                 "into smaller parts using the IDE Splitter "
                                 "tool, located under the Tools menu.\n\n"
                                 "Open the large file anyway?", "Large File Warning",
                                 wx.OK|wx.CANCEL, icon=wx.ICON_WARNING,
                                 pref="largeFileWarning")
                    if q != wx.ID_OK:
                        filename = ''
            except (OSError, IOError):
                # Ignore errors here; openFile() should handle them instead.
                pass
            if filename:
                if wx.GetKeyState(wx.WXK_SHIFT):
                    # Turn off bivariate refs if shift is held. Can allow some
                    # types of damaged file to load.
                    logger.info("Importing with bivariate references disabled.")
                    self.setNoBivariates(True)
                self.openFile(filename)

        # Note to self: do this last!
        dlg.Destroy()


    def OnFileOpenMulti(self, evt):
        """ Handle "File->Open Multiple" menu events.
        """
        importTypes =   "MIDE Data File (*.ide)|*.ide"

        defaultDir, _defaultFile = self.getDefaultImport()
        dlg = wx.FileDialog(self,
            message="Choose Multiple Files",
            defaultDir=defaultDir,
            wildcard=importTypes,
            style=wx.FD_OPEN|wx.FD_CHANGE_DIR|wx.FD_FILE_MUST_EXIST|wx.FD_MULTIPLE)
        dlg.SetFilterIndex(0)
        if dlg.ShowModal() == wx.ID_OK:
            filenames = dlg.GetPaths()
            self.openMultiple(filenames)

        # Note to self: do this last!
        dlg.Destroy()


    def OnFileExitMenu(self, evt):
        """ Handle File->Exit menu events.
        """
        if self.okayToExit():
            self.app.quit()


    def OnFileProperties(self, evt):
        """ Handle File->Recording Properties menu events.
        """
        if self.dataset:
            self.SetCursor(wx.Cursor(wx.CURSOR_WAIT))
            RecorderInfoDialog.showRecorderInfo(self.dataset)
            self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))


    def OnShowRecentFiles(self, evt):
        """ Populate the file history submenu.
        """
        for item in self.recentFilesMenu.GetMenuItems():
            self.recentFilesMenu.DestroyItem(item)

        filenames = self.app.prefs.getRecentFiles()
        for i, f in enumerate(filenames):
            self.addMenuItem(self.recentFilesMenu, i+wx.ID_FILE1, f, '')

        self.ID_CLEAR_HISTORY = getattr(self, 'ID_CLEAR_HISTORY', wx.ID_ANY)

        if filenames:
            self.recentFilesMenu.AppendSeparator()
            self.addMenuItem(self.recentFilesMenu, self.ID_CLEAR_HISTORY,
                             "Clear file history", "",
                             lambda _evt: self.app.prefs.clearRecentFiles())

        else:
            self.addMenuItem(self.recentFilesMenu, self.ID_CLEAR_HISTORY,
                             "No file history", "", enabled=False)


    def OnPickRecentFile(self, evt):
        """ Handle an item being picked from the file history submenu.
        """
        eid = evt.GetId()

        if eid < wx.ID_FILE1 or eid > wx.ID_FILE9:
            # Sanity check. Should never happen.
            return

        idx = eid - wx.ID_FILE1
        files = self.app.prefs.getRecentFiles()
        if idx < len(files):
            filename = files[idx]
            if self.dataset and filename == self.dataset.filename:
                return
            self.openFile(files[idx])


    def OnEditRanges(self, evt):
        """ Handle "View->Edit Visible Ranges..." menu events.
        """
        newRanges = RangeDialog.display(self)
        if newRanges is not None:
            self.setVisibleRange(*newRanges[0])
            p = self.plotarea.getActivePage()
            if p is not None:
                p.setValueRange(*newRanges[1])


    #===========================================================================
    # 
    #===========================================================================

    def OnDeviceConfigMenu(self, evt):
        """ Handle Device->Configure Device menu events.
        """
        showAdvanced = self.app.getPref('showAdvancedOptions', False)
        useUtc = self.app.getPref('configure.useUtc', True)
        setTime = self.app.getPref('configure.setTime', True)
        dev = selectDevice(showAdvanced=showAdvanced)
        if dev is not None:
            result = config_dialog.configureRecorder(dev,
                                                     setTime=setTime,
                                                     useUtc=useUtc,
                                                     parent=self,
                                                     showAdvanced=showAdvanced)
            if result is not None:
                _result, setTime, useUtc, dev, msg = result
                self.app.setPref('configure.setTime', setTime)
                self.app.setPref('configure.useUtc', useUtc)

                pref = "showConfigMsg_%s" % dev.__class__.__name__
                self.ask("Successfully Configured!", "Device Configuration",
                           wx.OK, icon=wx.ICON_INFORMATION, pref=pref,
                           extendedMessage=msg)


    def OnDeviceUpdateFW(self, evt):
        """ Handle "Device->Update Recorder Firmware..." menu events.
        """
        warning = self.ask("This operation can harm your device!\n\n"
                           "A failed firmware update attempt can potentially "
                           "render your recorder non-operational, and may "
                           "require repair by the manufacturer.\n\n"
                           "Do you wish to continue?",
                           "Update Firmware", icon=wx.ICON_WARNING,
                           pref="FWUpdateWarning", saveNo=False)
        if warning == wx.ID_YES:
            devices.efm32_firmware.updateFirmware(self)


    #===========================================================================
    # 
    #===========================================================================

    def OnScriptRun(self, evt):
        """ Handle "Scripting->Run Script" menu events.
        """
        types = "Python Script (*.py)|*.py"

        dlg = wx.FileDialog(self, message="Run Python Script",
                            wildcard=types, style=wx.FD_OPEN)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.runScript(dlg.GetPath())
        finally:
            dlg.Destroy()


    def OnShowRecentScripts(self, evt):
        """ Handle the appearance of the Recent Script submenu, updating its
            contents.
        """
        for item in self.recentScriptsMenu.GetMenuItems():
            self.recentScriptsMenu.DestroyItem(item)

        filenames = self.app.prefs.getRecentFiles("scripts")
        for i, f in enumerate(filenames):
            self.addMenuItem(self.recentScriptsMenu, i+self.ID_SCRIPT1, f, '')

        self.ID_CLEAR_SCRIPT_HISTORY = getattr(self, 'ID_CLEAR_SCRIPT_HISTORY',
                                               wx.ID_ANY)

        if filenames:
            self.recentScriptsMenu.AppendSeparator()
            self.addMenuItem(self.recentScriptsMenu, self.ID_CLEAR_SCRIPT_HISTORY,
                             "Clear script history",
                             'Clear the "Recent Scripts" menu.',
                             lambda _evt: self.app.prefs.clearRecentFiles("scripts"))

        else:
            self.addMenuItem(self.recentScriptsMenu, self.ID_CLEAR_SCRIPT_HISTORY,
                             "No script history", "", enabled=False)


    def OnPickRecentScript(self, evt):
        """ Handle an item being picked from the script history submenu.
        """
        eid = evt.GetId()

        if eid < self.ID_SCRIPT1 or eid > self.ID_SCRIPT1+7:
            # Sanity check. Should never happen.
            return

        idx = eid - self.ID_SCRIPT1
        files = self.app.prefs.getRecentFiles("scripts")
        if idx < len(files):
            filename = files[idx]
            self.runScript(filename)


    def OnShowScriptEditor(self, evt):
        """ Handle "Scripting->Show Script Editor" menu events.
        """
        # TODO: Get size from prefs, get last set of tabs?
        editor = scripting.editor.ScriptEditor(self, size=(800,600))
        self.childViews[editor.GetId()] = editor
        editor.Show()


    def OnShowScriptConsole(self, evt):
        """ Handle "Scripting->Open Console" menu events.
        """
        return self.showConsole(focus=True)

    #===========================================================================
    # 
    #===========================================================================

    def OnHelpAboutMenu(self, evt):
        """ Handle Help->About menu events.
        """
        updateCheck = self.app.getPref('updater.lastCheck', None)
        if isinstance(updateCheck, (int, float)):
            updateCheck = datetime.fromtimestamp(int(updateCheck))
        else:
            updateCheck = "Never"

        if REPO_BRANCH.lower() != "master":
            buildNum = "%s (%s)" % (BUILD_NUMBER, REPO_BRANCH)
        else:
            buildNum = BUILD_NUMBER

        AboutBox.showDialog(self, -1, strings={
           'appName': self.app.GetAppDisplayName(),
           'version': self.app.versionString,
           'copyright': datetime.fromtimestamp(BUILD_TIME).year,
           'buildNumber': buildNum,
           'buildTime': datetime.fromtimestamp(BUILD_TIME),
           'lastUpdateCheck': updateCheck,
        })


    def OnHelpCheckUpdates(self, evt):
        """ Handle "Help->Check for Updates" menu events.
        """
        self.app.setPref('updater.version', self.app.version)
        updater.startCheckUpdatesThread(self.app, force=True, quiet=False)


    def OnHelpFeedback(self, evt):
        """ Handle Help->About menu events.
        """
        wx.LaunchDefaultBrowser(FEEDBACK_URL)


    def OnHelpResources(self, evt):
        """ Handle "Help->enDAQ Recorder Resources" menu events.
        """
        wx.LaunchDefaultBrowser(RESOURCES_URL)


    def OnDontRemoveMeanCheck(self, evt):
        """ Handler for ID_DATA_NOMEAN menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.
            Changes the user prefs only if called with an Event.

            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """
        if isinstance(evt, bool):
            self.setMenuItem(self.menubar, self.ID_DATA_NOMEAN, checked=evt)
        else:
            checked = evt.IsChecked()
            if checked:
                self.app.setPref('removeMean', False)
                self.app.setPref('removeRollingMean', False)
                for p in self.plotarea:
                    p.removeMean(False)


    def OnRemoveRollingMeanCheck(self, evt):
        """ Handler for ID_DATA_MEAN menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.
            Changes the user prefs only if called with an Event.

            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """
        if isinstance(evt, bool):
            self.setMenuItem(self.menubar, self.ID_DATA_MEAN, checked=evt)
            checked = evt
        else:
            checked = evt.IsChecked()
            self.app.setPref('removeRollingMean', checked)
            if checked:
                self.app.setPref('removeMean', False)

        span = self.app.getPref('rollingMeanSpan', 5.0) / self.timeScalar
        for p in self.plotarea:
            p.removeMean(checked, span=span)

#         self.plotarea.getActivePage().enableMenus()


    def OnRemoveTotalMeanCheck(self, evt):
        """ Handler for ID_DATA_MEAN menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.
            Changes the user prefs only if called with an Event.

            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """
        if isinstance(evt, bool):
            self.setMenuItem(self.menubar, self.ID_DATA_MEAN_TOTAL,
                             checked=evt)
            checked = evt
        else:
            checked = evt.IsChecked()
            self.app.setPref('removeMean', checked)
            if checked:
                self.app.setPref('removeRollingMean', False)

        for p in self.plotarea:
            p.removeMean(checked, span=-1)


    def OnDataWarningsCheck(self, evt):
        """ Handler for ID_DATA_WARNINGS menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.

            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """
        try:
            p = self.plotarea.getActivePage()
            source = self.warningRanges[evt.GetId()]
            if evt.IsChecked():
                p.warningRanges.add(source)
            else:
                p.warningRanges.remove(source)
            p.redraw()
        except KeyError:
            pass


    def OnZoomInY(self, evt):
        """ Handle "View->Zoom In Y" menu events.
        """
        p = self.plotarea.getActivePage()
        if p is not None:
            p.zoomIn()


    def OnZoomOutY(self, evt):
        """ Handle "View->Zoom Out Y" menu events.
        """
        p = self.plotarea.getActivePage()
        if p is not None:
            p.zoomOut()


    def OnZoomFitY(self, evt):
        """ Handle "View->Zoom to Fit Y" menu events.
        """
        p = self.plotarea.getActivePage()
        if p is not None:
            p.zoomToFit()


    def OnZoomFitAll(self, evt):
        """ Handle "View->Zoom to Fit All" menu events.
        """
        # TODO: Make 'zoom to fit all' work better.
        # There's appears to be an event processing race condition which makes
        # the Y fit finish before the X fit. Forcing a yield makes it work,
        # but the plot refreshes after the X fit.
        self.OnZoomFitX(evt)
        wx.Yield()
        self.OnZoomFitY(evt)


    def _postCommandEvent(self, target, evtType, Id):
        """ Helper method to generate and transmit a ``wx.CommandEvent``
            (i.e. a simulated button press). """
        newEvt = wx.CommandEvent(evtType.typeId, Id)
        newEvt.SetEventObject(self)
        wx.PostEvent(target, newEvt)


    def OnZoomInX(self, evt):
        """ Handle "View->Zoom In X" menu events.
        """
        # Make navigator (top timeline) think its 'zoom in' button was pressed
        self._postCommandEvent(self.navigator, wx.EVT_BUTTON, wx.ID_ZOOM_IN)


    def OnZoomOutX(self, evt):
        """ Handle "View->Zoom Out X" menu events.
        """
        # Make navigator think its 'zoom out' button was pressed
        self._postCommandEvent(self.navigator, wx.EVT_BUTTON, wx.ID_ZOOM_OUT)


    def OnZoomFitX(self, evt):
        """ Handle "View->Zoom to Fit X" menu events.
        """
        # Make navigator think its 'zoom to fit' button was pressed
        self._postCommandEvent(self.navigator, wx.EVT_BUTTON, wx.ID_ZOOM_FIT)


    def OnToggleAA(self, evt):
        """ Handler for ID_VIEW_ANTIALIAS menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.

            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """
        if isinstance(evt, bool):
            checked = evt
            self.setMenuItem(self.ID_VIEW_ANTIALIAS, checked=evt)
        else:
            checked = evt.IsChecked()

        self.antialias = self.app.setPref('antialiasing', checked)
        self.plotarea.setAntialias(checked)


    def OnToggleNoise(self, evt):
        """ Handler for ID_VIEW_JITTER menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.

            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """
        if isinstance(evt, bool):
            checked = evt
            self.setMenuItem(self.ID_VIEW_JITTER, checked=evt)
        else:
            checked = evt.IsChecked()

        # 'noisy resampling' is turned on or off by changing its amount.
        if checked:
            self.noisyResample = self.app.getPref('resamplingJitterAmount',
                                                  RESAMPLING_JITTER)
        else:
            self.noisyResample = 0

        self.app.setPref('resamplingJitter', checked)
        self.plotarea.redraw()


    def OnToggleUtcTime(self, evt):
        """ Handler for ID_VIEW_UTCTIME menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.

            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """
        if isinstance(evt, bool):
            checked = evt
            self.menubar.FindItemById(self.ID_VIEW_UTCTIME).Check(evt)
        else:
            checked = evt.IsChecked()

        if checked:
            self.menubar.FindItemById(self.ID_VIEW_LOCALTIME).Check(False)
            self.showLocalTime = self.app.setPref('showLocalTime', False)

        self.showUtcTime = self.app.setPref('showUtcTime', checked)


    def OnToggleLocalTime(self, evt):
        """ Handler for ID_VIEW_LOCALTIME menu item selection. The method can
            also be used to explicitly set the item checked or unchecked.

            @param evt: The menu event. Can also be `True` or `False` to force
                the check to be set (kind of a hack).
        """
        if isinstance(evt, bool):
            checked = evt
            self.menubar.FindItemById(self.ID_VIEW_LOCALTIME).Check(evt)
        else:
            checked = evt.IsChecked()

        if checked:
            self.menubar.FindItemById(self.ID_VIEW_UTCTIME).Check(False)
            self.showUtcTime = self.app.setPref('showUtcTime', False)

        self.showLocalTime = self.app.setPref('showLocalTime', checked)


    def OnToggleMinMax(self, evt):
        """ Handler for ID_VIEW_MINMAX menu item selection.
        """
        self.drawMinMax = self.app.setPref('drawMinMax', evt.IsChecked())
        self.plotarea.redraw()


    def OnToggleViewMean(self, evt):
        """
        """
        self.drawMean = self.app.setPref('drawMean', evt.IsChecked())
        self.plotarea.redraw()


    def OnToggleLinesMajor(self, evt):
        """ Handler for ID_VIEW_LINES_MAJOR menu item selection.
        """
        checked = evt.IsChecked()
        self.drawMajorHLines = self.app.setPref('drawMajorHLines', checked)
        self.plotarea.redraw()


    def OnToggleLinesMinor(self, evt):
        """ Handler for ID_VIEW_LINES_MAJOR menu item selection.
        """
        checked = evt.IsChecked()
        self.drawMinorHLines = self.app.setPref('drawMinorHLines', checked)
        self.plotarea.redraw()


    def OnSourceChecked(self, evt):
        """ Toggle the display of a data source.
        """
        try:
            p = self.plotarea.getActivePage()
            source = self.dataSources[evt.GetId()]
            if evt.IsChecked():
                p.addSource(source)
            else:
                p.removeSource(source)
            p.redraw()
        except KeyError:
            pass


    def OnNewTabPicked(self, evt):
        """ Create a new display tab.
        """
        typeId = evt.GetId()
        units = self.tabTypes[typeId]

        removeRolling = self.app.getPref('removeRollingMean', False)
        removeMean = self.app.getPref('removeMean', True)
        meanSpan = None
        if removeRolling:
            meanSpan = self.app.getPref('rollingMeanSpan', 5) / self.timeScalar
            removeMean = True
        else:
            meanSpan = -1

        # TODO: Generate a realistic range from the sensor descriptions
        initialRange = (-10,10)

        p = self.plotarea.addPlot(None, title=units[0], units=units,
                                  initialRange=initialRange)
        if p is not None:
            p.removeMean(removeMean, meanSpan)

        # This is to make sure everything works if all tabs were closed first.
        self.enableMenus()
        self.updateSourceMenu(p)
        self.updateConversionMenu(p)


    def OnLegendToggle(self, evt):
        """ Handle 'Show Legend' menu item selection.
        """
        self.showLegend = evt.IsChecked()
        self.app.setPref("showLegend", self.showLegend)
        self.plotarea.redraw()


    def OnHollowToggle(self, evt):
        """ Handle 'Hollow Mode' menu item selection.
        """
        self.drawHollowPlot = evt.IsChecked()
        self.app.setPref('drawHollowPlot', self.drawHollowPlot)
        self.plotarea.redraw(force=True)


    def OnConversionConfig(self, evt):
        """ Handle selection of the unit converter configuration menu item.
        """
        p = self.plotarea.getActivePage()
        result = ConverterEditor.edit(p.transform, self)
        if result == wx.ID_OK:
            self.dataset.updateTransforms()
        p.redraw()


    def OnConversionPicked(self, evt):
        """ Handle selection of a unit converter menu item.
        """
        activePage = self.plotarea.getActivePage()
        if activePage is None:
            return
        units = activePage.units
        conv = self.unitConverters.get(evt.GetId(), None)
        for p in self.plotarea:
            if p is None:
                continue
            if p.units == units:
                p.setUnitConverter(conv)
        self.updateConversionMenu(activePage)


    def OnEditCalibration(self, evt):
        """ Handle Data->Edit Calibration Polynomials menu item selection.
        """
        changed = live_calibration.editCalibration(self)
        if changed:
            self.plotarea.redraw(force=True)


    def OnDisableBivariates(self, evt):
        """
        """
        self.setNoBivariates(evt.IsChecked())
#         self.app.setPref('noBivariates', self.noBivariates)
        self.plotarea.redraw(force=True)


    def OnToolMenuSelection(self, evt):
        """ Handle the selection of a plug-in 'tool' (utility).
        """
        tool = self.app.plugins.find(_wxId=evt.GetId())
        if tool:
            tool[0](self)

    
    def OnToolMenuShowPlugins(self, evt):
        """ Handle Tools->Show Plugins Folder menu item selection.
        """
        if not os.path.exists(self.app.pluginsDir):
            q = wx.MessageBox("The plug-ins directory (%s) does not exist.\n"
                              "Create it?" % self.app.pluginsDir,
                              "Show Plugins Directory", parent=self,
                              style=wx.ICON_INFORMATION | wx.YES_NO)

            if q == wx.NO:
                return
            
            try:
                os.makedirs(self.app.pluginsDir)
                # FUTURE: Create/copy a README into the new folder?
                
            except Exception as err:
                # FUTURE: Specific error messages for different exceptions?
                logger.error("Failed to create plugins directory: %s" % err)
                wx.MessageBox("The plug-ins directory could not be created.",
                              "Show Plugins Directory", parent=self,
                              style=wx.ICON_ERROR | wx.OK)
                return

        self.SetCursor(wx.Cursor(wx.CURSOR_WAIT))
        try:
            # FUTURE: OS-specific functionality
            if os.path.isdir(self.app.pluginsDir):
                os.system("explorer %s" % self.app.pluginsDir)
            
        except Exception as err:
            # FUTURE: Specific error messages for different exceptions?
            logger.error("Could not open plugins directory: %s" % err)
            wx.MessageBox("The plug-ins directory could not be created.",
                          "Show Plugins Directory", parent=self,
                          style=wx.ICON_ERROR | wx.OK)
        finally:
            self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        

    #===========================================================================
    # Custom Events
    #===========================================================================

    def OnSetVisibleRange(self, evt):
        """ Handle the event signifying a change in visual range. Used
            primarily by the import thread.
        """
        self.setVisibleRange(evt.start, evt.end, instigator=evt.instigator,
                             tracking=evt.tracking)


    def OnSetTimeRange(self, evt):
        """ Handle the event signifying a change in the dataset's total
            time range. Used primarily by the import thread.
        """
        self.setTimeRange(evt.start, evt.end, instigator=evt.instigator,
                          tracking=evt.tracking)


    def OnProgressStart(self, evt):
        """ Handle the event signifying the start of the progress bar. Used
            primarily by the import thread.
        """
        self.statusBar.startProgress(evt.label, evt.initialVal,
                                     evt.cancellable, evt.cancelEnabled)
        if evt.cancellable:
            self.menubar.FindItemById(wx.ID_CANCEL).Enable(True)


    def OnProgressUpdate(self, evt):
        """ Handle the event signifying an update of the progress bar. Used
            primarily by the import thread.
        """
        self.statusBar.updateProgress(val=evt.val, label=evt.label,
                                      cancellable=evt.cancellable)


    def OnProgressEnd(self, evt):
        """ Handle the event signifying a the completion of the progress bar.
            Used primarily by the import thread.
        """
        self.statusBar.stopProgress(evt.label)
        self.removeOperation(evt.job)
        self.menubar.FindItemById(wx.ID_CANCEL).Enable(False)


    #===========================================================================
    # Background operation stuff
    #===========================================================================

    def pushOperation(self, job):
        """ Adds a task thread to the stack of operations. All keyword arguments
            override attributes of the job object itself if not `None`.

            @param job: A `Job` process.
            @keyword modal: Can this operation not run in the background?
                Not currently implemented.
            @keyword prompt: Should the user be prompted prior to canceling?
            @keyword title: The title of the cancel dialog (if applicable).
            @keyword pref: The name of the preference to be used to suppress
                the cancel dialog, or `None` if the dialog isn't 'memorable.'
        """
        # The initial implementation is simply a list, wrapped for future dev.
        self.cancelQueue.append(job)


    def removeOperation(self, job):
        """ Given an instance of `Job`, remove its corresponding entry in the
            queue. Note that this does not cancel a job, only removes it from
            the queue.

            @param job: A `Job` object.
            @return: `True` if the operation was removed, `False` if not.
        """
        # The initial implementation is simply a list, wrapped for future dev.
        if job is None:
            return False
        try:
            self.cancelQueue.remove(job)
            return True
        except ValueError:
            return False


    def getCurrentOperation(self):
        """ Retrieve the currently-running background task.
        """
        # The initial implementation is simply a list, wrapped for future dev.
        if len(self.cancelQueue) == 0:
            return None
        return self.cancelQueue[-1]


    def cancelOperation(self, evt=None, job=None, prompt=True):
        """ Cancel the current background operation.

            @keyword evt: The event that initiated the cancel, if any.
            @keyword job: A specific `Job` to cancel. Defaults to the last
                job started.
            @keyword prompt: `True` to prompt the user before canceling (job
                must also have its `cancelPrompt` attribute `True`), `False`
                to suppress the prompt.
            @return: `False` if the operation could not be cancelled,
                or a message string to display upon cancellation.
                Anything but `False` is considered a successful shutdown.
        """
        # if the cancel takes some time to take effect, the thing that
        # caused it could be disabled like this (to prevent extra clicks):
        # evt.EventObject.Enable(False)

        if len(self.cancelQueue) == 0:
            # Nothing to cancel. Shouldn't happen.
            self.stopBusy()
            return ""

        if job is None:
            job = self.getCurrentOperation()

        if job.cancelPrompt and prompt:
            if self.ask(job.cancelMessage, job.cancelTitle,
                        pref=job.cancelPromptPref) != wx.ID_YES:
                return False

        cancelled = job.cancel()
        if cancelled:
            msg = job.cancelResponse
            self.removeOperation(job)
            if len(self.cancelQueue) == 0:
                self.stopBusy()
            return msg


    def cancelAllOperations(self, evt=None, prompt=False):
        """ Cancel any and all background operations.

            @keyword evt: The event that initiated the cancel, if any.
            @keyword prompt: `True` to prompt the user before canceling (job
                must also have its `cancelPrompt` attribute `True`), `False`
                to suppress the prompt.
            @return: `False` if any operation couldn't be cancelled, `True`
                if all operations were successfully shut down.
        """
        result = True
        while len(self.cancelQueue) > 0:
            result = result and self.cancelOperation(evt, prompt=prompt) is not False
        return result


    def pauseOperation(self, evt=None, job=None):
        """ Temporarily suspend the current background operation.

            @keyword evt: The event that initiated the pause, if any.
            @keyword job: A specific `Job` to pause. Defaults to the last
                job started.
            @return: `False` if the operation could not be paused,
                or a message string to display upon cancellation.
                Anything but `False` is considered a successful pause.
        """
        if len(self.cancelQueue) == 0:
            return None, False

        if job is None:
            job = self.getCurrentOperation()

        logger.info("Paused operation %r" % job)
        return job, job.pause(True)
        return job, True


    def resumeOperation(self, evt=None, job=None):
        """ Temporarily suspend the current background operation.

            @keyword evt: The event that initiated the pause, if any.
            @keyword job: A specific `Job` to pause. Defaults to the last
                job started.
            @return: `False` if the operation could not be paused,
                or a message string to display upon cancellation.
                Anything but `False` is considered a successful pause.
        """
        if len(self.cancelQueue) == 0:
            return False

        if job is None:
            job = self.getCurrentOperation()

        logger.info("Resumed operation %r" % job)
        return job.pause(False)


    #===========================================================================
    #
    #===========================================================================

    def startBusy(self, cancellable=False, modal=False):
        """ Start the 'busy' display.
            @keyword cancellable: if `True`, the 'Cancel' button in the menu
                bar is enabled.
            @keyword modal: If `True`, the 'wait' cursor is shown; if `False`,
                the 'wait arrow' one is used.
        """
        if modal:
            self.SetCursor(wx.Cursor(wx.CURSOR_WAIT))
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROWWAIT))
        if cancellable:
            self.menubar.FindItemById(wx.ID_CANCEL).Enable(True)
        self.busy = True


    def stopBusy(self):
        """ Change the cursor and cancel button back, presumably after calling
            `startBusy`.
        """
        self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        self.menubar.FindItemById(wx.ID_CANCEL).Enable(False)
        self.busy = False


    #===========================================================================
    #
    #===========================================================================

    def showMouseHPos(self, pos, units=None):
        """ Display the X axis value for a given mouse position. All Plots
            within the same PlotArea use the same horizontal axis scale/units.
        """
        if self.session is None:
            return

        if pos is None:
            self.statusBar.setPositionDisplay(x="", time="")
            return

        units = self.units[1] if units is None else units
        t = self.timeline.getValueAt(pos) * self.timeScalar
        msgX = self.xFormatter % (t, units)
        msgT = ""

        if self.session.utcStartTime is not None:
            absT = self.session.utcStartTime+t
            if self.showUtcTime:
                utc = str(datetime.utcfromtimestamp(absT))
                msgT = "X (UTC): %s" % utc[:-2]
            elif self.showLocalTime:
                local = str(datetime.fromtimestamp(absT))
                msgT = "X (Local): %s" % local[:-2]

        self.statusBar.setPositionDisplay(x=msgX, time=msgT)


    def showMouseVPos(self, pos, units=""):
        """ Show a Y axis value, presumably calculated from the current
            Plot's vertical axis. This will vary between Plots, so unlike
            `showMouseHPos()`, this will show a literal value.

            @param h:
        """
        msg = "" if pos is None else self.yFormatter % (pos, units)
        self.statusBar.setPositionDisplay(y=msg)


    #===========================================================================
    #
    #===========================================================================

    def handleError(self, err, msg=None, icon=wx.ICON_ERROR,
                    what='', where=None, fatal=False, closeFile=False):
        """ General-purpose exception handler that attempts to provide a
            meaningful error message. Also works as an event handler for
            custom error events (e.g. `EvtImportError`). Exception handling
            elsewhere in the program should attempt to catch expected
            exceptions first, then call this for the naked `Exception`.

            @param err: The raised exception, an event object (e.g.
                `EvtImportError`), or `None`.
            @keyword msg: An alternative error message, to be shown verbatim.
            @keyword icon: The icon to show in the dialog box.
            @keyword what: A description of the operation being performed that
                raised the exception.
            @keyword where: The method in which the exception was raised; a
                lightweight sort of traceback.
            @keyword fatal: If `True`, the app Viewer will shut down.
        """
        # TODO: Consider replacing with something using `sys.excepthook` 
        if DEBUG:
            raise

        if isinstance(err, wx.Event):
            err = err.err
            msg = getattr(err, 'msg', None)

        if what:
            what = " while %s" % what

        xmsg = None

        self.app.lastException = err

        if not isinstance(msg, basestring):
            # Slightly more specific error messages go here.
            if isinstance(err, MemoryError):
                msg = "The system ran out of memory%s" % what
            else:
                msg = u"An unexpected %s occurred%s" % \
                        (err.__class__.__name__, what)
                xmsg = unicode(err)
                if not xmsg:
                    xmsg = "No further information is available."

        if fatal:
            xmsg += "\n\nThe application will now shut down."

        self.ask(msg, APPNAME, wx.OK, icon=icon, extendedMessage=xmsg)
        ctrlPressed = wx.GetKeyState(wx.WXK_CONTROL)
        shiftPressed = wx.GetKeyState(wx.WXK_SHIFT)

        # Holding control when okaying alert shows more more info.
        if ctrlPressed and isinstance(err, Exception):
            import pdb; pdb.set_trace()

        # The error occurred someplace critical; self-destruct!
        if fatal:
            self.Destroy()

        if closeFile:
            self.closeFile()

        if ctrlPressed and shiftPressed and err is not None:
            raise


    #===========================================================================
    #
    #===========================================================================

    def updateSourceMenu(self, p):
        """ Check menu items for sources displayed in the active tab, disable
            menu items for sources that are not applicable.
        """
        if p is None:
            return
        for mi in self.viewSourceMenu.GetMenuItems():
            mid = mi.GetId()
            source = self.dataSources.get(mid, None)
            if source is None:
                return
            checked = source in p.sources
            enabled = p.yUnits == source.units
            self.setMenuItem(self.viewSourceMenu, mid, checked, enabled)


    def updateWarningsMenu(self, p):
        """ Check menu items for the warnings displayed on the active tab.
        """
        if p is None:
            return
        for mi in self.viewWarningsMenu.GetMenuItems():
            mid = mi.GetId()
            warn = self.warningRanges.get(mid, None)
            if warn is None:
                return
            checked = warn in p.warningRanges
            self.setMenuItem(self.viewWarningsMenu, mid, checked)


    #===========================================================================
    # Unit conversion/transform-related stuff
    #===========================================================================

    def updateConversionMenu(self, p):
        """ Update the enabled and checked items in the Data->Display menu.
        """
        if p is None:
            return
        for mi in self.displayMenu.GetMenuItems():
            mid = mi.GetId()
            if mi.GetKind() == wx.ITEM_SEPARATOR:
                continue
            elif mid == self.ID_DATA_DISPLAY_CONFIG:
                mi.Enable(getattr(p.transform, 'parameters', None) is not None)
                continue
            elif mid == self.ID_DATA_DISPLAY_NATIVE:
                mi.SetText("Native Units (%s as %s)" % p.nativeUnits)#p.units)
            elif len(p.sources) == 0:
                mi.Enable(self.unitConverters[mid].convertsFrom == p.units)
            else:
                mi.Enable(self.unitConverters[mid].isApplicable(p.sources))
            if p.transform == self.unitConverters[mid]:
                self.setMenuItem(self.displayMenu, mid, checked=True)


#===============================================================================
#
#===============================================================================

class ViewerApp(wx.App):
    """ The main class of the SSX Data Viewer. Most of the work is done by the
        Viewer; the app mainly handles global settings like preferences
        (and the primary functionality inherited from `wx.App`, of course).
    """
    HISTORY_SIZE = 8

    version = VERSION
    versionString = __version__
    buildVersion = VERSION + (BUILD_NUMBER,)

    defaultPlugins = [tools.raw2mat,
                      tools.filesplit,
                      tools.ide2csv]

    def saveAllPrefs(self, filename=None, hideFile=None):
        """ Save all preferences, including defaults, to the config file.
            Primarily for debugging.
        """
        self.prefs.saveAllPrefs(filename, hideFile)


    def getPref(self, name, default=None, section=None):
        """ Retrieve a value from the preferences.

            @param name: The name of the preference to retrieve.
            @keyword default: An optional default value to return if the
                preference is not found.
            @keyword section: An optional "section" name from which to
                get. Currently a prefix in this implementation.
        """
        return self.prefs.getPref(name, default, section)


    def setPref(self, name, val, section=None, persistent=True):
        """ Set the value of a preference. Returns the value set as a
            convenience.
        """
        return self.prefs.setPref(name, val, section, persistent)


    def hasPref(self, name, section=None, defaults=False):
        """ Check to see if a preference exists, in either the user-defined
            preferences or the defaults.

            @param name: The name of the preference to retrieve.
            @keyword defaults: An optional default value to return if the
                preference is not found.
            @keyword section: An optional "section" name from which to
                delete. Currently a prefix in this implementation.
        """
        return self.prefs.hasPref(name, section, defaults)


    def deletePref(self, name, section=None):
        """ Delete one or more preferences. Glob-style wildcards are allowed.

            @keyword name: The name of the preference to delete. Optional if
                `section` is supplied
            @keyword section: An optional section name, limiting the scope.
            @return: The number of deleted preferences.
        """
        return self.prefs.deletePref(name, section)


    def editPrefs(self, evt=None):
        """ Launch the Preferences editor.
        """
        if self.prefs.editPrefs():
            for v in self.viewers:
                v.loadPrefs()
                


    #===========================================================================
    #
    #===========================================================================

    def showBetaWarning(self):
        """ Warn the user that the software they're using is pre-release. The
            warning can be suppressed.
        """
        pref = 'hideBetaWarning_%s' % '.'.join(map(str, VERSION))
        if self.getPref(pref, False, section='ask'):
            return
        dlg = MemoryDialog(None, "This pre-release beta software!",
                           "Beta Warning", wx.OK|wx.ICON_INFORMATION,
                           remember=True)
        dlg.SetExtendedMessage(
            "This preview version of %s is an early release, and is expected "
            "to contain bugs,\nperformance limitations, and an incomplete "
            "user experience.\n\nDo not use for any mission-critical work!" %
            APPNAME)
        dlg.ShowModal()
        self.setPref(pref, dlg.getRememberCheck(), section='ask')
        dlg.Destroy()


    def __init__(self, *args, **kwargs):
        """ Constructor. Takes standard `wx.App` arguments, plus:

            @keyword prefsFile: The full path and name to an alternative
                configuration file.
            @keyword filename: The name of a file to open on load.
            @keyword clean: If `True`, the preferences are reset.
            @keyword loadLastFile: If `True` and no `initialFilename' is
                specified, the viewer will reload the last file opened.
            @keyword safe: If `True`, start in 'safe mode,' which disables
                plugins and external EBML schemata.
        """
        self.quitting = False
        
        self.prefsFile = kwargs.pop('prefsFile', None)
        self.initialFilename = kwargs.pop('filename', None)
        clean = kwargs.pop('clean', False)
        safeMode = kwargs.pop('safe', False)
        loadLast = kwargs.pop('loadLastFile', False)

        super(ViewerApp, self).__init__(*args, **kwargs)

        safeMode = safeMode or wx.GetKeyState(wx.WXK_SHIFT)

#         self.fileHistory = wx.FileHistory(self.HISTORY_SIZE)
        self.viewerIdx = 0
        self.lastException = None
        self.viewers = []
        self.changedFiles = True
        self.colorDb = wx.ColourDatabase()
        stdPaths = wx.StandardPaths.Get()
        self.docsDir = os.path.join(stdPaths.GetDocumentsDir(), APPNAME)
        self.prefs = Preferences(self.prefsFile, clean=(clean or safeMode))
        self.plugins = None

        self.pluginsDir = os.path.join(self.docsDir, 'Plugins')
        self.scriptsDir = os.path.join(self.docsDir, 'Scripts')

        self.loadPlugins(safeMode)

        # Insert user override EBML schema path
        if not safeMode:
            ebmlite.SCHEMA_PATH.insert(0, os.path.join(self.docsDir, 'schemata'))
            ebmlite.SCHEMATA.clear()

        if loadLast and self.initialFilename is None:
            try:
                self.initialFilename = self.prefs.getRecentFiles()[0]
            except (IndexError, KeyError):
                pass

#         locale.setlocale(locale.LC_ALL, str(self.getPref('locale')))
        localeName = self.getPref('locale', 'LANGUAGE_ENGLISH_US')
        self.locale = wx.Locale(getattr(wx, localeName, wx.LANGUAGE_ENGLISH_US))
        self.createNewView(filename=self.initialFilename)

        if DEBUG or BETA:
            self.showBetaWarning()

        # Automatic Update Check
        self.Bind(events.EVT_UPDATE_AVAILABLE, self.OnUpdateAvailable)

        if self.getPref('updater.interval',3) > 0:
            updater.startCheckUpdatesThread(self)


    def loadPlugins(self, safeMode=False):
        """ Search for and load plugin components.
        """
        self.plugins = plugins.PluginSet(app=APPNAME, appVersion=VERSION,
                                         quiet=True)

        if safeMode or wx.GetKeyState(wx.WXK_SHIFT):
            logger.info("Starting in SAFE MODE. No plug-ins will be loaded.")
            return

        logger.info("Searching for plug-ins...")
        self.plugins.add(self.defaultPlugins, builtin=True)
        numPlugins = len(self.plugins)
        logger.info("Found %d standard plug-in(s)" % numPlugins)

        if DEBUG and numPlugins > 0:
            stdPlugs = self.plugins.items()
            for p in stdPlugs:
                logger.info(u" * %s: %s" % p)

        if self.getPref('plugins.loadUserPlugins', False):
            dirs = [os.path.join(self.pluginsDir, '*')]
            dirs.extend(self.getPref('plugins.searchPaths', []))
            self.plugins.add(dirs, app=APPNAME, appVersion=VERSION, quiet=True,
                             builtin=False)
            newNum = len(self.plugins) - numPlugins
            logger.info("Found %d external plug-in(s)" % newNum)

            if DEBUG and newNum > 0:
                userPlugs = set(self.plugins.items()).difference(stdPlugs)
                for p in userPlugs:
                    logger.info(u" * %s: %s" % p)
        else:
            logger.info("External plug-ins disabled.")

        if not (self.plugins.incompatible or self.plugins.bad):
            return

        logger.warning("Skipped loading %d incompatible and %d bad plug-ins!" %
                       (len(self.plugins.incompatible), len(self.plugins.bad)))

        # Display warning that some plug-ins failed to load
        numIncomp = len(self.plugins.incompatible)
        numBad = len(self.plugins.bad)

        msg = ["Some plug-in modules (%d of %d) could not be loaded." %
               (numIncomp + numBad, numIncomp + numBad + len(self.plugins))]

        if numIncomp > 0:
            msg.append('\nIncompatible Plug-ins (%d):' % numIncomp)
            for p in self.plugins.incompatible:
                msg.append('    * %s' % (p[1]))
                logger.warning("Incompatible plug-in: %s (%s)" % (p[1],p[0]))

        if numBad > 0:
            msg.append('\nBad/Damaged Plug-ins (%d):' % numBad)
            for p in self.plugins.bad:
                msg.append('    * %s' % (p[1]))
                logger.error("Bad plug-in: %s (%s)" % (p[1],p[0]))

        wx.MessageBox('\n'.join(msg), "Plug-in Error",
                      style=wx.ICON_WARNING|wx.OK)


    def createNewView(self, filename=None, title=None, splash=True, **kwargs):
        """ Create a new viewer window.

            @keyword filename: The name of a recording to open in the new
                view.
            @keyword title: An alternate title, shown instead of the filename.
            @keyword splash: If `True`, show the 'splash screen'.
        """
        self.viewerIdx += 1
        viewer = Viewer(None, app=self, filename=filename, splash=splash,
                        number=self.viewerIdx, **kwargs)
        self.viewers.append(viewer)
        viewer.Show()


    def abbreviateName(self, filename, length=None):
        """ Create a shorter version of a filename. Primarily for display in
            `Viewer` windows' title bars.
        """
        length = length or self.getPref('titleLength', None)
        if length is None:
            return filename
        if len(filename) <= length:
            return filename

        dirname = os.path.dirname(filename)
        n1 = dirname.rfind(os.path.sep, 0, length/2-2)
        n2 = dirname.find(os.path.sep, len(dirname)-(length/2+2))
        if n1 == n2:
            return filename
        return os.path.join(dirname[:n1], u"\u2026", dirname[n2+1:],
                            os.path.basename(filename))


    def getWindowTitle(self, viewer=None, title='', showApp=True,
                       number=True):
        """ Generate a unique viewer window title.
        """
        if not title and viewer and viewer.dataset is not None:
            filename = viewer.dataset.filename
            if filename:
                if self.getPref('showFullPath', False):
                    # Abbreviate path if it's really long (ellipsis in center)
                    title = self.abbreviateName(filename)
                else:
                    title = os.path.basename(filename)

            if len(viewer.dataset.sessions) > 1:
                title = "%s, Session %d" % (title, viewer.session.sessionId)

            if showApp:
                title = "%s - %s" % (self.fullAppName, title)

        else:
            title = self.fullAppName if showApp else ""

        if number and (len(self.viewers) > 1 or self.viewerIdx > 1):
            title = u"%s (%d)" % (title, viewer.number)

        return title.strip()


    def quit(self):
        """ Quit the application by closing all windows.
        """
        # Not sure this is the best way to implement this
        self.quitting = True
        
        while self.viewers:
            self.viewers[0].Close()
        

    #===========================================================================
    # Event handlers
    #===========================================================================

    def OnInit(self):
        """ Post-Constructor initialization event handler.
        """
        self.fullAppName = "%s %s" % (APPNAME, self.versionString)
        self.SetAppName(APPNAME)
        self.SetAppDisplayName(APPNAME)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        if DEBUG:
            logger.info("Starting version %s" % __version__)
            logger.info("Repo branch %s, commit %s" % (REPO_BRANCH, REPO_COMMIT_ID))
        return True


    def OnClose(self, evt):
        """ Handle Quit.
        """
        evt.Skip()
        if len(self.viewers) > 0:
            evt.Veto()
            return
        self.prefs.savePrefs()


    def OnUpdateAvailable(self, evt):
        """ Handle events generated by the automatic version checker.
        """
        # Hack to make sure the dialog is in the foreground; sometimes a problem
        # if the check took particularly long. May no longer be required.
        topWindow = None
        for v in self.viewers:
            if v.HasFocus:
                topWindow = v

        if evt.error:
            # do logging of error
            logger.error('Update check at %s failed: %s' %
                         (evt.url, evt.response))
            if not evt.quiet:
                if isinstance(evt.response, IOError):
                    msg = ("%s could connect to the web to check for updates "
                           "due to a network error.\n\nTry again later."
                           % self.AppDisplayName)
                else:
                    msg = ("%s was unable to retrieve the update information "
                           "from the Mide web site.\n\nPlease try again later."
                           % self.AppDisplayName)
                if evt.url:
                    url = str(evt.url).split('?')[0]
                    msg = "%s\n\nVersion information URL: %s" % (msg, url)
                wx.MessageBox(msg, "Check for Updates", parent=topWindow,
                              style=wx.ICON_EXCLAMATION | wx.OK)
            return

        if not evt.newVersion:
            self.setPref('updater.lastCheck', time.time())
            if not evt.quiet:
                msg = "Your copy of %s is up to date." % self.GetAppDisplayName()
                if BETA or DEBUG:
                    msg = "%s\n\nNOTE: You are using a pre-release beta version. The automatic\n" \
                        "update notification system may not recognize it. Check manually." % msg
                # User-initiated checks show a dialog if there's no new version
                wx.MessageBox(msg, "Update Check", parent=topWindow,
                              style=wx.ICON_INFORMATION | wx.OK)
            return

        dlg = updater.UpdateDialog(topWindow, -1, updaterEvent=evt)
        response = dlg.ShowModal()

        # Dialog itself handles all the browser stuff, just handle preferences
        if response != wx.CANCEL:
            self.setPref('updater.lastCheck', time.time())
            if response == dlg.ID_SKIP:
                self.setPref('updater.version', evt.newVersion)

        dlg.Destroy()


#===============================================================================
#
#===============================================================================

def main():
    import argparse
    # Windows shell does not like high Unicode characters; remove the dot.
    desc = cleanUnicode("%s v%s \n%s" % (APPNAME.replace(u'\u2022', ' '),
                                         __version__, __copyright__))
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('filename', nargs="?",
                        help="The name of the MIDE (*.IDE) file to import")
    parser.add_argument("-p", "--prefsFile",
                        help="An alternate preferences file")
    parser.add_argument('-c', '--clean', action="store_true",
                        help="Reset all preferences to their defaults")

    args = parser.parse_args()
    kwargs = vars(args)

    app = ViewerApp(**kwargs)
    app.MainLoop()

if __name__ == '__main__':
    main()
