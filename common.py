'''
Controls, dialogs, and other things used by multiple files. 

Created on Dec 31, 2013

@author: dstokes
'''

import wx; wx = wx;

import images

#===============================================================================
# 
#===============================================================================

class StatusBar(wx.StatusBar):
    """
    The viewer status bar.  It mainly provides a progress bar and status text
    when the Viewer is doing something in the background (i.e. file import or
    export). The progress bar can show an actual value, or it can just run 
    continuously.
    """
    frameDelay = 30
    numFields = 6
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard wx.Panel arguments, plus:
        
            @keyword root: The viewer's 'root' window.
        """
        self.root = kwargs.pop('root', None)
        wx.StatusBar.__init__(self, *args, **kwargs)
        
        if self.root is None:
            self.root = self.GetParent().root
        
        logo = images.MideLogo.GetBitmap()
        self.logo = wx.StaticBitmap(self, -1, logo)

        self.progressBar = wx.Gauge(self, -1, 1000)
        self.cancelButton = wx.Button(self, wx.ID_CANCEL, style=wx.BU_EXACTFIT)
        bwidth, bheight = self.cancelButton.GetBestSize()
        self.buttonWidth = bwidth + 2
        self.cancelButton.SetSize((bwidth, bheight-2))

        fieldWidths = [-1] * self.numFields

        self.buttonFieldNum = self.numFields-1
        self.progressFieldNum = self.numFields-2
        self.messageFieldNum = self.numFields-3
        self.yFieldNum = self.numFields-4
        self.xFieldNum = self.numFields-5
        self.logoFieldNum = 0

        fieldWidths[self.logoFieldNum] = logo.GetSize()[0]
        fieldWidths[self.messageFieldNum] = -4
        fieldWidths[self.progressFieldNum] = -2
        fieldWidths[self.buttonFieldNum] = bwidth

        self.SetFieldsCount(self.numFields)
        self.SetStatusWidths(fieldWidths)

        self.Bind(wx.EVT_SIZE, self.repositionProgressBar)
        self.Bind(wx.EVT_BUTTON, self.OnCancelClicked, self.cancelButton)
        
        self.repositionProgressBar()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.TimerHandler)


    def __del__(self):
        self.timer.Stop()


    def OnCancelClicked(self, evt):
        """ Process a click to the 'Cancel' button, checking with the parent
            to make sure it's okay.
        """
        cancelled = self.GetParent().cancelOperation(evt, prompt=True)
        if cancelled is not False:
            if isinstance(cancelled, basestring):
                self.stopProgress(cancelled)
            else:
                self.stopProgress()


    def TimerHandler(self, event):
        """ Update the indefinite progress bar (if active). 
        """
        self.progressBar.Pulse()
   
        
    def repositionProgressBar(self, evt=None):
        """ The positions of the progress bar and cancel button need to be 
            manually set after resize.
            
            @keyword evt: The event that triggered the repositioning.
        """
        rect = self.GetFieldRect(self.numFields-2)
        self.progressBar.SetSize((rect.width-8, rect.height-8))
        self.progressBar.SetPosition((rect.x+4, rect.y+4))
        
        buttonRect = self.GetFieldRect(self.numFields-1)
        self.cancelButton.SetPosition(buttonRect[:2])

        
    def startProgress(self, label="Working...", initialVal=0, cancellable=True,
                      cancelEnabled=None, delay=frameDelay):
        """ Start the progress bar, showing a specific value.
        
            @keyword label: Text to display in the status bar.
            @keyword initialVal: The starting value displayed. -1 will start
                the progress bar in indefinite mode.
            @keyword cancellable: If `True`, the Cancel button will be visible.
            @keyword cancelEnabled: If `False` and `cancellable` is `True`,
                the Cancel button will be visible but disabled (grayed out).
                For use in cases where a process can only be cancelled after
                a certain point.
        """
        self.SetStatusText(label, 0)
        self.progressBar.Show(True)
        if initialVal < 0 or initialVal > 1.0:
            self.timer.Start(delay)
        else:
            self.timer.Stop()
            self.progressBar.SetValue(initialVal*1000.0)
            
        cancelEnabled = cancellable if cancelEnabled is None else cancelEnabled
        self.cancelButton.Show(cancellable)
        self.cancelButton.Enable(cancelEnabled)


    def updateProgress(self, val=None, label=None, cancellable=None):
        """ Change the progress bar's value and/or label. If the value is
            greater than 1.0, the bar automatically changes to its
            'throbber' mode (indefinite cycling bar).
        
            @param val: The value to display on the progress bar, as a
                normalized float.
            @keyword label: Text to display in the status bar.
            @keyword cancelEnabled: If the Cancel button is visible,
                `True` will enable it, `False` will disable it.
                `None` (default) will leave it as-is.
        """
        self.progressBar.Show(True)

        if label is not None:
            self.SetStatusText(label, self.messageFieldNum)
        if cancellable is not None:
            self.cancelButton.Enable(cancellable)
            if cancellable is True:
                self.progressBar.Show(True)
            
        if val is None:
            return
        
        if val > 1.0 or val < 0:
            if not self.timer.IsRunning():
                self.timer.Start(self.frameDelay)
        else:
            if self.timer.IsRunning():
                self.timer.Stop()
            self.progressBar.SetValue(val*1000.0)

        
    def stopProgress(self, label=""):
        """ Hide the progress bar and Cancel button (if visible).
            
            @keyword label: Text to display in the status bar.
        """
        self.timer.Stop()
        if label is not None:
            self.SetStatusText(label, self.messageFieldNum)
        self.progressBar.Show(False)
        self.cancelButton.Show(False)


#===============================================================================
# 
#===============================================================================

