'''
Created on Jun 7, 2019

@author: dstokes
'''

from __future__ import absolute_import, print_function

import os
import re

from mide_ebml.ebmlite import loadSchema

from devices.ssx import SlamStickX

#===============================================================================
# 
#===============================================================================

mideSchema = loadSchema('mide.xml')


#===============================================================================
# 
#===============================================================================

class EndaqS(SlamStickX):
    """ An enDAQ S-series recorder from Mide Technology Corporation. 
    """

    SN_FORMAT = "S%07d"
        
    # TODO: This really belongs in the configuration UI
    POST_CONFIG_MSG  = ("""When ready...\n"""
                        """    1. Disconnect the recorder\n"""
                        """    2. Mount to surface\n"""
                        """    3. Press the main button """)

    baseName = "enDAQ S-Series Data Recorder"
    manufacturer = u"Mid\xe9 Technology Corp."
    homepage = "http://www.mide.com/products/slamstick/slam-stick-x-vibration-temperature-pressure-data-logger.php"
    
    @classmethod
    def isRecorder(cls, dev, strict=True):
        try:
            if cls._isRecorder(dev, strict):
                infoFile = os.path.join(dev, cls.INFO_FILE)
                if os.path.exists(infoFile):
                    devinfo = mideSchema.load(infoFile).dump()
                    props = devinfo['RecordingProperties']['RecorderInfo']
                    pn = props['PartNumber']
                    
                    # Part number starts with "S", a 1-2 digit number, and "-"
                    return bool(re.match(r'^S(\d|\d\d)-*', pn))
                
        except (KeyError, AttributeError, IOError):
            pass
        
        return False

