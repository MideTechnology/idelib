'''
Created on Jul 13, 2015

@author: dstokes
'''
from __future__ import absolute_import, print_function

from .ssx import SlamStickX


#===============================================================================
# 
#===============================================================================

class SlamStickS(SlamStickX):
    """ A Slam Stick S data recorder from Mide Technology Corporation. 
    """
    SN_FORMAT = "SSS%07d"
    
    # TODO: This really belongs in the configuration UI
    POST_CONFIG_MSG  = ("""When ready...\n"""
                        """    1. Disconnect Slam Stick S\n"""
                        """    2. Mount to surface\n"""
                        """    3. Press the "S" button """)

    baseName = "Slam Stick S"
    manufacturer = u"Mid\xe9 Technology Corp."
    homepage = "http://www.mide.com/products/slamstick/slam-stick-x-vibration-temperature-pressure-data-logger.php"

