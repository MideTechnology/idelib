'''
Created on Dec 20, 2013

@author: dstokes
'''

import argparse
import os.path
import pkgutil
from StringIO import StringIO
import xml.dom.minidom

from ebml import core as ebml_core
from util import getSchemaElements, getSchemaDocument, ENCODERS

DEFAULT_SCHEMA = "ebml.schema.mide"

INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER = range(0, 8)

def fromInt(v):
    try:
        return int(v)
    except ValueError:
        return int(v, 16)
    
TYPES = {
    INT: fromInt,
    UINT: fromInt,
    FLOAT: float,
    STRING: str,
    UNICODE: unicode,
    DATE: ebml_core.encode_date,
    BINARY: lambda x: x
}


def getSizeList(schema):
    """
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


def encode_container(data, length=None, elements=None, sizes={}):
    """ EBML encoder for a 'container' (i.e. 'master') element, compatible with
        the `ebml.core` encoding methods for primitive types. Recursively calls 
        other encoders for its contents. 
        
        @param data: 
        @keyword length: Unused; for compatibility with `ebml.core` methods.
        @return: A `bytearray` of binary EBML data.
    """
    result = bytearray()
    
    for c in data.childNodes:
        if c.nodeType != c.TEXT_NODE:
            result.extend(build_ebml(c, elements=elements, sizes=sizes))
            
    return result


def build_ebml(xmlElement, schema=DEFAULT_SCHEMA, elements=None, sizes=None):
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
    if sizes is None:
        sizes = getSizeList(schema)
        
    name, value = xmlElement.tagName, xmlElement.getAttribute('value')
    
    if name not in elements:
        raise TypeError("Unknown element type: %r" % name)
    
    elementClass = elements[name]
    if elementClass.type not in ENCODERS:
        raise NotImplementedError("No encoder for element type %r" % name)
    
    elementId = elementClass.id
    
    if elementClass.type == CONTAINER:
        payload = encode_container(xmlElement, elements=elements, sizes=sizes)
    else:
        elementEncoder = ENCODERS[elementClass.type]
        elementTyper = TYPES[elementClass.type]
        payload = elementEncoder(elementTyper(value),
                                 length=sizes.get(name, None))
    
    result = ebml_core.encode_element_id(elementId)
    result.extend(ebml_core.encode_element_size(len(payload)))
    result.extend(payload)
    
    return result


def readXml(filename, schema=DEFAULT_SCHEMA):
    """ Opens an XML file and attempts to build EBML from it.
    
        @param filename: The full path of the XML file to read.
        @keyword schema: The full Python name of the module containing the
            schema. It must be in the current `PYTHONPATH`!
    """
    with open(filename,'rb') as f:
        doc = xml.dom.minidom.parse(f)
        
    result = bytearray()
    for c in doc.childNodes:
        if c.nodeType == c.ELEMENT_NODE:
            result.extend(build_ebml(c, schema))
    return result


def dumpXmlElement(el, indent=0, tabsize=2):
    """ Dump an EBML element as XML. The format is similar to the imported one,
        with the addition of an `offset` attribute, which is the EBML element's
        offset in the file.
    """
    if el.children:
        results = ['%s<%s offset="%d">' % (" "*indent, el.name, el.stream.offset)]
        for child in el.value:
            results.append(dumpXmlElement(child, indent+tabsize))
        results.append('%s</%s>' % ("  "*indent, el.name))
        return "\n".join(results)
    
    return '%s<%s offset="%d" value="%s" />' % \
        ("  "*indent, el.name, el.stream.offset, el.value)


def dumpXml(ebmldoc, indent=0, tabsize=2):
    """ Dump an EBML element as XML. The format is similar to the imported one,
        with the addition of an `offset` attribute, which is the EBML element's
        offset in the file.
    """
    docname = ebmldoc.__class__.__name__
    result = ['<?xml version="1.0" encoding="utf-8"?>\n<%s>' % docname]
    for child in ebmldoc.roots:
        result.append(dumpXmlElement(child, indent=1))
    result.append('</%s>' % docname)
    return "\n".join(result)


def readEbml(data, schema=DEFAULT_SCHEMA):
    if isinstance(data, bytearray):
        stream = StringIO(data)
    else:
        stream = data
    return getSchemaDocument(schema)(stream)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="xml2ebml: A simple utility for creating EBML data.")
    parser.add_argument("source", help="The source XML filename")
    parser.add_argument("--schema", "-s", default=DEFAULT_SCHEMA, 
                        help="The schema's Python module.")
    parser.add_argument("--output", "-o", help="The output filename.")
    parser.add_argument("--indices", "-i", action="store_true",
                        help="Print an XML dump with indices")
    parser.add_argument("--toxml", "-x", action="store_true",
                        help="Create XML from an EBML source file")
    
    args = parser.parse_args()
    
    # Conversion from EBML to XML
    if args.toxml:
        with open(args.source, 'rb') as f:
            ebmldoc = readEbml(f, schema=args.schema)
            xmldoc = dumpXml(ebmldoc)
        result = '<?xml version="1.0" encoding="utf-8"?>\n' + xmldoc
        if args.output:
            outfilename = os.path.realpath(args.output)
            with open(outfilename, 'wb') as f:
                f.write(xmldoc)
        else:
            print xmldoc
        exit(0)
    
    # Regular XML->EBML
    data = readXml(os.path.realpath(args.source), args.schema)
    
    if args.output:
        outfilename = os.path.realpath(args.output)
        with open(outfilename, 'wb') as f:
            f.write(data)
    else:
        print data
        
    if args.indices:
        print dumpXml(readEbml(data, schema=args.schema))
    
    
    