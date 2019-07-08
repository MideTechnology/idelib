'''
Created on Jul 13, 2015

@author: dstokes
'''
from __future__ import absolute_import, print_function

import os

from mide_ebml.ebmlite import loadSchema
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
    
    @classmethod
    def isRecorder(cls, dev, strict=True):
        try:
            if cls._isRecorder(dev, strict):
                infoFile = os.path.join(dev, cls.INFO_FILE)
                if os.path.exists(infoFile):
                    devinfo = loadSchema('mide.xml').load(infoFile).dump()
                    props = devinfo['RecordingProperties']['RecorderInfo']
                    return 'Slam Stick C' in props['ProductName']
        except (KeyError, AttributeError, IOError):
            pass
        return False


    def getAccelChannel(self, dc=True):
        """ Retrieve the accelerometer parent channel.
            
            @keyword dc: If `False`, return None.
        """
        if dc is False:
            return None
        return SlamStickX.getAccelChannel(self, dc=True)
    