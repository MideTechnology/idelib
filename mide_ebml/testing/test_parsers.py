from __future__ import division, absolute_import, print_function, unicode_literals
import unittest

import mock
import numpy as np
from mide_ebml.importer import openFile

from mide_ebml.parsers import ChannelDataArrayParser, ChannelDataArrayBlock
from mide_ebml.ebmlite.core import *


class TestChannelDataArrayParser(unittest.TestCase):

    def setUp(self):
        self.doc = openFile('./mide_ebml/testing/SSX70065.IDE')
        self.element = [x for x in self.doc.ebmldoc.value if type(x) is self.doc.ebmldoc.children[161] and x[0].value == 32][0]
        self.block = ChannelDataArrayBlock(self.element)

        self.parser = ChannelDataArrayParser(self.doc)

    def testConstructor(self):
        self.assertIsNone(self.parser.children)
        self.assertFalse(self.parser.isSubElement)
        self.assertFalse(self.parser.isHeader)

        self.assertIs(self.parser.doc, self.doc)
        self.assertIs(self.parser.product, ChannelDataArrayBlock)
        self.assertEqual(self.parser.elementName, ChannelDataArrayBlock.__name__)
        self.assertEqual(self.parser.timeScalar, 1000000.0 / 2**15)
        self.assertEqual(self.parser.timestampOffset, {})
        self.assertEqual(self.parser.lastStamp, {})
        self.assertEqual(self.parser.timeScalars, {})
        self.assertEqual(self.parser.timeModulus, {})

    def testFixOverflow(self):
        """ Test fixOverflow from SimpleChannelDataBlockParser. """
        # TODO test without modulus

        # TODO test with modulus

        # TODO test with timestamp greater than modulus
        pass

    def testParse(self):
        # TODO fix the iterator on the mock after implementing ChannlDataArrayBlock
        # Straightforward case
        ch = self.doc.channels[self.block.channel]
        self.assertEqual(self.parser.parse(self.element), self.block.getNumSamples(ch.parser) * len(ch.children))

        # TODO tests for: attributeErrors, None endtime, invalid channel, zeroDivision in getNumSamples

        # None element
        self.assertRaises(TypeError, self.parser.parse, None)

    def testGetElementName(self):
        """ Test getElementName from ElementHandler. """
        self.assertEqual(self.parser.getElementName(self.element), "'ChannelDataBlock' (0xa1) @1322L")

    def testMakesData(self):
        """ Test makesData from ElementHandler. """
        self.assertTrue(self.parser.makesData())


class TestChannelDataArrayBlock(unittest.TestCase):
    # NOTE: payload and parse* definitely need to be re-written, and tested
    # with new stuff, but (most of) the other stuff should be fine as-is

    def setUp(self):
        self.doc = openFile('./mide_ebml/testing/SSX70065.IDE')
        self.ebmldoc = self.doc.ebmldoc

        def chFilter(x):
            return type(x) is self.ebmldoc.children[161] and x[0].value == 32

        self.element = [x for x in self.ebmldoc.value if chFilter(x)][0]
        self.block = ChannelDataArrayBlock(self.element)

    def testConstructor(self):
        # TODO THIS
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
        self.assertEqual(self.block.timeScalar, 30.517578125)
        self.assertEqual(self.block.blockIndex, -1)
        self.assertEqual(self.block.startTime, 211)
        self.assertEqual(self.block.endTime, 14721)
        self.assertEqual(self.block.payloadSize, 8142)

    def testRepr(self):
        self.assertEqual(unicode(repr(self.block)),
                         unicode('<ChannelDataArrayBlock Channel: 32>'))

    def testPayload(self):
        np.testing.assert_array_equal(self.block.payload,
                                      np.asarray(self.block._payloadEl.value))

    def testMinMeanMax(self):
        # TODO THIS
        pass

    def testGetHeader(self):
        # TODO THIS
        pass

    def parseWith(self):
        # TODO THIS
        pass

    def parseByIndexWith(self):
        # TODO THIS
        pass

    def parseMinMeanMax(self):
        # TODO THIS
        pass

    def testGetNumSamples(self):
        # TODO THIS
        pass

    def testIsValidLength(self):
        # TODO THIS
        pass
