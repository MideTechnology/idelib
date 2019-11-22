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
        self.commandSchema = loadSchema('command-response.xml')
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
        """ Helper to retrieve an EBML response from the device's `RESPONSE`
            file. Checks that the data is EBML and that the first child
            element is a `ResponseIdx` (which all responses should contain).
        """
        raw = os_specific.readUncachedFile(self.responseFile)
        
        try:
            data = self.commandSchema.loads(raw)
            if data[0].name == "EBMLResponse":
                if data[0][0].name == "ResponseIdx":
                    return data[0]
        except (AttributeError, IndexError, TypeError):
            pass
        
        return None
        
    
    def sendCommand(self, cmd, response=True, timeout=10, interval=.25, 
                    callback=None):
        """ Send a raw command to the device and (optionally) retrieve the
            response.
            
            @param cmd: The raw EBML representing the command.
            @keyword response: If `True`, wait for and return a response.
            @keyword timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            @keyword interval: Time (in seconds) between checks for a
                response.
            @keyword callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
        """
        now = time()
        deadline = now + timeout
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
        
        while now <= deadline:
            now = time()
            
            if callback is not None and callback() is True:
                return
            
            sleep(interval)
            data = self._readResponseFile()
            if data and data[0].value != idx:
                return data

        raise DeviceTimeout("Timed out waiting for command response")


#===============================================================================
# 
#===============================================================================

class EndaqW(EndaqS):
    """ An enDAQ W-series wireless-enabled recorder from Mide Technology
        Corporation. 
    """
    
    baseName = "enDAQ W-Series Data Recorder"
    manufacturer = u"Mid\xe9 Technology Corp."
    homepage = "http://www.mide.com/products/slamstick/slam-stick-x-vibration-temperature-pressure-data-logger.php"

    @classmethod
    def _matchName(cls, name):
        """ Does a given product name match this device type?
        """
        # Part number starts with "S", a 1-2 digit number, and "-"
        return bool(re.match(r'^W(\d|\d\d)-*', name))


    def scanWifi(self, timeout=10, interval=.25, callback=None):
        """
        """
        cmd = self.commandSchema.encodes({'EBMLCommand': {'WiFiScan': None}})
        try:
            response = self.sendCommand(cmd, True, timeout, interval, callback)
            if response is None:
                return None
            data = response.dump()
            if 'WiFiScanResult' not in data:
                # TODO: Raise exception?
                return None

            aps = []
            for ap in data['WiFiScanResult'].get('AP', []):
                defaults = {'SSID': '', 'RSSI': -1, 'AuthType': 0, 'Known': 0,
                            'Selected': 0}
                defaults.update(ap)
                aps.append(defaults)
                    
        except DeviceTimeout:
            raise DeviceTimeout("WiFi scan timed out")
            