'''
Created on Oct 18, 2019

@author: dstokes
'''

import wx


#===============================================================================
# 
#===============================================================================

class SplashPage(wx.Panel):
    """
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        self.root = kwargs.pop('root', None)
        super(SplashPage, self).__init__(*args, **kwargs)
        
        