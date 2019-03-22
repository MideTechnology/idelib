"""
Basic IDE library unit tests.

@todo: Remove `Cascading` and `Transformable` unit tests? Those base/mix-in 
    classes were intended to be used internally, and may be factored out
    eventually.
@todo: Remove references to deprecated `parsers.AccelerometerParser` and
    `calibration.AccelTransform`. These classes may be refactored out in the
    future.
"""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from StringIO import StringIO
import sys
import unittest
import mock

from mide_ebml.dataset import *
from mide_ebml.dataset import EventArray  # TODO why won't my tests run w/o this? T-T

from mide_ebml.calibration import Transform, CombinedPoly, PolyPoly
from mide_ebml.calibration import AccelTransform
from mide_ebml import importer
from mide_ebml import parsers

import numpy as np


#===============================================================================
# 
#===============================================================================

class GenericObject(object):
    """ Provide a generic object to pass as an argument in order to mock 
        arbitrary objects.
    """
    def __init__(self):
        self.isUpdated = False
        self.id = None
        self.transform = None
        self.sessions = []
        self.data = []
        self.indexRange = [3]
        self.startTime = 0
        self.sampleTime = 0
        self.numSamples = 1
        
        
    def __getitem__(self, index):
        return self.data[index]
    
    
    def __len__(self):
        return len(self.data)
        
        
    def updateTransforms(self):
        self.isUpdated = True
        
        
    def parseWith(self, x, start, end, step, subchannel):
        return (x, start, end, step, subchannel)


    def parseByIndexWith(self, parser, indices, subchannel):
        return (parser, indices, subchannel)


#===============================================================================
# 
#===============================================================================

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
        """ Test for hierarchy method. """
        self.assertEqual(self.casc2.hierarchy(), [self.casc1, self.casc2])
        
        
    def testPath(self):
        """ Test for path method. """
        self.assertEqual(self.casc1.path(), 'parent')
        self.assertEqual(self.casc2.path(), 'parent:child')
        self.casc1.path = lambda : None
        self.assertEqual(self.casc2.path(), 'child')
     
     
    def testRepr(self):
        """ Test that casting to a string creates the correct string. """
        self.assertIn("<Cascading %r at" % 'parent', repr(self.casc1))
        

#===============================================================================
# 
#===============================================================================

class TransformableTestCase(unittest.TestCase):
    """ Test case for methods in the Transformable class. """
    def setUp(self):
        
        # create objects to be used during testing
        self.xform1 = Transformable()
        self.genericObject = GenericObject()
        
        # configure above objects
        fileStream = open(
            './SSX70065.IDE', 'rb')
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


#===============================================================================
# 
#===============================================================================

class DatasetTestCase(unittest.TestCase):
    """ Test case for methods in the Dataset class. """
    
    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.fileStream = open(
            './SSX70065.IDE', 'rb')
        self.dataset = Dataset(self.fileStream)

        self.channelCheck = {}
        
        # Copied from importer.py:181
        self.channels = DEFAULTS['channels'].copy()
        for chId, chInfo in self.channels.iteritems():
            chArgs = chInfo.copy()
            subchannels = chArgs.pop('subchannels', None)
            self.channelCheck[chId] = Channel(self.dataset, chId, **chArgs.copy())
            channel = self.dataset.addChannel(chId, **chArgs)
            self.assertEqual(channel, self.dataset.channels[chId])
            if subchannels is None:
                continue
            for subChId, subChInfo in subchannels.iteritems():
                channel.addSubChannel(subChId, **subChInfo)
                self.channelCheck[chId].addSubChannel(subChId, **subChInfo)
    
    
    def tearDown(self):
        """ Close and dispose of the file. """
        self.dataset.close()
        self.dataset = None
    
    
    def testConstructor(self):
        """ Exhaustively check that all the members that get initialized in the
            constructor are being initialized to the correct value.
        """
        self.assertEquals(self.dataset._channels, self.channelCheck)
        self.assertEquals(self.dataset._parsers, None)
        
        self.assertEquals(self.dataset.currentSession, None)
#         self.assertEquals(
#             self.dataset.ebmldoc, 
#             loadSchema(SCHEMA_FILE).load(self.fileStream, 'MideDocument'))
        self.assertEquals(self.dataset.fileDamaged, False)
        self.assertEquals(
            self.dataset.filename, getattr(self.fileStream, "name", None))
        self.assertEquals(self.dataset.lastUtcTime, None)
        self.assertEquals(self.dataset.loadCancelled, False)
        self.assertEquals(self.dataset.loading, True)
        self.assertEquals(self.dataset.name, 'SSX70065')
        self.assertEquals(self.dataset.parent, None)
        self.assertEquals(self.dataset.plots, {})
        self.assertEquals(self.dataset.recorderConfig, None)
        self.assertEquals(self.dataset.recorderInfo, {})
        self.assertEquals(self.dataset.schemaVersion, 2)
        self.assertEquals(self.dataset.sensors, {})
        self.assertEquals(self.dataset.sessions, [])
        self.assertEquals(self.dataset.subsets, [])
        self.assertEquals(self.dataset.transforms, {})
        self.assertEquals(self.dataset.warningRanges, {})
        
        
    def testChannels(self):
        """ Test the channels property. """
        self.assertEqual(self.dataset.channels[0], self.channelCheck[0])
        
        
    def testClose(self):
        """ Test the close method. """
        self.assertFalse(self.fileStream.closed)
        self.dataset.close()
        self.assertTrue(self.fileStream.closed)
        
        
    def testClosed(self):
        """ Test the closed property. """
        self.assertFalse(self.dataset.closed)
        self.dataset.close()
        self.assertTrue(self.dataset.closed)
    
    
    def testAddSession(self):
        """ Test that adding sessions properly appends a new session and
            replaces the old currentSession with the new session and that
            lastSession return the most recent session.
        """
        session1 = Session(self.dataset, sessionId=0, startTime=1, endTime=2,
                           utcStartTime=0)
        session2 = Session(self.dataset, sessionId=1, startTime=3, endTime=4,
                           utcStartTime=0)
        
        # Add a new session, assert that it's the current session
        self.dataset.addSession(1, 2)
        self.assertEqual(self.dataset.sessions[0], session1)
        self.assertEqual(self.dataset.currentSession, session1)
        
        # Add a new session, assert that it's replaced the previous session
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
        
        # test that numeric ids work
        self.dataset.addSensor(0)
        self.assertEqual(sensor1, self.dataset.sensors[0])
    
        # test that string ids work
        self.dataset.addSensor('q')
        self.assertEqual(sensor2, self.dataset.sensors['q'])
        
        
    def testAddChannel(self):
        """ Test that each channel is being added to the dataset correctly, and
            that when refering to channel, a dict is returned containing each 
            channel.
        """
        parser = self.channels[0]['parser']
        
        # assert errors
        self.assertRaises(TypeError, self.dataset.addChannel)
        self.assertRaises(TypeError, self.dataset.addChannel, 1)
        
        # assert that the correct channel is returned if it already exists
        self.assertEqual(
            self.dataset._channels[0], 
            self.dataset.addChannel(0, parser=parser))
        
        # assert that a new channel is made when it does not already exist
        self.assertEqual(
            self.dataset.addChannel(2, parser), Channel(self.dataset, 2, parser))
    
    
    def testAddTransform(self):
        """ Test that transforms are being added correctly.
            Using Transformables to test this because they're a simple object
            that already has an ID to use.
        """
        # set up new transforms
        xform1 = Transformable()
        xform1.id = 1
        xform2 = Transformable()
        xform2.id = 'q'
        xform3 = Transformable()
        xform3.id = None
        
        # assert that transforms are being added correctly
        self.dataset.addTransform(xform1)
        self.dataset.addTransform(xform2)
        self.assertEqual(self.dataset.transforms[1], xform1)
        self.assertEqual(self.dataset.transforms['q'], xform2)
        
        # assert that transforms without an id will raise errors
        self.assertRaises(ValueError, self.dataset.addTransform, xform3)
        
        
    def testAddWarning(self):
        """ Test that adding warnings is successfully adding warnings. """
        warning1 = WarningRange(self.dataset, warningId=1, channelId=0,
                                subchannelId=0, high=10)        
        self.dataset.addWarning(1, 0, 0, None, 10)

        self.assertEqual(self.dataset.warningRanges[1], warning1)
        
        
    def testPath(self):
        """ Test that the path is being assembled correctly. """
        self.assertEqual(self.dataset.name, self.dataset.path())
        
        
    def testLastSession(self):
        """ Test the lastSession property. """
        self.dataset.addSession(0, 1, 2)
        self.assertEqual(
            self.dataset.lastSession, 
            Session(self.dataset, 
                    sessionId=0, 
                    startTime=0, 
                    endTime=1, 
                    utcStartTime=2))
        
        self.dataset.addSession(4, 5, 6)
        self.assertEqual(
            self.dataset.lastSession,
            Session(self.dataset,
                    sessionId=1,
                    startTime=4,
                    endTime=5,
                    utcStartTime=6))
        
        
    def testHasSession(self):
        """ Test the hasSession method. """
        self.dataset.addSession(0, 1, 2)
        self.assertTrue(self.dataset.hasSession(None))
        self.assertTrue(self.dataset.hasSession(0))
        self.assertFalse(self.dataset.hasSession(1))


    def testGetPlots(self):
        """ Test that all the plots are being collected and sorted correctly. """
        subs = self.dataset._channels[0].subchannels
        subs = subs + self.dataset._channels[1].subchannels
        self.assertEquals(subs, self.dataset.getPlots(sort=False))
        
        subs.sort(key=lambda x: x.displayName)
        self.assertEquals(subs, self.dataset.getPlots())             
        
        
    def testUpdateTransforms(self):
        """ Test updateTransforms method. """
        
        # mock the updateTransforms method for the channels in the dataset
        # In this case, just count the number of times it was called
        self.transformsUpdated = 0
        def mockUpdateTransforms():
            self.transformsUpdated += 1
        
        for x in self.dataset.channels.values():
            x.updateTransforms = mockUpdateTransforms
        self.dataset.updateTransforms()
        self.assertEqual(self.transformsUpdated, len(self.dataset.channels))


#===============================================================================
# 
#===============================================================================

class SessionTestCase(unittest.TestCase):
    """ Test case for methods in the Session class. """
    
    def testInitAndEQ(self):
        self.dataset = importer.importFile('./SSX70065.IDE')
        session1 = Session(
            self.dataset, sessionId=1, startTime=2, endTime=3, utcStartTime=4)
        session2 = Session(
            self.dataset, sessionId=1, startTime=2, endTime=3, utcStartTime=4)
        
        self.assertEqual(session1, session2)
        self.assertNotEqual(session1, GenericObject())
        
        self.assertEqual(session1.dataset, self.dataset)
        self.assertEqual(session1.endTime, 3)
        self.assertEqual(session1.sessionId, 1)
        self.assertEqual(session1.startTime, 2)
        self.assertEqual(session1.utcStartTime, 4)
        
        
    def testRepr(self):
        """ Test that __repr__ is creating the correct string. """
        fileStream = open(
            './SSX70065.IDE', 'rb')
        dataset = Dataset(fileStream)
        session1 = Session(
            dataset, sessionId=1, startTime=2, endTime=3, utcStartTime=4)
        self.assertIn("<Session (id=1) at", repr(session1))
    

#===============================================================================
# 
#===============================================================================

class SensorTestCase(unittest.TestCase):
    """ Test case for methods in the Sensor class. """
    
    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.dataset = importer.importFile('./SSX70065.IDE')
        
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
        
        
    def testGetItem(self):
        """ Test for the __getitem__ method. """
        self.sensor1.channels = {'a': 2, 'b': 3, 'e': 4, 'test': 5}
        for x in self.sensor1.channels:
            self.assertEqual(self.sensor1[x], self.sensor1.channels[x])
        
        
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


#===============================================================================
# 
#===============================================================================

class ChannelTestCase(unittest.TestCase):
    """ Test case for methods in the Channel class. """
    
    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.dataset = importer.importFile('./SSX70065.IDE')
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
        
        
    def testRepr(self):
        """ Test the repr special method. """
        self.assertIn("<Channel 0: %r at" % 'channel1', repr(self.channel1))
        
        
    def testGetitem(self):
        """ Test the getitem special method. """
        self.assertEqual(self.channel1[0], SubChannel(self.channel1, 0))
        # self.assertEqual(self.channel1[1], SubChannel(self.channel1, 1))
        # TODO: should the above work or not?
        
        
    def testLen(self):
        """ Test the len override. """
        self.assertEqual(len(self.channel1),len(self.channel1.subchannels))
        
        
    def testIter(self):
        """ Test the iter special method. """
        self.channel1.subchannels = [None]*5
        self.channel1.types = self.channel1.displayRange = [1, 2, 3, 4, 5]
        
        idx = 0
        for x in self.channel1:
            self.assertEqual(x, SubChannel(self.channel1, idx))
            idx += 1
        
        
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
                         self.channel1.getSession(1))
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
        """ Test the updateTransforms method in this and the superclass. """
        # mock up a few things to isolate the channel
        genericObject = GenericObject()
        genericObject.isUpdated = False
        self.channel1.subchannels = [genericObject]
        
        self.channel1.updateTransforms()
        
        self.assertTrue(genericObject.isUpdated)


#===============================================================================
# 
#===============================================================================
 
class SubChannelTestCase(unittest.TestCase):
    """ Test case for methods in the SubChannel class. """
    
    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.dataset = importer.importFile('./SSX70065.IDE')
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
        
        
    def testRepr(self):
        """ Test the repr special method. """
        self.assertIn(
            "<SubChannel 2.0: %r at" % 'SSX70065:3:channel2:channel2:00', 
            repr(self.subChannel1))
        
        
    def testLen(self):
        """ Test the len special method. """
        self.assertRaises(AttributeError, self.subChannel1.__len__)
        
        
    def testParser(self):
        """ Test the parser property. """
        self.assertEqual(self.subChannel1.parser, self.channel2.parser)
        
        
    def testSessions(self):
        """ Test the sessions property. """
        self.assertEqual(self.subChannel1.sessions,{})
        
        self.subChannel1._sessions = [1, 2]
        
        self.assertEqual(self.subChannel1.sessions, [1, 2])
        
        
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
        # set up test
        self.subChannel1.dataset.addSession(0, 1, 2)
        self.channel2.subchannels = [GenericObject()]
        parentList = self.dataset.channels[32].getSession()
        parentList.dataset.addSession(0, 1, 2)
        eventList = EventList(
            self.subChannel1,
            session=self.dataset.lastSession,
            parentList=self.subChannel1.parent.getSession())
        
        # check the session was added
        self.assertEqual(self.subChannel1.getSession(), eventList)
        self.assertEqual(self.subChannel1._sessions[2], eventList)
        self.assertEqual(self.subChannel1.getSession(2), eventList)
        
        
    def testAddSubChannel(self):
        """ Test addSubChannel method.  This will throw an error. """
        self.assertRaises(AttributeError, self.subChannel1.addSubChannel)
        
        
    def testGetSubchannel(self):
        """ Test getSubChannel method.  This will always throw an error. """
        self.assertRaises(AttributeError, self.subChannel1.getSubChannel)

    
#===============================================================================
# 
#===============================================================================

class EventListTestCase(unittest.TestCase):
    """ Test case for methods in the EventList class. """
    
    def setUp(self):
        self.dataset = importer.importFile('./SSX70065.IDE')
        self.dataset.addSession(0, 1, 2)
        self.dataset.addSensor(0)
        
        self.fakeParser = GenericObject()
        self.fakeParser.types = [0]
        self.fakeParser.format = []
        
        self.channel1 = Channel(
            self.dataset, channelId=0, name="channel1", parser=self.fakeParser,
            displayRange=[0])
        self.eventList1 = EventList(self.channel1, session=self.dataset.sessions[0])
        
        self.channel1.addSubChannel(subchannelId=0)
        
        self.subChannel1 = SubChannel(self.channel1, 0)
        
        
    def tearDown(self):
        self.dataset = None
        self.fakeParser = None
        self.channel1 = None
        self.eventList1 = None
    
    
    def mockData(self):
        """ mock up a bit of fake data so I don't have to worry that external
            classes are working during testing.
        """
        fakeData = GenericObject()
        fakeData.startTime = 0
        fakeData.indexRange = [0, 3]
        fakeData.sampleTime = 1
        fakeData.numSamples = 1
        self.eventList1._data = [fakeData]
    
    
    def mockIterslice(self,  *args, **kwargs):
        """ Mock up iterslice so it doesn't get called while testing
            other methods.
        """
        self.iterArgs = args
        self.kwArgs = kwargs
        return [[1], [2], [3], [4]]
    
    
    def mockXform(self, times, session=None, noBivariates=None):
        self.xformArgs = (times, session, noBivariates)
        
        self.mockXformReturn[2] += 1

        return list(self.mockXformReturn)
    
    
    def testConstructor(self):
        """ Test the __init__ method. """
        self.assertEqual(self.eventList1._blockIndices, [])
        self.assertEqual(self.eventList1._blockTimes, [])
        self.assertEqual(self.eventList1._childLists, [])
        self.assertEqual(self.eventList1._data, [])
        self.assertEqual(self.eventList1._firstTime, None)
        self.assertFalse(self.eventList1._hasSubsamples)
        self.assertEqual(self.eventList1._lastTime, None)
        self.assertEqual(self.eventList1._length, 0)
        self.assertEqual(self.eventList1._parentList, None)
        self.assertEqual(
            self.eventList1._singleSample, self.channel1.singleSample)
        
        self.assertEqual(self.eventList1.channelId, self.channel1.id)
        self.assertEqual(self.eventList1.dataset, self.channel1.dataset)
        self.assertEqual(
            self.eventList1.displayRange, self.channel1.displayRange)
        self.assertTrue(self.eventList1.hasMinMeanMax)
        self.assertEqual(
            self.eventList1.hasDisplayRange, self.channel1.hasDisplayRange)
        self.assertTrue(self.eventList1.hasSubchannels)
        self.assertFalse(self.eventList1.noBivariates)
        self.assertEqual(self.eventList1.parent, self.channel1)
        self.assertFalse(self.eventList1.removeMean)
        self.assertEqual(
            self.eventList1.rollingMeanSpan, EventList.DEFAULT_MEAN_SPAN)
        self.assertEqual(self.eventList1.session, self.dataset.sessions[0])
        self.assertEqual(self.eventList1.subchannelId, None)        
            
            
    def testUpdateTransforms(self):
        """ Test the updateTransforms method. """
        # update transforms without recursion
        self.eventList1.updateTransforms(False)
        self.assertEqual(
            self.eventList1._comboXform, 
            PolyPoly([self.channel1.transform]*len(self.channel1.types)))
        xs = [c.transform if c is not None else None for c in self.channel1.subchannels]
        xs = [CombinedPoly(t, x=self.channel1.transform, dataset=self.dataset) for t in xs]
        self.assertEqual(self.eventList1._fullXform, PolyPoly(xs,dataset=self.dataset))
        self.tearDown()
        
        # update transforms with recursion
        self.setUp()
        self.eventList1.updateTransforms(True)
        self.assertEqual(
            self.eventList1._displayXform, 
            PolyPoly(xs, dataset=self.dataset))
        self.tearDown()
        
        # test for when there's a subchannel with a corresponding session
        self.setUp()
        self.eventList1.session.sessionId = 'session0'
        self.eventList1.parent.subchannels[0]._sessions = {'session0': self.eventList1}
        self.eventList1.updateTransforms()
        xs = [c.transform if c is not None else None for c in self.eventList1.parent.subchannels]
        self.assertEqual(
            self.eventList1._displayXform, 
            PolyPoly(
                [CombinedPoly(self.eventList1.transform, x=xs[0], dataset=self.dataset)], 
                dataset=self.dataset))
        
        
    def testUnits(self):
        """ Test the units property. """
        self.assertEqual(self.eventList1.units, ('',''))
        
        
    def testPath(self):
        """ Test the path method. """
        self.assertEqual(self.eventList1.path(), "channel1, 0")
        
        
    def testCopy(self):
        """ Test the copy method. Since this is a shallow copy, don't use the 
            build in equality check.
        """
        eventListCopy = self.eventList1.copy()
        self.assertEqual(self.eventList1.parent, eventListCopy.parent)
        self.assertEqual(self.eventList1.session, eventListCopy.session)
        self.assertEqual(self.eventList1.dataset, eventListCopy.dataset)
        self.assertEqual(self.eventList1.hasSubchannels, eventListCopy.hasSubchannels)
        self.assertEqual(self.eventList1.noBivariates, eventListCopy.noBivariates)
        self.assertEqual(self.eventList1.channelId, eventListCopy.channelId)
        self.assertEqual(self.eventList1.subchannelId, eventListCopy.subchannelId)
        self.assertEqual(self.eventList1.channelId, eventListCopy.channelId)
        self.assertEqual(self.eventList1.hasDisplayRange, eventListCopy.hasDisplayRange)
        self.assertEqual(self.eventList1.displayRange, eventListCopy.displayRange)
        self.assertEqual(self.eventList1.removeMean, eventListCopy.removeMean)
        self.assertEqual(self.eventList1.hasMinMeanMax, eventListCopy.hasMinMeanMax)
        self.assertEqual(self.eventList1.rollingMeanSpan, eventListCopy.rollingMeanSpan)
        self.assertEqual(self.eventList1.transform, eventListCopy.transform)
        self.assertEqual(self.eventList1.useAllTransforms, eventListCopy.useAllTransforms)
        self.assertEqual(self.eventList1.allowMeanRemoval, eventListCopy.allowMeanRemoval)
        
        
    def testAppend(self):
        """ Test the append method. """
        fakeData = GenericObject()
        fakeData.numSamples = 1
        fakeData.startTime = 2
        fakeData.endTime = 4
        fakeData.minMeanMax = (5, 6, 7)
        
        fakeData.parseMinMeanMax = lambda x: x
        
        # append boring basic fakeData
        self.eventList1.append(fakeData)
        
        self.assertEqual(fakeData.blockIndex, 0)
        self.assertFalse(fakeData.cache)
        self.assertEqual(fakeData.indexRange, (0, 0))
        self.assertEqual(self.eventList1._blockIndices,[0])
        self.assertEqual(self.eventList1._blockTimes, [2])
        self.assertEqual(self.eventList1._firstTime, 2)
        self.assertEqual(self.eventList1._lastTime, 4)
        self.assertEqual(self.eventList1._length, 1)
        self.assertTrue(self.eventList1._singleSample)
        
        # append single sample fakeData
        self.eventList1._singleSample = True
        
        self.eventList1.append(fakeData)
        
        self.assertEqual(fakeData.blockIndex, 1)
        self.assertFalse(fakeData.cache)
        self.assertEqual(fakeData.indexRange, (1, 1))
        self.assertEqual(self.eventList1._blockIndices,[0, 1])
        self.assertEqual(self.eventList1._blockTimes, [2,2])
        self.assertEqual(self.eventList1._firstTime, 2)
        self.assertEqual(self.eventList1._lastTime, 4)
        self.assertEqual(self.eventList1._length, 2)
        self.assertTrue(self.eventList1._singleSample)
        
        # append with times stripped out
        self.eventList1.session.firstTime = None
        self.eventList1.session.lastTime = None
        self.eventList1._firstTime = None
        
        self.eventList1.append(fakeData)
        
        self.assertEqual(fakeData.blockIndex, 2)
        self.assertFalse(fakeData.cache)
        self.assertEqual(fakeData.indexRange, (2, 2))
        self.assertEqual(self.eventList1._blockIndices,[0, 1, 2])
        self.assertEqual(self.eventList1._blockTimes, [2, 2, 2])
        self.assertEqual(self.eventList1._firstTime, 2)
        self.assertEqual(self.eventList1._lastTime, 4)
        self.assertEqual(self.eventList1._length, 3)
        self.assertTrue(self.eventList1._singleSample)


    def testGetInterval(self):
        """ Test the getInterval method. """
        fakeObject = GenericObject()
        fakeObject.endTime = 1
        accel = self.dataset.channels[32].getSession()
        
        # without _data, return None
        self.assertEqual(accel.getInterval(), None)
        self.assertEqual(accel._lastTime, None)
        
        # with mocked data
        accel._data = [fakeObject]
        accel._firstTime = 3
        self.assertEqual(accel.getInterval(), (3, 1))
        self.assertEqual(accel._lastTime, 1)
        
        # with mocked data and a mocked dataset
        accel.dataset = GenericObject()
        accel.dataset.loading = True
        self.assertEqual(accel.getInterval(), (3, 1))
        
        
    def mockForGetItem(self, section):
        """ Mock different things for testGetItem. """
        
        # mock with xforms
        if section == 0:
            
            mockBlockIndex = [0, 1, 2, 3]
            
            def mockGetBlockIndexWithIndex(idx, start=None):
                return mockBlockIndex[idx]
            
            def mockGetBlockIndexRange(idx):
                return mockBlockIndex
            
            def mockXform(timeAndVal, session=None, noBivariates=False):
                if type(timeAndVal[1]) == list:
                    return timeAndVal
                return (timeAndVal[0], [timeAndVal[1].id])
                
            def mockParseBlock(block, start=None, end=None, step=None):
                return [block]
            
            self.eventList1._getBlockIndexRange = mockGetBlockIndexRange
            self.eventList1._getBlockIndexWithIndex = mockGetBlockIndexWithIndex
            self.eventList1.parent.parseBlock = mockParseBlock
            self.eventList1._displayXform = self.eventList1._comboXform = \
                    self.eventList1._fullXform = mockXform
            
            self.eventList1._data = [GenericObject(),
                                     GenericObject(),
                                     GenericObject(),
                                     GenericObject()]
            
            for x in xrange(len(self.eventList1._data)):
                self.eventList1._data[x].id = x
            
        # mock without xforms
        elif section == 1:
            
            def mockXform(timeAndVal, session=None, noBivariates=False):
                return None
            
            self.eventList1._displayXform = self.eventList1._comboXform = \
                    self.eventList1._fullXform = mockXform
                    
        # with blockRollingMean
        elif section == 2:
        
            self.mockForGetItem(0)
            
            self.eventList1._getBlockRollingMean = lambda x: [1]
            
            def mockXform(timeAndVal, session=None, noBivariates=False):
                if type(timeAndVal[1]) == list:
                    return timeAndVal
                return (timeAndVal[0], [timeAndVal[1].id])
            
            self.eventList1._displayXform = self.eventList1._comboXform = \
                    self.eventList1._fullXform = mockXform
                
        # for __getitem__ to work in getEventIndexNear
        elif section == 3:
            self.mockForGetItem(0)
            
            def mockGetBlockSampleTime(idx, start=None):
                return 1
            
            self.eventList1._getBlockSampleTime = mockGetBlockSampleTime
                 
                        
    def testGetItem(self):
        """ Test the getitem special method. """
        self.assertRaises(TypeError, self.eventList1.__getitem__, 'd')
        
        # Mock everything surrounding this method in order to test it in isolation
        self.mockForGetItem(0)
        
        # if parent.parseBlock just bounces back data, then it should just
        # get a tuple with the timestamp and data
        self.assertEqual(self.eventList1[0], (0, [0]))
        self.assertEqual(self.eventList1[1], (0, [1]))
        self.assertEqual(self.eventList1[2], (0, [2]))
        self.assertEqual(self.eventList1[3], (0, [3]))
        
        self.mockForGetItem(1)
        
        # if the transform returns a none type, it should just skip through
        # and return None
        self.assertEqual(self.eventList1[0], None)
        self.assertEqual(self.eventList1[1], None)
        self.assertEqual(self.eventList1[2], None)
        self.assertEqual(self.eventList1[3], None)
        
        self.mockForGetItem(2)
        
        # If there is an offset, return a tuple of the timestamp and data,
        # minus the offset
        self.assertEqual(self.eventList1[0], (0, (-1,)))
        self.assertEqual(self.eventList1[1], (0, (0,)))
        self.assertEqual(self.eventList1[2], (0, (1,)))
        self.assertEqual(self.eventList1[3], (0, (2,)))
        
        
    def testIter(self):
        """ Test for iter special method. """
        self.eventList1._data = [GenericObject(),
                                 GenericObject(),
                                 GenericObject(),
                                 GenericObject()]
        self.eventList1._fullXform = lambda x, session, noBivariates: x
        
        self.assertListEqual(
            [x for x in self.eventList1],
            [x for x in self.eventList1.iterSlice()])
            
            
    # TODO talk to david about how to test these
    def testItervalues(self):
        """ Test for itervalues method. """
        self.mockData()
        self.eventList1.iterSlice = self.mockIterslice
        
        self.assertEqual([x for x in self.eventList1.itervalues()], [1, 2, 3, 4])            
        self.assertEqual(self.iterArgs, (0, -1, 1, False))
        
        
    def testIterSlice(self):
        """ print(self.eventList1.iterSlice()) """
        self.eventList1._data = [GenericObject(),
                                 GenericObject(),
                                 GenericObject(),
                                 GenericObject()]
        self.eventList1._fullXform = lambda x, session, noBivariates: x
        
        self.assertListEqual(
            [x for x in self.eventList1.iterSlice()], 
            [(0, self.channel1.parseBlock(self.eventList1._data[0])[0]), 
             (0, -3), 
             (0,1 ), 
             (0, 1)])
        
        
    def testIterJitterySlice(self):
        """ Test for the iterJitterySlice method. """
        self.eventList1._data = [GenericObject(),
                                 GenericObject(),
                                 GenericObject(),
                                 GenericObject()]
        self.eventList1._fullXform = lambda x, session, noBivariates: x
        
        self.assertListEqual(
            [x for x in self.eventList1.iterJitterySlice()],
            [(0, self.channel1.parseBlock(self.eventList1._data[0])[0]),
             (0, [-3, -2, -1, 0]), 
             (0, None)])


    def testGetEventIndexBefore(self):
        """ Test for getEventIndexBefore method. """
        self.mockData()

        self.assertEqual(self.eventList1.getEventIndexBefore(1), 1)
        self.assertEqual(self.eventList1.getEventIndexBefore(-1), -1)
        
        
    def testGetEventIndexNear(self):
        """ Test for getEventIndexNear method. """
        self.mockForGetItem(3)

        self.assertEqual(self.eventList1.getEventIndexNear(-1), 0)
        self.assertEqual(self.eventList1.getEventIndexNear(0), 0)
        self.assertEqual(self.eventList1.getEventIndexNear(1), 4)
        self.assertEqual(self.eventList1.getEventIndexNear(-1), 0)
    
    
    def testGetRangeIndices(self):
        """ Test for getRangeIndices method. """
        self.mockData()
        
        # input permutations for multi sample
        self.assertEqual(self.eventList1.getRangeIndices(1, 2), (2, 2))
        self.assertEqual(self.eventList1.getRangeIndices(None, 2), (0, 2))
        self.assertEqual(self.eventList1.getRangeIndices(None, None), (0, 3))
        self.assertEqual(self.eventList1.getRangeIndices(2, -51), (3, 0))
        
        # input permutations for single sample
        self.eventList1.parent.singleSample = True
        self.assertEqual(self.eventList1.getRangeIndices(2, -51), (0, 1))
        self.assertEqual(self.eventList1.getRangeIndices(2, None), (0, 3))
        
        
    def testGetRange(self):
        """ Test for getRange method. """
        self.mockData()
        self.eventList1.iterRange = lambda x, y, display: (x, y, display)
        
        self.assertEqual(
            self.eventList1.getRange(), 
            [None, None, False])
    
    
    def testIterRange(self):
        """ Test for iterRange method. """
        self.mockData()
        self.eventList1.iterSlice = lambda w, x, y, display: (w+1, x, y, display)
        
        self.assertEqual(
            self.eventList1.iterRange(1, 3, 1, display=False), 
            self.eventList1.iterSlice(2, 3, 1, display=False))
        
        
    def testIterMinMeanMax(self):
        """ Test for iterMinMeanMax method. """
        self.mockData()
        self.eventList1._data[0].minMeanMax = 1
        self.eventList1._data[0].blockIndex = 2
        self.eventList1._data[0].min = [3]
        self.eventList1._data[0].mean = [4]
        self.eventList1._data[0].max = [5]
        
        self.assertListEqual(
            [x for x in self.eventList1.iterMinMeanMax()], 
            [[(0,(3,)),(0,(4,)),(0,(5,))]])
         
            
    def testGetMinMeanMax(self):
        """ Test getMinMeanMax. """
        self.mockData()
        self.eventList1._data[0].minMeanMax = 1
        self.eventList1._data[0].blockIndex = 2
        self.eventList1._data[0].min = [3]
        self.eventList1._data[0].mean = [4]
        self.eventList1._data[0].max = [5]
        
        self.assertEqual(
            self.eventList1.getMinMeanMax(),
            [[(0,(3,)), (0,(4,)), (0,(5,))]])
        self.assertEqual(
            self.dataset.channels[32].getSession().getMinMeanMax(),
            [])
            
            
    def testGetRangeMinMeanMax(self):
        """ Test for getRangeMinMeanMax method. """
        self.mockData()
        self.eventList1._data[0].minMeanMax = 1
        self.eventList1._data[0].blockIndex = 2
        self.eventList1._data[0].min = [3]
        self.eventList1._data[0].mean = [4]
        self.eventList1._data[0].max = [5]
        
        self.assertEqual(self.eventList1.getRangeMinMeanMax(), (3, 4, 5))
        
        
    def testGetMax(self):
        """ Test for getMax method. """
        self.mockData()
        self.eventList1._data[0].minMeanMax = [1]
        self.eventList1._data[0].blockIndex = [2]
        self.eventList1._data[0].min = [3]
        self.eventList1._data[0].mean = [4]
        self.eventList1._data[0].max = [5]
        
        def mockSliceForMax(*args, **kwargs):
            return [[args]]
        self.eventList1.iterSlice = mockSliceForMax
             
        self.assertEqual(self.eventList1.getMax(), [(0, 3)])
        
        
    def testGetMin(self):
        """ test for getMin method. """
        self.mockData()
        self.eventList1._data[0].minMeanMax = [1]
        self.eventList1._data[0].blockIndex = [2]
        self.eventList1._data[0].min = [3]
        self.eventList1._data[0].mean = [4]
        self.eventList1._data[0].max = [5]
        
        def mockSliceForMax(*args, **kwargs):
            return [[args]]
        self.eventList1.iterSlice = mockSliceForMax
             
        self.assertEqual(self.eventList1.getMin(), [(0, 3)])
        
        
    def testGetSampleTime(self):
        """ Test for getSampleTime method. """
        self.mockData()
        
        self.assertEqual(self.eventList1.getSampleTime(), 1)
        self.assertEqual(self.eventList1.getSampleTime(1), 1)
        self.assertEqual(self.dataset.channels[32].getSession().getSampleTime(), -1)
        self.assertEqual(self.dataset.channels[32].getSession().getSampleTime(1), -1)
        
        
    def testGetSampleRate(self):
        """ Test for getSampleRate method. """
        self.mockData()
        self.eventList1._data[0].sampleRate = 5
        self.dataset.channels[32].sampleRate = 3
        self.dataset.channels[32].getSession()._data = self.eventList1._data
        
        self.assertEqual(self.eventList1.getSampleRate(), 5)
        self.assertEqual(self.eventList1.getSampleRate(0), 5)
        self.assertEqual(self.dataset.channels[32].getSession().getSampleRate(), 3)
        self.assertEqual(self.dataset.channels[32].getSession().getSampleRate(0), 5)
        
        
    def testGetValueAt(self):
        """ Test for getValueAt method. """
        # mocking
        self.mockData()
        fakeData = GenericObject()
        fakeData.numSamples = 1
        fakeData.startTime = 0
        fakeData.endTime = 4
        fakeData.minMeanMax = (5, 6, 7)
        fakeData.parseMinMeanMax = lambda x: x
        
        self.eventList1.append(fakeData)
        
        # bonus mocking.  repeating for every test to ensure that it's sending
        # the values it needs to
        self.eventList1._fullXform = self.mockXform
        self.mockXformReturn = [[0], [0], 0, [0]] 
        self.assertEqual(
            self.eventList1.getValueAt(0, outOfRange=True), 
            [[0], [0], 1, [0]])
        
        self.mockXformReturn = [[0], [0], -1, [0]]
        self.assertEqual(self.eventList1.getValueAt(0), [[0], [0], 0, [0]])
        
        self.mockXformReturn = [[0], [0], -1, [0]]        
        self.eventList1.getEventIndexBefore = lambda x: 1
        self.assertEqual(self.eventList1.getValueAt(0), [[0], [0], 0, [0]])
        
        self.mockXformReturn = [[0], [0], -1, [0]]        
        self.eventList1.getEventIndexBefore = lambda x: 0
        self.mockXformReturn = [[0], [0], 0, [0]]
        self.assertEqual(self.eventList1.getValueAt(0), (0, (0.0,)))
        
        
    def testGetMeanNear(self):
        """ Test for getMeanNear method. """
        # mock everthing up
        self.mockData()
        
        def mockComboXform(*args, **kwargs):
            self.comboArgs = args
            self.comboKwargs = kwargs
            
            return [[0]]
        
        self.eventList1._comboXform = mockComboXform
        self.eventList1._data[0].minMeanMax = 0
        self.eventList1._data[0]._rollingMean = 0
        self.eventList1._data[0]._rollingMeanSpan = 0
        self.eventList1._data[0].mean = 0
        
        self.assertEqual(self.eventList1.getMeanNear(0), [0])
        self.assertEqual(self.comboArgs, ((0,0),))
        self.assertEqual(self.comboKwargs, {})
        
        # test for an eventlist with no subchannels
        self.eventList1.hasSubchannels = False   
        self.eventList1.subchannelId = 0 
        
        self.assertEqual(self.eventList1.getMeanNear(0), 0)
        self.assertEqual(self.comboArgs, ((0,0),))
        self.assertEqual(self.comboKwargs, {})
        
        
    def testExportCSV(self):
        """ Test exportCsv, """
        self.mockData()
        self.eventList1._data[0].minMeanMax = 1
        self.eventList1._data[0].blockIndex = 2
        self.eventList1._data[0].min = [3]
        self.eventList1._data[0].mean = [4]
        self.eventList1._data[0].max = [5]
        
        # print(self.eventList1.exportCsv(streamMocker))


#===============================================================================
#
#===============================================================================

class EventArrayTestCase(unittest.TestCase):
    """ Test case for methods in the EventArray class. """

    def assertArrayEqual(self, array1, array2):
        self.assertTrue(np.all(array1 == array2))

    def setUp(self):
        self.dataset = importer.importFile('./SSX70065.IDE')
        self.dataset.addSession(0, 1, 2)
        self.dataset.addSensor(0)

        self.fakeParser = GenericObject()
        self.fakeParser.types = [0]
        self.fakeParser.format = []

        self.channel1 = Channel(
            self.dataset, channelId=0, name="channel1", parser=self.fakeParser,
            displayRange=[0]
        )
        self.eventArray1 = EventArray(self.channel1,
                                      session=self.dataset.sessions[0])

        self.channel1.addSubChannel(subchannelId=0)

        self.subChannel1 = SubChannel(self.channel1, 0)

    def tearDown(self):
        self.dataset = None
        self.fakeParser = None
        self.channel1 = None
        self.eventArray1 = None

    def mockData(self):
        """ mock up a bit of fake data so I don't have to worry that external
            classes are working during testing.
        """
        fakeData = GenericObject()
        fakeData.startTime = 0
        fakeData.indexRange = [0, 3]
        fakeData.sampleTime = 1
        fakeData.numSamples = 1
        self.eventArray1._data = [fakeData]

    def mockIterSlice(self,  *args, **kwargs):
        """ Mock up iterslice so it doesn't get called while testing
            other methods.
        """
        blockDataStub = np.array(
            [(0, (i,)) for i in [1, 2, 3, 4]],
            dtype=[
                ('time', np.float),
                ('channels', [('ch0'.format(i), np.int)])
            ]
        )

        self.iterArgs = args
        self.kwArgs = kwargs
        return iter(blockDataStub)

    def mockArraySlice(self,  *args, **kwargs):
        """ Mock up iterslice so it doesn't get called while testing
            other methods.
        """
        blockDataStub = np.array(
            [(0, (i,)) for i in [1, 2, 3, 4]],
            dtype=[
                ('time', np.float),
                ('channels', [('ch0'.format(i), np.int)])
            ]
        )

        self.iterArgs = args
        self.kwArgs = kwargs
        return blockDataStub

    def mockXform(self, times, session=None, noBivariates=None):
        self.xformArgs = (times, session, noBivariates)

        self.mockXformReturn[2] += 1

        return list(self.mockXformReturn)

    # --------------------------------------------------------------------------
    # Base Method Tests
    # --------------------------------------------------------------------------

    def testConstructor(self):
        """ Test the __init__ method. """
        self.assertEqual(self.eventArray1._blockIndices, [])
        self.assertEqual(self.eventArray1._blockTimes, [])
        self.assertEqual(self.eventArray1._childLists, [])
        self.assertEqual(self.eventArray1._data, [])
        self.assertEqual(self.eventArray1._firstTime, None)
        self.assertFalse(self.eventArray1._hasSubsamples)
        self.assertEqual(self.eventArray1._lastTime, None)
        self.assertEqual(self.eventArray1._length, 0)
        self.assertEqual(self.eventArray1._parentList, None)
        self.assertEqual(self.eventArray1._singleSample,
                         self.channel1.singleSample)

        self.assertEqual(self.eventArray1.channelId, self.channel1.id)
        self.assertEqual(self.eventArray1.dataset, self.channel1.dataset)
        self.assertEqual(self.eventArray1.displayRange,
                         self.channel1.displayRange)
        self.assertTrue(self.eventArray1.hasMinMeanMax)
        self.assertEqual(self.eventArray1.hasDisplayRange,
                         self.channel1.hasDisplayRange)
        self.assertTrue(self.eventArray1.hasSubchannels)
        self.assertFalse(self.eventArray1.noBivariates)
        self.assertEqual(self.eventArray1.parent, self.channel1)
        self.assertFalse(self.eventArray1.removeMean)
        self.assertEqual(self.eventArray1.rollingMeanSpan,
                         EventList.DEFAULT_MEAN_SPAN)
        self.assertEqual(self.eventArray1.session, self.dataset.sessions[0])
        self.assertEqual(self.eventArray1.subchannelId, None)

    # TODO add test
    #def test_JoinTimesValues(self):

    def testUpdateTransforms(self):
        """ Test the updateTransforms method. """
        # update transforms without recursion
        self.eventArray1.updateTransforms(False)
        self.assertEqual(
            self.eventArray1._comboXform,
            PolyPoly([self.channel1.transform]*len(self.channel1.types))
        )
        xs = [c.transform if c is not None else None
              for c in self.channel1.subchannels]
        xs = [CombinedPoly(t, x=self.channel1.transform, dataset=self.dataset)
              for t in xs]
        self.assertEqual(self.eventArray1._fullXform,
                         PolyPoly(xs, dataset=self.dataset))
        self.tearDown()

        # update transforms with recursion
        self.setUp()
        self.eventArray1.updateTransforms(True)
        self.assertEqual(self.eventArray1._displayXform,
                         PolyPoly(xs, dataset=self.dataset))
        self.tearDown()

        # test for when there's a subchannel with a corresponding session
        self.setUp()
        self.eventArray1.session.sessionId = 'session0'
        self.eventArray1.parent.subchannels[0]._sessions = {'session0': self.eventArray1}
        self.eventArray1.updateTransforms()
        xs = [c.transform if c is not None else None
              for c in self.eventArray1.parent.subchannels]
        self.assertEqual(
            self.eventArray1._displayXform,
            PolyPoly(
                [CombinedPoly(self.eventArray1.transform,
                              x=xs[0], dataset=self.dataset)],
                dataset=self.dataset,
            )
        )

    def testUnits(self):
        """ Test the units property. """
        self.assertEqual(self.eventArray1.units, ('', ''))

    def testPath(self):
        """ Test the path method. """
        self.assertEqual(self.eventArray1.path(), "channel1, 0")

    def testCopy(self):
        """ Test the copy method. Since this is a shallow copy, don't use the
            build in equality check.
        """
        eventArrayCopy = self.eventArray1.copy()
        self.assertEqual(self.eventArray1.parent, eventArrayCopy.parent)
        self.assertEqual(self.eventArray1.session, eventArrayCopy.session)
        self.assertEqual(self.eventArray1.dataset, eventArrayCopy.dataset)
        self.assertEqual(self.eventArray1.hasSubchannels, eventArrayCopy.hasSubchannels)
        self.assertEqual(self.eventArray1.noBivariates, eventArrayCopy.noBivariates)
        self.assertEqual(self.eventArray1.channelId, eventArrayCopy.channelId)
        self.assertEqual(self.eventArray1.subchannelId, eventArrayCopy.subchannelId)
        self.assertEqual(self.eventArray1.channelId, eventArrayCopy.channelId)
        self.assertEqual(self.eventArray1.hasDisplayRange, eventArrayCopy.hasDisplayRange)
        self.assertEqual(self.eventArray1.displayRange, eventArrayCopy.displayRange)
        self.assertEqual(self.eventArray1.removeMean, eventArrayCopy.removeMean)
        self.assertEqual(self.eventArray1.hasMinMeanMax, eventArrayCopy.hasMinMeanMax)
        self.assertEqual(self.eventArray1.rollingMeanSpan, eventArrayCopy.rollingMeanSpan)
        self.assertEqual(self.eventArray1.transform, eventArrayCopy.transform)
        self.assertEqual(self.eventArray1.useAllTransforms, eventArrayCopy.useAllTransforms)
        self.assertEqual(self.eventArray1.allowMeanRemoval, eventArrayCopy.allowMeanRemoval)

    def testAppend(self):
        """ Test the append method. """
        fakeData = GenericObject()
        fakeData.numSamples = 1
        fakeData.startTime = 2
        fakeData.endTime = 4
        fakeData.minMeanMax = (5, 6, 7)

        fakeData.parseMinMeanMax = lambda x: x

        # append boring basic fakeData
        self.eventArray1.append(fakeData)

        self.assertEqual(fakeData.blockIndex, 0)
        self.assertFalse(fakeData.cache)
        self.assertEqual(fakeData.indexRange, (0, 0))
        self.assertEqual(self.eventArray1._blockIndices, [0])
        self.assertEqual(self.eventArray1._blockTimes, [2])
        self.assertEqual(self.eventArray1._firstTime, 2)
        self.assertEqual(self.eventArray1._lastTime, 4)
        self.assertEqual(self.eventArray1._length, 1)
        self.assertTrue(self.eventArray1._singleSample)

        # append single sample fakeData
        self.eventArray1._singleSample = True

        self.eventArray1.append(fakeData)

        self.assertEqual(fakeData.blockIndex, 1)
        self.assertFalse(fakeData.cache)
        self.assertEqual(fakeData.indexRange, (1, 1))
        self.assertEqual(self.eventArray1._blockIndices, [0, 1])
        self.assertEqual(self.eventArray1._blockTimes, [2, 2])
        self.assertEqual(self.eventArray1._firstTime, 2)
        self.assertEqual(self.eventArray1._lastTime, 4)
        self.assertEqual(self.eventArray1._length, 2)
        self.assertTrue(self.eventArray1._singleSample)

        # append with times stripped out
        self.eventArray1.session.firstTime = None
        self.eventArray1.session.lastTime = None
        self.eventArray1._firstTime = None

        self.eventArray1.append(fakeData)

        self.assertEqual(fakeData.blockIndex, 2)
        self.assertFalse(fakeData.cache)
        self.assertEqual(fakeData.indexRange, (2, 2))
        self.assertEqual(self.eventArray1._blockIndices, [0, 1, 2])
        self.assertEqual(self.eventArray1._blockTimes, [2, 2, 2])
        self.assertEqual(self.eventArray1._firstTime, 2)
        self.assertEqual(self.eventArray1._lastTime, 4)
        self.assertEqual(self.eventArray1._length, 3)
        self.assertTrue(self.eventArray1._singleSample)

    def testGetInterval(self):
        """ Test the getInterval method. """
        fakeObject = GenericObject()
        fakeObject.endTime = 1
        accel = self.dataset.channels[32].getSession()

        # without _data, return None
        self.assertEqual(accel.getInterval(), None)
        self.assertEqual(accel._lastTime, None)

        # with mocked data
        accel._data = [fakeObject]
        accel._firstTime = 3
        self.assertEqual(accel.getInterval(), (3, 1))
        self.assertEqual(accel._lastTime, 1)

        # with mocked data and a mocked dataset
        accel.dataset = GenericObject()
        accel.dataset.loading = True
        self.assertEqual(accel.getInterval(), (3, 1))

    def mockForGetItem(self, section):
        """ Mock different things for testGetItem. """

        # mock with xforms
        if section == 0:

            mockBlockIndex = [0, 1, 2, 3]

            def mockGetBlockIndexWithIndex(idx, start=None):
                return mockBlockIndex[idx]

            def mockGetBlockIndexRange(idx):
                return mockBlockIndex

            def mockXform(timeAndVal, session=None, noBivariates=False):
                if type(timeAndVal[1]) == list:
                    return timeAndVal
                return (timeAndVal[0], [timeAndVal[1].id])

            def mockParseBlock(block, start=None, end=None, step=None):
                return [block]

            self.eventArray1._getBlockIndexRange = mockGetBlockIndexRange
            self.eventArray1._getBlockIndexWithIndex = mockGetBlockIndexWithIndex
            self.eventArray1.parent.parseBlock = mockParseBlock
            self.eventArray1._displayXform = self.eventArray1._comboXform = \
                self.eventArray1._fullXform = mockXform

            self.eventArray1._data = [GenericObject() for _ in range(4)]

            for x in xrange(len(self.eventArray1._data)):
                self.eventArray1._data[x].id = x

        # mock without xforms
        elif section == 1:

            def mockXform(timeAndVal, session=None, noBivariates=False):
                return None

            self.eventArray1._displayXform = self.eventArray1._comboXform = \
                self.eventArray1._fullXform = mockXform

        # with blockRollingMean
        elif section == 2:

            self.mockForGetItem(0)

            self.eventArray1._getBlockRollingMean = lambda x: [1]

            def mockXform(timeAndVal, session=None, noBivariates=False):
                if type(timeAndVal[1]) == list:
                    return timeAndVal
                return (timeAndVal[0], [timeAndVal[1].id])

            self.eventArray1._displayXform = self.eventArray1._comboXform = \
                self.eventArray1._fullXform = mockXform

        # for __getitem__ to work in getEventIndexNear
        elif section == 3:
            self.mockForGetItem(0)

            def mockGetBlockSampleTime(idx, start=None):
                return 1

            self.eventArray1._getBlockSampleTime = mockGetBlockSampleTime

    def testGetItem(self):
        """ Test the getitem special method. """
        self.assertRaises(TypeError, self.eventArray1.__getitem__, 'd')

        # Mock everything surrounding this method to test it in isolation
        self.mockForGetItem(0)

        # if parent.parseBlock just bounces back data, then it should just
        # get a tuple with the timestamp and data
        self.assertEqual(self.eventArray1[0], (0, [0]))
        self.assertEqual(self.eventArray1[1], (0, [1]))
        self.assertEqual(self.eventArray1[2], (0, [2]))
        self.assertEqual(self.eventArray1[3], (0, [3]))

        self.mockForGetItem(1)

        # if the transform returns a none type, it should just skip through
        # and return None
        self.assertEqual(self.eventArray1[0], None)
        self.assertEqual(self.eventArray1[1], None)
        self.assertEqual(self.eventArray1[2], None)
        self.assertEqual(self.eventArray1[3], None)

        self.mockForGetItem(2)

        # If there is an offset, return a tuple of the timestamp and data,
        # minus the offset
        self.assertEqual(self.eventArray1[0], (0, (-1,)))
        self.assertEqual(self.eventArray1[1], (0, (0,)))
        self.assertEqual(self.eventArray1[2], (0, (1,)))
        self.assertEqual(self.eventArray1[3], (0, (2,)))

    def testIter(self):
        """ Test for iter special method. """
        self.eventArray1.iterSlice = self.mockIterSlice
        self.assertListEqual([x for x in self.eventArray1],
                             [x for x in self.eventArray1.iterSlice()])

    # TODO talk to david about how to test these
    def testIterValues(self):
        """ Test for itervalues method. """
        self.mockData()
        self.eventArray1.iterSlice = self.mockIterSlice

        self.assertEqual([tuple(x) for x in self.eventArray1.itervalues()],
                         [(i,) for i in (1, 2, 3, 4)])
        self.assertEqual(self.iterArgs, (None, None, None, False))

    def testArrayValues(self):
        """ Test for arrayValues method. """

        # Stub data/methods
        eventArray = mock.Mock(spec=EventArray, hasSubchannels=True)

        blockDataStub = np.array(
            [(0, (i,)) for i in [1, 2, 3, 4]],
            dtype=[
                ('time', np.float),
                ('channels', [('ch0'.format(i), np.int)])
            ]
        )
        eventArray._data = [mock.Mock(startTime=0, indexRange=[0, 3],
                                      sampleTime=1, numSamples=1)]
        eventArray.arraySlice = mock.Mock(spec=EventArray.arraySlice,
                                          return_value=blockDataStub)

        # Run tests
        self.assertArrayEqual(
            EventArray.arrayValues(
                eventArray,
                start=mock.sentinel.start,
                end=mock.sentinel.end,
                step=mock.sentinel.step,
                display=mock.sentinel.display,
                subchannels=iter([0])
            ),
            blockDataStub['channels']
        )
        self.assertEqual(
            eventArray.arraySlice.call_args[0],
            (
                mock.sentinel.start,
                mock.sentinel.end,
                mock.sentinel.step,
                mock.sentinel.display,
            )
        )

    def testIterSlice(self):
        """ Test for the iterSlice method. """
        self.eventArray1._data = [GenericObject() for _ in xrange(4)]
        for i, b in enumerate(self.eventArray1._data):
            b.id = i
            b.indexRange = (i, i)
        self.eventArray1._fullXform = lambda x, session, noBivariates: x

        self.eventArray1._getBlockIndexWithIndex = (
            lambda idx, start=0, stop=None: idx
        )
        self.eventArray1.parent.parseBlock = (
            lambda block, start, end, step, subchannel=None: [
                np.array([(b.id+1,)] * ((end-start)//step),
                         dtype=[('ch0', np.int)])
                for b in self.eventArray1._data
            ][block.id]
        )

        self.assertListEqual(
            [
                (x['time'], tuple(x['channels']))
                for x in self.eventArray1.iterSlice()
            ],
            [(0, (i,)) for i in [1, 2, 3, 4]],
        )

    def testArraySlice(self):
        """ Test for the arraySlice method. """
        self.eventArray1._data = [GenericObject() for _ in xrange(4)]
        for i, b in enumerate(self.eventArray1._data):
            b.id = i
            b.indexRange = (i, i)
        self.eventArray1._fullXform = lambda x, session, noBivariates: x

        self.eventArray1._getBlockIndexWithIndex = (
            lambda idx, start=0, stop=None: idx
        )
        self.eventArray1.parent.parseBlock = (
            lambda block, start, end, step, subchannel=None: [
                np.array([(b.id+1,)] * ((end-start)//step),
                         dtype=[('ch0', np.int)])
                for b in self.eventArray1._data
            ][block.id]
        )

        self.assertArrayEqual(
            self.eventArray1.arraySlice(),
            np.array(
                [(0, (i,)) for i in [1, 2, 3, 4]],
                dtype=[
                    ('time', np.int),
                    ('channels', [('ch0'.format(i), np.int)])
                ]
            )
        )

    def testIterJitterySlice(self):
        """ Test for the iterJitterySlice method. """

        # Stub data/methods
        self.eventArray1._data = [GenericObject() for _ in xrange(4)]
        for i, b in enumerate(self.eventArray1._data):
            b.id = i
            b.indexRange = (i, i)
        self.eventArray1._fullXform = lambda x, session, noBivariates: x

        self.eventArray1._getBlockIndexWithIndex = (
            lambda idx, start=0, stop=None: idx
        )
        self.eventArray1.parent.parseBlockByIndex = (
            lambda block, indices: [
                np.array([(b.id+1,)] * len(indices),
                         dtype=[('ch0', np.int)])
                for b in self.eventArray1._data
            ][block.id]
        )

        # Run tests
        self.assertListEqual(
            [
                (x['time'], tuple(x['channels']))
                for x in self.eventArray1.iterJitterySlice()
            ],
            [(0, (i,)) for i in [1, 2, 3, 4]],
        )

    def testArrayJitterySlice(self):
        """ Test for the arrayJitterySlice method. """
        self.eventArray1._data = [GenericObject() for _ in xrange(4)]
        for i, b in enumerate(self.eventArray1._data):
            b.id = i
            b.indexRange = (i, i)
        self.eventArray1._fullXform = lambda x, session, noBivariates: x

        self.eventArray1._getBlockIndexWithIndex = (
            lambda idx, start=0, stop=None: idx
        )
        self.eventArray1.parent.parseBlockByIndex = (
            lambda block, indices: [
                np.array([(b.id+1,)] * len(indices),
                         dtype=[('ch0', np.int)])
                for b in self.eventArray1._data
            ][block.id]
        )

        self.assertArrayEqual(
            self.eventArray1.arrayJitterySlice(),
            np.array(
                [(0, (i,)) for i in [1, 2, 3, 4]],
                dtype=[
                    ('time', np.int),
                    ('channels', [('ch0'.format(i), np.int)])
                ]
            )
        )

    def testGetEventIndexBefore(self):
        """ Test for getEventIndexBefore method. """
        self.mockData()

        self.assertEqual(self.eventArray1.getEventIndexBefore(1), 1)
        self.assertEqual(self.eventArray1.getEventIndexBefore(-1), -1)

    def testGetEventIndexNear(self):
        """ Test for getEventIndexNear method. """

        # Stub data/methods
        eventArray = mock.Mock(spec=EventArray)
        eventArray._data = [mock.Mock(startTime=0, indexRange=[0, 3],
                                      sampleTime=1, numSamples=1)]
        eventArray.getEventIndexBefore = lambda t: int(t)
        eventArray.__getitem__ = (
            lambda self, index: np.array(
                [
                    (i, (i+1,))
                    for i in range(index.start or 0, index.stop,
                                   index.step or 1)
                ],
                dtype=[('time', '<f4'), ('channels', [('ch0', '<i4')])],
            )
        )

        # Tests
        self.assertEqual(EventArray.getEventIndexNear(eventArray, -1), 0)
        self.assertEqual(EventArray.getEventIndexNear(eventArray, 0), 0)
        self.assertEqual(EventArray.getEventIndexNear(eventArray, 1), 1)
        self.assertEqual(EventArray.getEventIndexNear(eventArray, -1), 0)

    def testGetRangeIndices(self):
        """ Test for getRangeIndices method. """
        self.mockData()

        # input permutations for multi sample
        self.assertEqual(self.eventArray1.getRangeIndices(1, 2), (2, 2))
        self.assertEqual(self.eventArray1.getRangeIndices(None, 2), (0, 2))
        self.assertEqual(self.eventArray1.getRangeIndices(None, None), (0, 3))
        self.assertEqual(self.eventArray1.getRangeIndices(2, -51), (3, 0))

        # input permutations for single sample
        self.eventArray1.parent.singleSample = True
        self.assertEqual(self.eventArray1.getRangeIndices(2, -51), (0, 1))
        self.assertEqual(self.eventArray1.getRangeIndices(2, None), (0, 3))

    def testIterRange(self):
        """ Test for iterRange method. """
        self.mockData()
        self.eventArray1.iterSlice = lambda w, x, y, display: (w+1, x, y, display)

        self.assertEqual(
            self.eventArray1.iterRange(1, 3, 1, display=False),
            self.eventArray1.iterSlice(2, 3, 1, display=False)
        )

    def testArrayRange(self):
        """ Test for arrayRange method. """
        self.mockData()
        self.eventArray1.arraySlice = (
            lambda w, x, y, display: np.array([w+1, x, y, display])
        )

        self.assertArrayEqual(
            self.eventArray1.arrayRange(1, 3, 1, display=False),
            self.eventArray1.arraySlice(2, 3, 1, display=False)
        )

    def testGetRange(self):
        """ Test for getRange method. """
        self.mockData()
        self.eventArray1.arrayRange = lambda x, y, display: (x, y, display)

        self.assertSequenceEqual(self.eventArray1.getRange(),
                                 [None, None, False])

    def testIterMinMeanMax(self):
        """ Test for iterMinMeanMax method. """
        self.mockData()
        self.eventArray1._data[0].minMeanMax = 1
        self.eventArray1._data[0].blockIndex = 2
        self.eventArray1._data[0].min = [3]
        self.eventArray1._data[0].mean = [4]
        self.eventArray1._data[0].max = [5]

        self.assertListEqual(
            [x for x in self.eventArray1.iterMinMeanMax()],
            [[(0, (3,)), (0, (4,)), (0, (5,))]]
        )

    def testArrayMinMeanMax(self):
        """ Test arrayMinMeanMax. """
        # TODO test other hasSubchannels x times combos

        # Stub data/methods
        eventArray = mock.Mock(spec=EventArray)
        eventArray.iterMinMeanMax = mock.Mock(spec=EventArray.iterMinMeanMax)

        statsStub = [[(0., (3,)), (0., (4,)), (0., (5,))]]
        eventArray.hasSubchannels = True
        eventArray.iterMinMeanMax.return_value = iter(statsStub)

        # Run tests
        result = EventArray.arrayMinMeanMax(eventArray)
        self.assertArrayEqual(
            result,
            np.array(statsStub[0], dtype=result.dtype)
        )

    def testGetMinMeanMax(self):
        """ Test getMinMeanMax. """

        # Stub data/methods
        eventArray = mock.Mock(spec=EventArray)
        eventArray.arrayMinMeanMax = mock.Mock(
            spec=EventArray.arrayMinMeanMax,
            return_value=mock.sentinel.return_value
        )
        args = (mock.sentinel.startTime, mock.sentinel.endTime,
                mock.sentinel.padding, mock.sentinel.times,
                mock.sentinel.display)

        self.assertEqual(EventArray.getMinMeanMax(eventArray, *args),
                         mock.sentinel.return_value)
        self.assertEqual(eventArray.arrayMinMeanMax.call_args, (args,))

    def testGetRangeMinMeanMax(self):
        """ Test for getRangeMinMeanMax method. """

        eventArray = mock.Mock(spec=EventArray, hasSubchannels=True)

        chDtypeDesc = [('ch0', '<i4'), ('ch1', '<f4')]
        statsStub = np.array(
            [
                ((3, 4.), (5, 6.), (7, 8.)),
                ((10, 11.), (12, 13.), (14, 15.)),
            ],
            dtype=[(stat, chDtypeDesc) for stat in ('min', 'mean', 'max')]
        )
        eventArray.arrayMinMeanMax = mock.Mock(spec=EventArray.arrayMinMeanMax,
                                               return_value=statsStub)

        self.assertSequenceEqual(EventArray.getRangeMinMeanMax(eventArray),
                                 (3, 9, 15), seq_type=tuple)

    def testGetMax(self):
        """ Test for getMax method. """

        # Stub data/methods
        eventArray = mock.Mock(spec=EventArray, hasSubchannels=True)

        chDtypeDesc = [('ch0', '<i4'), ('ch1', '<f4')]
        statsStub = np.array(
            [
                ((3, 4.), (5, 6.), (7, 8.)),
                ((10, 11.), (12, 13.), (14, 15.)),
            ],
            dtype=[(stat, chDtypeDesc) for stat in ('min', 'mean', 'max')]
        )
        timesValsStub = np.array(
            [(0, (10, 15.,)), (0.5, (14, 11.,))],
            dtype=[('time', '<f4'), ('channels', chDtypeDesc)],
        )

        eventArray._data = [mock.Mock(startTime=0, indexRange=[0, 2],
                                      sampleTime=1, numSamples=2)] * 2
        eventArray.arrayMinMeanMax = mock.Mock(spec=EventArray.arrayMinMeanMax,
                                               return_value=statsStub)
        eventArray.arraySlice = mock.Mock(spec=EventArray.arraySlice,
                                          return_value=timesValsStub)

        # Run tests
        self.assertEqual(EventArray.getMax(eventArray), timesValsStub[0])

    def testGetMin(self):
        """ test for getMin method. """

        # Stub data/methods
        eventArray = mock.Mock(spec=EventArray, hasSubchannels=True,
                               hasMinMeanMax=False)

        chDtypeDesc = [('ch0', '<i4'), ('ch1', '<f4')]
        statsStub = np.array(
            [
                ((3, 4.), (5, 6.), (7, 8.)),
                ((10, 11.), (12, 13.), (14, 15.)),
            ],
            dtype=[(stat, chDtypeDesc) for stat in ('min', 'mean', 'max')]
        )
        timesValsStub = np.array(
            [(0, (7, 4.,)), (0.5, (3, 8.,))],
            dtype=[('time', '<f4'), ('channels', chDtypeDesc)],
        )

        eventArray._data = [mock.Mock(startTime=0, indexRange=[0, 2],
                                      sampleTime=1, numSamples=2)] * 2
        eventArray.arrayMinMeanMax = mock.Mock(spec=EventArray.arrayMinMeanMax,
                                               return_value=statsStub)
        eventArray.arraySlice = mock.Mock(spec=EventArray.arraySlice,
                                          return_value=timesValsStub)

        # Run tests
        self.assertEqual(EventArray.getMin(eventArray), timesValsStub[1])
        self.assertEqual(eventArray._computeMinMeanMax.call_count, 1)

    def testGetSampleTime(self):
        """ Test for getSampleTime method. """
        self.mockData()

        self.assertEqual(self.eventArray1.getSampleTime(), 1)
        self.assertEqual(self.eventArray1.getSampleTime(1), 1)
        self.assertEqual(
            self.dataset.channels[32].getSession().getSampleTime(), -1
        )
        self.assertEqual(
            self.dataset.channels[32].getSession().getSampleTime(1), -1
        )

    def testGetSampleRate(self):
        """ Test for getSampleRate method. """
        self.mockData()
        self.eventArray1._data[0].sampleRate = 5
        self.dataset.channels[32].sampleRate = 3
        self.dataset.channels[32].getSession()._data = self.eventArray1._data

        self.assertEqual(self.eventArray1.getSampleRate(), 5)
        self.assertEqual(self.eventArray1.getSampleRate(0), 5)
        self.assertEqual(self.dataset.channels[32].getSession().getSampleRate(), 3)
        self.assertEqual(self.dataset.channels[32].getSession().getSampleRate(0), 5)

    def testGetValueAt(self):
        """ Test for getValueAt method. """
        # mocking
        self.mockData()
        fakeData = GenericObject()
        fakeData.numSamples = 1
        fakeData.startTime = 0
        fakeData.endTime = 4
        fakeData.minMeanMax = (5, 6, 7)
        fakeData.parseMinMeanMax = lambda x: x

        self.eventArray1.append(fakeData)

        # bonus mocking.  repeating for every test to ensure that it's sending
        # the values it needs to
        self.eventArray1._fullXform = self.mockXform
        self.mockXformReturn = [[0], [0], 0, [0]]
        self.assertEqual(self.eventArray1.getValueAt(0, outOfRange=True),
                         [[0], [0], 1, [0]])

        self.mockXformReturn = [[0], [0], -1, [0]]
        self.assertEqual(self.eventArray1.getValueAt(0),
                         [[0], [0], 0, [0]])

        self.mockXformReturn = [[0], [0], -1, [0]]
        self.eventArray1.getEventIndexBefore = lambda x: 1
        self.assertEqual(self.eventArray1.getValueAt(0),
                         [[0], [0], 0, [0]])

        self.mockXformReturn = [[0], [0], -1, [0]]
        self.eventArray1.getEventIndexBefore = lambda x: 0
        self.mockXformReturn = [[0], [0], 0, [0]]
        self.assertEqual(self.eventArray1.getValueAt(0),
                         (0, (0.0,)))

    def testGetMeanNear(self):
        """ Test for getMeanNear method. """
        # mock everthing up
        self.mockData()

        def mockComboXform(*args, **kwargs):
            self.comboArgs = args
            self.comboKwargs = kwargs

            return [[0]]

        self.eventArray1._comboXform = mockComboXform
        self.eventArray1._data[0].minMeanMax = 0
        self.eventArray1._data[0]._rollingMean = 0
        self.eventArray1._data[0]._rollingMeanSpan = 0
        self.eventArray1._data[0].mean = 0

        self.assertEqual(self.eventArray1.getMeanNear(0), [0])
        self.assertEqual(self.comboArgs, ((0, 0),))
        self.assertEqual(self.comboKwargs, {})

        # test for an eventlist with no subchannels
        self.eventArray1.hasSubchannels = False
        self.eventArray1.subchannelId = 0

        self.assertEqual(self.eventArray1.getMeanNear(0), 0)
        self.assertEqual(self.comboArgs, ((0, 0),))
        self.assertEqual(self.comboKwargs, {})

    def testIterResampledRange(self):
        """ Test for iterResampledRange method. """
        
        # Stub data/methods
        eventArray = mock.Mock(spec=EventArray)
        eventArray.__len__ = lambda self: 100
        eventArray.getRangeIndices.return_value = 0, 105

        eventArray.iterSlice.return_value = mock.sentinel.a
        eventArray.iterJitterySlice.return_value = mock.sentinel.b

        startTime = mock.sentinel.startTime
        stopTime = mock.sentinel.stopTime
        maxPoints = 43

        # Run tests
        self.assertEqual(
            EventArray.iterResampledRange(eventArray, startTime, stopTime,
                                          maxPoints),
            mock.sentinel.a
        )
        startIdx, stopIdx, step = (
            eventArray.iterSlice.call_args[0]
        )
        self.assertTrue(startIdx >= 0)
        self.assertTrue(stopIdx <= len(eventArray))
        self.assertTrue(len(xrange(startIdx, stopIdx, step)) <= maxPoints)

        self.assertEqual(
            EventArray.iterResampledRange(eventArray, startTime, stopTime,
                                          maxPoints, jitter=0.1,),
            mock.sentinel.b
        )
        startIdx, stopIdx, step, jitter = (
            eventArray.iterJitterySlice.call_args[0]
        )
        self.assertTrue(startIdx >= 0)
        self.assertTrue(stopIdx <= len(eventArray))
        self.assertTrue(len(xrange(startIdx, stopIdx, step)) <= maxPoints)

    def testArrayResampledRange(self):
        """ Test for arrayResampledRange method. """
        
        # Stub data/methods
        eventArray = mock.Mock(spec=EventArray)
        eventArray.__len__ = lambda self: 100
        eventArray.getRangeIndices.return_value = 0, 105

        eventArray.arraySlice.return_value = mock.sentinel.a
        eventArray.arrayJitterySlice.return_value = mock.sentinel.b

        startTime = mock.sentinel.startTime
        stopTime = mock.sentinel.stopTime
        maxPoints = 43

        # Run tests
        self.assertEqual(
            EventArray.arrayResampledRange(eventArray, startTime, stopTime,
                                          maxPoints),
            mock.sentinel.a
        )
        startIdx, stopIdx, step = (
            eventArray.arraySlice.call_args[0]
        )
        self.assertTrue(startIdx >= 0)
        self.assertTrue(stopIdx <= len(eventArray))
        self.assertTrue(len(xrange(startIdx, stopIdx, step)) <= maxPoints)

        self.assertEqual(
            EventArray.arrayResampledRange(eventArray, startTime, stopTime,
                                          maxPoints, jitter=0.1,),
            mock.sentinel.b
        )
        startIdx, stopIdx, step, jitter = (
            eventArray.arrayJitterySlice.call_args[0]
        )
        self.assertTrue(startIdx >= 0)
        self.assertTrue(stopIdx <= len(eventArray))
        self.assertTrue(len(xrange(startIdx, stopIdx, step)) <= maxPoints)

    def testExportCSV(self):
        """ Test for exportCsv method."""
        self.mockData()
        self.eventArray1._data[0].minMeanMax = 1
        self.eventArray1._data[0].blockIndex = 2
        self.eventArray1._data[0].min = [3]
        self.eventArray1._data[0].mean = [4]
        self.eventArray1._data[0].max = [5]


#===============================================================================
#
#===============================================================================

class PlotTestCase(unittest.TestCase):
    """ Unit test for the Plot class. """
    
    def setUp(self):
        self.dataset = importer.importFile('./SSX70065.IDE')
        self.dataset.addSession(0, 1, 2)
        self.dataset.addSensor(0)
        
        self.fakeParser = GenericObject()
        self.fakeParser.types = [0]
        self.fakeParser.format = []
        
        self.channel1 = Channel(
            self.dataset, channelId=0, name="channel1", parser=self.fakeParser,
            displayRange=[0])
        self.eventList1 = EventList(self.channel1, session=self.dataset.sessions[0])
        
        self.channel1.addSubChannel(subchannelId=0)
        
        self.subChannel1 = SubChannel(self.channel1, 0)
        
        self.plot1 =  Plot(self.eventList1, 0, name="Plot1")
    
    
    def tearDown(self):
        self.dataset.close()
        self.dataset = None
        
        self.fakeParser = None
        self.channel1 = None
        self.eventList1 = None
        self.subChannel1 = None
        self.plot1 = None
    
    
    def mockData(self):
        """ mock up a bit of fake data so I don't have to worry that external
            classes are working during testing.
        """
        fakeData = GenericObject()
        fakeData.startTime = 0
        fakeData.indexRange = [0, 3]
        fakeData.sampleTime = 1
        fakeData.numSamples = 1
        self.eventList1._data = [fakeData]
    
    
    def testConstructor(self):
        """ Test for the constructor. """
        self.assertEqual(self.plot1.source, self.eventList1)
        self.assertEqual(self.plot1.id, 0)
        self.assertEqual(self.plot1.session, self.eventList1.session)
        self.assertEqual(self.plot1.dataset, self.eventList1.dataset)
        self.assertEqual(self.plot1.name, "Plot1")
        self.assertEqual(self.plot1.units, self.eventList1.units)
        self.assertEqual(self.plot1.attributes, None)
        
        
    def testGetEventIndexBefore(self):
        """ Test for getEventIndexBefore method. """
        self.mockData()
        
        self.assertEqual(
            self.plot1.getEventIndexBefore(0), 
            self.eventList1.getEventIndexBefore(0))
        
        
    def testGetRange(self):
        """ Test for getRange method. """
        print('gotta get to this')#self.plot1.getRange(0, 1))
        # TODO


#===============================================================================
#--- Data test cases 
#===============================================================================

class DataTestCase(unittest.TestCase):
    """ Basic tests of data fidelity against older, "known good" CSV exports.
        Exports were generated using the library as of the release of 1.8.0.

        Tests are done within a threshold of 0.0015g to account for rounding
        errors. 
    """

    def setUp(self):
        self.dataset = importer.importFile('./SSX_Data.IDE')
        self.delta = 0.0015


    def testCalibratedExport(self):
        """ Test regular export, with bivariate polynomials applied.
        """
        out = StringIO()
        accel = self.dataset.channels[8].getSession()

        accel.exportCsv(out)
        out.seek(0)
        
        with open('./SSX_Data_Ch8_Calibrated.csv', 'rb') as f:
            for new, old in zip(out, f):
#                 self.assertEqual(old.strip(), new.strip())
                for a,b in zip(eval(new),eval(old)):
                    self.assertAlmostEqual(a, b, delta=self.delta, 
                                           msg="Output differs: %r != %r" %
                                           (old,new))

    
    def testUncalibratedExport(self):
        """ Test export with no per-channel polynomials.
        """
        self.dataset.channels[8][0].setTransform(None)
        self.dataset.channels[8][1].setTransform(None)
        self.dataset.channels[8][2].setTransform(None)

        out = StringIO()
        accel = self.dataset.channels[8].getSession()

        accel.exportCsv(out)
        out.seek(0)
        
        with open('./SSX_Data_Ch8_NoCalibration.csv', 'rb') as f:
            for new, old in zip(out, f):
#                 self.assertEqual(old.strip(), new.strip())
                for a,b in zip(eval(new),eval(old)):
                    self.assertAlmostEqual(a, b, delta=self.delta, 
                                           msg="Output differs: %r != %r" %
                                           (old,new))


    def testNoBivariates(self):
        """ Test export with bivariate polynomial references disabled (values
            only offset, not temperature-corrected).
        """
        out = StringIO()
        accel = self.dataset.channels[8].getSession()
        accel.noBivariates = True

        accel.exportCsv(out)
        out.seek(0)
        
        with open('./SSX_Data_Ch8_NoBivariates.csv', 'rb') as f:
            for new, old in zip(out, f):
#                 self.assertEqual(old.strip(), new.strip())
                for a,b in zip(eval(new),eval(old)):
                    self.assertAlmostEqual(a, b, delta=self.delta, 
                                           msg="Output differs: %r != %r" %
                                           (old,new))


    def testRollingMeanRemoval(self):
        """ Test regular export, with the rolling mean removed from the data.
        """
        self.dataset.channels[8][0].setTransform(None)
        self.dataset.channels[8][1].setTransform(None)
        self.dataset.channels[8][2].setTransform(None)
        
        out = StringIO()
        accel = self.dataset.channels[8].getSession()
        accel.removeMean = True
        accel.rollingMeanSpan = 5000000

        accel.exportCsv(out)
        out.seek(0)
        
        with open('./SSX_Data_Ch8_RollingMean_NoCal.csv', 'rb') as f:
            for new, old in zip(out, f):
                for a,b in zip(eval(new),eval(old)):
                    self.assertAlmostEqual(a, b, delta=self.delta, 
                                           msg="Output differs: %r != %r" %
                                           (old,new))

    
    def testTotalMeanRemoval(self):
        """ Test regular export, calibrated, with the total mean removed from
            the data.
        """
        self.dataset.channels[8][0].setTransform(None)
        self.dataset.channels[8][1].setTransform(None)
        self.dataset.channels[8][2].setTransform(None)

        out = StringIO()
        accel = self.dataset.channels[8].getSession()
        accel.removeMean = True
        accel.rollingMeanSpan = -1

        accel.exportCsv(out)
        out.seek(0)
        
        with open('./SSX_Data_Ch8_TotalMean_NoCal.csv', 'rb') as f:
            for new, old in zip(out, f):
                for a,b in zip(eval(new),eval(old)):
                    self.assertAlmostEqual(a, b, delta=self.delta, 
                                           msg="Output differs: %r != %r" %
                                           (old,new))
    

    def testCalibratedRollingMeanRemoval(self):
        """ Test regular export, calibrated, with the rolling mean removed from
            the data.
        """
        out = StringIO()
        accel = self.dataset.channels[8].getSession()
        accel.removeMean = True
        accel.rollingMeanSpan = 5000000

        accel.exportCsv(out)
        out.seek(0)
        
        with open('./SSX_Data_Ch8_RollingMean.csv', 'rb') as f:
            for new, old in zip(out, f):
                for a,b in zip(eval(new),eval(old)):
                    self.assertAlmostEqual(a, b, delta=self.delta, 
                                           msg="Output differs: %r != %r" %
                                           (old,new))

    
    def testCalibratedTotalMeanRemoval(self):
        """ Test regular export, with the total mean removed from the data.
        """
        out = StringIO()
        accel = self.dataset.channels[8].getSession()
        accel.removeMean = True
        accel.rollingMeanSpan = -1

        accel.exportCsv(out)
        out.seek(0)
        
        with open('./SSX_Data_Ch8_TotalMean.csv', 'rb') as f:
            for new, old in zip(out, f):
                for a,b in zip(eval(new),eval(old)):
                    self.assertAlmostEqual(a, b, delta=self.delta, 
                                           msg="Output differs: %r != %r" %
                                           (old,new))
    

#===============================================================================
# 
#===============================================================================

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
                    "transform": AccelTransform(-500,500),
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
        