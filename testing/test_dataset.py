"""
Basic IDE library unit tests.

@todo: Remove `Cascading` and `Transformable` unit tests? Those base/mix-in 
    classes were intended to be used internally, and may be factored out
    eventually.
@todo: Remove references to deprecated `parsers.AccelerometerParser` and
    `calibration.AccelTransform`. These classes may be refactored out in the
    future.
"""
import struct
from io import StringIO, BytesIO
import sys
import unittest
import mock

import pytest

import numpy as np  # type: ignore

from idelib.dataset import (Cascading,
                            Channel,
                            Dataset,
                            EventArray,
                            Plot,
                            Sensor,
                            Session,
                            SubChannel,
                            Transformable,
                            WarningRange,
                            )
from idelib.transforms import Transform, CombinedPoly, PolyPoly
from idelib.transforms import AccelTransform, Univariate
from idelib import importer
from idelib import parsers

from testing.utils import nullcontext

from .file_streams import makeStreamLike


# ==============================================================================
# Fixtures
# ==============================================================================

_fileStrings = {}


def _load_file(filePath):
    if filePath not in _fileStrings:
        with open(filePath, 'rb') as f:
            _fileStrings[filePath] = f.read()
    out = BytesIO(_fileStrings[filePath])
    out.name = filePath
    return out


@pytest.fixture
def testIDE():
    doc = importer.openFile(_load_file('./test.ide'))
    importer.readData(doc)
    return doc


@pytest.fixture
def SSX70065IDE():
    doc = importer.openFile(_load_file('./testing/SSX70065.IDE'))
    importer.readData(doc)
    return doc


@pytest.fixture
def SSX_DataIDE():
    doc = importer.openFile(_load_file('./testing/SSX_Data.IDE'))
    importer.readData(doc)
    return doc


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

class TestCascading(unittest.TestCase):
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

class TestTransformable(unittest.TestCase):
    """ Test case for methods in the Transformable class. """
    def setUp(self):

        # create objects to be used during testing
        self.xform1 = Transformable()
        self.genericObject = GenericObject()

        # configure above objects
        fileStream = makeStreamLike('./testing/SSX70065.IDE')
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

class TestDataset(unittest.TestCase):
    """ Test case for methods in the Dataset class. """

    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.fileStream = makeStreamLike('./testing/SSX70065.IDE')
        self.dataset = Dataset(self.fileStream)

        self.channelCheck = {}

        # Copied from importer.py:181
        self.channels = DEFAULTS['channels'].copy()
        for chId, chInfo in self.channels.items():
            chArgs = chInfo.copy()
            subchannels = chArgs.pop('subchannels', None)
            self.channelCheck[chId] = Channel(self.dataset, chId, **chArgs.copy())
            channel = self.dataset.addChannel(chId, **chArgs)
            self.assertEqual(channel, self.dataset.channels[chId])
            if subchannels is None:
                continue
            for subChId, subChInfo in subchannels.items():
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
        self.assertEqual(self.dataset._channels, self.channelCheck)
        self.assertEqual(self.dataset._parsers, None)

        self.assertEqual(self.dataset.currentSession, None)
#         self.assertEqual(
#             self.dataset.ebmldoc,
#             loadSchema(SCHEMA_FILE).load(self.fileStream, 'MideDocument'))
        self.assertEqual(self.dataset.fileDamaged, False)
        self.assertEqual(
            self.dataset.filename, getattr(self.fileStream, "name", None))
        self.assertEqual(self.dataset.lastUtcTime, None)
        self.assertEqual(self.dataset.loadCancelled, False)
        self.assertEqual(self.dataset.loading, True)
        self.assertEqual(self.dataset.name, 'SSX70065')
        self.assertEqual(self.dataset.parent, None)
        self.assertEqual(self.dataset.plots, {})
        self.assertEqual(self.dataset.recorderConfig, None)
        self.assertEqual(self.dataset.recorderInfo, {})
        self.assertEqual(self.dataset.schemaVersion, 2)
        self.assertEqual(self.dataset.sensors, {})
        self.assertEqual(self.dataset.sessions, [])
        self.assertEqual(self.dataset.subsets, [])
        self.assertEqual(self.dataset.transforms, {})
        self.assertEqual(self.dataset.warningRanges, {})


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
        self.assertEqual(subs, self.dataset.getPlots(sort=False))

        subs.sort(key=lambda x: x.displayName)
        self.assertEqual(subs, self.dataset.getPlots())


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

class TestSession(unittest.TestCase):
    """ Test case for methods in the Session class. """

    def testInitAndEQ(self):
        self.dataset = importer.importFile('./testing/SSX70065.IDE')
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
        fileStream = makeStreamLike('./testing/SSX70065.IDE')
        dataset = Dataset(fileStream)
        session1 = Session(
            dataset, sessionId=1, startTime=2, endTime=3, utcStartTime=4)
        self.assertIn("<Session (id=1) at", repr(session1))


#===============================================================================
# 
#===============================================================================

class TestSensor(unittest.TestCase):
    """ Test case for methods in the Sensor class. """

    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.dataset = importer.importFile('./testing/SSX70065.IDE')

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

class TestChannel(unittest.TestCase):
    """ Test case for methods in the Channel class. """

    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.dataset = importer.importFile('./testing/SSX70065.IDE')
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
        self.assertEqual(self.channel1.subsampleCount, [0,sys.maxsize])
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
        self.assertEqual(self.channel2.subsampleCount, [0,sys.maxsize])
        self.assertEqual(self.channel2._lastParsed, (None, None))
        self.assertFalse(self.channel2.allowMeanRemoval)


    def testChildren(self):
        """ Test the children property. """
        self.assertEqual(self.channel1.children, list(iter(self.channel1)))


    def testRepr(self):
        """ Test the repr special method. """
        self.assertIn("<Channel 0 %r" % 'channel1', repr(self.channel1))


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
        eventArray = EventArray(self.channel1, self.dataset.lastSession)
        self.assertEqual(self.channel1.getSession(), eventArray)
        self.assertEqual(self.channel1.getSession(),
                         self.channel1.getSession(1))
        self.assertRaises(KeyError, self.channel1.getSession, 5)


    def testParseBlock(self):
        """ Test the parseBlock method. """
        fakeBlock = GenericObject()
        self.assertEqual(self.channel1.parseBlock(fakeBlock),
                         [self.channel1.parser, None, None, 1, None])
        self.assertEqual(self.channel1._lastParsed[0],
                         (fakeBlock, None, None, 1, None))
        self.assertEqual(self.channel1._lastParsed[1],
                         [self.channel1.parser, None, None, 1, None])


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

class TestSubChannel:
    """ Test case for methods in the SubChannel class. """

    @pytest.fixture
    def dataset(self, SSX70065IDE):
        SSX70065IDE.addSensor(0)
        return SSX70065IDE

    @pytest.fixture
    def fakeParser(self):
        return struct.Struct(b'<hh')

    @pytest.fixture
    def sensor1(self, dataset):
        return Sensor(dataset, 2, '3', 4, 5, 6, 7)

    @pytest.fixture
    def channel1(self, dataset, fakeParser):
        return Channel(
                dataset,
                channelId=0,
                name="channel1",
                parser=fakeParser,
                displayRange=[0],
                )

    @pytest.fixture
    def channel2(self, dataset, fakeParser, sensor1):
        return Channel(
                dataset,
                channelId=2,
                parser=fakeParser,
                sensor=sensor1,
                name="channel2",
                units=6,
                displayRange=[8],
                sampleRate=9,
                cache=10,
                singleSample=11,
                attributes=12,
                )

    @pytest.fixture
    def subChannel1(self, channel2):
        return SubChannel(
                channel2,
                0,
                name=None,
                units=('a', 'b'),
                transform=3,
                displayRange=[4],
                sensorId=5,
                warningId=6,
                axisName=7,
                attributes=8,
                )

    def setUp(self):
        """ Open a file for testing in a new dataset. """
        self.dataset = importer.importFile('./testing/SSX70065.IDE')
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
                                      units=('a', 'b'), transform=3,
                                      displayRange=[4], sensorId=5, warningId=6,
                                      axisName=7, attributes=8)


    def tearDown(self):
        """ Close and dispose of the file. """
        self.dataset.close()
        self.dataset = None
        self.channel1 = None
        self.channel2 = None
        self.fakeParser = None

    def testInit(self, dataset, channel1, channel2, subChannel1):
        """ Test the constructor for SubChannel. """
        assert subChannel1.id == 0
        assert subChannel1.parent == channel2
        assert subChannel1.warningId == 6
        assert subChannel1.cache == channel2.cache
        assert subChannel1.dataset == dataset
        assert subChannel1.axisName == 7
        assert subChannel1.attributes == 8
        assert subChannel1.name == "channel2:00"
        assert subChannel1.units == ('a', 'b')
        assert subChannel1.displayName == 'a'
        assert subChannel1.sensor == channel1.sensor
        assert subChannel1.types == (channel1.types[0], )
        assert subChannel1.displayRange == [4]
        assert subChannel1.hasDisplayRange is True
        assert subChannel1.allowMeanRemoval == channel2.allowMeanRemoval
        assert subChannel1.removeMean is False
        assert subChannel1.singleSample == channel2.singleSample

    def testChildren(self, subChannel1):
        """ Test the children property. """
        assert subChannel1.children == []

    def testSampleRate(self, subChannel1, channel2):
        """ Test the sampleRate property. """
        assert subChannel1.sampleRate == channel2.sampleRate

    def testRepr(self, subChannel1):
        """ Test the repr special method. """
        assert "<SubChannel 2.0 'SSX70065:3:channel2:channel2:00'" in repr(subChannel1)

    def testLen(self, subChannel1):
        """ Test the len special method. """
        with pytest.raises(AttributeError):
            len(subChannel1)

    def testParser(self, subChannel1, channel2):
        """ Test the parser property. """
        assert subChannel1.parser == channel2.parser

    def testSessions(self, subChannel1):
        """ Test the sessions property. """

        assert subChannel1.sessions == {}

        subChannel1._sessions = [1, 2]

        assert subChannel1.sessions == [1, 2]

    def testParseBlock(self, channel2, subChannel1):
        """ Test the parseBlock method.
            Run the same test as for Channel.
        """
        fakeBlock = GenericObject()

        assert channel2.parseBlock(fakeBlock) == subChannel1.parseBlock(fakeBlock)

    def testParseBlockByIndex(self, channel2, subChannel1):
        """ Test the parseBlockByIndex method.
            Run the same test as for Channel.
        """
        fakeBlock = GenericObject()

        assert channel2.parseBlockByIndex(fakeBlock, 1) == \
               subChannel1.parseBlockByIndex(fakeBlock, 1)

    def testGetSession(self, dataset, channel2, subChannel1):
        """ Test the getSession method. """
        # set up test
        subChannel1.dataset.addSession(0, 1, 2)
        channel2.subchannels = [GenericObject()]
        parentList = dataset.channels[32].getSession()
        parentList.dataset.addSession(0, 1, 2)
        eventArray = EventArray(
            subChannel1,
            session=dataset.lastSession,
            parentList=subChannel1.parent.getSession())

        # check the session was added
        assert subChannel1.getSession() == eventArray
        assert subChannel1._sessions[2] == eventArray
        assert subChannel1.getSession(2) == eventArray

    def testAddSubChannel(self, subChannel1):
        """ Test addSubChannel method.  This will throw an error. """
        with pytest.raises(AttributeError):
            subChannel1.addSubChannel()

    def testGetSubchannel(self, subChannel1):
        """ Test getSubChannel method.  This will always throw an error. """
        with pytest.raises(AttributeError):
            subChannel1.getSubChannel()


#===============================================================================
#
#===============================================================================

class TestEventArray:
    """ Test case for methods in the EventArray class. """

    @pytest.fixture
    def dataset(self, SSX70065IDE):
        SSX70065IDE.addSession(0, 1, 2)
        SSX70065IDE.addSensor(0)

        return SSX70065IDE

    @pytest.fixture
    def fakeParser(self):
        parser = GenericObject()
        parser.types = [0]
        parser.format = []

        return parser

    @pytest.fixture
    def _channel1(self, dataset, fakeParser):
        return Channel(
            dataset, channelId=0, name="channel1", parser=fakeParser,
            displayRange=[0]
        )

    @pytest.fixture
    def eventArray1(self, _channel1, dataset):
        return EventArray(_channel1, session=dataset.sessions[0])

    @pytest.fixture
    def channel1(self, _channel1):
        _channel1.addSubChannel(subchannelId=0)

        return _channel1

    @pytest.fixture
    def subchannel1(self, channel1):
        return SubChannel(channel1, 0)

    @pytest.fixture
    def mockData(self, eventArray1):
        """ mock up a bit of fake data so I don't have to worry that external
            classes are working during testing.
        """
        fakeData = GenericObject()
        fakeData.startTime = 0
        fakeData.indexRange = [0, 4]
        fakeData.sampleTime = 1
        fakeData.numSamples = 1
        eventArray1._data = [fakeData]

    @pytest.fixture
    def channel8(self, testIDE):
        return testIDE.channels[8]

    @pytest.fixture
    def eventArray(self, channel8):
        return channel8.getSession()

    def mockIterSlice(self,  *args, **kwargs):
        """ Mock up iterslice so it doesn't get called while testing
            other methods.
        """
        self.iterArgs = args
        self.kwArgs = kwargs
        return iter(np.array([(0, 1), (0, 2), (0, 3), (0, 4)], dtype=np.float64))

    def mockArraySlice(self,  *args, **kwargs):
        """ Mock up iterslice so it doesn't get called while testing
            other methods.
        """
        self.iterArgs = args
        self.kwArgs = kwargs
        return np.array([(0, 1), (0, 2), (0, 3), (0, 4)], dtype=np.float64)

    def mockXform(self, times, session=None, noBivariates=None):
        self.xformArgs = (times, session, noBivariates)

        self.mockXformReturn[2] += 1

        return list(self.mockXformReturn)

    # --------------------------------------------------------------------------
    # Base Method Tests
    # --------------------------------------------------------------------------

    def testConstructor(self, eventArray1, channel1, dataset):
        """ Test the __init__ method. """
        assert eventArray1._blockIndices == []
        assert eventArray1._blockTimes == []
        assert eventArray1._childLists == []
        assert eventArray1._data == []
        assert eventArray1._firstTime is None
        assert eventArray1._hasSubsamples is False
        assert eventArray1._lastTime is None
        assert eventArray1._length == 0
        assert eventArray1._parentList is None
        assert eventArray1._singleSample == channel1.singleSample

        assert eventArray1.channelId == channel1.id
        assert eventArray1.dataset == channel1.dataset
        assert eventArray1.displayRange == channel1.displayRange
        assert eventArray1.hasMinMeanMax is True
        assert eventArray1.hasDisplayRange == channel1.hasDisplayRange
        assert eventArray1.hasSubchannels is True
        assert eventArray1.noBivariates is False
        assert eventArray1.parent == channel1
        assert eventArray1.removeMean is False
        assert eventArray1.rollingMeanSpan == EventArray.DEFAULT_MEAN_SPAN
        assert eventArray1.session == dataset.sessions[0]
        assert eventArray1.subchannelId is None

        assert eventArray1._blockIndicesArray.size == 0
        assert eventArray1._blockTimesArray.size == 0

    def testUpdateTransformsNoRecursion(self, eventArray1, channel1, dataset):
        """ Test the updateTransforms method. """
        # update transforms without recursion
        eventArray1.updateTransforms(False)
        assert eventArray1._comboXform == PolyPoly([channel1.transform]*len(channel1.types))

        xs = [c.transform if c is not None else None
              for c in channel1.subchannels]
        xs = [CombinedPoly(t, x=channel1.transform, dataset=dataset)
              for t in xs]
        assert eventArray1._fullXform == PolyPoly(xs, dataset=dataset)

    def testUpdateTransformsYesRecursion(self, eventArray1, channel1, dataset):

        # update transforms with recursion
        xs = [c.transform if c is not None else None
              for c in channel1.subchannels]
        xs = [CombinedPoly(t, x=channel1.transform, dataset=dataset)
              for t in xs]
        eventArray1.updateTransforms(True)
        assert eventArray1._displayXform == PolyPoly(xs, dataset=self.dataset)

    def testUpdateTransformsOther(self, eventArray1, channel1, dataset):

        # test for when there's a subchannel with a corresponding session
        eventArray1.session.sessionId = 'session0'
        eventArray1.parent.subchannels[0]._sessions = {'session0': eventArray1}
        eventArray1.updateTransforms()
        xs = [c.transform if c is not None else None
              for c in eventArray1.parent.subchannels]
        assert eventArray1._displayXform == PolyPoly(
                [CombinedPoly(eventArray1.transform, x=xs[0], dataset=dataset)],
                dataset=dataset,
                )

    def testUnits(self, eventArray1):
        """ Test the units property. """
        assert eventArray1.units == ('', '')

    def testPath(self, eventArray1):
        """ Test the path method. """
        assert eventArray1.path() == "channel1"

    def testCopy(self, eventArray1):
        """ Test the copy method. Since this is a shallow copy, don't use the
            build in equality check.
        """
        eventArrayCopy = eventArray1.copy()
        assert eventArray1.parent == eventArrayCopy.parent
        assert eventArray1.session == eventArrayCopy.session
        assert eventArray1.dataset == eventArrayCopy.dataset
        assert eventArray1.hasSubchannels == eventArrayCopy.hasSubchannels
        assert eventArray1.noBivariates == eventArrayCopy.noBivariates
        assert eventArray1.channelId == eventArrayCopy.channelId
        assert eventArray1.subchannelId == eventArrayCopy.subchannelId
        assert eventArray1.channelId == eventArrayCopy.channelId
        assert eventArray1.hasDisplayRange == eventArrayCopy.hasDisplayRange
        assert eventArray1.displayRange == eventArrayCopy.displayRange
        assert eventArray1.removeMean == eventArrayCopy.removeMean
        assert eventArray1.hasMinMeanMax == eventArrayCopy.hasMinMeanMax
        assert eventArray1.rollingMeanSpan == eventArrayCopy.rollingMeanSpan
        assert eventArray1.transform == eventArrayCopy.transform
        assert eventArray1.useAllTransforms == eventArrayCopy.useAllTransforms
        assert eventArray1.allowMeanRemoval == eventArrayCopy.allowMeanRemoval


    @unittest.skip('failing, poorly formed')
    def testAppend(self, eventArray1):
        """ Test the append method. """
        fakeData = GenericObject()
        fakeData.numSamples = 1
        fakeData.startTime = 2
        fakeData.endTime = 4
        fakeData.minMeanMax = (5, 6, 7)

        fakeData.parseMinMeanMax = lambda x: x

        # append boring basic fakeData
        eventArray1.append(fakeData)

        assert fakeData.blockIndex == 0
        assert fakeData.cache is False
        assert fakeData.indexRange == (0, 1)
        assert eventArray1._blockIndices == [0]
        assert eventArray1._blockTimes == [2]
        assert eventArray1._firstTime == 2
        assert eventArray1._lastTime == 4
        assert eventArray1._length == 1
        assert eventArray1._singleSample is True

        # append single sample fakeData
        eventArray1._singleSample = True

        eventArray1.append(fakeData)

        assert fakeData.blockIndex == 1
        assert fakeData.cache is False
        assert fakeData.indexRange == (1, 2)
        assert eventArray1._blockIndices == [0, 1]
        assert eventArray1._blockTimes == [2, 2]
        assert eventArray1._firstTime == 2
        assert eventArray1._lastTime == 4
        assert eventArray1._length == 2
        assert eventArray1._singleSample is True

        # append with times stripped out
        eventArray1.session.firstTime = None
        eventArray1.session.lastTime = None
        eventArray1._firstTime = None

        eventArray1.append(fakeData)

        assert fakeData.blockIndex == 2
        assert fakeData.cache is False
        assert fakeData.indexRange == (2, 3)
        assert eventArray1._blockIndices == [0, 1, 2]
        assert eventArray1._blockTimes == [2, 2, 2]
        assert eventArray1._firstTime == 2
        assert eventArray1._lastTime == 4
        assert eventArray1._length == 3
        assert eventArray1._singleSample is True

    def testGetInterval(self, dataset):
        """ Test the getInterval method. """
        fakeObject = GenericObject()
        fakeObject.startTime = 3
        fakeObject.endTime = 1
        accel = dataset.channels[32].getSession()

        # without _data, return None
        assert accel.getInterval() == None
        assert accel._lastTime is None

        # with mocked data
        accel._data = [fakeObject]
        assert accel.getInterval() == (3, 1)
        assert accel._lastTime == 1

        # with mocked data and a mocked dataset
        accel.dataset = GenericObject()
        accel.dataset.loading = True
        assert accel.getInterval() == (3, 1)

    @pytest.mark.parametrize(
            'idx, raises',
            [(0, nullcontext()),
             (5, nullcontext()),
             (100, nullcontext()),
             (-1, nullcontext()),
             (-500, nullcontext()),
             (1000, pytest.raises(IndexError)),
             ('d', pytest.raises(TypeError)),
             ])
    def testGetItem(self, eventArray, idx, raises):
        """ Test the getitem special method. """

        if isinstance(raises, nullcontext):
            x = idx
            if x < 0:
                x += 1000
            expected = np.floor(np.array([x*1000, x, 1000.*(x/1000)**2, 1000*(x/1000)**0.5]))
        else:
            expected = None

        with raises:
            np.testing.assert_array_equal(eventArray[idx], expected)

    def testIter(self, eventArray1):
        """ Test for iter special method. """
        eventArray1.iterSlice = self.mockIterSlice
        np.testing.assert_array_equal(
            [x for x in eventArray1],
            [x for x in eventArray1.iterSlice()]
        )

    @pytest.mark.parametrize('start, end, step',
                             [
                                 (None, None, 1),
                                 (None, None, 5),
                                 (10, 300, 3),
                                 ],
                             )
    def testIterValues(self, eventArray, start, end, step):
        """ Test for itervalues method. """

        values = np.stack(tuple(eventArray.itervalues(start, end, step))).T

        np.testing.assert_array_equal(values, eventArray.arrayValues(start, end, step))

    @pytest.mark.parametrize('start, end, step',
                             [
                                 (None, None, 1),
                                 (None, None, 5),
                                 (10, 300, 3),
                                 ],
                             )
    def testArrayValues(self, testIDE, start, end, step):
        """ Test for arrayValues method. """

        x = np.arange(*(slice(start, end, step).indices(1000)))/1000
        expected = np.floor(np.vstack((x, x**2, x**0.5))*1000 + 1e-6)

        actual = testIDE.channels[8].getSession().arrayValues(start, end, step)

        np.testing.assert_equal(actual, expected)

    @pytest.mark.parametrize('start, end, step',
                             [
                                 (None, None, 1),
                                 (None, None, 5),
                                 (10, 300, 3),
                                 ],
                             )
    def testIterSlice(self, eventArray, start, end, step):
        """ Test for the iterSlice method. """

        values = np.stack(tuple(eventArray.iterSlice(start, end, step))).T

        np.testing.assert_array_equal(values, eventArray.arraySlice(start, end, step))

    @pytest.mark.parametrize('start, end, step',
                             [
                                 (None, None, 1),
                                 (None, None, 5),
                                 (10, 300, 3),
                                 ],
                             )
    def testArraySlice(self, testIDE, start, end, step):
        """ Test for the arraySlice method. """

        x = np.arange(*(slice(start, end, step).indices(1000)))/1000
        expected = np.floor(np.vstack((x, x, x**2, x**0.5))*1000 + 1e-6)
        expected[0] = np.arange(*(slice(start, end, step).indices(1000)))*1000

        actual = testIDE.channels[8].getSession().arraySlice(start, end, step)

        np.testing.assert_equal(actual, expected)

    @pytest.mark.parametrize('jitter, step', [(0.5, 5), (0.5, 1), (0.1, 20), (0.1, 5)])
    def testIterJitterySlice(self, testIDE, jitter, step):
        """ Test for the iterJitterySlice method. """

        targetIdx = np.arange(0, 1000, step)

        dt = np.diff(testIDE.channels[8].getSession()[:][0]).mean()
        idx = np.array([x[0] for x in testIDE.channels[8].getSession().iterJitterySlice(None, None, step, jitter=jitter)])/dt

        np.testing.assert_array_less(np.abs(targetIdx - idx).round(), step/jitter)

    @pytest.mark.parametrize('jitter, step', [(0.5, 5), (0.5, 1), (0.1, 20), (0.1, 5)])
    def testArrayJitterySlice(self, testIDE, jitter, step):
        """ Test for the arrayJitterySlice method. """

        targetIdx = np.arange(0, 1000, step)

        dt = np.diff(testIDE.channels[8].getSession()[:][0]).mean()
        idx = testIDE.channels[8].getSession().arrayJitterySlice(None, None, step, jitter=jitter)[0]/dt

        np.testing.assert_array_less(np.abs(targetIdx - idx).round(), step/jitter)

    @pytest.mark.parametrize('t, expected', [(1, 0), (-1, -1), (1005, 1)])
    def testGetEventIndexBefore(self, testIDE, t, expected):
        """ Test for getEventIndexBefore method. """

        assert testIDE.channels[8].getSession().getEventIndexBefore(t) == expected

    @pytest.mark.parametrize('t, expected', [(1, 0), (-1, 0), (1005, 1), (1e99, 1000)])
    def testGetEventIndexNear(self, testIDE, t, expected):
        """ Test for getEventIndexNear method. """

        assert testIDE.channels[8].getSession().getEventIndexNear(t) == expected

    @pytest.mark.parametrize(
            'indices, expected, isSingleSample',
            [
                ((1,    1500), (1, 2),    False),
                ((None, 1),    (0, 1),    False),
                ((None, None), (0, 1000), False),
                ((2,    -51),  (1, 0),    False),
                ((2,    -51),  (0, 1),    True),
                ((2,    None), (0, 1000), True)
                ],
            )
    def testGetRangeIndices(self, testIDE, indices, expected, isSingleSample):
        """ Test for getRangeIndices method. """
        testIDE.channels[8].singleSample = isSingleSample
        eventArray = testIDE.channels[8].getSession()

        assert eventArray.getRangeIndices(*indices) == expected

    @pytest.mark.parametrize(
            'args, kwargs, expectedIdx',
            [
                ((0, 10000, 1), {'display': False}, (None, 11, None)),
                ((0, 99999999, 1), {'display': False}, (None, None, None)),
                ],
            )
    def testIterRange(self, testIDE, args, kwargs, expectedIdx):
        """ Test for iterRange method. """

        np.testing.assert_array_almost_equal(
                np.vstack(list(testIDE.channels[8].getSession().iterRange(*args, **kwargs))).T,
                testIDE.channels[8].getSession().arraySlice(*expectedIdx),
                )

    @pytest.mark.parametrize(
            'args, kwargs, expectedIdx',
            [
                ((0, 10000, 1), {'display': False}, (None, 11, None)),
                ((0, 99999999, 1), {'display': False}, (None, None, None)),
                ],
            )
    def testArrayRange(self, testIDE, args, kwargs, expectedIdx):
        """ Test for arrayRange method. """

        np.testing.assert_array_almost_equal(
                testIDE.channels[8].getSession().arrayRange(*args, **kwargs),
                testIDE.channels[8].getSession().arraySlice(*expectedIdx),
                )

    def testGetRange(self, testIDE):
        """ Test for getRange method. """

        eventArray = testIDE.channels[8].getSession()

        np.testing.assert_array_almost_equal(
                eventArray.getRange(),
                eventArray.arraySlice(),
                )

    def testIterMinMeanMax(self, eventArray):
        """ Test for iterMinMeanMax method. """

        # modify transform to ensure that transforms are being applied properly
        eventArray.parent.dataset.transforms[9].coefficients = (2., 0.)
        eventArray.parent.dataset.updateTransforms()

        expected = np.zeros((3, 4, 10))
        expected[:, 0, :] = np.linspace(0, 900000, 10)
        expected[1, 1, :] = 499*2
        expected[1, 2, :] = 332*2
        expected[1, 3, :] = 666*2
        expected[2, 1, :] = 999*2
        expected[2, 2, :] = 998*2
        expected[2, 3, :] = 999*2

        # Run tests
        result = eventArray.arrayMinMeanMax()
        print(result[:, 0, :])
        np.testing.assert_array_equal(result, expected)

    def testArrayMinMeanMax(self):
        """ Test arrayMinMeanMax. """
        # TODO test other hasSubchannels x times combos

        doc = importer.importFile('test.ide')
        eventArray8 = doc.channels[8].getSession()
        doc.transforms[9].coefficients = (2, 0)  # modify a transform to ensure it's being used
        doc.updateTransforms()

        # issue with the test file, all blocks have the same minmeanmax.  Could be worse.
        # (min, mean, max) x (t, sch1, sch2, sch3) x (time)
        expected = np.empty((3, 4, 10))
        # fill times
        expected[:, 0] = 1e5*np.arange(10)
        # mins are all 0
        expected[0, 1:] = 0
        # means: [499, 332, 666]
        expected[1, 1:, :] = 2*np.array([499, 332, 666])[:, np.newaxis]
        # maxes: [999, 998, 999]
        expected[2, 1:, :] = 2*np.array([999, 998, 999])[:, np.newaxis]

        result = eventArray8.arrayMinMeanMax()

        # Run tests
        np.testing.assert_array_equal(result, expected)

    def testGetMinMeanMax(self):
        """ Test getMinMeanMax. """

        doc = importer.importFile('test.ide')
        eventArray8 = doc.channels[8].getSession()
        doc.transforms[9].coefficients = (2, 0)  # modify a transform to ensure it's being used
        doc.updateTransforms()

        # issue with the test file, all blocks have the same minmeanmax.  Could be worse.
        # (min, mean, max) x (t, sch1, sch2, sch3) x (time)
        expected = np.empty((3, 4, 10))
        # fill times
        expected[:, 0] = 1e5*np.arange(10)
        # mins are all 0
        expected[0, 1:] = 0
        # means: [499, 332, 666]
        expected[1, 1:, :] = 2*np.array([499, 332, 666])[:, np.newaxis]
        # maxes: [999, 998, 999]
        expected[2, 1:, :] = 2*np.array([999, 998, 999])[:, np.newaxis]

        result = eventArray8.getMinMeanMax()

        # Run tests
        np.testing.assert_array_equal(result, expected)

    def testGetRangeMinMeanMax(self, testIDE):
        """ Test for getRangeMinMeanMax method. """

        eventArray = testIDE.channels[8].getSession()
        eventArray.hasMinMeanMax = False

        mmm = eventArray.getMinMeanMax()
        _min = mmm[0][1:].min()
        _mean = np.median(mmm[1][1:], axis=-1).mean()
        _max = mmm[2][1:].max()

        np.testing.assert_array_equal(
                eventArray.getRangeMinMeanMax(),
                [_min, _mean, _max],
                )

    def testGetMax(self):
        """ Test for getMax method. """
        # Stub dependencies
        eventArray = mock.Mock(spec=EventArray)
        eventArray.configure_mock(
            _data=mock.Mock(__getitem__=lambda self, idx: mock.Mock(
                indexRange=(mock.sentinel.start, mock.sentinel.end)
            )),
            hasMinMeanMax=False,
            hasSubchannels=False,
            arrayMinMeanMax=(
                lambda *a, **kw:
                np.array([[(0, 3)], [(0, 4)], [(0, 5)]])
            ),
            arraySlice=(
                lambda *a, **kw:
                np.array([(0, 0, 0, 0), (3, 3.5, 4.5, 5)])
            ),
        )

        # Run test
        np.testing.assert_array_equal(EventArray.getMax(eventArray), (0, 5))

    def testGetMin(self):
        """ test for getMin method. """
        # Stub dependencies
        eventArray = mock.Mock(spec=EventArray)
        eventArray.configure_mock(
            _data=mock.Mock(__getitem__=lambda self, idx: mock.Mock(
                indexRange=(mock.sentinel.start, mock.sentinel.end)
            )),
            hasMinMeanMax=False,
            hasSubchannels=False,
            arrayMinMeanMax=(
                lambda *a, **kw:
                np.array([[(0, 3)], [(0, 4)], [(0, 5)]])
            ),
            arraySlice=(
                lambda *a, **kw:
                np.array([(0, 0, 0, 0), (3, 3.5, 4.5, 5)])
            ),
        )

        # Run test
        np.testing.assert_array_equal(EventArray.getMin(eventArray), (0, 3))
        assert eventArray._computeMinMeanMax.call_count == 1

    @pytest.mark.parametrize(
            'kwargs, expected',
            [
                ({}, 1e-3),
                ({'idx': 1}, 1000.),
                ({'idx': 404}, 1000.),
                ],
            )
    def testGetSampleTime(self, testIDE, kwargs, expected):
        """ Test for getSampleTime method. """
        testIDE.channels[8].sampleRate = 1000.
        eventArray = testIDE.channels[8].getSession()

        assert eventArray.getSampleTime(**kwargs) == expected

    @pytest.mark.parametrize(
            'sr, idx, expected',
            [
                (None, None, 1000.),
                (100., None, 100.),
                (None, 1, 1000.),
                (None, 8, 1000.),
                ]
            )
    def testGetSampleRate(self, testIDE, sr, idx, expected):
        """ Test for getSampleRate method. """

        eventArray = testIDE.channels[8].getSession()
        eventArray.parent.sampleRate = sr

        assert eventArray.getSampleRate(idx) == expected

    @pytest.mark.parametrize(
            'at, raises',
            [
                (0, nullcontext()),
                (10, nullcontext()),
                (2000, nullcontext()),
                (9500, nullcontext()),
                (-1, pytest.raises(IndexError)),
                ],
            )
    def testGetValueAt(self, testIDE, at, raises):
        """ Test for getValueAt method. """
        if isinstance(raises, nullcontext):
            x = np.arange(1000)
            vals = np.floor(np.array([x*1000, x, 1000.*(x/1000)**2, 1000*(x/1000)**0.5]))
            expected = np.zeros([4])
            expected[0] = at
            for i in range(1, 4):
                expected[i] = np.interp([at], vals[0], vals[i])
        else:
            expected = None

        eventArray = testIDE.channels[8].getSession()
        with raises:
            np.testing.assert_equal(eventArray.getValueAt(at), expected)

    @pytest.mark.parametrize(
            't, expected',
            [
                (0, (499., 332., 666.)),
                (10, (499., 332., 666.)),
                (2000, (499., 332., 666.)),
                (9500, (499., 332., 666.)),
                (-1, (499., 332., 666.)),
                ],
            )
    def testGetMeanNear(self, testIDE, t, expected):
        """ Test for getMeanNear method. """

        eventArray = testIDE.channels[8].getSession()
        assert eventArray.getMeanNear(t) == expected

    def testIterResampledRange(self, testIDE):
        """ Test for iterResampledRange method. """

        eventArray = testIDE.channels[8].getSession()

        dat = eventArray.arraySlice()

        # Run tests
        np.testing.assert_array_almost_equal(
                np.stack(list(eventArray.iterResampledRange(0, 1e6, 9))).T,
                dat[:, [0, 112, 224, 336, 448, 560, 672, 784, 896]],
                )

    def testArrayResampledRange(self, testIDE):
        """ Test for arrayResampledRange method. """

        eventArray = testIDE.channels[8].getSession()

        dat = eventArray.arraySlice()

        # Run tests
        np.testing.assert_array_almost_equal(
                eventArray.arrayResampledRange(0, 1e6, 9),
                dat[:, [0, 112, 224, 336, 448, 560, 672, 784, 896]],
                )

    @pytest.mark.skip("this doesn't actually do anything")
    def testExportCSV(self, eventArray1):
        """ Test for exportCsv method."""
        self.mockData()
        eventArray1._data[0].minMeanMax = 1
        eventArray1._data[0].blockIndex = 2
        eventArray1._data[0].min = [3]
        eventArray1._data[0].mean = [4]
        eventArray1._data[0].max = [5]

    def testMeanRemovalSingleBlock(self, testIDE):
        """ Testing mean removal for spans less than one block """

        eventArray = testIDE.channels[8].getSession()
        eventArray.removeMean = False

        unremovedData = eventArray[:]

        eventArray.rollingMeanSpan = 1
        eventArray.removeMean = True

        # for d in eventArray._data:
        #     unremovedData[1:, slice(*d.indexRange)] -= d.mean[:, np.newaxis]
        unremovedData[1:] -= unremovedData[1:].mean(axis=1, keepdims=True)

        removedData = eventArray[:]

        np.testing.assert_array_equal(removedData, unremovedData)

    def testMeanRemovalFullFile(self, testIDE):
        """ Testing mean removal spanning the full file """

        eventArray = testIDE.channels[8].getSession()
        eventArray.removeMean = False

        unremovedData = eventArray[:]
        unremovedData[1:] -= unremovedData[1:].mean(axis=1)[:, np.newaxis]

        eventArray.rollingMeanSpan = -1
        eventArray.removeMean = True

        removedData = eventArray[:]

        np.testing.assert_array_equal(removedData, unremovedData)

#===============================================================================
#
#===============================================================================

class TestPlot:
    """ Unit test for the Plot class. """

    @pytest.fixture
    def channel32(self, SSX70065IDE):
        return SSX70065IDE.channels[32]

    @pytest.fixture
    def eventArray(self, channel32):
        return channel32.getSession()

    @pytest.fixture
    def plot1(self, eventArray):
        return Plot(eventArray, 0, name='Plot1')

    def testConstructor(self, plot1, eventArray):
        """ Test for the constructor. """

        plotParams = (
            plot1.source,
            plot1.id,
            plot1.session,
            plot1.dataset,
            plot1.name,
            plot1.units,
            plot1.attributes,
            )

        targetParams = (
            eventArray,
            0,
            eventArray.session,
            eventArray.dataset,
            'Plot1',
            eventArray.units,
            None,
            )

        assert plotParams == targetParams

    @pytest.mark.parametrize('t', [0, 1, 10, 100, 1000, 10000, 100000])
    def testGetEventIndexBefore(self, eventArray, plot1, t):
        """ Test for getEventIndexBefore method. """

        assert plot1.getEventIndexBefore(t) == eventArray.getEventIndexBefore(t)

    @pytest.mark.skip('not implemented')
    def testGetRange(self):
        """ Test for getRange method. """
        pass


#===============================================================================
#--- Data test cases
#===============================================================================

class TestData:
    """ Basic tests of data fidelity against older, "known good" CSV exports.
        Exports were generated using the library as of the release of 1.8.0.

        Tests are done within a threshold of 0.0015g to account for rounding
        errors. 
    """

    @pytest.fixture
    def dataset(self, SSX_DataIDE):
        return SSX_DataIDE

    @pytest.fixture
    def channel8(self, dataset):
        return dataset.channels[8]

    @pytest.fixture
    def accelArray(self, channel8):
        return channel8.getSession()

    @pytest.fixture
    def out(self):
        return StringIO()

    @staticmethod
    def generateCsvArray(filestream, eventArray, **kwargs):
        eventArray.exportCsv(filestream, **kwargs)
        filestream.seek(0)
        return np.genfromtxt(filestream, delimiter=', ').T

    def testCalibratedExport(self, accelArray, out):
        """ Test regular export, with bivariate polynomials applied.
        """

        new = self.generateCsvArray(out, accelArray)
        old = accelArray.__getitem__(slice(None), display=True)
        old = np.round(1e6*old)/1e6

        np.testing.assert_equal(new[1:], old[1:])

    def testUncalibratedExport(self, accelArray, out):
        """ Test export with no per-channel polynomials."""
        new = self.generateCsvArray(out, accelArray)
        old = accelArray.__getitem__(slice(None), display=True)
        old = np.round(1e6*old)/1e6

        np.testing.assert_equal(new[1:], old[1:])

    def testNoBivariates(self, accelArray, out):
        """ Test export with bivariate polynomial references disabled (values
            only offset, not temperature-corrected).
        """

        accelArray.noBivariates = True

        new = self.generateCsvArray(out, accelArray)
        old = accelArray.__getitem__(slice(None), display=True)
        old = np.round(1e6*old)/1e6

        np.testing.assert_equal(new[1:], old[1:])

    def testRollingMeanRemoval(self, accelArray, out):
        """ Test regular export, with the rolling mean removed from the data.
        """

        removeMean = True
        meanSpan = 5000000

        accelArray.removeMean = removeMean
        accelArray.rollingMeanSpan = meanSpan

        new = self.generateCsvArray(out, accelArray, removeMean=removeMean, meanSpan=meanSpan)
        old = accelArray.__getitem__(slice(None), display=True)
        old = np.round(1e6*old)/1e6

        np.testing.assert_equal(new[1:], old[1:])

    def testTotalMeanRemoval(self, accelArray, out):
        """ Test regular export, calibrated, with the total mean removed from
            the data.
        """

        removeMean = True
        meanSpan = -1

        accelArray.removeMean = removeMean
        accelArray.rollingMeanSpan = meanSpan

        new = self.generateCsvArray(out, accelArray, removeMean=removeMean, meanSpan=meanSpan)
        old = accelArray.__getitem__(slice(None), display=True)
        old = np.round(1e6*old)/1e6

        np.testing.assert_equal(new[1:], old[1:])

    def testCalibratedRollingMeanRemoval(self, accelArray, out):
        """ Test regular export, calibrated, with the rolling mean removed from
            the data.
        """

        removeMean = True
        meanSpan = 5000000

        accelArray.removeMean = removeMean
        accelArray.rollingMeanSpan = meanSpan

        new = self.generateCsvArray(out, accelArray, removeMean=removeMean, meanSpan=meanSpan)
        old = accelArray.__getitem__(slice(None), display=True)
        old = np.round(1e6*old)/1e6

        np.testing.assert_equal(new[1:], old[1:])

    def testCalibratedTotalMeanRemoval(self, accelArray, out):
        """ Test regular export, with the total mean removed from the data.
        """

        removeMean = True
        meanSpan = -1

        accelArray.removeMean = removeMean
        accelArray.rollingMeanSpan = meanSpan

        new = self.generateCsvArray(out, accelArray, removeMean=removeMean, meanSpan=meanSpan)
        old = accelArray.__getitem__(slice(None), display=True)
        old = np.round(1e6*old)/1e6

        np.testing.assert_equal(new[1:], old[1:])

    def testTimestamps(self, accelArray, out):
        """ Tests the timestamps, which are the same on all exports
        """

        new = self.generateCsvArray(out, accelArray)
        old = accelArray[:]
        old = np.round(1e6*old)/1e6

        np.testing.assert_allclose(new[0], old[0], rtol=1e-10)


# ===============================================================================
# 
# ==============================================================================

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
                                       "units":('Temperature','\xb0C'),
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
