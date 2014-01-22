'''
Utility functions for doing low-level, general-purpose EBML reading and writing.

Most important are `build_ebml()` and `read_ebml()`.

Created on Dec 10, 2013

@author: dstokes
'''

from collections import Sequence

from ebml import core as ebml_core
from ebml.schema import base as schema_base
# from ebml.schema import mide as mide_schema

import importlib

#===============================================================================
# Element types and encoding schemes
#===============================================================================

def encode_container(data, length=None, schema="ebml.schema.mide", 
                     elements=None):
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
            result.extend(build_ebml(*child, schema=schema, elements=elements))
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

def getSchemaElements(schema="ebml.schema.mide"):
    """
    """
    schemaMod = importlib.import_module(schema)
    return dict(((k[:-7],v) for k,v in schemaMod.__dict__.iteritems() \
                 if k.endswith("Element")))


def getSchemaDocument(schema="ebml.schema.mide"):
    """
    """
    schemaMod = importlib.import_module(schema)
    for k,v in schemaMod.__dict__.iteritems():
        if k.endswith("Document"):
            return v
    return None

#===============================================================================
# Writing EBML
#===============================================================================

def build_ebml(name, value, schema="ebml.schema.mide", elements=None):
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
        @return: A `bytearray` containing the raw binary EBML.
    """
    if elements is None:
        elements = getSchemaElements(schema)
        
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
            payload.extend(build_ebml(name, v, schema, elements))
        return payload
    
    if elementClass.type == CONTAINER:
        payload = elementEncoder(value, schema=schema, elements=elements)
    else:
        payload = elementEncoder(value)
    
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
            
    
def dump_ebml(el, indent=0, tabsize=4):
    """ Testing: Crawl an EBML Document and dump its contents, showing the 
        stream offset, name, and value of each child element. 
    """
    if isinstance(el, schema_base.Document):
        print "offset  name/value"
        print "------  --------------------------------"
        for r in el.iterroots():
            dump_ebml(r, indent, tabsize)
        return
    
    print ("%6d  %s%s:" % (el.stream.offset," "*indent, el.name)),
    if not el.children:
        print "%r" % el.value
    else:
        print ""
        for child in el.value:
            dump_ebml(child, indent+tabsize) 


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
