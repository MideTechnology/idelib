'''
Base classes, mixin classes, custom events, utility functions and other 
(non-stand-alone) stuff used by multiple components of the viewer. 

Created on Dec 4, 2013

@author: dstokes
'''

import sys as _sys

import wx.lib.newevent
import wx; wx = wx # Workaround for Eclipse code comprehension


#===============================================================================
# 
#===============================================================================

def expandRange(l, v):
    """ Given a two element list containing a minimum and maximum value, 
        expand it if the given value is outside that range. 
    """
    l[0] = min(l[0],v)
    l[1] = max(l[1],v)


#===============================================================================
# 
#===============================================================================

class TimeValidator(wx.PyValidator):
    """
    """
    validCharacters = "-+.0123456789"
    
    def __init__(self):
        super(TimeValidator, self).__init__()
        self.Bind(wx.EVT_CHAR, self.OnChar)

    def Validate(self, win):
        val = self.GetWindow.GetValue()
        return all((c in self.validCharacters for c in val))

    def OnChar(self, evt):
        key = evt.GetKeyCode()

        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
            evt.Skip()
            return

        if chr(key) in self.validCharacters:
            evt.Skip()
            return

        if not wx.Validator_IsSilent():
            wx.Bell()
            
        return        
    
    
#===============================================================================
# 
#===============================================================================

class ViewerPanel(wx.Panel):
    """ Base class for Viewer component panels. Contains common utility
        methods; also does some viewer-specific initialization.
    """
    
    def __init__(self, *args, **kwargs):
        self.root = kwargs.pop('root', None)
        self.visibleRange = kwargs.pop('visibleRange',(1.0,-1.0))
        self.timerange = kwargs.pop('timerange',(0,10**6))
        self.defaultButtonStyle=kwargs.pop('defaultButtonStyle',None)
        self.defaultSizerFlags=kwargs.pop('defaultSizerFlags',wx.EXPAND)
        
        super(ViewerPanel, self).__init__(*args, **kwargs)

        if self.root is None:
            self.root = self.GetParent().root
                

    def _addButton(self, sizer, bitmaps, evtHandler, Id=-1, tooltip=None,
                   buttonStyle=None, sizerFlags=None):
        """ Helper method to do the nitty gritty part of button adding.
            Used internally.
            
            @param sizer: The sizer to which to add the button.
            @param bitmaps: A 1 or more element tuple/list with the normal
                and (optionally) the disabled button images.
            @param evtHandler: The event handler called by the button.
            @keyword Id: The button's ID.
            @keyword tooltip: The button's hover text.
            @keyword buttonStyle: The style for the button. Defaults to
                `self.defaultButtonStyle`.
            @keyword sizerFlags: The flags to use when adding the button to
                the sizer. Defaults to `self.defaultSizerFlags`. 
        """
        if buttonStyle is None:
            buttonStyle = self.defaultButtonStyle
        if sizerFlags is None:
            sizerFlags = self.defaultSizerFlags
            
        if buttonStyle is not None:
            btn = wx.BitmapButton(self, Id, bitmaps[0].GetBitmap(), 
                                  style=buttonStyle)
        else:
            btn = wx.BitmapButton(self, Id, bitmaps[0].GetBitmap())
            
        if len(bitmaps) < 2 or bitmaps[1] is not None:
            btn.SetBitmapDisabled(bitmaps[1].GetBitmap())
            
        if tooltip is not None:
            btn.SetToolTipString(tooltip)
     
        sizer.Add(btn, 0, sizerFlags)
        self.Bind(wx.EVT_BUTTON, evtHandler, btn)
        
        return btn
        
        
    def _bindScrollEvents(self, parent, scroll, scrollTrack, scrollEnd):
        # http://www.wxpython.org/docs/api/wx.ScrollEvent-class.html
        parent.Bind(wx.EVT_SCROLL, scroll)
        parent.Bind(wx.EVT_SCROLL_TOP, scroll)
        parent.Bind(wx.EVT_SCROLL_BOTTOM, scroll)
        parent.Bind(wx.EVT_SCROLL_LINEUP, scroll)
        parent.Bind(wx.EVT_SCROLL_LINEDOWN, scroll)
        parent.Bind(wx.EVT_SCROLL_PAGEUP, scroll)
        parent.Bind(wx.EVT_SCROLL_PAGEDOWN, scroll)
        parent.Bind(wx.EVT_SCROLL_THUMBTRACK, scrollTrack)
        parent.Bind(wx.EVT_SCROLL_CHANGED, scrollEnd)
#         parent.Bind(wx.EVT_SCROLL_THUMBRELEASE, scroll) # thumb release events


    def setTimeRange(self, start=None, end=None, instigator=None, 
                     tracking=None):
        """ Change the total range start and/or end time. Not applicable to
            all displays but should exist for compatibility's sake.
        """
        pass
    

    def setVisibleRange(self, start=None, end=None, instigator=None,
                        tracking=False, broadcast=False):
        """ Change the visible range start and/or end time. Not applicable to
            all displays but should exist for compatibility's sake.
        """
        pass
    
    #===========================================================================
    # 
    #===========================================================================
    
    def postSetVisibleRangeEvent(self, start, end, tracking=False, 
                                 instigator=False):
        """ Send a change in visible range event to the root window.
        
            @param start: The first time in the visible range.
            @param end: The last time in the visible range. 
            @keyword instigator: The object that initiated the change, in 
                order to avoid an infinite loop of child calling parent 
                calling child. Defaults to `self`.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator is False:
            instigator = self
        wx.PostEvent(self.root, EvtSetVisibleRange(
            start=start, end=end, instigator=instigator, tracking=tracking))


    def postSetTimeRangeEvent(self, start, end, tracking=False, 
                                 instigator=False):
        """ Send a change in the total time range event to the root window.
        
            @param start: The first time in the new range.
            @param end: The last time in the new range. 
            @keyword instigator: The object that initiated the change, in 
                order to avoid an infinite loop of child calling parent 
                calling child. Defaults to `self`.
            @keyword tracking: `True` if the widget doing the update is
                tracking (a/k/a scrubbing), `False` if the update is final.
                Elements that take a long time to draw shouldn't respond
                if `tracking` is `True`.
        """
        if instigator is False:
            instigator = self
        wx.PostEvent(self.root, EvtSetTimeRange(
            start=start, end=end, instigator=instigator, tracking=tracking))
        
    #===========================================================================
    # 
    #===========================================================================

    def OnScroll(self, evt):
        evt.Skip()
        
    def OnScrollTrack(self, evt):
        evt.Skip()
    
    def OnScrollEnd(self, evt):
        evt.Skip()


#===============================================================================
# 
#===============================================================================

class MenuMixin(object):
    """
    """
    def addMenuItem(self, menu, id_, text, helpString, handler=None, 
                    enabled=True, kind=wx.ITEM_NORMAL):
        item = menu.Append(id_, text, helpString, kind)
        item.Enable(enabled)
        if handler is not None:
            self.Bind(wx.EVT_MENU, handler, item)
        if not hasattr(self, 'menuItems'):
            self.menuItems = {}
        self.menuItems[id_] = item
        return item


    def setContextMenu(self, menu):
        """ Set a menu as the the context (e.g. 'right click') popup menu,
            and bind it so it pops up on demand.
            This assumes the object has only one context menu named
            `contextMenu`; bind
        """
        self.contextMenu = menu
        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
        self.contextMenuEnabled = True
        return menu
    
    
    def enableContextMenu(self, enabled=True):
        self.contextMenuEnabled = enabled


    def OnContextMenu(self, evt):
        """ Handler for context menu popup.
        """
        if not self.contextMenuEnabled:
            evt.Skip()
            return
        if isinstance(getattr(self, 'contextMenu', None), wx.Menu):
            self.PopupMenu(self.contextMenu)
    


#===============================================================================
# Custom Events (for multithreaded UI updating)
#===============================================================================

(EvtSetVisibleRange, EVT_SET_VISIBLE_RANGE) = wx.lib.newevent.NewEvent()
(EvtSetTimeRange, EVT_SET_TIME_RANGE) = wx.lib.newevent.NewEvent()
(EvtProgressStart, EVT_PROGRESS_START) = wx.lib.newevent.NewEvent()
(EvtProgressUpdate, EVT_PROGRESS_UPDATE) = wx.lib.newevent.NewEvent()
(EvtProgressEnd, EVT_PROGRESS_END) = wx.lib.newevent.NewEvent()
(EvtInitPlots, EVT_INIT_PLOTS) = wx.lib.newevent.NewEvent()
(EvtImportError, EVT_IMPORT_ERROR) = wx.lib.newevent.NewEvent()


#===============================================================================
# Automatically build list of things for 'from base import *'
#===============================================================================

if __name__ in _sys.modules:
    _moduleDict = _sys.modules[__name__].__dict__
else:
    _moduleDict = globals()

__all__ = filter(lambda x: not(x.startswith("_") or x.startswith('wx')),
                 _moduleDict.keys())

del _moduleDict