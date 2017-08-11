'''
Module mide_ebml.ebmlite.util

Created on Aug 11, 2017
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

from base64 import b64encode
from xml.etree import ElementTree as ET

import core

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


def toXml(el, parent=None, offsets=True, sizes=True, types=True, ids=True):
    """ Convert an EBML Document to XML.
        
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
    
    if offsets:
        xmlEl.set('offset', str(el.offset))
    if sizes:
        xmlEl.set('size', str(el.size).strip('L'))
    if types:
        xmlEl.set('type', TYPE_NAMES.get(el.type, el.type))
    
    if isinstance(el, core.MasterElement):
        for chEl in el:
            toXml(chEl, xmlEl, offsets, sizes, types)
    elif isinstance(el, core.BinaryElement):
        xmlEl.text = b64encode(el.value)
    elif not isinstance(el, core.VoidElement):
        xmlEl.set('value', str(el.value))
    
    return xmlEl
    

def xml2ebml(xmlFile, ebmlFile, schema):
    """ 
    """
    if isinstance(ebmlFile, basestring):
        ebmlFile = open(ebmlFile, 'wb')
        openedEbml = True
    else:
        openedEbml = False
    
    xmlDoc = ET.parse(xmlFile)
    xmlRoot = xmlDoc.getroot()
    
    # TODO: Check schema Document type vs. XML root element attributes.
    # Need to update `ebmlite.core.Document` so it is more consistent.
    