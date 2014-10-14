'''
The MIDE EBML recording file importer.

@todo: The viewer depends on this sending update events in order to draw
    anything. It's currently a little brittle; it needs to have done some
    updates before finishing, burdening the importers. Add something that the 
    importer can call that will be certain to send the 'completed' event.
'''

from datetime import datetime
import locale

import wx; wx = wx # Workaround for Eclipse code comprehension

from common import Job
from events import EvtProgressStart, EvtProgressEnd, EvtProgressUpdate
from events import EvtInitPlots, EvtSetTimeRange, EvtSetVisibleRange
from events import EvtImportError

# import mide_ebml

class Loader(Job):
    """ The object that does the work of spawning an asynchronous file-loading
        thread and updating the viewer as data is loaded.
        
    """

    cancelPrompt = True
    cancelMessage = "Are you sure you want to cancel the file import?"
    cancelResponse = "Import cancelled."
    cancelTitle = "Cancel Import"
    cancelPromptPref = "cancelImportPrompt"
    
    def __init__(self, root, dataset, reader, numUpdates=100, updateInterval=1.0):
        """ Create the Loader and start the loading process.
            
            @param root: The Viewer.
            @param dataset: The Dataset being loaded. It should be fresh,
                referencing a file stream but not yet loaded.
            @keyword numUpdates: The minimum number of calls to the updater to
                be made. There will be more than this number of updates if
                any takes longer than the specified `updateInterval` (below).
            @keyword updateInterval: The maximum number of seconds between
                calls to the updater
        """
        self.readingData = False
        self.lastCount = 0
        self.reader = reader

        super(Loader, self).__init__(root, dataset, numUpdates, updateInterval)


    def run(self):
        evt = EvtProgressStart(label="Importing...", initialVal=-1, 
                               cancellable=True, cancelEnabled=None)
        wx.PostEvent(self.root, evt)
        
        sessionId = -1
        if self.root.session is not None:
            sessionId = self.root.session.sessionId
        elif self.dataset.lastSession:
            sessionId = self.dataset.lastSession.sessionId
        
        self.totalUpdates = 0
        self.reader(self.dataset, updater=self, 
                    numUpdates=self.numUpdates,
                    updateInterval=self.updateInterval,
                    sessionId=sessionId)

        evt = EvtProgressEnd(label=self.formatMessage(self.lastCount),
                             job=self)
        wx.PostEvent(self.root, evt)


    def formatMessage(self, count, est=None):
        """ Create a nice message string containing the total import count
            and (optionally) the estimated time remaining.
        """
        countStr = locale.format("%d", count, grouping=True)

        if est is None or est.seconds < 2:
            estStr = ""
        elif est.seconds < 60:
            estStr = "- Est. finish in %d sec." % est.seconds
        else:
            estStr = "- Est. finish in %s" % str(est)[:-7].lstrip("0:")
            
        return "%s samples imported %s" % (countStr, estStr)
        

    def __call__(self, count=0, percent=None, total=None, error=None, 
                 done=False):
        """ Update the Viewer's display.
        
            @param count: the current line number.
            @param percent: The estimated percentage of the file read, as a
                normalized float (0.0 to 1.0). 
            @param total: the total number of samples (if known).
            @param error: Any unexpected exception, if raised during the import.
            @param done: `True` when the export is complete.
        """
        self.totalUpdates += 1

        if error is not None:
            self.cancel()
            wx.PostEvent(self.root, EvtImportError(err=error))
            return
        
        if done:
            # Nothing else needs to be done. Put cleanup here if need be.
            return
        
        if not self.readingData:
            if count or percent:
                # The start of data.
                self.readingData = True
                if self.root.session is None:
                    self.root.session = self.dataset.lastSession
                wx.PostEvent(self.root, EvtInitPlots())
                endTime = self.root.session.endTime
                if endTime is None:
                    endTime = self.root.session.lastTime
                if endTime is not None:
                    kwargs = {'start': self.root.session.firstTime, 
                              'end': endTime, 
                              'instigator': None, 
                              'tracking': False}
                    wx.PostEvent(self.root, EvtSetTimeRange(**kwargs))
                    wx.PostEvent(self.root, EvtSetVisibleRange(**kwargs))
            else:
                # Still in header; don't update.
                return
        
        est = None
        thisTime = datetime.now()
        if self.startTime is None:
            self.startTime = thisTime
        elif percent is not None:
            p = int(percent * 100)
            if p > 0 and p < 100:
                est = ((thisTime - self.startTime) / p) * (100-p)
        
        msg = self.formatMessage(count, est)
        
        wx.PostEvent(self.root, 
            EvtProgressUpdate(val=percent, label=msg, cancellable=True))

        if self.dataset.lastSession == self.root.session:
            evt = EvtSetTimeRange(start=self.root.session.firstTime, 
                                  end=self.root.session.lastTime, 
                                  instigator=None, 
                                  tracking=True)
            wx.PostEvent(self.root, evt)
        
        self.lastTime = thisTime
        self.lastCount = count


