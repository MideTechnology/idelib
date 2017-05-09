'''
EBMLite: A lightweight EBML parsing library.

Created on Apr 27, 2017

@todo: Remove benchmarking code from end of script.
@todo: Unit tests.
@todo: Refactor other code and remove python-ebml compatibility cruft.
@todo: New schema format, getting further away from python-ebml. 
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
    substreams = {}
    
    def __init__(self, parent):
        self.parent = parent
    
    @property
    def file(self):
        return self.parent._stream
    
    @property
    def offset(self):
        return self.parent.offset
    
    @property
    def size(self):
        return self.parent.size
    
    def close(self):
        return self.parent._stream.close()


#===============================================================================
#
#===============================================================================

class Element(object):
    """ Base class for all EBML elements. Also used for unknown elements (i.e.
        those with IDs not in the schema.
    """
    # python-ebml type ID. 
    type = UNKNOWN

    # Should this element's value be read/cached when the element is parsed?
    precache = False

    # For python-ebml compatibility; not currently used.
    children = None
    
    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload.
            It is assumed the file pointer is at the start of the payload.
        """
        # Document-wide caching could be implemented here.
        return  bytearray(stream.read(size))


    def __init__(self, stream=None, offset=0, size=0, payloadOffset=0):
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
        self._stream = stream
        self.offset = offset
        self.size = size
        self.payloadOffset = payloadOffset
        self._value = None

        # For python-ebml compatibility. Remove later.
        self.stream = DummyStream(self)
        self.body_size = size - (payloadOffset - offset)


    def __repr__(self):
        return "<%s (ID:0x%02X) at 0x%08X>" % (self.__class__.__name__,
                                               self.id, id(self))


    def __eq__(self, other):
        """ Equality check. Elements are considered equal if they are the same
            type and have the same ID, size, offset, and schema. Note: element
            value is not considered! 
        """
        if other is self:
            return True
        try:
            return (self.type == other.type
                    and self.id == other.id 
                    and self.offset == other.offset
                    and self.size == other.size 
                    and self.schema == other.schema)
        except AttributeError:
            return False


    @property
    def value(self):
        """ Parse and cache the element's value. """
        if self._value is not None:
            return self._value
        self._stream.seek(self.payloadOffset)
        self._value = self.parse(self._stream, self.size)
        return self._value


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
    """ Base class for an EBML signed integer element.
    """
    type = INT
    precache = True

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload.
            It is assumed the file pointer is at the start of the payload.
        """
        return core.read_signed_integer(stream, size)


#===============================================================================

class UIntegerElement(Element):
    """ Base class for an EBML unsigned integer element.
    """
    type = UINT
    precache = True

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload.
            It is assumed the file pointer is at the start of the payload.
        """
        return core.read_unsigned_integer(stream, size)


#===============================================================================

class FloatElement(Element):
    """ Base class for an EBML floating point element.
    """
    type = FLOAT
    precache = True

    def parse(self, stream, size):
        return core.read_float(stream, size)


#===============================================================================

class StringElement(Element):
    """ Base class for an EBML ASCII string element.
    """
    type = STRING

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload. 
            It is assumed the file pointer is at the start of the payload.
        """
        return core.read_string(stream, size)


#===============================================================================

class UnicodeElement(Element):
    """ Base class for an EBML UTF-8 string element.
    """
    type = UNICODE

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload. 
            It is assumed the file pointer is at the start of the payload.
        """
        return core.read_unicode_string(stream, size)


#===============================================================================

class DateElement(Element):
    """ Base class for an EBML 'date' element.
    """
    type = DATE

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload. 
            It is assumed the file pointer is at the start of the payload.
        """
        return core.read_date(stream, size)


#===============================================================================

class BinaryElement(Element):
    """ Base class for an EBML 'binary' element.
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
    """ Base class for an EBML 'master' element, a container for other
        elements.
    """
    type = CONTAINER

    def parse(self):
        """ Type-specific helper function for parsing the element's payload. """
        # Special case; unlike other elements, value() property doesn't call 
        # parse(). Used only when pre-caching. 
        return self.value


    def parseElement(self, stream):
        """ Read the next element from a stream, instantiate a `MasterElement` 
            object, and then return it and the offset of the next element
            (this element's position + size).
        """
        offset = stream.tell()
        eid, idlen = core.read_element_id(stream)
        esize, sizelen = core.read_element_size(stream)
        payloadOffset = offset + idlen + sizelen

        etype = self.schema.elements.get(eid, ("UnknownElement", Element))
        el = etype(stream, offset, esize, payloadOffset)
        
        if el.precache:
            # Read the value now, avoiding a seek later.
            el._value = el.parse(stream, esize)

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
        """ Parse and cache the element's value. 
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
        if el.name == "EBML":
            # Load 'header' info from the file
            self.info = {c.name: c.value for c in el.value}
            self.payloadOffset = pos
        else:
            self.info = {}
        self._stream.seek(startPos)

        # For python-ebml compatibility. Remove later.
        self.stream = DummyStream(self)
        
        self.body_size = self.size - self.payloadOffset


    def __repr__(self):
        return "<%s %r (type %r) at 0x%08X>" % (self.__class__.__name__, 
                                                self.name, self.type, id(self))


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
        return list(self)


    @property
    def value(self):
        """ An iterator for iterating the document's root elements. Same as
            `Document.__iter__()`.
        """
        # 'value' not really applicable to a document; return an iterator.
        return iter(self)


    def __getitem__(self, idx):
        """ Get one of the document's root elements by index. 
        """
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
        @ivar elementIds: A dictionary mapping element names to IDs.
        @ivar elementInfo: A dictionary mapping IDs to the raw schema attribute
            data. Is likely to have additional items not present in the created
            element class' attributes.
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
            @keyword name: The schema's name. Defaults to the document type
                element's default value (if defined) or the base file name.
        """
        
        # Helper function to cast schema attributes to Booleans.
        def _bool(v, default=False):
            try:
                return str(v).strip()[0] in 'Tt1'
            except (TypeError, IndexError, ValueError):
                return default
            
        self.filename = filename

        self.elements = {}    # Element types, keyed by ID
        self.elementInfo = {} # Raw element schema attributes, keyed by ID
        self.elementIds = {}  # Element IDs, keyed by element name
        
        schema = ET.parse(filename)

        for el in schema.findall('element'):
            attribs = el.attrib.copy()
            
            # Mandatory element attributes
            try:
                eid = int(attribs['id'],16)
                ename = el.attrib['name'].strip()
                etype = el.attrib['type'].lower().strip()
            except KeyError as err:
                raise KeyError("Element definition missing required attribute: %s" %
                               err)
            
            if etype not in self.ELEMENT_TYPES:
                raise ValueError("Unknown type for element %s (ID 0x%02x): %r" %
                                 (ename, eid, etype))

            if eid in self.elements:
                # Already appeared in schema. Duplicates are permitted, so long
                # as they have the same attributes. Second appearance may 
                # omit everything but the ID, name, and type.
                newatts = self.elementInfo[eid].copy()
                newatts.update(attribs)
                if self.elementInfo[eid] == newatts:
                    continue
                else:
                    raise TypeError('Element %s (ID 0x%02x) redefined with different attributes' %
                                    (ename, eid))
                        
            baseClass = self.ELEMENT_TYPES[etype]

            mandatory = _bool(attribs.get('mandatory', False))
            multiple = _bool(attribs.get('multiple', False))
            precache = _bool(attribs.get('precache', baseClass.precache))
            
            # Create a new Element subclass
            eclass = type('%sElement' % ename, (baseClass,),
                          {'id':eid, 'name':ename, 'schema':self,
                           'mandatory': mandatory, 'multiple': multiple, 
                           'precache': precache})
             
            self.elements[eid] = eclass
            self.elementInfo[eid] = attribs
            self.elementIds[ename] = eid

        # Special case: `Void` is a standard EBML element, but not its own
        # type (it's technically binary). Use the special `VoidElement` type.
        if 'Void' in self.elementIds:
            eid = self.elementIds['Void']
            void = type('VoidElement', (VoidElement,), 
                        {'id':eid, 'name':'Void', 'schema':self})
            self.elements[eid] = void
        
        # Schema name. Defaults to the schema's default EBML 'DocType' or
        # the schema file's base name.
        if name is None:
            name = self.type or os.path.splitext(os.path.basename(filename))[0]
        self.name = name
        

    def __repr__(self):
        return "<%s %r from '%s'>" % (self.__class__.__name__, self.name,
                                      os.path.realpath(self.filename))

    
    def __eq__(self, other):
        """ Equality check. Schemata are considered equal if the attributes of
            their elements match.
        """
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
        """ Schema version, extracted from EBML ``DocTypeVersion`` default. """
        return self._getInfo(0x4287, int) # ID of EBML 'DocTypeVersion'


    @property
    def type(self):
        """ Schema type name, extracted from EBML ``DocType`` default. """
        return self._getInfo(0x4282, str) # ID of EBML 'DocType'


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
