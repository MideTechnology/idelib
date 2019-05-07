'''
Base classes, mixin classes, custom events, utility functions and other 
(non-stand-alone) stuff used by multiple components of the viewer. 

Created on Dec 4, 2013

@author: dstokes
'''

__all__ = ('ViewerPanel', 'MenuMixin')

import wx

from events import EvtSetTimeRange, EvtSetVisibleRange

#===============================================================================
# 
#===============================================================================

class ViewerPanel(wx.Panel):
    """ Base class for Viewer component panels. Contains common utility
        methods; also does some viewer-specific initialization.
    """
    
    def __init__(self, *args, **kwargs):
        """ Constructor. Takes the standard `wx.Panel` arguments, plus:
        
            @keyword root: The Viewer root window.
            @keyword visibleRange: The currently displayed time interval
            @keyword timerange: The complete time interval
            @keyword defaultButtonStyle: A default style for buttons added with
                `ViewerPanel._addButton()`
            @keyword defaultSizerFlags: A default set of sizer flags for
                automatically-added controls
        """
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
            @keyword Id: The button's ID. If an ID is provided, the button
                event handler is bound to the ID rather than the button widget.
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
        if Id == -1:
            # Bind specifically to the button widget
            self.Bind(wx.EVT_BUTTON, evtHandler, btn)
        else:
            # Bind to the given ID
            self.Bind(wx.EVT_BUTTON, evtHandler, id=Id)
        
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
    # Event-posting methods
    #===========================================================================

    def postCommandEvent(self, target, evtType, Id=-1):
        """ Post a Command Event to a specific target.
            @param target: The target for the event posting.
            @param evtType: The type of the event, e.g. `wx.EVT_BUTTON`. *Not*
                an event `typeId`!
            @keyword Id: The event ID (e.g. the button ID for a `wx.EVT_BUTTON`) 
        """
        newEvt = wx.CommandEvent(evtType.typeId, Id)
        newEvt.SetEventObject(self)
        wx.PostEvent(target, newEvt)
        

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
    # Default scrolling methods. Override these.
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
    """ A mix-in class that adds menu-related functionality.
    
        @ivar contextMenu: The object's context menu, if any.
    """
    
    def addMenuItem(self, menu, id_, text=u'', helpString=u'', handler=None, 
                    enabled=True, kind=wx.ITEM_NORMAL, checked=False):
        """ Helper method for doing the grunt work involved in adding a menu
            item to a menu.
            
            @param menu: The menu to which to add the menu item.
            @param id_: The menu item's ID (e.g. `wx.OPEN`, `wx.CLOSE`, etc.)
            @param text: The menu item text.
            @param helpString: Help text for the menu item.
            @keyword handler: A method for handling `wx.EVT_MENU` events.
            @keyword enabled: The initial enabled state of the menu item.
            @keyword kind: WX flags for the menu item type (e.g.
                `wx.ITEM_NORMAL`, `wx.ITEM_CHECK`, etc).
            @keyword checked: If `True`, the menu item will be checked by
                default. Only applicable to `wx.ITEM_CHECK` items; radio buttons
                need to be set separately.
            @return: The new menu item.
        """
        if id_ == -1:
            id_ = wx.NewId()
        item = menu.Append(id_, text, helpString, kind)
        item.Enable(enabled)
        if kind == wx.ITEM_CHECK:
            item.Check(checked)
        if handler is not None:
            self.Bind(wx.EVT_MENU, handler, item)
        return item

    def addMenu(self, menubar, text):
        """ Create a submenu in a given menu bar.
            
            @param menu: The menu bar to which to add the submenu.
            @param text: The menu item text.
            @return: The new submenu.
        """
        menu = wx.Menu()
        menubar.Append(menu, text)
        return menu


    def addSubMenu(self, menu, id_, text, enabled=True):
        """ Helper method for doing the grunt work involved in adding a submenu.
            
            @param menu: The menu to which to add the menu item.
            @param id_: The submenu's ID (or -1)
            @param text: The submenu's text.
            @keyword enabled: The initial enabled state of the submenu.
        """
        if id_ == -1:
            id_ = wx.NewId()
        subM = wx.Menu()
        menu.AppendMenu(id_, text, subM)
        menu.Enable(id_, enabled)
        return subM

    
    def setMenuItem(self, menu, itemId, checked=None, enabled=None, label=None):
        """ Helper method to set various properties of a MenuItem. 
        """
        if not isinstance(menu, (wx.Menu, wx.MenuBar)):
            return
        mi = menu.FindItemById(itemId)
        if mi:
            if checked is not None:
                mi.Check(checked)
            if enabled is not None:
                mi.Enable(enabled)
            if label is not None:
                mi.SetItemLabel(label)
                
                
    def getAllMenuItems(self, menu, _items=None):
        """ Recursively collect all menu items from a menu or submenu.
        """
        _items = list() if _items is None else _items
        if isinstance(menu, wx.MenuItem):
            _items.append(menu)
        if isinstance(menu,wx.MenuBar):
            children = [x[0] for x in menu.GetMenus()]
        elif isinstance(menu, wx.Menu):
            children = menu.GetMenuItems()
        elif isinstance(menu, wx.MenuItemList):
            children = menu
        else:
            c = menu.GetSubMenu()
            if c is None:
                return _items
            children = c.GetMenuItems()
        
        for c in children:
            self.getAllMenuItems(c, _items)
        return _items
        

    def enableMenuItems(self, menu, items=None, enable=True, excluded=None):
        """ Recursively crawl a set of nested menus and enable or disable them.
        
            @param menu: 
            @keyword items: A list of menu item IDs, or `None` for all items.
            @keyword enable: `True` to enable, `False` to disable items.
            @keyword excluded: If `True` or `False` and `items` is not
                `None`, enable or disable all items not in the `items` list.
                Items not in the list are left as-is if `None`.
        """
        allItems = self.getAllMenuItems(menu)
        if items is None:
            for mi in allItems:
                mi.Enable(enable)
        else:
            for mi in self.getAllMenuItems(menu):
                if mi.GetId() in items:
                    mi.Enable(enable)
                elif excluded is not None:
                    mi.Enable(excluded)
    

    def setContextMenu(self, menu):
        """ Set a menu as the the context (e.g. 'right click') popup menu,
            and bind it so it pops up on demand. This assumes the object has 
            only one context menu named `contextMenu`; bind any other context 
            menus manually.
        """
        self.contextMenu = menu
        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
        self.contextMenuEnabled = True
        return menu
    
    
    def enableContextMenu(self, enabled=True):
        """ Enable (or disable) the context menu. """
        self.contextMenuEnabled = enabled


    def OnContextMenu(self, evt):
        """ Event handler for context menu popup.
        """
        if not self.contextMenuEnabled:
            evt.Skip()
            return
        if isinstance(getattr(self, 'contextMenu', None), wx.Menu):
            self.PopupMenu(self.contextMenu)
    

