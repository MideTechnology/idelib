import unittest
import mock
import struct

from ebmlite.core import *  # type: ignore
import numpy as np  # type: ignore

from idelib.importer import openFile
from idelib.parsers import ChannelDataBlockParser, ChannelDataBlock

from .file_streams import makeStreamLike

class TestChannelDataBlockParser(unittest.TestCase):
    """ Tests for ChannelDataBlockParser """

    def setUp(self):
        self.doc = openFile(makeStreamLike('./testing/SSX70065.IDE'))
        chDatBlockEl = self.doc.ebmldoc.children[161]
        self.element = [x for x in self.doc.ebmldoc.value if type(x) is chDatBlockEl and x[0].value == 32][0]
        self.block = ChannelDataBlock(self.element)

        self.parser = ChannelDataBlockParser(self.doc)

    def testConstructor(self):
        self.assertIsNone(self.parser.children)
        self.assertFalse(self.parser.isSubElement)
        self.assertFalse(self.parser.isHeader)

        self.assertIs(self.doc,                          self.parser.doc)
        self.assertIs(ChannelDataBlock,             self.parser.product)
        self.assertEqual(ChannelDataBlock.__name__, self.parser.elementName)
        self.assertEqual(10**6 / 2**15,                  self.parser.timeScalar)
        self.assertEqual({},                             self.parser.timestampOffset)
        self.assertEqual({},                             self.parser.lastStamp)
        self.assertEqual({},                             self.parser.timeScalars)
        self.assertEqual({},                             self.parser.timeModulus, )

    def testParse(self):
        """ Test parsing for ChannelDataBlocks, which is basically the same """
        # Straightforward case
        ch = self.doc.channels[self.block.channel]
        self.assertEqual(self.parser.parse(self.element), self.block.getNumSamples(ch.parser) * len(ch.children))

        # None element
        self.assertRaises(TypeError, self.parser.parse, None)

    def testGetElementName(self):
        """ Test getElementName from ElementHandler. """
        self.assertEqual(self.parser.getElementName(self.element), "'ChannelDataBlock' (0xa1) @1322")

    def testMakesData(self):
        """ Test makesData from ElementHandler. """
        self.assertTrue(self.parser.makesData())


class TestChannelDataBlock(unittest.TestCase):
    """ Tests for ChannelDataBlock """
    # NOTE: payload and parse* definitely need to be re-written, and tested
    # with new stuff, but (most of) the other stuff should be fine as-is

    def setUp(self):
        self.doc = openFile(makeStreamLike('./testing/SSX70065.IDE'))
        self.ebmldoc = self.doc.ebmldoc

        def chFilter(x):
            return type(x) is self.ebmldoc.children[161] and x[0].value == 32

        self.element = [x for x in self.ebmldoc.value if chFilter(x)][0]
        self.block = ChannelDataBlock(self.element)

    def testConstructor(self):
        self.assertIs(self.block.element, self.element)
        self.assertIsNone(self.block.numSamples)
        self.assertIsNone(self.block.sampleRate)
        self.assertIsNone(self.block.sampleTime)
        self.assertIsNone(self.block.indexRange)
        # self.assertIsNone(self.block.minMeanMax)
        # self.assertIsNone(self.block.min)
        # self.assertIsNone(self.block.mean)
        # self.assertIsNone(self.block.max)
        self.assertIsNone(self.block._rollingMean)
        self.assertIsNone(self.block._rollingMeanLen)

        self.assertFalse(self.block.cache)

        self.assertEqual(self.block.maxTimestamp, 16777216)
        self.assertEqual(self.block.timeScalar,   30.517578125)
        self.assertEqual(self.block.blockIndex,   -1)
        self.assertEqual(self.block.startTime,    211)
        self.assertEqual(self.block.endTime,      14721)
        self.assertEqual(self.block.payloadSize,  8142)

    def testRepr(self):
        self.assertEqual(repr(self.block),
                         '<ChannelDataBlock Channel: 32>')

    def testPayload(self):
        np.testing.assert_array_equal(self.block.payload,
                                      np.asarray(self.block._payloadEl.value))

    def testParseMinMeanMax(self):
        parser = self.doc.channels[32].parser

        oldVal = super(self.block.__class__, self.block).parseMinMeanMax(parser)
        newVal = self.block.parseMinMeanMax(parser)
        np.testing.assert_array_equal(oldVal, newVal)

    def testGetHeader(self):
        self.assertEqual(self.block.getHeader(), (211, 32))

    def testToNpTypestr(self):
        for stype, nptype in ChannelDataBlock.TO_NP_TYPESTR.items():
            for endian in ('<', '>'):
                assert (
                    struct.calcsize(endian+stype)
                    == np.dtype(endian+nptype).itemsize
                )

    def testGetNumSamples(self):
        self.assertEqual(self.block.getNumSamples(self.doc.channels[32].parser), 1357)

    def testIsValidLength(self):
        parser = self.doc.channels[32].parser
        self.assertTrue(self.block.isValidLength(parser))

        self.block.payloadSize -= 1
        self.assertFalse(self.block.isValidLength(parser))


def tuplify(arr):

    out = []
    for i in range(len(arr.T)):
        out.append(tuple(arr[:, i]))
    return out