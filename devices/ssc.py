'''
Created on Jul 13, 2015

@author: dstokes
'''
import os

from mide_ebml import util
import mide_ebml.ebml.schema.mide as schema_mide

from ssx import SlamStickX

class SlamStickC(SlamStickX):
    """ A Slam Stick C data recorder from Mide Technology Corporation. 
    """
    
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
                    devinfo = util.read_ebml(infoFile, schema=schema_mide)
                    props = devinfo['RecordingProperties']['RecorderInfo']
                    return 'Slam Stick C' in props['ProductName']
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
                self._sn = "SSC%07d" % self._snInt
        return self._sn


    def getAccelChannel(self, dc=True):
        """ Retrieve the accelerometer parent channel.
            
            @keyword dc: If `False`, return None.
        """
        if dc is False:
            return None
        return SlamStickX.getAccelChannel(self, dc=True)
    