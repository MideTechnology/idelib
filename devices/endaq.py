'''
Created on Jun 7, 2019

@author: dstokes
'''

from __future__ import absolute_import, print_function

import os
import re
from time import time, sleep

from mide_ebml.ebmlite import loadSchema

from devices.base import DeviceTimeout, os_specific
from devices.ssx import SlamStickX

#===============================================================================
# 
#===============================================================================

commandSchema = loadSchema('command-response.xml')

#===============================================================================
# 
#===============================================================================

class EndaqS(SlamStickX):
    """ An enDAQ S-series recorder from Mide Technology Corporation. 
    """
    FW_UPDATE_FILE = os.path.join(SlamStickX.SYSTEM_PATH, 'update.pkg')
    RESPONSE_FILE = os.path.join(SlamStickX.SYSTEM_PATH, 'RESPONSE')
    
    SN_FORMAT = "S%07d"
        
    # TODO: This really belongs in the configuration UI
    POST_CONFIG_MSG  = ("""When ready...\n"""
                        """    1. Disconnect the recorder\n"""
                        """    2. Mount to surface\n"""
                        """    3. Press the main button """)

    baseName = "enDAQ S-Series Data Recorder"
    manufacturer = u"Mid\xe9 Technology Corp."
    homepage = "http://www.mide.com/products/slamstick/slam-stick-x-vibration-temperature-pressure-data-logger.php"


    def __init__(self, *args, **kwargs):
        """
        """
        super(EndaqS, self).__init__(*args, **kwargs)
        self.responseFile = os.path.join(self.root, self.RESPOPNSE_FILE)


    @classmethod
    def _matchName(cls, name):
        """ Does a given product name match this device type?
        """
        # Part number starts with "S", a 1-2 digit number, and "-"
        return bool(re.match(r'^S(\d|\d\d)-*', name))


    #===========================================================================
    # 
    #===========================================================================
    
    def _readResponseFile(self):
        """
        """
        raw = os_specific.readUncachedFile(self.responseFile)
        
        try:
            data = commandSchema.loads(raw)
            if data[0].name == "ResponseIdx":
                return data
        except (IndexError, TypeError):
            pass
        
        return None
        
    
    def sendCommand(self, cmd, response=True, timeout=10, interval=.25, 
                    cancel=None):
        """
        """
        deadline = time() + timeout
        idx = None
        
        if response:
            data = self._readResponseFile()
            if data is not None:
                idx = data[0].value

        # Write to command file
        with open(self.commandFile, 'wb') as f:
            f.write(cmd)

        if not response:
            return
        
        while time() < deadline:
            if cancel is not None and cancel.isSet():
                return
            
            sleep(interval)
            data = self._readResponseFile()
            if data and data[0].value != idx:
                return data

        raise DeviceTimeout()
