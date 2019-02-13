from __future__ import division, absolute_import, print_function, unicode_literals
import unittest

import mock
import numpy as np

from mide_ebml.parsers import ChannelDataArrayParser, ChannelDataArrayBlock
from mide_ebml.ebmlite.core import *


class TestChannelDataArrayParser(unittest.TestCase):

    def setUp(self):
        self.schema = loadSchema('./mide_ebml/ebmlite/schemata/mide.xml')
        self.doc = self.schema.load('./mide_ebml/testing/SSX70065.IDE')
        self.element = [x for x in self.doc.value if type(x) is self.doc.children[161] and x[0].value == 32][0]
        self.block = ChannelDataArrayBlock(self.element)

        self.parser = ChannelDataArrayParser(self.doc)

    def testConstructor(self):
        print(self.block.payload)
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
        ch = self.block.channel
        self.assertEqual(self.parser.parse(self.element), self.block.getNumSamples(ch.parser) * len(ch.children))

        # TODO tests for: attributeErrors, None endtime, invalid channel, zeroDivision in getNumSamples

        # None element
        self.assertRaises(TypeError, self.parser.parse, None)

    def testGetElementName(self):
        """ Test getElementName from ElementHandler. """
        self.assertEqual(self.parser.getElementName(self.element), "'ChannelDataBlock' (0xa1) @766L")

    def testMakesData(self):
        """ Test makesData from ElementHandler. """
        self.assertTrue(self.parser.makesData())


class TestChannelDataArrayBlock(unittest.TestCase):
    # NOTE: payload and parse* definitely need to be re-written, and tested
    # with new stuff, but (most of) the other stuff should be fine as-is

    def setUp(self):
        self.schema = loadSchema('./mide_ebml/ebmlite/schemata/mide.xml')
        self.doc = self.schema.load('./mide_ebml/testing/SSX70065.IDE')
        self.element = [x for x in self.doc.value if type(x) is self.doc.children[161] and x[0].value == 32][0]
        self.block = ChannelDataArrayBlock(self.element)

    def testConstructor(self):
        # TODO THIS
        1+1
        pass

    def testRepr(self):
        # TODO THIS
        pass

    def testPayload(self):
        # TODO THIS
        pass

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
