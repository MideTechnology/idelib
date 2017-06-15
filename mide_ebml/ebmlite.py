'''
EBMLite: A lightweight EBML parsing library. It is designed to crawl through
EBML files quickly and efficiently, and that's about it.

Created on Apr 27, 2017

@todo: Remove benchmarking code from end of script.
@todo: Unit tests.
@todo: Refactor other code and remove python-ebml compatibility cruft.
@todo: Complete EBML encoding, making it a full replacement for python-ebml.
@todo: New schema format, getting further away from python-ebml. 
@todo: Validation. Extract valid child element info from the schema.
@todo: Proper support for 'infinite' Documents (i.e `size` is `None`).
@todo: Document-wide caching, for future handling of streamed data.
@todo: Some sort of schema caching, to prevent redundant element types.
@todo: Utilities for conversion to/from XML, etc.
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

__all__ = ['BinaryElement', 'DateElement', 
           'Document', 'Element', 'FloatElement', 
           'IntegerElement', 'MasterElement',  
           'Schema', 'StringElement', 'UIntegerElement', 
           'UnicodeElement', 'VoidElement']

from collections import OrderedDict
from datetime import datetime
import os.path
from StringIO import StringIO
from xml.etree import ElementTree as ET

from ebml import core
from ebml.core import read_element_id, read_element_size
from ebml.core import read_float, read_signed_integer, read_unsigned_integer
from ebml.core import read_date, read_string, read_unicode_string

#===============================================================================
#
#===============================================================================

# Type IDs, for python-ebml compatibility
INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER = range(0, 8)
UNKNOWN = -1 # not in python-ebml


#===============================================================================
#
#===============================================================================

class Element(object):
    """ Base class for all EBML elements. Also used for unknown elements (i.e.
        those with IDs not in the schema.
        
        @cvar id: The element's EBML ID.
        @cvar name: The element's name. 
        @cvar schema: The `Schema` to which this element belongs.
        @cvar multiple: Can this element be appear multiple times? Note: 
            Not currently enforced.
        @cvar mandatory: Must this element appear in all EBML files using
            this element's schema? Note: Not currently enforced.
        @cvar type: The element's numeric EBML type (from python-ebml).
        @cvar precache: If `True`, the Element's value is read when the Element
            is parsed. if `False`, the value is lazy-loaded when needed.
        @cvar length: An explicit length (in bytes) of the element when
            encoding. `None` will use standard EBML variable-length encoding.
    """
    # python-ebml type ID. 
    type = UNKNOWN

    dtype = bytearray

    # Should this element's value be read/cached when the element is parsed?
    precache = False

    # Do valid EBML documents require this element?
    mandatory = False
    
    # Does a valid EBML document permit more than one of the element?
    multiple = False

    # Explicit length for this Element subclass, used for encoding.
    length = None
    
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
            @keyword stream: A file-like object containing EBML data.
            @keyword offset: The element's starting location in the file.
            @keyword size: The size of the whole element.
            @keyword payloadOffset: The starting location of the element's
                payload (i.e. immediately after the element's header).
        """
#         self._stream = stream
        self.stream = stream
        self.offset = offset
        self.size = size
        self.payloadOffset = payloadOffset
        self._value = None

        # For python-ebml compatibility. Remove later.
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
        self.stream.seek(self.payloadOffset)
        self._value = self.parse(self.stream, self.size)
        return self._value


    #===========================================================================
    # Caching (experimental)
    #===========================================================================

    def gc(self, recurse=False):
        """ Clear any cached values. To save memory and/or force values to be
            re-read from the file. Returns the number of cached values cleared.
        """
        if self._value is None:
            return 0
        self._value = None
        
        return 1

    #===========================================================================
    # Encoding (WIP)
    #===========================================================================
    
    @classmethod
    def encodePayload(cls, data, length=None):
        """ Type-specific payload encoder. """
        if isinstance(data, basestring):
            return core.encode_unicode_string(data, length)
        return core.encode_string(bytearray(data), length)
         
     
    @classmethod
    def encode(cls, value, length=None, lengthSize=None):
        """ Encode an EBML element.
            
            @param value: The value to encode, or a list of values to encode.
                If a list is provided, each item will be encoded as its own
                element.
            @keyword length: An explicit length for the encoded data, 
                overriding the variable length encoding. For producing
                byte-aligned structures.
            @keyword lengthSize: An explicit length for the encoded element
                size, overriding the variable length encoding.
            @return: A bytearray containing the encoded EBML data.
        """ 
        length = length or cls.length
        if isinstance(value, (list, tuple)):
            if not cls.multiple:
                raise ValueError("Multiple %s elements per parent not permitted" 
                                 % cls.name)
            result = bytearray()
            for v in value:
                result.extend(cls.encode(v, length=length, lengthSize=lengthSize))
            return result
        payload = cls.encodePayload(value, length=length)
        length = length or len(payload)
        encId = core.encode_element_id(cls.id) 
        return encId + core.encode_element_size(length, lengthSize) + payload
        


#===============================================================================

class IntegerElement(Element):
    """ Base class for an EBML signed integer element.
    """
    type = INT
    dtype = int
    precache = True

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload.
            It is assumed the file pointer is at the start of the payload.
        """
        return read_signed_integer(stream, size)


    @classmethod
    def encodePayload(cls, data, length=None):
        """ Type-specific payload encoder for signed integer elements. """
        return core.encode_signed_integer(data, length)


#===============================================================================

class UIntegerElement(Element):
    """ Base class for an EBML unsigned integer element.
    """
    type = UINT
    dtype = int
    precache = True

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload.
            It is assumed the file pointer is at the start of the payload.
        """
        return read_unsigned_integer(stream, size)


    @classmethod
    def encodePayload(cls, data, length=None):
        """ Type-specific payload encoder for unsigned integer elements. """
        return core.encode_unsigned_integer(data, length)


#===============================================================================

class FloatElement(Element):
    """ Base class for an EBML floating point element.
    """
    type = FLOAT
    dtype = float
    precache = True

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload. 
            It is assumed the file pointer is at the start of the payload.
        """
        return read_float(stream, size)


    @classmethod
    def encodePayload(cls, data, length=None):
        """ Type-specific payload encoder for floating point elements. """
        return core.encode_float(data, length)


#===============================================================================

class StringElement(Element):
    """ Base class for an EBML ASCII string element.
    """
    type = STRING
    dtype = str

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload. 
            It is assumed the file pointer is at the start of the payload.
        """
        return read_string(stream, size)


    @classmethod
    def encodePayload(cls, data, length=None):
        """ Type-specific payload encoder for ASCII string elements. """
        return core.encode_string(data, length)



#===============================================================================

class UnicodeElement(Element):
    """ Base class for an EBML UTF-8 string element.
    """
    type = UNICODE
    dtype = unicode

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload. 
            It is assumed the file pointer is at the start of the payload.
        """
        return read_unicode_string(stream, size)


    @classmethod
    def encodePayload(cls, data, length=None):
        """ Type-specific payload encoder for Unicode string elements. """
        return core.encode_unicode_string(data, length)


#===============================================================================

class DateElement(Element):
    """ Base class for an EBML 'date' element.
    """
    type = DATE
    dtype = datetime

    def parse(self, stream, size):
        """ Type-specific helper function for parsing the element's payload. 
            It is assumed the file pointer is at the start of the payload.
        """
        return read_date(stream, size)


    @classmethod
    def encodePayload(cls, data, length=None):
        """ Type-specific payload encoder for date elements. """
        return core.encode_date(data, length)



#===============================================================================

class BinaryElement(Element):
    """ Base class for an EBML 'binary' element.
    """
    type = BINARY


#===============================================================================

class VoidElement(BinaryElement):
    """ Special case ``Void`` element. Its contents are ignored; they are never
        even read. 
    """
   
    def parse(self, stream, size):
        return bytearray()


    @classmethod
    def encodePayload(cls, data, length=0):
        """ Type-specific payload encoder for Void elements. """
        return bytearray('\xff' * length)


#===============================================================================

class MasterElement(Element):
    """ Base class for an EBML 'master' element, a container for other
        elements.
    """
    type = CONTAINER
    dtype = list

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
        eid, idlen = read_element_id(stream)
        esize, sizelen = read_element_size(stream)
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
#             self._stream.seek(pos)
#             el, pos = self.parseElement(self._stream)
            self.stream.seek(pos)
            el, pos = self.parseElement(self.stream)
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
            

    #===========================================================================
    # Encoding (very experimental!)
    #===========================================================================
    
    @classmethod
    def encodePayload(cls, data, length=None):
        """ Type-specific payload encoder for 'master' elements. 
        """
        if isinstance(data, dict):
            data = data.items()
        elif not isinstance(data, (list, tuple)):
            raise TypeError("wrong type for %s payload: %s" % (cls.name, 
                                                               type(data)))
        result = bytearray()
        for k,v in data:
            if k not in cls.schema:
                raise TypeError("Element type %r not found in schema" % k)
            # TODO: Validation of hierarchy, multiplicity, mandate, etc.
            result.extend(cls.schema[k].encode(v))
         
        return result

    
    @classmethod
    def encode(cls, data, **kwargs):
        """ Encode an EBML master element.
            
            @param data: The data to encode, provided as a dictionary keyed by
                element name, a list of two-item name/value tuples, or a list
                of either. Note: individual items in a list of name/value pairs
                *must* be tuples!
            @return: A bytearray containing the encoded EBML binary.
        """ 
        if isinstance(data, list) and len(data)>0 and isinstance(data[0],list):
            # List of lists: special case for 'master' elements.
            # Encode as multiple 'master' elements.
            result = bytearray()
            for v in data:
                result.extend(cls.encode(v))
            return result
        return super(MasterElement, cls).encode(data)


#===============================================================================
# 
#===============================================================================

class Document(MasterElement):
    """ Base class for an EBML document, containing multiple 'root' elements.
    """

    def __init__(self, stream, name=None, size=None):
        """ Constructor.
        
            @param stream: A stream object (e.g. a file) from which to read 
                the EBML content, or a filename.
            @keyword name: The name of the document. Defaults to the filename
                (if applicable).
        """
        self._value = None
        self._stream = stream
        self.stream = stream
        self.size = size
        self.name = name
        self.id = None
        self.offset =  self.payloadOffset = 0

        try:
            self.filename = stream.name
        except AttributeError:
            self.filename = ""
            
        if name is None:
            if self.filename:
                self.name = os.path.splitext(os.path.basename(self.filename))[0]
            else:
                self.name = self.__class__.__name__

        if size is None:
            if isinstance(stream, StringIO):
                self.size = stream.len
            elif os.path.exists(self.filename):
                self.size = os.path.getsize(self.stream.name)

        startPos = self.stream.tell()
        el, pos = self.parseElement(self.stream)
        if el.name == "EBML":
            # Load 'header' info from the file
            self.info = {c.name: c.value for c in el.value}
            self.payloadOffset = pos
        else:
            self.info = {}
        self.stream.seek(startPos)

        if self.size is not None:
            self.body_size = self.size - self.payloadOffset
        else:
            self.body_size = None


    def __repr__(self):
        return "<%s %r at 0x%08X>" % (self.__class__.__name__, self.name, 
                                      id(self))


    def close(self):
        """ Close the EBML file. Should generally be used only if the object was
            created using a filename, rather than a stream.
        """
        self.stream.close()


    def __iter__(self):
        """ Iterate root elements.
        """
        # TODO: Cache root elements, prevent unnecessary duplicates.
        pos = self.payloadOffset
        while True:
            self.stream.seek(pos)
            try:
                el, pos = self.parseElement(self.stream)
                yield el
            except TypeError:
                # Occurs when trying to parse zero-length file (EOF)
                break


    def iterroots(self):
        """ Iterate root elements. For working like old python-ebml.
        """
        return iter(self)


    @property
    def roots(self):
        """ The document's root elements. For python-ebml compatibility.
            Using this is not recommended.
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


    #===========================================================================
    # Encoding (very experimental!)
    #===========================================================================

    @classmethod
    def _createHeaders(cls):
        """ Create the default EBML 'header' elements for a Document, using
            the default values in the schema.
            
            @return: A dictionary containing a single key (``EBML``) with a
                dictionary as its value. The child dictionary contains
                element names and values.
        """
        if 'EBML' not in cls.schema:
            return {}
        
        headers = OrderedDict()
        for elName, elType in (('EBMLVersion', int), 
                               ('EBMLReadVersion', int),
                               ('DocType', str),
                               ('DocTypeVersion', int),
                               ('DocTypeReadVersion', int)):
            if elName in cls.schema:
                v = cls.schema._getInfo(cls.schema[elName].id, elType)
                if v is not None:
                    headers[elName] = v
                    
        return OrderedDict(EBML=headers)
    
        
    @classmethod
    def encode(cls, stream, data, headers=False, **kwargs):
        """ Encode an EBML document.
            
            @param value: The data to encode, provided as a dictionary keyed by
                element name, or a list of two-item name/value tuples. Note: 
                individual items in a list of name/value pairs *must* be tuples!
            @return: A bytearray containing the encoded EBML binary.
        """ 
        if headers is True:
            stream.write(cls.encodePayload(cls._createHeaders()))
            
        if isinstance(data, list):
            if len(data)>0 and isinstance(data[0],list):
                # List of lists: special case for Documents.
                # Encode as multiple 'root' elements.
                raise TypeError('Cannot encode multiple Documents')
            else:
                for v in data:
                    stream.write(cls.encodePayload(v))
        else:
            stream.write(cls.encodePayload(data))


#===============================================================================
#
#===============================================================================

class Schema(object):
    """ An EBML schema, mapping element IDs to names and data types. Unlike the
        document and element types, this is not a base class; all schemata are
        actual instances of this class.
    
        @ivar document: The schema's Document subclass.
        @ivar elements: A dictionary mapping element IDs to the schema's
            corresponding `Element` subclasses.
        @ivar elementIds: A dictionary mapping element names to the schema's
            corresponding `Element` subclasses.
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
        self.filename = filename

        self.elements = {}    # Element types, keyed by ID
        self.elementIds = {}  # Element types, keyed by element name
        self.elementInfo = {} # Raw element schema attributes, keyed by ID
        
        # Parse. 
        schema = ET.parse(filename)
        self._parseSchema(schema)

        # Special case: `Void` is a standard EBML element, but not its own
        # type (it's technically binary). Use the special `VoidElement` type.
        if 'Void' in self.elementIds:
            el = self.elementIds['Void']
            void = type('VoidElement', (VoidElement,), 
                        {'id':el.id, 'name':'Void', 'schema':self, 
                         'mandatory': el.mandatory, 'multiple': el.multiple})
            self.elements[el.id] = void
            self.elementIds['Void'] = void
        
        # Schema name. Defaults to the schema's default EBML 'DocType' or
        # the schema file's base name.
        if name is None:
            name = self.type or os.path.splitext(os.path.basename(filename))[0]
        self.name = name
        
        # Create the schema's Document subclass.
        self.document = type('%sDocument' % self.name.title(), (Document,),
                             {'schema': self})

    
    def old_parseSchema(self, schema):
        """ Parse a python-ebml schema XML file. Isolated from `__init__()` for
            alternative future schema format.
        """
        def _bool(v, default=False):
            try:
                return str(v).strip()[0] in 'Tt1'
            except (TypeError, IndexError, ValueError):
                return default
            
        for el in schema.findall('element'):
            attribs = el.attrib.copy()
            
            eid = int(attribs['id'],16) if 'id' in attribs else None
            ename = el.attrib['name'].strip() if 'name' in attribs else None
            etype = el.attrib['type'].strip() if 'type' in attribs else None
            
            # Duplicate elements are permitted, for defining a child element
            # that can appear as a child to multiple master elements. Additional
            # definitions only need to specify the element ID or name.
            if ename in self.elementIds:
                eid = eid or self.elementIds[ename].id
            
            if eid in self.elements:
                # Already appeared in schema. Duplicates are permitted, so long
                # as they have the same attributes. Second appearance may 
                # omit everything the ID and/or the name.
                newatts = self.elementInfo[eid].copy()
                newatts.update(attribs)
                if self.elementInfo[eid] == newatts:
                    # TODO: Update hierarchy information. Not currently used.
                    continue
                else:
                    raise TypeError('Element %r (ID 0x%02X) redefined with '
                                    'different attributes' % (ename, eid))
            
            # Mandatory element attributes
            if eid is None:
                raise ValueError('Element definition missing required '
                                 '"id" attribute')
            elif ename is None:
                raise ValueError('Element ID 0x%02X missing required '
                                 '"name" attribute' % eid)
            elif etype is None:
                raise ValueError('Element "%s" (ID 0x%02X) missing required '
                                 '"type" attribute' % (ename, eid))
            
            if etype not in self.ELEMENT_TYPES:
                raise ValueError("Unknown type for element %r (ID 0x%02x): %r" %
                                 (ename, eid, etype))

            etype = etype.lower()
            baseClass = self.ELEMENT_TYPES[etype]

            mandatory = _bool(attribs.get('mandatory', False))
            multiple = _bool(attribs.get('multiple', True))
            precache = _bool(attribs.get('precache', baseClass.precache))
            length = int(attribs.get('length', 0)) or None
            
            # Create a new Element subclass
            eclass = type('%sElement' % ename, (baseClass,),
                          {'id':eid, 'name':ename, 'schema':self,
                           'mandatory': mandatory, 'multiple': multiple, 
                           'precache': precache, 'length':length})
             
            self.elements[eid] = eclass
            self.elementInfo[eid] = attribs
            self.elementIds[ename] = eclass


    def _parseSchema(self, schema):
        def _bool(v, default=False):
            try:
                return str(v).strip()[0] in 'Tt1'
            except (TypeError, IndexError, ValueError):
                return default
            
        for el in schema.findall('element'):
            attribs = el.attrib.copy()
            
            eid = int(attribs['id'],16) if 'id' in attribs else None
            ename = attribs['name'].strip() if 'name' in attribs else None
            etype = attribs['type'].strip() if 'type' in attribs else None
            mandatory = _bool(attribs.get('mandatory', False))
            multiple = _bool(attribs.get('multiple', True))
            precache = _bool(attribs['precache']) if 'precache' in attribs else None
            length = int(attribs['length']) if 'length' in attribs else None
        
            self.addElement(eid, ename, etype, multiple, mandatory, length, precache, attribs)
        

    def addElement(self, eid, ename, etype, multiple=True, mandatory=False,
                   length=None, precache=None, attribs={}):
        """ Create a new `Element` subclass and add it to the schema. 
        
            Duplicate elements are permitted (e.g. if one kind of element can 
            appear in different master elements), provided their attributes do 
            not conflict. The first appearance of an element definition in the
            schema must contain the required ID, name, and type; successive 
            appearances only need the ID and/or name.
        
            @param eid: The element's EBML ID.
            @param ename: The element's name.
            @param etype: The element's type (string, see `ELEMENT_TYPES`)
            @keyword multiple: If `True`, an EBML document can contain more
                than one of this element. Not currently enforced.
            @keyword mandatory: If `True`, a valid EBML document requires one 
                (or more) of this element. Not currently enforced.
            @keyword length: A fixed length to use when writing the element.
                `None` will use the minimum length required.
            @keyword precache: If `True`, the element's value will be read
                when the element is parsed, rather than when the value is
                explicitly accessed. Can save time for small elements.
            @keyword attribs: A dictionary of raw element attributes, as read
                from the schema file.
        """
        # Duplicate elements are permitted, for defining a child element
        # that can appear as a child to multiple master elements. Additional
        # definitions only need to specify the element ID or name.
        if ename in self.elementIds:
            eid = eid or self.elementIds[ename].id
        
        if eid in self.elements:
            # Already appeared in schema. Duplicates are permitted, so long
            # as they have the same attributes. Second appearance may 
            # omit everything the ID and/or the name.
            newatts = self.elementInfo[eid].copy()
            newatts.update(attribs)
            if self.elementInfo[eid] == newatts:
                # TODO: Update hierarchy information. Not currently used.
                return self.elements[eid]
            else:
                raise TypeError('Element %r (ID 0x%02X) redefined with '
                                'different attributes' % (ename, eid))
        
        # Mandatory element attributes
        if eid is None:
            raise ValueError('Element definition missing required '
                             '"id" attribute')
        elif ename is None:
            raise ValueError('Element ID 0x%02X missing required '
                             '"name" attribute' % eid)
        elif etype is None:
            raise ValueError('Element "%s" (ID 0x%02X) missing required '
                             '"type" attribute' % (ename, eid))
        
        if etype not in self.ELEMENT_TYPES:
            raise ValueError("Unknown type for element %r (ID 0x%02x): %r" %
                             (ename, eid, etype))

        etype = etype.lower()
        baseClass = self.ELEMENT_TYPES[etype]
        precache = baseClass.precache if precache is None else precache
        
        # Create a new Element subclass
        eclass = type('%sElement' % ename, (baseClass,),
                      {'id':eid, 'name':ename, 'schema':self,
                       'mandatory': mandatory, 'multiple': multiple, 
                       'precache': precache, 'length':length})
         
        self.elements[eid] = eclass
        self.elementInfo[eid] = attribs
        self.elementIds[ename] = eclass

        return eclass
        

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


    def __contains__(self, key):
        return (key in self.elementIds) or (key in self.elements)
    
    
    def __getitem__(self, key):
        if isinstance(key, basestring):
            return self.elementIds[key]
        return self.elements[key]



    def load(self, fp, name=None):
        """ Load an EBML file using this Schema.
            
            @param fp: A file-like object containing the EBML to load, or the
                name of an EBML file.
            @keyword name: The name of the document. Defaults to filename.
        """
        if isinstance(fp, basestring):
            fp = open(fp, 'rb')

        return self.document(fp, name=name)


    def __call__(self, fp, name=None):
        return self.load(fp, name=name)


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


    #===========================================================================
    # 
    #===========================================================================
    
    def encode(self, stream, data, headers=False):
        """ Write an EBML document using this Schema to a file or file-like
            stream.
            
            @param stream: The file (or ``.write()``-supporting file-like 
                object) to which to write the encoded EBML.
            @param value: The data to encode, provided as a dictionary keyed by
                element name, or a list of two-item name/value tuples. Note: 
                individual items in a list of name/value pairs *must* be tuples!
        """ 
        self.document.encode(stream, data, headers=headers)
        return stream


    def encodes(self, data, headers=False):
        """ Create an EBML document using this Schema, returned as a string.
            
            @param value: The data to encode, provided as a dictionary keyed by
                element name, or a list of two-item name/value tuples. Note: 
                individual items in a list of name/value pairs *must* be tuples!
            @return: A string containing the encoded EBML binary.
        """ 
        stream = StringIO()
        self.encode(stream, data, headers=headers)
        return stream.getvalue()


#===============================================================================
# 
#===============================================================================

SCHEMATA = {}

def loadSchema(filename, reload=False, **kwargs):
    """ Import a Schema XML file. Loading the same file more than once will
        return the initial instantiation, unless `reload` is `True`.
        
        @param filename: The full path and name of the Schema XML file.
        @keyword reload: If `True`, the resulting Schema is guaranteed to be
            new. Note: references to previous instances of the Schema will not
            update.
    """
    global SCHEMATA
    
    filename = os.path.realpath(filename)
    if filename in SCHEMATA and not reload:
        return SCHEMATA[filename]
    return SCHEMATA.setdefault(filename, Schema(filename, **kwargs))


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
