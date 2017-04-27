'''
Module mide_ebml.ebmlite

Created on Apr 27, 2017
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

import os.path
from StringIO import StringIO
from xml.etree import ElementTree as ET

# import sys
# LAB_PATH = r"C:\Users\dstokes\workspace\SSXViewer"
# sys.path.insert(0, LAB_PATH)
# 
# from mide_ebml.ebml import core

from ebml import core

#===============================================================================
#
#===============================================================================

# Type IDs, for python-ebml compatibility
INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER = range(0, 8)
UNKNOWN = -1 # not in python-ebml

#===============================================================================
#
#===============================================================================

class DummyStream(object):
    """ Placeholder for python-ebml compatibility.
    """ 
    def __init__(self, stream, offset, size):
        self.file = stream
        self.offset = offset
        self.size = size

#===============================================================================
#
#===============================================================================

class Element(object):
    """ Base class for all EBML elements.
    """
    # python-ebml type ID. PyLint won't like this.
    type = UNKNOWN

    children = None
    
    def parse(self, stream, size):
        return  bytearray(stream.read(size))


    def __init__(self, eid, ename="UnknownElement", stream=None, offset=0,
                 size=0, payloadOffset=0, schema=None, parent=None):
        self.id = eid
        self.name = ename
        self._stream = stream
        self.offset = offset
        self.size = size
        self.payloadOffset = payloadOffset
        self.schema = schema
        self.parent = parent
        self._value = None

        # For python-ebml compatibility. Remove later.
        self.stream = DummyStream(stream, offset, size)
        self.body_size = size - (payloadOffset - offset)


    def __repr__(self):
        return "<%s %r (0x%02X) at 0x%08X>" % (self.__class__.__name__,
                                               self.name, self.id, id(self))


    @property
    def value(self):
        if self._value is not None:
            return self._value
        self._stream.seek(self.payloadOffset)
        self._value = self.parse(self._stream, self.size)
        return self._value


    def _getSchemaInfo(self, attrib, default):
        """ Helper method to wrap getting element info from the schema. """
        try:
            return self.schema.elementInfo[self.id].get(attrib, default)
        except AttributeError:
            raise ValueError("Element %r has no schema!" % (self.name))
        except KeyError:
            raise ValueError("Element %r not in schema %r!" % \
                             (self.name, self.schema.name))


    @property
    def multiple(self):
        """ Are multiples of this element allowed? For python-ebml
            compatibility.
        """
        return self._getSchemaInfo('multiple','1') == '1'


    @property
    def mandatory(self):
        """ Is the element required in all documents? For python-ebml
            compatibility.
        """
        return self._getSchemaInfo('mandatory','0') == '1'


class IntegerElement(Element):
    """ Representation of an EBML signed integer element.
    """
    type = INT

    def parse(self, stream, size):
        return core.read_signed_integer(stream, size)


class UIntegerElement(Element):
    """ Representation of an EBML unsigned integer element.
    """
    type = UINT

    def parse(self, stream, size):
        return core.read_unsigned_integer(stream, size)


class FloatElement(Element):
    """ Representation of an EBML floating point element.
    """
    type = FLOAT

    def parse(self, stream, size):
        return core.read_float(stream, size)


class StringElement(Element):
    """ Representation of an EBML ASCII string element.
    """
    type = STRING

    def parse(self, stream, size):
        return core.read_string(stream, size)


class UnicodeElement(Element):
    """ Repesentation of an EBML UTF-8 string element.
    """
    type = UNICODE

    def parse(self, stream, size):
        return core.read_unicode_string(stream, size)


class DateElement(Element):
    """ Representation of an EBML 'date' element.
    """
    type = DATE

    def parse(self, stream, size):
        return core.read_date(stream, size)


class BinaryElement(Element):
    """ Representation of an EBML 'binary' element.
    """
    type = BINARY


class MasterElement(Element):
    """ Representation of an EBML 'master' element, a container for other
        elements.
    """
    type = CONTAINER

    def parseElement(self, stream):
        """
        """
        offset = stream.tell()
        eid, idlen = core.read_element_id(stream)
        esize, sizelen = core.read_element_size(stream)
        payloadOffset = offset + idlen + sizelen

        ename, etype = self.schema.elements.get(eid, ("UnknownElement", Element))
        el = etype(eid, ename, stream, offset, esize, payloadOffset, self.schema, self)

        return el, payloadOffset + esize


    def iterChildren(self):
        """
        """
        pos = self.payloadOffset
        payloadEnd = pos + self.size
        while pos < payloadEnd:
            self._stream.seek(pos)
            el, pos = self.parseElement(self._stream)
            yield el


    @property
    def value(self):
        """
        """
        if self._value is not None:
            return self._value
        self._value = list(self.iterChildren())
        return self._value


    def __getitem__(self, *args):
        return self.value.__getitem__(*args)


class Document(MasterElement):
    """ Representation of an EBML document, containing multiple 'root'
        elements.
    """

    def __init__(self, stream, schema, name=None, size=None):
        """
        """
        self._value = None
        self.schema = schema
        self._stream = stream
        self.size = size
        self.name = name
        self.id = None
        self.offset =  self.payloadOffset = 0

        if name is None:
            try:
                self.name = self._stream.name
            except AttributeError:
                self.name = ""

        if size is None:
            if isinstance(stream, StringIO):
                self.size = stream.len
            else:
                try:
                    self.size = os.path.getsize(self._stream.name)
                except (AttributeError, IOError, WindowsError):
                    pass

        startPos = self._stream.tell()
        el, pos = self.parseElement(self._stream)
        if el.name == "EBML":
            # Load 'header' info from the file
            self.info = {c.name: c.value for c in el.value}
            self.payloadOffset = pos
        else:
            self.info = {}
        self._stream.seek(startPos)

        # For python-ebml compatibility. Remove later.
        self.stream = DummyStream(stream, 0, self.size)
        self.body_size = self.size - self.payloadOffset
        

    def close(self):
        self._stream.close()


    def __iter__(self):
        """ Iterate root elements.
        """
        pos = self.payloadOffset
        while True:
            self._stream.seek(pos)
            try:
                el, pos = self.parseElement(self._stream)
                yield el
            except TypeError:
                break


    def iterroots(self):
        """ Iterate root elements. For working like old python-ebml.
        """
        return self.__iter__()


    @property
    def roots(self):
        """ The document's root elements. For python-ebml compatibility.
        """
        # TODO: Cache roots
        return list(self)


    @property
    def value(self):
        return self


    def __getitem__(self, idx):
        # TODO: Cache parsed root elements, handle indexing dynamically.
        if isinstance(idx, (int, long)):
            for n, el in enumerate(self):
                if n == idx:
                    return el
            raise IndexError("list index out of range (0-%d)" % n)
        elif isinstance(idx, slice):
            raise IndexError("Document root slicing not (yet) supported!")
        else:
            raise TypeError("list indices must be integers, not %s" % type(idx))


    @property
    def version(self):
        return self.info.get('DocTypeVersion')


    @property
    def type(self):
        """ The document's type (string). """
        # NOTE: in python-ebml, an element's 'type' is numeric, while the
        # document's 'type' is a string. This follows that model.
        return self.info.get('DocType')


#===============================================================================
#
#===============================================================================

class Schema(object):
    """ An EBML schema, mapping element IDs to names and data types.
    """

    ELEMENT_TYPES = {
        'integer': IntegerElement,
        'uinteger': UIntegerElement,
        'float': FloatElement,
        'string': StringElement,
        'utf-8': UnicodeElement,
        'date': DateElement,
        'binary': BinaryElement,
        'master': MasterElement,
    }


    def __init__(self, filename, name=None):
        self.filename = filename
        self.name = name
        if name is None:
            self.name = os.path.splitext(os.path.basename(filename))[0]

        self.elements = {}
        self.elementInfo = {}
        schema = ET.parse(filename)

        for el in schema.findall('element'):
            attribs = el.attrib.copy()
            eid = int(el.attrib['id'],16)
            ename = el.attrib['name']
            etype = el.attrib['type'].lower()
            if etype not in self.ELEMENT_TYPES:
                raise ValueError("Unknown type for %r: %r" % (ename, etype))
            self.elements[eid] = (ename, self.ELEMENT_TYPES[etype])
            self.elementInfo[eid] = attribs


    def __repr__(self):
        return "<%s %r from '%s'>" % (self.__class__.__name__, self.name,
                                      os.path.realpath(self.filename))


    def load(self, fp, name=None):
        """ Load an EBML file using this Schema.
        """
        if isinstance(fp, basestring):
            fp = open(fp, 'rb')

        name = name or self.type
        return Document(fp, self, name=name)


    #===========================================================================
    # Schema info stuff. Uses python-ebml schema XML data. Refactor later.
    #===========================================================================

    def _getInfo(self, eid, dtype):
        try:
            return dtype(self.elementInfo[eid]['default'])
        except (KeyError, ValueError):
            return None


    @property
    def version(self):
        return self._getInfo(0x4287, int) # EBML 'DocTypeVersion'


    @property
    def type(self):
        return self._getInfo(0x4282, str) # EBML 'DocType'


#===============================================================================
#
#===============================================================================

# # TEST
# schemaFile = os.path.join(LAB_PATH, r"mide_ebml\ebml\schema\mide.xml")
# testFile = 'test_recordings/5kHz_Full.IDE'
# 
# from time import clock
# from mide_ebml.ebml.schema.mide import MideDocument
# 
# def crawl(el):
#     v = el.value
#     if isinstance(v, list):
#         return sum(map(crawl, v))
#     return 1
# 
# def testOld():
#     total = 0
#     t0 = clock()
#     with open(testFile, 'rb') as f:
#         doc = MideDocument(f)
#         for el in doc.iterroots():
#             total += crawl(el)
#     return total, clock() - t0
# 
# def testNew():
#     total = 0
#     t0 = clock()
#     schema = Schema(schemaFile)
#     with open(testFile, 'rb') as f:
#         doc = schema.load(f)
#         for el in doc.iterroots():
#             total += crawl(el)
#     return total, clock() - t0
