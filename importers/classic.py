'''
Module importers.classic

Created on Feb 23, 2018
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2020 Mide Technology Corporation"

import os.path

import wx

import idelib.classic
from .base import Importer, FileImportError
from threaded_file import ThreadAwareFile

#===============================================================================
# 
#===============================================================================

PLUGIN_INFO = {"type": "importer",
               "name": "Slam Stick Classic Importer",
               }

#===============================================================================
# 
#===============================================================================

class SSClassicImporter(Importer):
    """
    """

    TYPE = "Slam Stick Classic Data File"
    EXT = "*.dat"

    OPENER = idelib.classic.importer.openFile
    READER = idelib.classic.importer.readData


    def importFile(self, filename, root):
        """ Initiate the file import. Opens the file and does initial work.
            Reading the actual data is done by the main application, which
            uses the function specified by ``READER``.
            
            @param filename: The full path and name of the recording to import.
            @param root: The initiating viewer window.
            @return: An instance of the new recording object.
        """
        name = os.path.basename(filename)
        
        try:
            stream = ThreadAwareFile(filename, 'rb')
            newDoc = self.OPENER(stream, quiet=True)
            
            if not newDoc.sessions:
                root.ask("This Classic file contains no data.\n\n"
                         "Slam Stick Classic recorders always contain "
                         "a 'data.dat' file,\n"
                         "regardless whether a recording has been made.", 
                         "Import Error", wx.OK, wx.ICON_ERROR)
                stream.closeAll()
                return None, None
            
        except idelib.parsers.ParsingError as err:
            stream.closeAll()
            raise FileImportError("The file '%s' could not be opened" % name,
                                  exception=err)

        return newDoc, self.READER


#===============================================================================
# 
#===============================================================================

def init(*args, **kwargs):
    """ Plug-in initialization function, called when the plug-in is loaded.
        Returns the class that actually does the importing. Calling the plugin
        will instantiate it.
    """
    return SSClassicImporter
    