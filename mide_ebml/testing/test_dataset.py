import unittest

from mide_ebml.dataset import *

import mide_ebml.parsers as parsers
import mide_ebml.calibration as calibration

class CascadingTestCase(unittest.TestCase):
    """ Test that the Cascading class's methods are working correctly.
        Get this done first because several other classes inherit it.
    """
    def setUp(self):
        self.casc1 = Cascading()
        self.casc1.name = 'parent'
        self.casc2 = Cascading()
        self.casc2.name = 'child'
        self.casc2.parent = self.casc1
        
    def tearDown(self):
        self.casc1 = None
        self.casc2 = None
        
    def testHierarchy(self):
        self.assertTrue(self.casc2.hierarchy() == [self.casc1, self.casc2])
        
    def testPath(self):
        self.assertTrue(self.casc1.path() == 'parent')
        self.assertTrue(self.casc2.path() == 'parent:child')
   
class DatasetTestCase(unittest.TestCase):
    """ test the Dataset class """
    
    def setUp(self):
        """ open a file for testing in a new dataset """
        self.fileStream = open('C:\\Users\\cflanigan\\desktop\\20160503\\SSX70065.IDE', 'rb')
        self.dataset = Dataset(self.fileStream)
    
    def tearDown(self):
        """ close and dispose of the file """
        self.dataset.close()
        self.dataset = None
    
    def testConstructor(self):
        self.assertEquals(self.dataset.lastUtcTime, None)
        self.assertEquals(self.dataset.sessions, [])
        self.assertEquals(self.dataset.sensors, {})
        self.assertEquals(self.dataset._channels, {})
        self.assertEquals(self.dataset.warningRanges, {})
        self.assertEquals(self.dataset.plots, {})
        self.assertEquals(self.dataset.transforms, {})
        self.assertEquals(self.dataset.parent, None)
        self.assertEquals(self.dataset.currentSession, None)
        self.assertEquals(self.dataset.recorderInfo, {})
        self.assertEquals(self.dataset.recorderConfig, None)
        
        self.assertEquals(self.dataset._parsers, None)
        
        self.assertEquals(self.dataset.fileDamaged, False)
        self.assertEquals(self.dataset.loadCancelled, False)
        self.assertEquals(self.dataset.loading, True)
        print(getattr(self.fileStream, "name", None))
        self.assertEquals(self.dataset.filename, getattr(self.fileStream,
                                                         "name", None))
        
        self.assertEquals(self.dataset.subsets, [])
        
        self.assertEquals(self.dataset.name, 'SSX70065')
        self.assertEquals(self.dataset.ebmldoc, loadSchema(SCHEMA_FILE).load(self.fileStream, 'MideDocument'))
        self.assertEquals(self.dataset.schemaVersion, 2)
        
    # TODO: flush this out a bit more
    # test that each channel is being added to the dataset correctly, and that
    # when refering to channel, a dict is returned containing each channel
    def testAddChannel(self):
        channelCheck = {}
        
        channels = DEFAULTS['channels'].copy()
        for chId, chInfo in channels.iteritems():
            chArgs = chInfo.copy()
            subchannels = chArgs.pop('subchannels', None)
            channelCheck[chId] = Channel(self.dataset, chId, **chArgs.copy())
            channel = self.dataset.addChannel(chId, **chArgs)
            self.assertEqual(channel, self.dataset.channels[chId])
            if subchannels is None:
                continue
            for subChId, subChInfo in subchannels.iteritems():
                channel.addSubChannel(subChId, **subChInfo)
        
        self.assertEqual(self.dataset.channels[0].displayName, 
                         channelCheck[0].displayName)
    
    def testAddSession(self):
        """ test that adding sessions properly appends a new session and
            replaces the old currentSession with the new session and that
            lastSession return the most recent session
        """
        session1 = Session(self.dataset, sessionId=0, startTime=1, endTime=2,
                           utcStartTime=0)
        session2 = Session(self.dataset, sessionId=1, startTime=3, endTime=4,
                           utcStartTime=0)
        
        self.dataset.addSession(1, 2)
       
        self.assertEqual(self.dataset.sessions[0], session1)
        self.assertEqual(self.dataset.currentSession, session1)
        
        self.dataset.addSession(3, 4)
        
        self.assertEqual(self.dataset.sessions[1], session2)
        self.assertEqual(self.dataset.currentSession, session2)
        
        self.assertEqual(self.dataset.sessions[1], self.dataset.lastSession)
        
    def testEndSession(self):
        """ test that ending the current session ends the current session """
        self.dataset.addSession(1, 2)
        self.dataset.endSession()
        
        self.assertFalse(self.dataset.currentSession)
        
    def testAddSensor(self):
        sensor1 = Sensor(self.dataset, 0)
        sensor2 = Sensor(self.dataset, 'q')
        
        self.dataset.addSensor(0)
        self.assertEqual(sensor1, self.dataset.sensors[0])
    
        self.dataset.addSensor('q')
        self.assertEqual(sensor2, self.dataset.sensors['q'])
    
    def testAddTransform(self):
        xform1 = Transformable()
        xform1.id = 1
        xform2 = Transformable()
        xform2.id = 'q'
        xform3 = Transformable()
        xform3.id = None
        
        self.dataset.addTransform(xform1)
        self.dataset.addTransform(xform2)
        
        self.assertEqual(self.dataset.transforms[1], xform1)
        self.assertEqual(self.dataset.transforms['q'], xform2)
        
        self.assertRaises(ValueError, self.dataset.addTransform, xform3)
        
    def testAddWarning(self):
        warning1 = WarningRange(self.dataset, warningId=1, channelId=0,
                                subchannelId=0, high=10)
        channels = DEFAULTS['channels'].copy()
        for chId, chInfo in channels.iteritems():
            chArgs = chInfo.copy()
            subchannels = chArgs.pop('subchannels', None)
            channel = self.dataset.addChannel(chId, **chArgs)
            self.assertEqual(channel, self.dataset.channels[chId])
            if subchannels is None:
                continue
            for subChId, subChInfo in subchannels.iteritems():
                channel.addSubChannel(subChId, **subChInfo)
        
        self.dataset.addWarning(1, 0, 0, None, 10)

        self.assertEqual(self.dataset.warningRanges[1], warning1)
    
    def testClose(self):
        """ test if closing a dataset closes the datastream used to read
            its ebml file
        """
        self.dataset.close()
        self.assertTrue(self.dataset.ebmldoc.stream.closed)
        
    def testPath(self):
        self.assertEqual(self.dataset.name, self.dataset.path())
        
    def testGetPlots(self):
        """ test that all the plots are being collected and sorted correctly """
        channels = DEFAULTS['channels'].copy()
        for chId, chInfo in channels.iteritems():
            chArgs = chInfo.copy()
            subchannels = chArgs.pop('subchannels', None)
            channel = self.dataset.addChannel(chId, **chArgs)
            self.assertEqual(channel, self.dataset.channels[chId])
            if subchannels is None:
                continue
            for subChId, subChInfo in subchannels.iteritems():
                channel.addSubChannel(subChId, **subChInfo)
        
        subs = self.dataset._channels[0].subchannels
        subs = subs + self.dataset._channels[1].subchannels
        self.assertEquals(subs, self.dataset.getPlots(sort=False))
        
        subs.sort(key=lambda x: x.displayName)
        print(subs)
        self.assertEquals(subs, self.dataset.getPlots())        
        
        
        """
class TransformableTestCase(unittest.TestCase):
    def setUp(self):
        self.xform1 = Transformable()
        
    def tearDown(self):
        self.xform1 = None
        
    def testSetTransform(self):
        # self.xform1.setTransform(None)
        self.assertTrue(False,'can I put messages here?')
        """


DEFAULTS = {
    "sensors": {
        0x00: {"name": "832M1 Accelerometer"},
        0x01: {"name": "MPL3115 Temperature/Pressure"}
    },
    
    "channels": {
            0x00: {"name": "Accelerometer XYZ",
    #                 "parser": struct.Struct("<HHH"), 
    #                 "transform": 0, #calibration.AccelTransform(),
                    "parser": parsers.AccelerometerParser(),
                    "transform": calibration.AccelTransform(-500,500),
                    "subchannels":{0: {"name": "Accelerometer Z", 
                                       "axisName": "Z",
                                       "units":('Acceleration','g'),
                                       "displayRange": (-100.0,100.0),
                                       "transform": 3,
                                       "warningId": [0],
                                       "sensorId": 0,
                                     },
                                  1: {"name": "Accelerometer Y", 
                                      "axisName": "Y",
                                      "units":('Acceleration','g'),
                                      "displayRange": (-100.0,100.0),
                                      "transform": 2,
                                      "warningId": [0],
                                      "sensorId": 0,
                                      },
                                  2: {"name": "Accelerometer X", 
                                      "axisName": "X",
                                      "units":('Acceleration','g'),
                                      "displayRange": (-100.0,100.0),
                                      "transform": 1,
                                      "warningId": [0],
                                      "sensorId": 0,
                                      },
                                },
                   },
            0x01: {"name": "Pressure/Temperature",
                   "parser": parsers.MPL3115PressureTempParser(),
                   "subchannels": {0: {"name": "Pressure", 
                                       "units":('Pressure','Pa'),
                                       "displayRange": (0.0,120000.0),
                                      "sensorId": 1,
                                       },
                                   1: {"name": "Temperature", 
                                       "units":(u'Temperature',u'\xb0C'),
                                       "displayRange": (-40.0,80.0),
                                      "sensorId": 1,
                                       }
                                   },
                   "cache": True,
                   "singleSample": True,
                   },
    },
    
    "warnings": [{"warningId": 0,
                   "channelId": 1,
                   "subchannelId": 1,
                   "low": -20.0,
                   "high": 60.0
                   }]
}
        