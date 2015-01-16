'''
========================
Example MIDE File Reader
========================

This script 

Requirements
------------
python-ebml (https://github.com/jspiros/python-ebml)


Getting Started
---------------
1. Download the python-ebml library and place it the same directory as this
    script (or elsewhere in your PYTHONPATH). 
2. Copy the files `mide.py` and `mide.xml` to the library's schema directory
    (`ebml/schema/`). The directory should already contain `matroska.py` and
    `matroska.xml`.


Created on Jan 16, 2015

@author: dstokes
'''

try:
    import ebml.schema.base
    from ebml.schema.mide import MideDocument
except ImportError as err:
    msg = "%s - see the file's docstring for setup info!" % err.message
    raise ImportError(msg)



def iter_elements(stream, document, children):
    """ Iterate over an EBML stream's elements. Note that this does some
        low-level manipulation of the python-ebml library, so any major change
        in that library may cause this to break.
    """
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



class ChannelDataBlockParser(object):
    """
    """
    maxTimestamp = 2**16
    timeScalar = 1000000.0 / 2**15

    def __init__(self):
        self.firstTime = None
        self.lastTime = 0
        self.timestampOffset = 0
        self.lastStamp = 0
    

    def fixOverflow(self, timestamp):
        """ Return an adjusted, scaled time from a low-resolution timestamp.
        """
        timestamp += self.timestampOffset
        while timestamp < self.lastStamp:
            timestamp += self.maxTimestamp
            self.timestampOffset += self.maxTimestamp
        self.lastStamp = timestamp
        return timestamp

    def parse(self, element):
        """
        """
        
