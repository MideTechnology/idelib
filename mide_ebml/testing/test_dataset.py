import unittest

from mide_ebml.dataset import *

import mide_ebml.parsers as parsers
import mide_ebml.calibration as calibration

class GenericObject(object):
    """ Provide a generic object to pass as an argument.
        It's basically mocking up an object.
    """
    def __init__(self):
        self.isUpdated = False
        self.id = None
        self.transform = None
        self.sessions = []
        
    def updateTransforms(self):
        self.isUpdated = True
        
    def parseWith(self, x, start, end, step, subchannel):
        return (x, start, end, step, subchannel)

    def parseByIndexWith(self, parser, indices, subchannel):
        return (parser, indices, subchannel)

class CascadingTestCase(unittest.TestCase):
    """ Test case for methods in the Cascading class. """
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
   
class TransformableTestCase(unittest.TestCase):
    """ Test case for methods in the Transformable class. """
    def setUp(self):
        
        # create objects to be used during testing
        self.xform1 = Transformable()
        self.genericObject = GenericObject()
        
        # configure above objects
        fileStream = open(
            '.\\SSX70065.IDE', 'rb')
        self.xform1.dataset = Dataset(fileStream)
        self.xform1.dataset.transforms = {1: "123", 2: "456"}
        self.xform1.children = [self.genericObject]
        
    def tearDown(self):
        self.xform1.dataset.close()
        self.xform1 = None
        
    def testSetTransform(self):
        """ Test the setTransform method without updating. """
        self.xform1.setTransform(1, False)
        self.assertEqual(self.xform1.transformId, 1)
        self.assertEqual(self.xform1._transform, 1)
        
        self.genericObject.id = "12345"
        self.xform1.setTransform(self.genericObject, False)
        self.assertEqual(self.xform1.transformId, "12345")
        self.assertEqual(self.xform1._transform, self.genericObject)
        
        self.xform1.setTransform(None, False)
        self.assertEqual(self.xform1._transform, Transform.null)
        
    def testUpdateTransforms(self):
        """ Test the updateTransforms and _updateXformIds methods by calling
            setTransform with updating.
        """        
        self.xform1.setTransform(1)
        self.assertEqual(self.xform1.transform, "123")
        self.assertTrue(self.genericObject.isUpdated)
        
        self.genericObject.isUpdated = False
        aPlaceholderTransform = Transform()
        aPlaceholderTransform.id = 2
        self.xform1.setTransform(aPlaceholderTransform)
        self.assertEqual(self.xform1.transform, "456")
        self.assertTrue(self.genericObject.isUpdated)
        
    def testGetTransforms(self):
        """ Test that the list of tansforms is being returned properly """
        # TODO: check that this is getting returned properly,
        # I feel like I might be missing something.
        self.xform1.setTransform(1, False)
        self.assertEqual(self.xform1.getTransforms(), [1])
        self.assertEqual(self.xform1.getTransforms(_tlist=[0]), [1, 0])
        
        parentXform = Transformable()
        parentXform.id = 5
        parentXform.children = [self.xform1]
        parentXform.setTransform(self.xform1, False)
        self.xform1.id = 3
        self.xform1.parent = parentXform
        
        self.assertEqual(parentXform.getTransforms(), [self.xform1])


class DatasetTestCase(unittest.TestCase):
    """ Test case for methods in the Dataset class. """
    
    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.fileStream = open(
            '.\\SSX70065.IDE', 'rb')
        self.dataset = Dataset(self.fileStream)
    
    def tearDown(self):
        """ Close and dispose of the file. """
        self.dataset.close()
        self.dataset = None
    
    def testConstructor(self):
        """ Exhaustively check that all the members that get initialized in the
            constructor are being initialized to the correct value.
        """
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
        self.assertEquals(self.dataset.filename, getattr(self.fileStream,
                                                         "name", None))
        
        self.assertEquals(self.dataset.subsets, [])
        
        self.assertEquals(self.dataset.name, 'SSX70065')
        self.assertEquals(
            self.dataset.ebmldoc, loadSchema(SCHEMA_FILE).load(
                self.fileStream, 'MideDocument'))
        self.assertEquals(self.dataset.schemaVersion, 2)
        
    # TODO: flush this out a bit more
    def testAddChannel(self):
        """ Test that each channel is being added to the dataset correctly, and
            that when refering to channel, a dict is returned containing each 
            channel.
        """
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
        """ Test that adding sessions properly appends a new session and
            replaces the old currentSession with the new session and that
            lastSession return the most recent session.
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
        """ Test that ending the current session ends the current session. """
        self.dataset.addSession(1, 2)
        self.dataset.endSession()
        
        self.assertFalse(self.dataset.currentSession)
        
    def testAddSensor(self):
        """ Test that the sensors are being added correctly. """
        sensor1 = Sensor(self.dataset, 0)
        sensor2 = Sensor(self.dataset, 'q')
        
        self.dataset.addSensor(0)
        self.assertEqual(sensor1, self.dataset.sensors[0])
    
        self.dataset.addSensor('q')
        self.assertEqual(sensor2, self.dataset.sensors['q'])
    
    def testAddTransform(self):
        """ Test that transforms are being added correctly.
            Using Transformables to test this because they're a simple object
            that already has an ID to use.
        """
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
        """ Test that adding warnings is successfully adding warnings. """
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
        """ Test if closing a dataset closes the datastream used to read
            its ebml file.
        """
        self.dataset.close()
        self.assertTrue(self.dataset.ebmldoc.stream.closed)
        
    def testPath(self):
        self.assertEqual(self.dataset.name, self.dataset.path())
        
    def testGetPlots(self):
        """ Test that all the plots are being collected and sorted correctly. """
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
        self.assertEquals(subs, self.dataset.getPlots())                


class SessionTestCase(unittest.TestCase):
    """ Test case for methods in the Session class. """
    
    def testInitAndEQ(self):
        fileStream = open(
            '.\\SSX70065.IDE', 'rb')
        dataset = Dataset(fileStream)
        session1 = Session(dataset, 1, 2, 3, 4)
        session2 = Session(dataset, 1, 2, 3, 4)
        self.assertEqual(session1, session2)
    
    
class SensorTestCase(unittest.TestCase):
    """ Test case for methods in the Sensor class. """
    
    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.fileStream = open(
            '.\\SSX70065.IDE', 'rb')
        self.dataset = Dataset(self.fileStream)
        
        self.sensor1 = Sensor(self.dataset, 1)
        self.sensor2 = Sensor(self.dataset, 2, "3", 4, 5, 6, 7)
    
    def tearDown(self):
        """ Close and dispose of the file. """
        self.dataset.close()
        self.dataset = None
        self.sensor1 = None
        self.sensor2 = None
    
    def testInitAndEQ(self):
        """ Test __init__ and __eq__ in Sensor. """
        self.assertNotEqual(self.sensor1, self.sensor2) 
        self.assertEqual(self.sensor1, Sensor(self.dataset, 1))
        
        sensor3 = Sensor(self.dataset, 3, name=None)
        self.assertEqual(sensor3.name, "Sensor%02d")
        
    def testChildren(self):
        """ Test the children property. """
        self.sensor1.channels = {1: "1"}
        self.assertEqual(self.sensor1.children, ["1"])
        self.assertEqual(self.sensor2.children, [])
    
    def testBandwidthCutoff(self):
        """ Test the bandwidthCutoff property. """
        self.sensor1._bandwidthCutoff = 5
        self.assertEqual(self.sensor1.bandwidthCutoff, 5)
        
        self.sensor2.dataset.bandwidthLimits = [0,1,2,3,4,5,6,
                                                {"LowerCutoff":1,
                                                 "UpperCutoff":2}]
        self.assertEqual(self.sensor2.bandwidthCutoff, (1, 2))
    
    def testBandwidthRolloff(self):
        """ Test the bandwidthRolloff property. """
        self.sensor1._bandwidthRolloff = 5
        self.assertEqual(self.sensor1.bandwidthRolloff, 5)
        
        self.sensor2.dataset.bandwidthLimits = [0,1,2,3,4,5,6,
                                                {"LowerRolloff":1,
                                                 "UpperRolloff":2}]
        # self.assertEqual(self.sensor2.bandwidthRolloff, (1, 2))
        # TODO make sure that the bandwidthRolloff vs. cutoff thing gets followed up

class ChannelTestCase(unittest.TestCase):
    """ Test case for methods in the Channel class. """
    
    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.fileStream = open(
            '.\\SSX70065.IDE', 'rb')
        self.dataset = Dataset(self.fileStream)
        self.dataset.addSensor(0)
        
        self.fakeParser = GenericObject()
        self.fakeParser.types = [0]
        self.fakeParser.format = []
        
        self.channel1 = Channel(
            self.dataset, channelId=0, name="channel1", parser=self.fakeParser,
            displayRange=[0])
        self.channel2 = Channel(
            self.dataset, channelId=2, parser=self.fakeParser, sensor=0, name=5,
            units=6, transform=7, displayRange=[8], sampleRate=9, cache=10, 
            singleSample=11, attributes=12)
    
    def tearDown(self):
        """ Close and dispose of the file. """
        self.dataset.close()
        self.dataset = None
        self.channel1 = None
        self.channel2 = None
        self.fileStream.close()
        self.fileStream = None
        self.fakeParser = None
        
    def testInit(self):
        """ Exhaustively test parameters for __init__ """
        self.assertNotEqual(self.channel1, self.channel2)
        
        self.assertEqual(self.channel1.id, 0)
        self.assertEqual(self.channel1.sensor, None)
        self.assertEqual(self.channel1.parser, self.fakeParser)
        self.assertEqual(self.channel1.units, ('',''))
        self.assertEqual(self.channel1.parent, None)
        self.assertEqual(self.channel1.dataset, self.dataset)
        self.assertEqual(self.channel1.sampleRate, None)
        self.assertEqual(self.channel1.attributes, None)
        self.assertFalse(self.channel1.cache)
        self.assertEqual(self.channel1.singleSample, None)
        self.assertEqual(self.channel1.name, "channel1")
        self.assertEqual(self.channel1.displayName, "channel1")
        self.assertEqual(self.channel1.types, [0])
        self.assertEqual(self.channel1.displayRange,[0])
        self.assertTrue(self.channel1.hasDisplayRange)
        self.assertEqual(self.channel1.subchannels,[None])
        self.assertEqual(self.channel1.sessions, {})
        self.assertEqual(self.channel1.subsampleCount, [0,sys.maxint])
        self.assertEqual(self.channel1._lastParsed, (None, None))
        self.assertTrue(self.channel1.allowMeanRemoval)
        
        self.assertEqual(self.channel2.id, 2)
        self.assertEqual(self.channel2.sensor, 0)
        self.assertEqual(self.channel2.parser, self.fakeParser)
        self.assertEqual(self.channel2.units, 6)
        self.assertEqual(self.channel2.parent, 0)
        self.assertEqual(self.channel2.dataset, self.dataset)
        self.assertEqual(self.channel2.sampleRate, 9)
        self.assertEqual(self.channel2.attributes, 12)
        self.assertTrue(self.channel2.cache)
        self.assertEqual(self.channel2.singleSample, 11)
        self.assertEqual(self.channel2.name, 5)
        self.assertEqual(self.channel2.displayName, 5)
        self.assertEqual(self.channel2.types, [0])
        self.assertEqual(self.channel2.displayRange,[8])
        self.assertTrue(self.channel2.hasDisplayRange)
        self.assertEqual(self.channel2.subchannels,[None])
        self.assertEqual(self.channel2.sessions, {})
        self.assertEqual(self.channel2.subsampleCount, [0,sys.maxint])
        self.assertEqual(self.channel2._lastParsed, (None, None))
        self.assertTrue(self.channel2.allowMeanRemoval)
        
    def testChildren(self):
        """ Test the children property. """
        self.assertEqual(self.channel1.children, list(iter(self.channel1)))
        
    def testLen(self):
        """ Test the len override. """
        self.assertEqual(len(self.channel1),len(self.channel1.subchannels))
        
    def testAddSubChannel(self):
        """ Test the addSubChannel method. """
        self.assertRaises(TypeError, self.channel1.addSubChannel, None)
        self.assertRaises(IndexError, self.channel1.addSubChannel, 5)
        self.assertEqual(self.channel1.addSubChannel(subchannelId=0),
                         SubChannel(self.channel1, 0))
        
    def testGetSubChannel(self):
        """ Test the getSubChannel method. """
        self.assertEqual(self.channel1.getSubChannel(0), 
                         SubChannel(self.channel1, 0))
        self.assertEqual(self.channel1.getSubChannel(0).singleSample, 
                         self.channel1.singleSample)
        
    def testGetSession(self):
        """ Test the getSession method. """
        self.dataset.addSession(0, 1, 2) 
        eventList = EventList(self.channel1, self.dataset.lastSession)
        self.assertEqual(self.channel1.getSession(), eventList)
        self.assertEqual(self.channel1.getSession(),
                         self.channel1.getSession(0))
        self.assertRaises(KeyError, self.channel1.getSession, 5)
        
    def testParseBlock(self):
        """ Test the parseBlock method. """
        fakeBlock = GenericObject()
        self.assertEqual(self.channel1.parseBlock(fakeBlock),
                         [self.channel1.parser, 0, -1, 1, None])
        self.assertEqual(self.channel1._lastParsed[0],
                         (fakeBlock, 0, -1, 1, None))
        self.assertEqual(self.channel1._lastParsed[1],
                         [self.channel1.parser, 0, -1, 1, None])
        
    def testParseBlockByIndex(self):
        """ Test the parseBlockByIndex method. """
        fakeBlock = GenericObject()
        self.assertEqual(self.channel1.parseBlockByIndex(fakeBlock, 1), 
                         [self.channel1.parser, 1, None])
        
    def testUpdateTransforms(self):
        """ Test the updateTransforms method in this and the parent class. """
        self.dataset.addSession(0, 1, 2)
        eventList = EventList(self.channel1, self.dataset.lastSession)
        self.assertEqual(self.channel1.getSession(), eventList)
        self.assertEqual(self.channel1.getSession(),
                         self.channel1.getSession(0))
        
        genericObject = GenericObject()
        genericObject.isUpdated = False
        
        aPlaceholderTransform = Transform()
        aPlaceholderTransform.id = 2
        
        self.channel1.dataset.transforms = {1: "123", 2: aPlaceholderTransform}
        self.channel1.subchannels = [genericObject]

        self.channel1.updateTransforms()
        self.assertTrue(genericObject.isUpdated)
        
class SubChannelTestCase(unittest.TestCase):
    """ Test case for methods in the Channel class. """
    
    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.fileStream = open(
            '.\\SSX70065.IDE', 'rb')
        self.dataset = Dataset(self.fileStream)
        self.dataset.addSensor(0)
        
        self.fakeParser = GenericObject()
        self.fakeParser.types = [0]
        self.fakeParser.format = []
        
        self.sensor1 = Sensor(self.dataset, 2, "3", 4, 5, 6, 7)
        
        self.channel1 = Channel(
            self.dataset, channelId=0, name="channel1", parser=self.fakeParser,
            displayRange=[0])
        self.channel2 = Channel(
            self.dataset, channelId=2, parser=self.fakeParser, 
            sensor=self.sensor1, name="channel2", units=6,
            displayRange=[8], sampleRate=9, cache=10, singleSample=11,
            attributes=12)
        
        self.subChannel1 = SubChannel(self.channel2, 0, name=None, 
                                      units=('a','b'), transform=3, 
                                      displayRange=[4], sensorId=5, warningId=6, 
                                      axisName=7, attributes=8)
    
    def tearDown(self):
        """ Close and dispose of the file. """
        self.dataset.close()
        self.dataset = None
        self.channel1 = None
        self.channel2 = None
        self.fileStream.close()
        self.fileStream = None
        self.fakeParser = None
    
    def testInit(self):
        """ Test the constructor for SubChannel. """
        self.assertEqual(self.subChannel1.id, 0)
        self.assertEqual(self.subChannel1.parent, self.channel2)
        self.assertEqual(self.subChannel1.warningId, 6)
        self.assertEqual(self.subChannel1.cache, self.channel2.cache)
        self.assertEqual(self.subChannel1.dataset, self.dataset)
        self.assertEqual(self.subChannel1.axisName, 7)
        self.assertEqual(self.subChannel1.attributes, 8)
        self.assertEqual(self.subChannel1.name, "channel2:00")
        self.assertEqual(self.subChannel1.units, ('a','b'))
        self.assertEqual(self.subChannel1.displayName, 'a')
        self.assertEqual(self.subChannel1.sensor, self.channel1.sensor)
        self.assertEqual(self.subChannel1.types, (self.channel1.types[0], ))
        self.assertEqual(self.subChannel1.displayRange, [4])
        self.assertTrue(self.subChannel1.hasDisplayRange)
        self.assertEqual(self.subChannel1.allowMeanRemoval, 
                         self.channel2.allowMeanRemoval)
        self.assertFalse(self.subChannel1.removeMean)
        self.assertEqual(self.subChannel1.singleSample, 
                         self.channel2.singleSample)
        
    def testChildren(self):
        """ Test the children property. """
        self.assertEqual(self.subChannel1.children, [])
        
    def testSampleRate(self):
        """ Test the sampleRate property. """
        self.assertEqual(self.subChannel1.sampleRate, self.channel2.sampleRate)
        
    def testParser(self):
        """ Test the parser property. """
        self.assertEqual(self.subChannel1.parser, self.channel2.parser)
        
    def testSessions(self):
        """ Test the sessions property. """
        self.assertEqual(self.subChannel1.sessions,{})
        
    def testParseBlock(self):
        """ Test the parseBlock method.
            Run the same test as for Channel.
        """
        fakeBlock = GenericObject()
        self.assertEqual(self.channel2.parseBlock(fakeBlock),
                         self.subChannel1.parseBlock(fakeBlock))
        
    def testParseBlockByIndex(self):
        """ Test the parseBlockByIndex method.
            Run the same test as for Channel.
        """
        fakeBlock = GenericObject()
        self.assertEqual(self.channel2.parseBlockByIndex(fakeBlock, 1),
                         self.subChannel1.parseBlockByIndex(fakeBlock, 1))
        
    def testGetSession(self):
        """ Test the getSession method. """
        self.subChannel1.dataset.addSession(0, 1, 2)
        self.channel2.subchannels = [GenericObject()]
        self.subChannel1.subchannels = [GenericObject()]
        eventList = EventList(self.channel2, session=self.dataset.lastSession)
        self.assertEqual(self.subChannel1.getSession(0),eventList)
        
    
    
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
        