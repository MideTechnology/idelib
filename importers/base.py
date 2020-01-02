'''
Module importers.base

Created on Feb 14, 2018
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2020 Mide Technology Corporation"

import os

import wx

from logger import logger
import mide_ebml
from threaded_file import ThreadAwareFile

#===============================================================================
# 
#===============================================================================

class FileImportError(IOError):
    """ Exception raised when an import fails.
    """
    def __init__(self, message, exception=None):
        IOError.__init__(self, getattr(exception, 'errno', None), message)
        self.exception = exception
        

#===============================================================================
# 
#===============================================================================

class Importer(object):
    """ Base class for plug-in importers.
    
        @cvar TYPE: The description of the file type (shown in the types list
            in an Open File dialog)
        @cvar EXT: The file extension, as used in an Open File dialog's
            "wildcard" list. Can be more than one, semicolon-delimited.
        @cvar OPENER: The method/function used to open a file. It should return
            a `Dataset` subclass. 
        @cvar READER: The method/function used to read  the contents of a 
            file, which will run asynchronously after the file has been opened.
            It may be `None` if the `OPENER` does the entire import.
    """
    
    TYPE = "MIDE Data File"
    EXT = "*.ide"

    OPENER = mide_ebml.importer.openFile
    READER = mide_ebml.importer.readData
    
    
    def __init__(self):
        self.app = wx.GetApp()
        
    
    @classmethod
    def getType(cls):
        """
        """
        return u"%s (%s)|%s" % (cls.TYPE, cls.EXT, cls.EXT)
    
    
    def importFile(self, filename, root):
        """ Initiate the file import. Opens the file and does initial work.
            Reading the actual data is done by the main application, which
            uses the function specified by ``READER``. Any special handling
            (import options, etc.) should be done in this method.
            
            @param filename: The full path and name of the recording to import.
            @param root: The initiating viewer window.
            @return: An instance of the new recording object, and the 
                function/method used to read its contents.
        """
        name = os.path.basename(filename)
        
        try:
            stream = ThreadAwareFile(filename, 'rb')
            newDoc = self.OPENER(stream, quiet=True)
            
            # SSX: Check EBML schema version
            if newDoc.schemaVersion is not None and newDoc.schemaVersion < newDoc.ebmldoc.version:
                q = root.ask("The data file was created using a newer version "
                             "of the MIDE data schema."
                             "\n\nLab's version is %s, file's version is %s; "
                             "this could potentially cause problems."
                             "\n\nOpen anyway?" % (newDoc.schemaVersion, 
                                                   newDoc.ebmldoc.version), 
                             "Schema Version Mismatch", 
                             wx.YES|wx.CANCEL, wx.ICON_WARNING,
                             pref="schemaVersionMismatch")
                if q == wx.ID_NO:
                    stream.closeAll()
                    return None, None
                
        except mide_ebml.parsers.ParsingError as err:
            stream.closeAll()
            raise FileImportError("The file '%s' could not be opened" % name,
                                  exception=err)

        # Import external calibration file, if it has the same name as the
        # recording file.
        # This might have to go before the loader is started.
        calfile = os.path.splitext(filename)[0] + '.cal'
        if os.path.exists(calfile):
            q = root.ask("Import matching calibration file?\n\n"
                         "This recording has a corresponding calibration file "
                         "(%s). Do you want to import calibration data from "
                         "this file, overriding the recording's calibration "
                         "data?" % os.path.basename(calfile),
                         title="Import Calibration Data?", pref="autoImportCal")
            if q == wx.ID_YES:
                logger.info("Importing external calibration file.")
                root.importCalibration(calfile)
            else:
                logger.info("Not importing external calibration file.")
        
        return newDoc, self.READER

        