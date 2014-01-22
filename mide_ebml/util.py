'''
Utility functions for doing low-level, general-purpose EBML reading and writing.

Most important are `build_ebml()` and `read_ebml()`.

Created on Dec 10, 2013

@author: dstokes
'''

from collections import Sequence
import pkgutil
import sys
import xml.dom.minidom

from ebml import core as ebml_core
from ebml.schema import base as schema_base
# from ebml.schema import mide as mide_schema

import importlib

#===============================================================================
# 
#===============================================================================

DEFAULT_SCHEMA = "ebml.schema.mide"

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
    """ EBML encoder for a binary element, which does nothing (binary is
        binary). Compatible with the `ebml.core` encoding methods.
        
        @param data: The data to put into the container, either a `dict` or
            a set of `(name, value)` pairs. The data can be nested, combining
            both.
        @keyword length: Unused; for compatibility with `ebml.core` methods.
    """
    return data

# Element data type IDs, as used in `ebml.schema.base`.
INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER = range(0, 8)

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

# Mapping of all Mide element type names to their respective classes
# MIDE_ELEMENTS = dict(((k[:-7],v) for k,v in mide_schema.__dict__.iteritems() \
#                       if k.endswith("Element")))

def getSchemaElements(schema=DEFAULT_SCHEMA):
    """ Get all the EBML element classes for a given schema.

        @keyword schema: The full module name of the EBML schema.
        @return: A dictionary of element classes keyed on element name.
    """
    schemaMod = importlib.import_module(schema)
    return dict(((k[:-7],v) for k,v in schemaMod.__dict__.iteritems() \
                 if k.endswith("Element")))


def getSchemaDocument(schema=DEFAULT_SCHEMA):
    """ Get the `Document` class for a given EBML schema.
    
        @keyword schema: The full module name of the EBML schema.
        @return: A subclass of `ebml.schema.base.Document`.
        """
    schemaMod = importlib.import_module(schema)
    for k,v in schemaMod.__dict__.iteritems():
        if k.endswith("Document"):
            return v
    return None


def getElementSizes(schema=DEFAULT_SCHEMA):
    """ Parse the schema's XML file to get element `size` attribute for any
        element that specifies one. Intended for writing fixed-size EBML
        data. 
        
        @note: The `size` attribute is not part of the standard python-ebml 
            implementation.
            
        @keyword schema: The full module name of the EBML schema.
        @return: A dictionary of sizes keyed on element name.
    """
    results = {}
    filename = schema.split('.')[-1] + ".xml"
    doc = xml.dom.minidom.parseString(pkgutil.get_data(schema, filename))
    for el in doc.getElementsByTagName('element'):
        name = el.getAttribute('name')
        length = el.getAttribute('length')
        if name and length:
            results[name] = int(length)
    return results


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

def read_ebml(elements):
    """ Reads a sequence of EBML elements and builds a (nested) dictionary,
        keyed by element name. Elements marked as "multiple" in the schema
        will produce a list containing one item for each element.
    """
    result = {}
    if not isinstance(elements, Sequence):
        elements = [elements]
    for el in elements:
        if isinstance(el.value, list) or el.children:
            value = read_ebml(el.value)
        else:
            value = el.value
        if el.multiple:
            result.setdefault(el.name, []).append(value)
        else:
            result[el.name] = value
    return result
            
    
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
    
    stream.write("%6d  %s%s:" % (el.stream.offset," "*indent, el.name))
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
    read_ebml(doc)
    return True

#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    # TODO: Move this testing into a real unit test.
    from pprint import pprint
    from StringIO import StringIO
    from dataset import MideDocument
    
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
        readConfig = read_ebml(doc.roots)[parentElementName]
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
            'Trigger': {
                'TriggerChannel': -1,
                'TriggerSubChannel': -1,
                'TriggerWindowLo': -1,
                'TriggerWindowHi': 1,
            },
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
