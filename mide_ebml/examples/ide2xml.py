'''
==================================
Example MIDE File to XML Converter
==================================
(c) 2015 Mide Technology Corp.

The Mide Instrumentation Data Exchange (MIDE) format is based on EBML,
a structured binary format. This script does a simple conversion from EBML to
XML. It does not, however, process any of the data.

While this code is usable as-is, it is intended as an example. As such, Mide
cannot provide technical support for its use as a utility.


Requirements
------------
Python 2.7.* 
python-ebml (https://github.com/jspiros/python-ebml)


Getting Started
---------------
1. Download the python-ebml library and place it the same directory as this
    script (or elsewhere in your PYTHONPATH). 
2. Copy the files `mide.py` and `mide.xml` to the library's schema directory
    (`ebml/schema/`). The directory should already contain `matroska.py` and
    `matroska.xml`.


Output Format
-------------
The XML elements generated (apart from the root element) have several
attributes:

    * type: The name of the element's value type (as string)
    * ebmlId: The numeric ID of the element type, as specified in the EBML
        schema. These are written in hexadecimal form to match the schema's
        format. 
    * offset: The original EBML element's position in the source file.
    * size: The size of the original EBML element in the source file, in bytes.


Disclaimer
----------
THIS CODE IS PROVIDED ONLY AS AN EXAMPLE. USE AT YOUR OWN RISK. MIDE TECHNOLOGY
CORPORATION DISCLAIMS ANY AND ALL WARRANTIES, EXPRESSED OR IMPLIED. 

Created on Oct 19, 2015
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2015 Mide Technology Corporation"

import base64
import sys
import xml.dom.minidom
import xml.sax.saxutils

try:
    import ebml.schema.base
    from ebml.schema.mide import MideDocument
except ImportError as err:
    # The user may not have installed python_ebml or the Mide schema.
    msg = "%s - see the file's docstring for setup info!" % err.message
    raise ImportError(msg)

from ebml.schema.base import INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER

# Mapping of python_ebml element value types from numeric IDs to names
EBML_TYPES = {INT: "int",
              UINT: "uint",
              FLOAT: "float",
              STRING: "unicode",
              UNICODE: "unicode",
              DATE: "date",
              BINARY: "binary",
              CONTAINER: "container"
              }

#===============================================================================
# Low-level EBML parsing and utility functions, not specific to IDE data
#===============================================================================

def iter_roots(document):
    """ Iterate over an EBML document's elements. Note that this does some
        low-level manipulation of the python-ebml library, so any major change
        in that library may cause this to break.
    """
    stream = document.stream
    children = document.children
    size = stream.size
    while size:
        element_offset = stream.size - size
        stream.seek(element_offset)
        element_id, element_id_size = ebml.schema.base.read_element_id(stream)
        element_size, element_size_size = ebml.schema.base.read_element_size(stream)
        element_stream_size = element_id_size + element_size_size + element_size
        element_stream = stream.substream(element_offset, element_stream_size)
        size -= element_stream_size
        
        element_class = None
        for child in (children + document.globals):
            if child.id == element_id:
                element_class = child
                break
        
        if element_class is None:
            element = ebml.schema.base.UnknownElement(document, element_stream, element_id)
        else:
            element = element_class(document, element_stream)
        
        yield(element)


#===============================================================================
# 
#===============================================================================

def createXmlElement(element, xmlDoc, xmlParent=None, ignoreVoid=True):
    """ Convert an XML element from an EBML element. 'Container' elements are
        crawled recursively.
        
        @param element: The EBML element to process.
        @param xmlDoc: The parent XML document being generated.
        @keyword xmlParent: The XML parent element of the generated XML
            element.
        @keyword ignoreVoid: If ``True``, `Void` elements in the EBML will not
            be written to the XML. `Void` elements are placeholder and contain
            no real data.
        @return: The generated XML element.
    """
    xmlElement = xmlDoc.createElement(element.name)
    xmlElement.setAttribute('type', EBML_TYPES.get(element.type, "unknown"))
    xmlElement.setAttribute('ebmlId', "0x%04x" % element.id)
    xmlElement.setAttribute('offset', str(element.stream.offset))
    xmlElement.setAttribute('size', str(element.size))
    
    # 'Container' elements (called 'master' in the schema) contain elements.
    # Recursively crawl these.
    if element.type == CONTAINER:
        for child in element.value:
            if ignoreVoid and child.name == "Void":
                # 'Void' elements are used as padding to make elements a
                # uniform size, simplifying certain things for the recorder.
                # These can be safely ignored.
                continue
            createXmlElement(child, xmlDoc, xmlParent=xmlElement)
        return xmlElement
    
    if element.type == BINARY:
        # Encode binary data in an XML-friendly form.
        val = base64.encodestring(element.value)
    elif element.type == UNICODE:
        # Unicode strings get re-encoded as UTF-8
        val = element.value.encode('utf8')
    else:
        # All other types get converted to ASCII strings
        val = str(element.value)
        
    xmlElement.appendChild(xmlDoc.createTextNode(xml.sax.saxutils.escape(val)))
    
    if xmlParent is not None:
        xmlParent.appendChild(xmlElement)
        
    return xmlElement
    

def xml2ebml(ideFilename, output=sys.stdout, ignoreVoid=True):
    """ Convert an IDE file to XML. 
    
        @param ideFilename: The source .IDE file.
        @keyword output: A stream or filename to which to write the XML.
            Defaults to the system's standard output stream.
        @keyword ignoreVoid: If ``True``, `Void` elements in the EBML will not
            be written to the XML. `Void` elements are placeholder and contain
            no real data.
        @return: The number of root-level EBML elements handled.
    """
    elCount = 0
    with open(ideFilename, 'rb') as f:
        ebmldoc = MideDocument(f)
        
        # If the specified output is a stream (e.g. a file or the system
        # `stdout`), use it as the output. Otherwise, assume it is a filename.
        if isinstance(output, file):
            outStream = output
        else:
            outStream = open(output, 'wb')

        # Create a fresh XML document. This script doesn't actually generate
        # a complete XML document, however: it generates individual elements
        # and writes those directly to the output stream. The XML 
        # representation of an IDE file can get large, so this saves memory.        
        xmldoc = xml.dom.minidom.Document()
        outStream.write(xmldoc.toprettyxml(encoding="utf8"))
        outStream.write("<MideDocument>\n")
        
        try:
            for el in iter_roots(ebmldoc):
                xmlEl = createXmlElement(el, xmldoc, ignoreVoid=ignoreVoid)
                outStream.write(xmlEl.toprettyxml(encoding="utf8"))
                elCount += 1
                
        except IOError as err:
            # A premature end-of-file can occur if the recording stops 
            # unexpectedly. The Slam Stick X tries to close all recordings
            # cleanly, but it is possible that some worst-case scenario could
            # prevent that.
            
            # HACK:
            # The current python_ebml library raises naked IOError exceptions 
            # without any messages. IOErrors raised by standard functions (or
            # other well-behaved code) will have messages, so if the exception 
            # has no message, assume it was generated by python_ebml 
            # encountering an unexpected end-of-file, which is okay. 
            if err.message:
                raise err
        
        except KeyboardInterrupt:
            # Handle ctrl-c nicely.
            pass
         
        finally:
            outStream.write("</MideDocument>\n")
            if outStream != sys.stdout:
                outStream.close()
    
    return elCount

#===============================================================================
# Code executed if this script is run from the command line.
#===============================================================================

if __name__ == "__main__":
    # Rudimentary command-line argument parsing. The script can be called with
    # 1 or 2 parameters: the source and destination files. If there is no 2nd
    # filename, the output is written to the system standard out stream.
    args = sys.argv[1:]
    numArgs = len(args)
    
    if numArgs == 0 or numArgs > 2:
        print "IDE-to-XML Example"
        print __copyright__
        print
        print "Usage: python %s <input.IDE> [<output.XML>]" % sys.argv[0]
        sys.exit(0)
    
    source = args[1]
    if numArgs == 2:
        source, out = args
    else:
        source, out = args[0], sys.stdout
    
    print "Reading from %s..." % source
    numProcessed = xml2ebml(source, out)
    print "Processed %s EBML elements." % numProcessed
    