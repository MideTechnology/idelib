'''
A utility script/module for converting XML to EBML and back. 

Created on Dec 20, 2013

@author: dstokes
'''

import argparse
import os.path
from StringIO import StringIO
import xml.dom.minidom
import xml.sax.saxutils

from ebml import core as ebml_core
from util import getSchemaElements, getSchemaDocument, getElementSizes, ENCODERS

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


def encode_container(data, length=None, elements=None, sizes={}, 
                     schema=DEFAULT_SCHEMA):
    """ EBML encoder for a 'container' (i.e. 'master') element, compatible with
        the `ebml.core` encoding methods for primitive types. Recursively calls 
        other encoders for its contents. 
        
        @param data: 
        @keyword length: Unused; for compatibility with `ebml.core` methods.
        @return: A `bytearray` of binary EBML data.
    """
    result = bytearray()
    
    for c in data.childNodes:
        if c.nodeType == c.ELEMENT_NODE:
            result.extend(build_ebml(c, elements=elements, sizes=sizes,
                                     schema=schema))
            
    return result


def build_ebml(xmlElement, schema=DEFAULT_SCHEMA, elements=None, sizes=None):
    """ Construct an EBML element of the given type containing the given
        data. Operates recursively. Note that this function does not do any 
        significant type-checking, nor does it check against the schema.
        
        @param xmlElement: 
        @keyword schema: The full Python name of the module containing the
            schema. It must be in the current `PYTHONPATH`!
        @keyword elements:
        @keyword sizes: 
        @return: A `bytearray` containing the raw binary EBML.
    """
    if elements is None:
        elements = getSchemaElements(schema)
    if sizes is None:
        sizes = getElementSizes(schema)

    name, value = xmlElement.tagName, xmlElement.getAttribute('value')
    
    if name not in elements:
        raise TypeError("Unknown element type in schema %s: %r" % (schema, name))
    
    elementClass = elements[name]
    if elementClass.type not in ENCODERS:
        raise NotImplementedError("No encoder for element type %r" % name)
    
    elementId = elementClass.id
    
    if elementClass.type == CONTAINER:
        payload = encode_container(xmlElement, elements=elements, sizes=sizes,
                                   schema=schema)
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


def dumpXmlElement(el, indent=0, tabsize=4):
    """ Dump an EBML element as XML. The format is similar to the imported one,
        with the addition of two attributes: `offset`, which is the EBML 
        element's offset in the file, and `size`, the size of the element's
        payload. These are for reference only, and are ignored in any XML
        converted back to EBML. 
    """
    tab = u" " * tabsize * indent
    if el.type == CONTAINER:
        results = [u'%s<%s offset="%d" body_size="%s">' % \
                   (tab, el.name, el.offset, el.size)]
        for child in el.value:
            results.append(dumpXmlElement(child, indent+1, tabsize))
        results.append(u'%s</%s>' % (tab, el.name))
        return u"\n".join(results)
    
    if el.name == 'Void':
        return u'%s<%s offset="%d" size="%s" />' % \
            (tab, el.name, el.offset, el.size)
    
    val = el.value
    if isinstance(el.value, (str, bytearray)):
        try:
            val = unicode(str(el.value), "utf8")
        except UnicodeDecodeError:
            val = repr(str(val))[1:-1]
        val = xml.sax.saxutils.escape(val)
    return u'%s<%s offset="%d" size="%s" value="%s" />' % \
        (tab, el.name, el.offset, el.size, val)


def dumpXml(ebmldoc, indent=0, tabsize=2):
    """ Dump an EBML document as XML. The format is similar to the imported one,
        with the addition of two attributes: `offset`, which is the EBML 
        element's offset in the file, and `size`, the size of the element's
        payload. These are for reference only, and are ignored in any XML
        converted back to EBML. 
    """
    docname = ebmldoc.__class__.__name__
    result = [u'<?xml version="1.0" encoding="utf-8"?>\n<%s>' % docname]
    for child in ebmldoc.roots:
        result.append(dumpXmlElement(child, indent=1))
    result.append(u'</%s>' % docname)
    return u"\n".join(result)


def readEbml(data, schema=DEFAULT_SCHEMA):
    """ Wrapper for reading a file or set of bytes as EBML.
    """
    if isinstance(data, (basestring, bytearray)):
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
    parser.add_argument("--whitespace", "-w", action="store_true",
                        help="Keep any leading or trailing whitespace in the "
                        "paths (trimmed by default). Embedded whitespace is "
                        "always preserved.")
    
    args = parser.parse_args()
    
    # Calling this script from another script (batch file, shell script, etc.)
    # can add whitespace to the start and/or end of a string argument. Since
    # it isn't impossible that this is deliberate, the `--whitespace` argument
    # can force the whitespace to be kept.
    if args.whitespace:
        fixpath = lambda x: x
    else:
        fixpath = lambda x: x.strip() if isinstance(x, basestring) else x
    
    # Conversion from EBML to XML
    if args.toxml:
        with open(args.source, 'rb') as f:
            ebmldoc = readEbml(f, schema=fixpath(args.schema))
            xmldoc = dumpXml(ebmldoc).encode('utf8')
        result = '<?xml version="1.0" encoding="utf-8"?>\n' + xmldoc
        if args.output:
            outfilename = os.path.realpath(args.output.strip())
            with open(outfilename, 'wb') as f:
                f.write(xmldoc)
        else:
            print xmldoc
        exit(0)
    
    # Regular XML->EBML
    data = readXml(os.path.realpath(fixpath(args.source)), fixpath(args.schema))
    
    if args.output:
        outfilename = os.path.realpath(fixpath(args.output))
        with open(outfilename, 'wb') as f:
            f.write(data)
    else:
        print data
        
    if args.indices:
        print dumpXml(readEbml(data, schema=fixpath(args.schema)))
    
    
    
