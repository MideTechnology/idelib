'''
Created on Jul 13, 2015

@author: dstokes
'''
import os

# from mide_ebml import util
# import mide_ebml.ebml.schema.mide as schema_mide
from mide_ebml.ebmlite import loadSchema

from ssx import SlamStickX

#===============================================================================
# 
#===============================================================================

mideSchema = loadSchema('mide.xml')

#===============================================================================
# 
#===============================================================================

class SlamStickS(SlamStickX):
    """ A Slam Stick S data recorder from Mide Technology Corporation. 
    """
    
    # TODO: This really belongs in the configuration UI
    POST_CONFIG_MSG  = ("""When ready...\n"""
                        """    1. Disconnect Slam Stick S\n"""
                        """    2. Mount to surface\n"""
                        """    3. Press the "S" button """)

    baseName = "Slam Stick S"
    manufacturer = u"Mid\xe9 Technology Corp."
    homepage = "http://www.mide.com/products/slamstick/slam-stick-x-vibration-temperature-pressure-data-logger.php"
    
    @classmethod
    def isRecorder(cls, dev, strict=True):
        try:
            if cls._isRecorder(dev, strict):
                infoFile = os.path.join(dev, cls.INFO_FILE)
                if os.path.exists(infoFile):
                    devinfo = mideSchema.load(infoFile).dump()
#                     devinfo = util.read_ebml(infoFile, schema=schema_mide)
                    props = devinfo['RecordingProperties']['RecorderInfo']
                    return 'Slam Stick S' in props['ProductName']
        except (KeyError, AttributeError, IOError):
            pass
        return False


    @property
    def serial(self):
        """ The recorder's manufacturer-issued serial number. """
        if self._sn is None:
            self._snInt = self._getInfoAttr('RecorderSerial', None)
            if self._snInt == None:
                self._sn = ""
            else:
                self._sn = "SSS%07d" % self._snInt
        return self._sn

    