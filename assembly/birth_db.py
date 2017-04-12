'''
Module assembly.birth_db

An interface for the SlamStick birthing and calibration database.

The first version establishes the API but still uses the old system (a 
collection of files on the shared drive.

High-level representations will be used where possible; recorders will be
represented as instances of `Recorder` subclasses, polynomials as polynomial
objects, etc.

@todo: Possibly add methods and/or properties to `Recorder` subclasses like 
    `setCalibration()` for various read-only attributes. These will raise 
    exceptions if the device is 'real' and/or used outside of the birthing
    process. Maybe a specialized mix-in class, as not to pollute the basic
    representation. 
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2015 Mide Technology Corporation"

import getpass
import os
import sys

#===============================================================================
# 
#===============================================================================

PRODUCT_ROOT_PATH = "R:/LOG-Data_Loggers/LOG-0002_Slam_Stick_X/"

DESIGN_PATH = os.path.join(PRODUCT_ROOT_PATH, "Design_Files/Firmware_and_Software/")
BIRTHER_PATH = os.path.join(DESIGN_PATH, "Manufacturing/LOG-XXXX-SlamStickX_Birther/")
VIEWER_PATH = os.path.join(DESIGN_PATH, "Development/Source/Slam_Stick_Lab/")

FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "firmware")
TEMPLATE_PATH = os.path.join(BIRTHER_PATH, "data_templates")
DB_PATH = os.path.join(PRODUCT_ROOT_PATH, "Product_Database")
CAL_PATH = os.path.join(DB_PATH, '_Calibration')

# The current files. The first iteration of the 'database' will still use
# these, and the real database (using the same API) will be swapped in later.
DEV_SN_FILE = os.path.join(DB_PATH, 'last_sn.txt')
CAL_SN_FILE = os.path.join(DB_PATH, 'last_cal_sn.txt')

BIRTH_LOG_FILE = os.path.join(DB_PATH, "product_log.csv")
CAL_LOG_FILE = os.path.join(DB_PATH, "calibration_log.csv")

DB_LOG_FILE = os.path.join(CAL_PATH, 'SSX_Calibration_Sheet.csv') 
DB_BAD_LOG_FILE = os.path.join(CAL_PATH, 'SSX_Bad_Calibration.csv') 


# Rigmarole to make sure the mide_ebml library can be found.
try:
    CWD = os.path.abspath(os.path.dirname(__file__))
    sys.path.append(CWD)
    sys.path.append(os.path.abspath(os.path.join(CWD, '..')))
    sys.path.append(VIEWER_PATH)
    
    import mide_ebml
except ImportError:
    if os.path.exists('../mide_ebml'):
        sys.path.append(os.path.abspath('..'))
    elif os.path.exists(os.path.join(CWD, '../mide_ebml')):
        sys.path.append(os.path.abspath(os.path.join(CWD, '../mide_ebml')))
    import mide_ebml #@UnusedImport


#===============================================================================
# 
#===============================================================================

class Database(object):
    """ An interface for the SlamStick birthing and calibration database.
    """
    
    def __init__(self, user=None, pw=None):
        """ Constructor.
        
            @keyword user: The database's user name. Defaults to the name of
                the current Windows user.
            @keyword pw: The user's database password.
        """
        self.user = user or getpass.getuser()
        self.pw = pw
        

    def getRecorderById(self, chipId):
        """ Get a recorder by its unique MCU ID.
        
            @param chipId: The recorder's unique MCU ID.
        """
        

    def getRecorder(self, serialNum):
        """ Get a recorder by its serial number.

            @keyword serialNum: The recorder's serial number.
        """
    

    def newRecorder(self, chipId, partNum, hwRev=None, fwRev=None, 
                    serialNum=None, custom=False, size=8, batch=None):
        """ Add a new recorder to the database. 
        
            @param chipId: The recorder's unique MCU ID.
            @param partNum: The recorder's part number (e.g. ``LOG-0002-100g``).
            @keyword hwRev: The recorder's hardware revision. Defaults to the
                latest.
            @keyword fwRev: The recorder's firmware version string. Defaults to
                the latest.
            @keyword serialNum: The recorder's serial number. Defaults to a new
                serial number. An exception is raised if the serial number
                already exists.
            @keyword custom: `True` if the recorder is a custom job.
            @keyword size: The size of the recorder's flash storage.
            @keyword batch: The ID of the recorder's batch (i.e. a shipment
                from the factory).
            @return: An instance of a `Recorder` subclass. 
        """

    
    def saveRecorder(self, recorder):
        """ Update a recorder's entry in the database.
        
            @param recorder: The recorder to save, an instance of a `Recorder`
                subclass.
        """
        

    def newBatch(self, batchId, date, manufacturer):
        """ Create a new batch record.
            
            @param batchId: The batch's ID code.
            @param date: Batch manufacturing date.
            @param manufacturer: The manufacturer of the batch.
        """
    
    
    def getBatch(self, batchId):
        """ Get all recorders from a batch.
            
            @param batchId: The batch's ID code.
        """
    

    #===========================================================================
    # 
    #===========================================================================

    def getCalibration(self, calId):
        """ Get the database's latest calibration information for a given 
            calibration ID.
        
            @param calId: The calibration ID (serial number).
            @return: A list of calibration polynomials.
        """
    
        
    def getRecorderCalibration(self, serialNum):
        """ Get the database's latest calibration information for a given 
            recorder.
        
            @param serialNum: The recorder's serial number.
            @return: A list of calibration polynomials.
        """
    
        
    def addCalibration(self, serialNum, polynomial, calId=None, new=False, 
                       date=None, humidity=None, referenceId=None, user=None):
        """ Save a new calibration polynomial to the database.
        
            @param serialNum: The recorder's serial number.
            @param polynomial: The `UnivariatePolynomial` or 
                `BivariatePolynomial` to add.
            @keyword calId: The calibration ID (serial number). Defaults to the
                latest (since one calibration session contains multiple 
                channels), unless `new` is `True`.
            @keyword new: If `True`, a new calibration ID is generated.
            @keyword date: The calibration date/time. Defaults to present.
            @keyword humidity: 
            @keyword referenceId: 
            @keyword user: The name/ID of the technician who performed the
                calibration. Defaults to the current user.
            @return: The calibration ID.
        """
    
    
    def addTransverse(self, serialNum, channelId, subchannelId1, subchannelId2, 
                      value, calId=None):
        """ Add transverse sensitivity.
        
            @param serialNum: The recorder's serial number.
            @param channelId: The channel calibrated. Transverse can only apply
                to subchannels of the same parent channel.
            @param subchannelId1: The first axis' ID.
            @param subchannelId2: The second axis' ID.
            @param value: The transverse value.
            @keyword calId: The calibration ID. Defaults to the latest.
        """
        
    #===========================================================================
    # 
    #===========================================================================

    
    def findRecorder(self, *args, **kwargs):
        """ Search for recorders. This will probably not get implemented until
            the real database. Actual arguments TBD.
        """

    def findBatch(self, *args, **kwargs):
        """ Search for batches. This will probably not get implemented until
            the real database. Actual arguments TBD.
        """

