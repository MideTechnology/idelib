'''
Wrapper for abstracting the app preferences. wxPython has nice support for
things like file history, but it works (best) with their configuration
system.

Created on Nov 26, 2013

@author: dstokes
'''

import wx; wx = wx

class Preferences(object):
    """
    """
    
    def color2str(self, c):
        """
        """
        if isinstance(c, basestring):
            return c
        return str(tuple(c))


    def str2color(self, s):
        """
        """
        if s.startswith("(") and s.strip("1234567890., ()") == '':
            return wx.Colour(*eval(s))
        return s


    def __init__(self, appName="", vendorName=""):
        self.config = wx.Config(appName, vendorName, 
                                style=wx.CONFIG_USE_LOCAL_FILE)

