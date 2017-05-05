'''
EBMLite: A lightweight EBML parsing library.

Created on Apr 27, 2017

@todo: Refactor other code and remove python-ebml compatibility cruft.
@todo: EBML encoding, making it a full replacement for python-ebml.
@todo: Validation. Extract valid child element info from the schema.
@todo: Document-wide caching, for future handling of streamed data.
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
        self.substreams = {}


#===============================================================================
#
#===============================================================================

class Element(object):
    """ Base class for all EBML elements. Also used for unknown elements (i.e.
        those with IDs not in the schema.
    """
    # python-ebml type ID. PyLint won't like this.
    type = UNKNOWN

    children = None
    
    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload. """
        # Document-wide caching could be implemented here.
        return  bytearray(stream.read(size))


    def __init__(self, eid, ename="UnknownElement", stream=None, offset=0,
                 size=0, payloadOffset=0, document=None, schema=None):
        """ Constructor. Instantiate a new Element from a file.
        
            @param eid: The element's EBML ID, as defined in the Schema.
            @keyword ename: The element's name, defined in the Schema.
            @keyword stream: A file-like object containing EBML data.
            @keyword offset: The element's starting location in the file.
            @keyword size: The size of the whole element.
            @keyword payloadOffset: The starting location of the element's
                payload (i.e. immediately after the element's header).
            @keyword document: The parent EBML document.
            @keyword schema: The Schema defining the element. Defaults to the
                document's schema.
        """
        self.id = eid
        self._stream = stream
        self.offset = offset
        self.size = size
        self.payloadOffset = payloadOffset
        self.schema = schema or document.schema
        self.document = document
        self._value = None

        # TODO: Determine if memory used to store element name is worth the
        # time savings (importer currently works using element names).
        self.name = ename

        # For python-ebml compatibility. Remove later.
        self.stream = DummyStream(stream, offset, size)
        self.body_size = size - (payloadOffset - offset)


    def __repr__(self):
        return "<%s %r (0x%02X) at 0x%08X>" % (self.__class__.__name__,
                                               self.name, self.id, id(self))


    def __eq__(self, other):
        """ Equality check. Elements are considered equal if they are the same
            type and have the same ID, size, offset, and schema. Note: element
            value is not considered! 
        """
        if other is self:
            return True
        try:
            return (isinstance(other, self.__class__) 
                    and self.schema == other.schema
                    and self.id == other.id 
                    and self.offset == other.offset 
                    and self.size == other.size)
        except AttributeError:
            return False


#     @property
#     def name(self):
#         # Get the object name from the schema, avoiding redundant strings
#         try:
#             return self.schema.elements[self.id][0]
#         except (KeyError, IndexError):
#             return 'UnknownElement'
    

    @property
    def value(self):
        """ Parse and cache the element's value. """
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


    #===========================================================================
    # Caching (experimental)
    #===========================================================================

    def gc(self, recurse=False):
        """ Clear any cached values. To save memory and/or force values to be
            re-read from the file.
        """
        if self._value is None:
            return 0
        self._value = None
        
        return 1
        


#===============================================================================

class IntegerElement(Element):
    """ Representation of an EBML signed integer element.
    """
    type = INT

    def parse(self, stream, size):
        return core.read_signed_integer(stream, size)


#===============================================================================

class UIntegerElement(Element):
    """ Representation of an EBML unsigned integer element.
    """
    type = UINT

    def parse(self, stream, size):
        return core.read_unsigned_integer(stream, size)


#===============================================================================

class FloatElement(Element):
    """ Representation of an EBML floating point element.
    """
    type = FLOAT

    def parse(self, stream, size):
        return core.read_float(stream, size)


#===============================================================================

class StringElement(Element):
    """ Representation of an EBML ASCII string element.
    """
    type = STRING

    def parse(self, stream, size):
        return core.read_string(stream, size)


#===============================================================================

class UnicodeElement(Element):
    """ Representation of an EBML UTF-8 string element.
    """
    type = UNICODE

    def parse(self, stream, size):
        return core.read_unicode_string(stream, size)


#===============================================================================

class DateElement(Element):
    """ Representation of an EBML 'date' element.
    """
    type = DATE

    def parse(self, stream, size):
        return core.read_date(stream, size)


#===============================================================================

class BinaryElement(Element):
    """ Representation of an EBML 'binary' element.
    """
    type = BINARY


#===============================================================================

class VoidElement(BinaryElement):
    """ Special case ``Void`` element. Its contents are ignored.
    """
    type = BINARY
    
    def parse(self, stream, size):
        return bytearray()


#===============================================================================

class MasterElement(Element):
    """ Representation of an EBML 'master' element, a container for other
        elements.
    """
    type = CONTAINER

    def parseElement(self, stream):
        """ Read the next element from a stream, instantiate a `MasterElement` 
            object, and then return it and the offset of the next element
            (element position + element size).
        """
        offset = stream.tell()
        eid, idlen = core.read_element_id(stream)
        esize, sizelen = core.read_element_size(stream)
        payloadOffset = offset + idlen + sizelen

        ename, etype = self.schema.elements.get(eid, ("UnknownElement", Element))
        el = etype(eid, ename, stream, offset, esize, payloadOffset, self.document)

        return el, payloadOffset + esize


    def iterChildren(self):
        """ Create an iterator to iterate over the element's children.
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


    #===========================================================================
    # Caching (experimental!)
    #===========================================================================
    
    def gc(self, recurse=False):
        """ Clear any cached values. To save memory and/or force values to be
            re-read from the file.
        """
        cleared = 0
        if self._value is not None:
            if recurse:
                cleared = sum(ch.gc(recurse) for ch in self._value) + 1
            self._value = None
        return cleared
            

#===============================================================================
# 
#===============================================================================

class Document(MasterElement):
    """ Representation of an EBML document, containing multiple 'root'
        elements.
    """

    def __init__(self, stream, schema, name=None, size=None):
        """ Constructor.
        
            @param stream: A stream object (e.g. a file) from which to read 
                the EBML content, or a filename.
            @param schema: The EBML schema used by the file.
            @keyword name: The name of the document. Defaults to the filename
                (if applicable).
        """
        self._value = None
        self.schema = schema
        self.document = self
        self._stream = stream
        self.size = size
        self.name = name
        self.id = None
        self.offset =  self.payloadOffset = 0

        try:
            self.filename = stream.name
        except AttributeError:
            self.filename = ""
            
        if name is None:
            self.name = os.path.splitext(os.path.basename(self.filename))[0]

        if size is None:
            if isinstance(stream, StringIO):
                self.size = stream.len
            elif os.path.exists(self.filename):
                self.size = os.path.getsize(self._stream.name)

        startPos = self._stream.tell()
        el, pos = self.parseElement(self._stream)
        if el.id == 0x1A45DFA3: # "EBML":
            # Load 'header' info from the file
            self.info = {c.name: c.value for c in el.value}
            self.payloadOffset = pos
        else:
            self.info = {}
        self._stream.seek(startPos)

        # For python-ebml compatibility. Remove later.
        self.stream = DummyStream(stream, 0, self.size)
        
        self.body_size = self.size - self.payloadOffset



    def __repr__(self):
        return "<%s %r (%s) at 0x%08X>" % (self.__class__.__name__, self.name,
                                           self.type, id(self))


    def close(self):
        """ Close the EBML file. Should generally be used only if the object was
            created using a filename, rather than a stream.
        """
        self._stream.close()


    def __iter__(self):
        """ Iterate root elements.
        """
        # TODO: Cache root elements, prevent unnecessary duplicates.
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
        return iter(self)


    @property
    def roots(self):
        """ The document's root elements. For python-ebml compatibility.
        """
        # TODO: Cache roots (see `__iter__()`)
        return list(self)


    @property
    def value(self):
        # 'value' not really applicable to a document; return an iterator.
        return iter(self)


    def __getitem__(self, idx):
        # TODO: Cache parsed root elements, handle indexing dynamically.
        if isinstance(idx, (int, long)):
            for n, el in enumerate(self):
                if n == idx:
                    return el
            raise IndexError("list index out of range (0-%d)" % n)
        elif isinstance(idx, slice):
            raise IndexError("Document root slicing not (yet) supported")
        else:
            raise TypeError("list indices must be integers, not %s" % type(idx))


    @property
    def version(self):
        """ The document's type version (i.e. the EBML ``DocTypeVersion``). """
        return self.info.get('DocTypeVersion')


    @property
    def type(self):
        """ The document's type name (i.e. the EBML ``DocType``). """
        # NOTE: in python-ebml, an element's 'type' is numeric, while the
        # document's 'type' is a string. This follows that model.
        return self.info.get('DocType')


    #===========================================================================
    # Caching (experimental!)
    #===========================================================================
    
    def gc(self, recurse=False):
        # TODO: Implement this if/when caching of root elements  is implemented.
        return 0



#===============================================================================
#
#===============================================================================

class Schema(object):
    """ An EBML schema, mapping element IDs to names and data types.
    
        @ivar elements: A dictionary mapping element IDs to the corresponding
            name and data type (an `Element` subclass).
        @ivar elementInfo: A dictionary mapping IDs to the raw schema data.
        @ivar elementIds: A dictionary mapping element names to IDs.
    """

    # Mapping of schema type names to the corresponding Element subclasses.
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
        """ Constructor. Creates a new Schema from a schema description XML.
        
            @param filename: The full path and name of the schema XML file.
            @keyword name: The schema's name. Defaults to the filename.
        """
        self.filename = filename

        self.elements = {}
        self.elementInfo = {}
        self.elementIds = {}
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
            self.elementIds[ename] = eid

        # Special case: `Void` is a standard EBML element, but not its own
        # type (it's technically binary). Use the special `VoidElement` type.
        if 'Void' in self.elementIds:
            self.elements[self.elementIds['Void']] = ("Void", VoidElement)
                    
        if name is None:
            name = self.type
            if name is None:
                name = os.path.splitext(os.path.basename(filename))[0]
        self.name = name
        

    def __repr__(self):
        return "<%s %r from '%s'>" % (self.__class__.__name__, self.name,
                                      os.path.realpath(self.filename))

    
    def __eq__(self, other):
        try:
            return self is other or self.elementInfo == other.elementInfo
        except AttributeError:
            return False


    def load(self, fp, name=None):
        """ Load an EBML file using this Schema.
            
            @param fp: A file-like object containing the EBML to load, or the
                name of an EBML file.
            @keyword name: The name of the document. Defaults to filename.
        """
        if isinstance(fp, basestring):
            fp = open(fp, 'rb')

        return Document(fp, self, name=name)


    #===========================================================================
    # Schema info stuff. Uses python-ebml schema XML data. Refactor later.
    #===========================================================================

    def _getInfo(self, eid, dtype):
        """ Helper method to get the 'default' value of an element. """
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

# TEST
schemaFile = os.path.join(os.path.dirname(__file__), r"ebml\schema\mide.xml")
testFile = 'test_recordings/5kHz_Full.IDE'
  
from time import clock
from mide_ebml.ebml.schema.mide import MideDocument
  
def crawl(el):
    v = el.value
    if isinstance(v, list):
        return sum(map(crawl, v))
    return 1
  
def testOld():
    total = 0
    t0 = clock()
    with open(testFile, 'rb') as f:
        doc = MideDocument(f)
        for el in doc.iterroots():
            total += crawl(el)
    return doc, total, clock() - t0
  
def testNew():
    total = 0
    t0 = clock()
    schema = Schema(schemaFile)
    with open(testFile, 'rb') as f:
        doc = schema.load(f)
        for el in doc.iterroots():
            total += crawl(el)
    return doc, total, clock() - t0
