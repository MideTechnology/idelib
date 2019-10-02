'''
Created on Jul 13, 2015

@author: dstokes
'''
from __future__ import absolute_import, print_function

from .ssx import SlamStickX


#===============================================================================
# 
#===============================================================================

class SlamStickC(SlamStickX):
    """ A Slam Stick C data recorder from Mide Technology Corporation. 
    """
    
    SN_FORMAT = "SSC%07d"
    
    # TODO: This really belongs in the configuration UI
    POST_CONFIG_MSG  = ("""When ready...\n"""
                        """    1. Disconnect Slam Stick C\n"""
                        """    2. Mount to surface\n"""
                        """    3. Press the "C" button """)

    baseName = "Slam Stick C"
    manufacturer = u"Mid\xe9 Technology Corp."
    homepage = "http://www.mide.com/products/slamstick/slam-stick-x-vibration-temperature-pressure-data-logger.php"

    def getAccelChannel(self, dc=True):
        """ Retrieve the accelerometer parent channel.
            
            @keyword dc: If `False`, return None.
        """
        if dc is False:
            return None
        return SlamStickX.getAccelChannel(self, dc=True)
    