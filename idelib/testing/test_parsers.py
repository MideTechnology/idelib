from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import unittest
import mock
import numpy as np

from idelib.importer import openFile
from idelib.parsers import ChannelDataArrayBlockParser, ChannelDataArrayBlock
from idelib.ebmlite.core import *


class TestChannelDataArrayBlockParser(unittest.TestCase):
    """ Tests for ChannelDataArrayBlockParser """

    def setUp(self):
        self.doc = openFile('./idelib/testing/SSX70065.IDE')
        chDatBlockEl = self.doc.ebmldoc.children[161]
        self.element = [x for x in self.doc.ebmldoc.value if type(x) is chDatBlockEl and x[0].value == 32][0]
        self.block = ChannelDataArrayBlock(self.element)

        self.parser = ChannelDataArrayBlockParser(self.doc)

    def testConstructor(self):
        self.assertIsNone(self.parser.children)
        self.assertFalse(self.parser.isSubElement)
        self.assertFalse(self.parser.isHeader)

        self.assertIs(self.doc,                          self.parser.doc)
        self.assertIs(ChannelDataArrayBlock,             self.parser.product)
        self.assertEqual(ChannelDataArrayBlock.__name__, self.parser.elementName)
        self.assertEqual(10**6 / 2**15,                  self.parser.timeScalar)
        self.assertEqual({},                             self.parser.timestampOffset)
        self.assertEqual({},                             self.parser.lastStamp)
        self.assertEqual({},                             self.parser.timeScalars)
        self.assertEqual({},                             self.parser.timeModulus, )

    def testParse(self):
        """ Test parsing for ChannelDataArrayBlocks, which is basically the same """
        # Straightforward case
        ch = self.doc.channels[self.block.channel]
        self.assertEqual(self.parser.parse(self.element), self.block.getNumSamples(ch.parser) * len(ch.children))

        # None element
        self.assertRaises(TypeError, self.parser.parse, None)

    def testGetElementName(self):
        """ Test getElementName from ElementHandler. """
        self.assertEqual(self.parser.getElementName(self.element), "'ChannelDataBlock' (0xa1) @1322L")

    def testMakesData(self):
        """ Test makesData from ElementHandler. """
        self.assertTrue(self.parser.makesData())


class TestChannelDataArrayBlock(unittest.TestCase):
    """ Tests for ChannelDataArrayBlock """
    # NOTE: payload and parse* definitely need to be re-written, and tested
    # with new stuff, but (most of) the other stuff should be fine as-is

    def setUp(self):
        self.doc = openFile('./idelib/testing/SSX70065.IDE')
        self.ebmldoc = self.doc.ebmldoc

        def chFilter(x):
            return type(x) is self.ebmldoc.children[161] and x[0].value == 32

        self.element = [x for x in self.ebmldoc.value if chFilter(x)][0]
        self.block = ChannelDataArrayBlock(self.element)

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
                         '<ChannelDataArrayBlock Channel: 32>')

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

    def testParseWith(self):
        parser = self.doc.channels[32].parser

        # Plain case
        blockOut = self.block.parseWith(parser)
        oldOut = [x for x in super(self.block.__class__, self.block).parseWith(parser)]
        oldOut = np.array(oldOut).T
        np.testing.assert_array_equal(oldOut, blockOut)

        # different start
        blockOut = self.block.parseWith(parser, start=5)
        oldOut = [x for x in super(self.block.__class__, self.block).parseWith(parser, start=5)]
        oldOut = np.array(oldOut).T
        np.testing.assert_array_equal(oldOut, blockOut)

        # different end
        blockOut = self.block.parseWith(parser, end=100)
        oldOut = [x for x in super(self.block.__class__, self.block).parseWith(parser, end=100)]
        oldOut = np.array(oldOut).T
        np.testing.assert_array_equal(oldOut, blockOut)

        # different step
        blockOut = self.block.parseWith(parser, step=10)
        oldOut = [x for x in super(self.block.__class__, self.block).parseWith(parser, step=10)]
        oldOut = np.array(oldOut).T
        np.testing.assert_array_equal(oldOut, blockOut)

        # fully different params
        blockOut = self.block.parseWith(parser, start=10, end=100, step=10)
        oldOut = [x for x in super(self.block.__class__, self.block).parseWith(parser, start= 10, end=100, step=10)]
        oldOut = np.array(oldOut).T
        np.testing.assert_array_equal(oldOut, blockOut)

        # specific subchannel
        blockOut = self.block.parseWith(parser, subchannel=1)
        oldOut = [x for x in super(self.block.__class__, self.block).parseWith(parser, subchannel=1)]
        oldOut = np.array(oldOut)[np.newaxis]
        np.testing.assert_array_equal(oldOut, blockOut)

    def testParseByIndexWith(self):
        parser = self.doc.channels[32].parser
        dtype_desc = [('ch'+str(i), parser.format[0:2])
                      for i in xrange(len(parser.format[1:]))]
        self.block.getNumSamples(parser)

        blockOut = self.block.parseByIndexWith(parser, range(20, 100))
        oldOut = [x for x in super(self.block.__class__, self.block).parseByIndexWith(parser, range(20, 100))]
        np.testing.assert_array_equal(oldOut, tuplify(blockOut))

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