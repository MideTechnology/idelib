'''
Utility functions for doing low-level, general-purpose EBML reading and writing.

Most important are `build_ebml()` and `parse_ebml()`.

Created on Dec 10, 2013

@author: dstokes

@todo: Full refactoring to use `ebmlite`. 

'''

from collections import Sequence, OrderedDict
import datetime
import errno
import importlib
import os.path
import pkgutil
from StringIO import StringIO
import sys
import time
import types
import xml.dom.minidom

import ebml #@UnusedImport
from ebml import core as ebml_core
from ebml.schema import base as schema_base
from ebml.schema import specs as schema_specs

from ebmlite import Schema
from ebmlite import INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER

#===============================================================================
# 
#===============================================================================

DEFAULT_SCHEMA = "ebml.schema.mide"
# if __package__ is not None:
#     DEFAULT_SCHEMA = '.'.join([__package__, DEFAULT_SCHEMA])
# print "DEFAULT_SCHEMA = %r" % DEFAULT_SCHEMA

#===============================================================================
# Element types and encoding schemes
#===============================================================================

def encode_container(data, length=None, schema=DEFAULT_SCHEMA, 
                     elements=None, sizes={}):
    """ EBML encoder for a 'container' (i.e. 'master') element, compatible with
        the `ebml.core` encoding methods for primitive types. Recursively calls 
        other encoders for its contents. 
        
        @param data: The data to put into the container, either a `dict` or
            a set of `(name, value)` pairs. The data can be nested, combining
            both.  
        @keyword length: Unused; for compatibility with `ebml.core` methods.
        @keyword schema: The full module name of the EBML schema.
        @keyword elements: A dictionary of the schema's elements keyed by name.
            This should generally be left `None`, which defaults to all
            elements in the schema.
        @return: A `bytearray` of binary EBML data.
    """
    result = bytearray()
    if isinstance(data, dict):
        data = data.items()

    for child in data:
        if child[1] is not None:
            result.extend(build_ebml(*child, schema=schema, elements=elements,
                                     sizes=sizes))
    return result


def encode_binary(data, length=None):
    """ EBML encoder for a binary element. Compatible with the `ebml.core` 
        encoding methods.
        
        @param data: The raw binary data to write, presumably a string or 
            bytearray.
        @keyword length: A forced, fixed size of the resulting data.
    """
    # The existing string encoders are basically the same as binary encoders.
    # Note that if python-ebml changes encode_string so that it is no longer
    # compatible with bytearrays this will fail!
    if isinstance(data, basestring):
        return ebml_core.encode_unicode_string(data, length)
    return ebml_core.encode_string(bytearray(data), length)


# Element data type IDs, as used in `ebml.schema.base`.
# INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER = range(0, 8)

# Mapping of encoder data type IDs to their respective EBML encoder.
ENCODERS = {
    INT: ebml_core.encode_signed_integer,
    UINT: ebml_core.encode_unsigned_integer,
    FLOAT: ebml_core.encode_float,
    STRING: ebml_core.encode_string,
    UNICODE: ebml_core.encode_unicode_string,
    DATE: ebml_core.encode_date,
    BINARY: encode_binary,
    CONTAINER: encode_container
}

# Mapping of encoder data types to standard Python types
PYTHONTYPES = {
    INT: int,
    UINT: int,
    FLOAT: float,
    STRING: str,
    UNICODE: unicode,
    DATE: int,
    BINARY: bytearray,
    CONTAINER: None
}

def getSchemaModule(schema=DEFAULT_SCHEMA):
    """ Import a schema module.
    
        @keyword schema: The schema module, or the full module name of the 
            EBML schema. If the module cannot be found as specified, a path 
            relative to the current module is used.
    """
    if isinstance(schema, types.ModuleType):
        return schema
    schema = str(schema).strip()
    try:
        return importlib.import_module(schema)
    except ImportError:
        if __package__ is None:
            raise
        return importlib.import_module("%s.%s" % (__package__, schema))
            
    

def _getSchemaItems(schema=DEFAULT_SCHEMA, itemType=schema_specs.Element):
    """ Helper to retrieve data from a schema module.
    """
    result = []
    schemaMod = getSchemaModule(schema)
    for k,v in schemaMod.__dict__.iteritems():
        if k.startswith('_'): 
            continue
        try:
            if issubclass(v, itemType):
                result.append((k,v))
        except TypeError:
            # issubclass() doesn't like some types
            pass
    return result


def getSchemaElements(schema=DEFAULT_SCHEMA):
    """ Get all the EBML element classes for a given schema.

        @keyword schema: The full module name of the EBML schema.
        @return: A dictionary of element classes keyed on element name.
    """
    elements = _getSchemaItems(schema, schema_specs.Element)
    return dict([(el.name, el) for _, el in elements])


def getSchemaDocument(schema=DEFAULT_SCHEMA):
    """ Get the `Document` class for a given EBML schema.
    
        @keyword schema: The full module name of the EBML schema.
        @return: A subclass of `ebml.schema.base.Document`.
        """
    docs = _getSchemaItems(schema, schema_specs.Document)
    if len(docs) == 0:
        return None
    docname, doctype = docs[0]
    setattr(doctype, "name", docname)
    return doctype


def getElementSizes(schema=DEFAULT_SCHEMA):
    """ Parse the schema's XML file to get element `size` attribute for any
        element that specifies one. Intended for writing fixed-size EBML
        data. 
        
        @note: The `size` attribute is not part of the standard python-ebml 
            implementation, but its addition does not adversely affect the
            reading of the schema file.
            
        @keyword schema: The full module name of the EBML schema.
        @return: A dictionary of sizes keyed on element name. Only elements
            that have the `size` attribute will be included.
    """
    results = {}
    schema = getSchemaModule(schema).__name__
    filename = schema.split('.')[-1] + ".xml"
    doc = xml.dom.minidom.parseString(pkgutil.get_data(schema, filename))
    for el in doc.getElementsByTagName('element'):
        name = el.getAttribute('name')
        length = el.getAttribute('length')
        if name and length:
            results[name] = int(length)
    return results


def getElementTypes(schema=DEFAULT_SCHEMA):
    """
    """
    els = getSchemaElements(schema)
    for name,el in els.iteritems():
        els[name] = PYTHONTYPES.get(el.type, None)
    return els
    
#===============================================================================
# Writing EBML
#===============================================================================

def build_ebml(name, value, schema=DEFAULT_SCHEMA, elements=None, sizes=None):
    """ Construct an EBML element of the given type containing the given
        data. Operates recursively. Note that this function does not do any 
        significant type-checking, nor does it check against the schema.
        
        @param name: The name of the EBML element to create. It must match
            one defined in the Mide schema.
        @param value: The value for the EBML element. For non-"multiple" 
            elements, it can be either a primitive type or a dictionary. For 
            "multiple" elements, it can be a list of identically-typed items;
            each item will become its own element of the specified type, in the
            same order as elements in the list.
        @keyword schema: The full module name of the EBML schema.
        @keyword elements: A dictionary of the schema's elements keyed by name.
            This should generally be left `None`, which defaults to all
            elements in the schema.
        @keyword sizes: A dictionary of element fixed sizes keyed by name.
            Elements appearing in the dictionary will be written at the
            specified size. `None` will read the sizes from the schema's XML 
            file. `False` will not use fixed sizes.
        @return: A `bytearray` containing the raw binary EBML.
    """
    if elements is None:
        elements = getSchemaElements(schema)
    if sizes is None:
        sizes = getElementSizes(schema)
    elif sizes is False:
        sizes = {}
        
    if name not in elements:
        raise TypeError("Unknown element type: %r" % name)
    elementClass = elements[name]
    if elementClass.type not in ENCODERS:
        raise NotImplementedError("No encoder for element type %r" % name)
    
    elementId = elementClass.id
    elementEncoder = ENCODERS[elementClass.type]
    
    if not isinstance(value, basestring) and isinstance(value, Sequence):
        payload = bytearray()
        for v in value:
            payload.extend(build_ebml(name, v, schema, elements, sizes))
        return payload
    
    if elementClass.type == CONTAINER:
        payload = elementEncoder(value, None, schema, elements, sizes)
    else:
        payload = elementEncoder(value, length=sizes.get(name, None))
    
    result = ebml_core.encode_element_id(elementId)
    result.extend(ebml_core.encode_element_size(len(payload)))
    result.extend(payload)
    
    return result


#===============================================================================
# Reading EBML
#===============================================================================

def parse_ebml(elements, ordered=True):
    """ Reads a sequence of EBML elements and builds a (nested) dictionary,
        keyed by element name. Elements marked as "multiple" in the schema
        will produce a list containing one item for each element.
    """
    result = OrderedDict() if ordered else dict()
    if not isinstance(elements, Sequence):
        elements = [elements]
    for el in elements:
        if isinstance(el.value, list) or el.children:
            value = parse_ebml(el.value, ordered)
        else:
            value = el.value
        if el.multiple:
            result.setdefault(el.name, []).append(value)
        else:
            result[el.name] = value
    return result
            

def read_ebml(stream, schema=DEFAULT_SCHEMA, ordered=True):
    """ Import data from an EBML file. Wraps the process of creating the
        EBML document and parsing its contents.
        
        @param stream: The source EBML data. This can be a stream or a
            filename.
        @keyword schema: The full module name of the EBML schema.
        @keyword ordered: If `True` (default), the results are returned as
            instances of `OrderedDict` rather than standard dictionaries, 
            preserving the order of the elements.
        @return: A nested dictionary of values keyed by element name. Elements 
            marked as "multiple" in the schema will produce a list containing 
            one item for each element.
    """
    newStream = isinstance(stream, basestring)
    if newStream:
        stream = open(stream, 'rb')
    else:
        try:
            stream.seek(0)
        except IOError as e:
            # Some stream-like objects (like stdout) don't support seek.
            if e.errno != errno.EBADF:
                raise
            
    doctype = getSchemaDocument(schema)
    result = parse_ebml(doctype(stream).roots, ordered)
    if newStream:
        stream.close()
    return result


def getRawData(el, fs=None):
    """ Retrieve an EBML element's raw binary. The element must be part of a
        Document, and the Document must be from a file or file-like stream.
        Note that since this changes the read position in the file, this 
        function is NOT thread safe unless a separate file stream is provided,
        or `threaded_file` was used to open the main document.
        
        @param el: An EBML element
        @keyword fs: An alternate file-like object, so that the EBML document's
            main stream is not affected.
        @return: The EBML element's binary data, headers and payload and all.
    """
    if fs is None:
        fs = el.stream
    closed = fs.closed
    if closed:
        fs = file(fs.name, 'rb') 
    oldPos = fs.tell()
    fs.seek(el.offset)
    data = bytearray(fs.read(el.size))
    fs.seek(oldPos)
    if closed:
        fs.close()
    return data


#===============================================================================
# 
#===============================================================================

def dump_ebml(el, stream=None, indent=0, tabsize=4):
    """ Testing: Crawl an EBML Document and dump its contents, showing the 
        stream offset, name, and value of each child element. 
    """
    if stream is None:
        stream = sys.stdout
        
    if isinstance(el, schema_base.Document):
        stream.write("offset  name/value\n")
        stream.write("------  --------------------------------\n")
        for r in el.iterroots():
            dump_ebml(r, stream, indent, tabsize)
        return
    
    stream.write("%6d  %s%s:" % (el.offset," "*indent, el.name))
    if not el.children:
        stream.write("%r\n" % el.value)
    else:
        stream.write("\n")
        for child in el.value:
            dump_ebml(child, stream, indent+tabsize, tabsize) 


#===============================================================================
# 
#===============================================================================

def verify(data, schema=DEFAULT_SCHEMA):
    """ Basic sanity-check of data validity. If the data is bad an exception
        will be raised. The specific exception varies depending on the problem
        in the data.
        
        @keyword schema: The full module name of the EBML schema.
        @return: `True`. Any problems will raise exceptions.
    """
    docclass = getSchemaDocument(schema)
    if docclass is None:
        raise TypeError("Schema %r contained no Document" % schema)
    doc = docclass(StringIO(data))
    parse_ebml(doc.roots)
    return True

#===============================================================================
# 
#===============================================================================

def decode_attributes(data, withTypes=False):
    """ Convert a set of Attributes (as a list of dictionaries containing an
        `AttributeName` and one of the Attribute value elements (`IntAttribute`,
        `FloatAttribute`, etc.) to a proper dictionary. Attributes are tagged
        as 'multiple,' so they become lists when the EBML is parsed.
    """
    result = OrderedDict()
    for atts in data:
        k = atts.pop('AttributeName', None)
        if k is None:
            continue
        t,v = atts.items()[0]
        if withTypes:
            att = (v, t)
        else:
            att = v
        result.setdefault(k, []).append(att)
    return result

    
def encode_attributes(data):
    """ Construct a set of `Attribute` dicts from a dictionary or list of
        tuples/lists. Each value should be either a simple data type or a
        tuple containing the value and the specific value element name
        (IntAttribute, FloatAttribute, etc.). The value element type will 
        otherwise be inferred.
    """
    datetimeTypes = (datetime.datetime, datetime.date)
    attTypes = ((unicode,'UnicodeAttribute'),
                (basestring, 'StringAttribute'),
                (float, 'FloatAttribute'),
                (int, 'IntAttribute'),
                (time.struct_time, 'DateAttribute'),
                (datetimeTypes, 'DateAttribute'))
    
    if isinstance(data, dict):
        data = data.items()
    
    result = []
    for d in data:
        if isinstance(d[1], (tuple, list)):
            print d
            k = d[0]
            v, elementType = d[1]
        else:
            k,v = d
            for t, elementType in attTypes:
                if isinstance(v, t):
                    break
                elementType = 'BinaryAttribute'
        
        if elementType == 'DateAttribute':
            if isinstance(v, (int, float)):
                v = int(v)
            elif isinstance(data, datetimeTypes):
                v = int(time.mktime(data.timetuple()))
            elif isinstance(data, time.struct_time):
                v = int(time.mktime(v))
                
        result.append({'AttributeName': k, elementType: v})

    return result
    

def build_attributes(data):
    """ Construct `Attribute` EBML from dictionary or list of key/value pairs. 
        Each value should be either a simple data type or a tuple containing 
        the value and the specific value element name (`IntAttribute`, 
        `FloatAttribute`, etc.). The value element type will otherwise be 
        inferred.
    """
    return build_ebml('Attribute', encode_attributes(data))

#===============================================================================
# 
#===============================================================================

SCHEMATA = {}

def getSchema(schema, reload=False):
    """ Attempt to load a schema, using a filename, a module, or the name of
        a module. For backwards compatibility with old code.
    """
    global SCHEMATA
    
    if isinstance(schema, Schema):
        return schema
    
    if schema in SCHEMATA and not reload:
        return SCHEMATA[schema]
        
    if isinstance(schema, types.ModuleType):
        # python-ebml schema, probably; load from module path.
        schema = schema.__name__
        
    if isinstance(schema, basestring):
        # First, try it as a filename.
        filename = os.path.realpath(schema)
        if os.path.exists(filename):
            s = Schema(filename)
            SCHEMATA[filename] = s
            return s
        
        # Second, try it as a module name (like old mide_ebml.util functions)
        modname, _, filename = schema.rpartition('.')
        try:
            if pkgutil.get_loader(modname) is not None:
                filename = "%s.xml" % filename
                data = pkgutil.get_data(modname, filename)
                if data:
                    s = Schema(StringIO(data))
                    SCHEMATA[schema] = s
                    s.source = schema
                    return s
                else:
                    raise IOError("Could not read %s from module %s" % (modname, filename))
        except ImportError:
            raise IOError("Could not load schema from module %s" % schema)
                
    raise IOError("Could not load schema from %s" % schema)


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    # TODO: Move this testing into a real unit test.
    from pprint import pprint
    from ebml.schema.mide import MideDocument
    
    print "\n*** Testing configuration EBML input and output"
    
    def uglyprint(*args, **kwargs):
        print repr(args[0])
        
    def testWriteRead(parentElementName, children, pretty=True):
        printer = pprint if pretty else uglyprint
        
        print "*" * 78
        print "*** Source data:"
        printer(children)
    
        print "\n*** Building EBML data:"    
        config = build_ebml(parentElementName, children)
        printer(config)
        
        print "\n*** Creating MideDocument from data: ",
        doc = MideDocument(StringIO(config))
        printer(doc)
        
        print "*** Document structure:"
        dump_ebml(doc)
        
        print "\n*** Parsed Data:"
        readConfig = parse_ebml(doc.roots, ordered=False)[parentElementName]
        printer(readConfig)
        
        print "\n*** Comparing the output to the input...", 
        try:
            assert(readConfig == children)
            print "Input matches the output!"
        except AssertionError:
            print "Input and output did not match!"
            
        print "*" * 78


    testWriteRead("RecorderConfiguration", {
        'SSXBasicRecorderConfiguration': {
            'SampleFreq': 5000,
            'AAFilterCornerFreq': 1234,
            'OSR': 16,
        },
        'SSXTriggerConfiguration': {
            'WakeTimeUTC': 0,
            'PreRecordDelay': 0,
            'AutoRearm': 0,
            'RecordingTime': 0,
            'Trigger': [{
                'TriggerChannel': -1,
                'TriggerSubChannel': -1,
                'TriggerWindowLo': -1,
                'TriggerWindowHi': 1,
            }],
        },
    })

    testWriteRead("CalibrationList", {
        'UnivariatePolynomial': [
            {'CalID': 1,
             'CalReferenceValue': 4.0,
             'PolynomialCoef': [1.1, 2.2, 3.3],
             },
        ],
    })
