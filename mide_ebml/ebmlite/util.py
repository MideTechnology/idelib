'''
Module mide_ebml.ebmlite.util

Created on Aug 11, 2017

@todo: Clean up and standardize usage of the term 'size' versus 'length.'
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

from base64 import b64encode, b64decode
from xml.etree import ElementTree as ET

import core, encoding

#===============================================================================
# 
#===============================================================================

TYPE_NAMES = {
    core.CONTAINER: 'master',
    core.INT:       'int',
    core.UINT:      'uint',
    core.FLOAT:     'float',
    core.STRING:    'str',
    core.UNICODE:   'utf-8',
    core.DATE:      'date', 
    core.BINARY:    'binary',
    core.UNKNOWN:   'binary'
}

#===============================================================================
# 
#===============================================================================

def toXml(el, parent=None, offsets=True, sizes=True, types=True, ids=True):
    """ Convert an EBML Document to XML. Binary elements will contain 
        base64-encoded data in their body. Other non-master elements will
        contain their value in a ``value`` attribute.
        
        @param el: An instance of an EBML Element or Document subclass.
        @keyword parent: The resulting XML element's parent element, if any.
        @keyword offsets: If `True`, create a ``offset`` attributes for each
            generated XML element, containing the corresponding EBML element's 
            offset.
        @keyword sizes: If `True`, create ``size`` attributes containing the
            corresponding EBML element's size.
        @keyword types: If `True`, create ``type`` attributes containing the
            name of the corresponding EBML element type.
        @keyword ids: If `True`, create ``id`` attributes containing the
            corresponding EBML element's EBML ID.
    """
    if isinstance(el, core.Document):
        elname = el.__class__.__name__
    else:
        elname = el.name
        
    if parent is None:
        xmlEl = ET.Element(elname)
        xmlEl.set('source', str(el.filename))
        xmlEl.set('schemaName', str(el.schema.name))
        xmlEl.set('schemaFile', str(el.schema.filename))
    else:
        xmlEl = ET.SubElement(parent, elname)
        if ids and isinstance(el.id, (int, long)):
            xmlEl.set('id', "0x%X" % el.id)
        if types:
            xmlEl.set('type', TYPE_NAMES.get(el.type, el.type))
    
    if offsets:
        xmlEl.set('offset', str(el.offset))
    if sizes:
        xmlEl.set('size', str(el.size).strip('L'))
    
    if isinstance(el, core.MasterElement):
        for chEl in el:
            toXml(chEl, xmlEl, offsets, sizes, types)
    elif isinstance(el, core.BinaryElement):
        xmlEl.text = b64encode(el.value)
    elif not isinstance(el, core.VoidElement):
        xmlEl.set('value', str(el.value))
    
    return xmlEl


#===============================================================================
# 
#===============================================================================

def xmlElement2ebml(xmlEl, ebmlFile, schema, sizeLength=4, unknown=True):
    """ Convert an XML element to EBML, recursing if necessary. For converting
        an entire XML document, use `xml2ebml()`.
        
        @param xmlEl: The XML element. Its tag must match an element specified
            in the schema. 
        @param ebmlFile: An open file-like stream, to which the EBML data will
            be written.
        @param schema: An `ebmlite.core.Schema` instance to use when
            writing the EBML document.
        @param unknown: If `True`, unknown element names will be allowed, 
            provided their XML elements include an ``id`` attribute with the 
            EBML ID (in hexadecimal).
    """
    try:
        cls = schema[xmlEl.tag]
        encId = encoding.encodeId(cls.id)
    except KeyError:
        # Element name not in schema. Go ahead if allowed (`unknown` is `True`)
        # and the XML element specifies an ID, 
        if not unknown:
            raise NameError("Unrecognized EBML element name: %s" % xmlEl.tag)
        
        eid = xmlEl.get('id', None)
        if eid is None:
            raise NameError("Unrecognized EBML element name with no 'id' "
                            "attribute in XML: %s" % xmlEl.tag)
        cls = core.UnknownElement
        encId = encoding.encodeId(int(eid, 16))
    
    sl = int(xmlEl.get('sizeLength', sizeLength))
    
    if issubclass(cls, core.MasterElement): #.type == core.CONTAINER:
        ebmlFile.write(encId)
        sizePos = ebmlFile.tell()
        ebmlFile.write(encoding.encodeSize(None, sl))
        size = 0
        for chEl in xmlEl:
            size += xmlElement2ebml(chEl, ebmlFile, schema, sl)
        endPos = ebmlFile.tell()
        ebmlFile.seek(sizePos)
        ebmlFile.write(encoding.encodeSize(size, sl))
        ebmlFile.seek(endPos)
        return len(encId) + (endPos - sizePos)
    
    elif issubclass(cls, core.BinaryElement): #.type == core.BINARY:
        val = b64decode(xmlEl.text)
    else:
        val = cls.dtype(xmlEl.get('value'))
    
    size = xmlEl.get('size', None)
    if size is not None:
        size = int(size)
    sl = xmlEl.get('sizeLength')
    if sl is not None:
        sl = int(sl)
    
    encoded = cls.encode(val, size, lengthSize=sl)
    ebmlFile.write(encoded)
    return len(encoded)


def xml2ebml(xmlFile, ebmlFile, schema, sizeLength=4, headers=True, 
             unknown=True):
    """ Convert an XML file to EBML. 
    
        @param xmlFile: The XML source. Can be a filename, an open file-like
            stream, or a parsed XML document.
        @param ebmlFile: The EBML file to write. Can be a filename or an open
            file-like stream.
        @param schema: The EBML schema to use. Can be a filename or an
            instance of a `Schema`.
        @keyword sizeLength: The default length of each element's size
            descriptor. Must be large enough to store the largest 'master' 
            element. If an XML element has a ``sizeLength`` attribute, it will
            override this
        @keyword headers: If `True`, generate the standard ``EBML`` EBML
            element if the XML document does not contain one.
        @param unknown: If `True`, unknown element names will be allowed, 
            provided their XML elements include an ``id`` attribute with the 
            EBML ID (in hexadecimal). 
    """
    if isinstance(ebmlFile, basestring):
        ebmlFile = open(ebmlFile, 'wb')
        openedEbml = True
    else:
        openedEbml = False
    
    if isinstance(schema, basestring):
        schema = core.loadSchema(schema)
    
    if isinstance(xmlFile, ET.Element):
        # Already a parsed 
        xmlRoot = xmlFile
    elif isinstance(xmlFile, ET.ElementTree):
        xmlRoot = xmlFile.getroot()
    else:
        xmlDoc = ET.parse(xmlFile)
        xmlRoot = xmlDoc.getroot()

    if xmlRoot.tag not in schema and xmlRoot.tag != schema.document.__name__:
        raise NameError("XML element %s not an element or document in "
                        "schema %s (wrong schema)" % (xmlRoot.tag, schema.name))

    numBytes = 0
    
    headers = headers and 'EBML' in schema
    if headers and 'EBML' not in (el.tag for el in xmlRoot):
        pos = ebmlFile.tell()
        cls = schema.document
        ebmlFile.write(cls.encodePayload(cls._createHeaders()))
        numBytes = ebmlFile.tell() - pos

    # TODO: Check schema Document type vs. XML root element attributes.
    # Need to update `ebmlite.core.Document` so it is more consistent.
    
    if xmlRoot.tag == schema.document.__name__:
        for el in xmlRoot:
            numBytes += xmlElement2ebml(el, ebmlFile, schema, sizeLength, 
                                        unknown=unknown)
    else:
        numBytes += xmlElement2ebml(xmlRoot, ebmlFile, schema, sizeLength, 
                                    unknown=unknown)
    
    if openedEbml:
        ebmlFile.close()
    
    return numBytes

