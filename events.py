'''
Custom events used by the viewer.

Created on Jan 16, 2014

@author: dstokes
'''

from wx.lib.newevent import NewEvent as _NewEvent

#===============================================================================
# Custom Events (for multithreaded UI updating)
#===============================================================================

(EvtSetVisibleRange, EVT_SET_VISIBLE_RANGE) =_NewEvent()
(EvtSetTimeRange,    EVT_SET_TIME_RANGE) =_NewEvent()
(EvtProgressStart,   EVT_PROGRESS_START) =_NewEvent()
(EvtProgressUpdate,  EVT_PROGRESS_UPDATE) =_NewEvent()
(EvtProgressEnd,     EVT_PROGRESS_END) =_NewEvent()
(EvtInitPlots,       EVT_INIT_PLOTS) =_NewEvent()
(EvtImportError,     EVT_IMPORT_ERROR) =_NewEvent()

(EvtSuspendDrawing,  EVT_SUSPEND_DRAWING) = _NewEvent()
(EvtResumeDrawing,   EVT_RESUME_DRAWING) = _NewEvent()

(EvtUpdateAvailable, EVT_UPDATE_AVAILABLE) = _NewEvent()

# Not currently used
# (EvtZoomInH,  EVT_ZOOM_IN_H ) =_NewEvent()
# (EvtZoomOutH, EVT_ZOOM_OUT_H) =_NewEvent()
# (EvtZoomFitH, EVT_ZOOM_FIT_H) =_NewEvent()
# (EvtZoomInV,  EVT_ZOOM_IN_V ) =_NewEvent()
# (EvtZoomOutV, EVT_ZOOM_OUT_V) =_NewEvent()
# (EvtZoomFitV, EVT_ZOOM_FIT_V) =_NewEvent()

