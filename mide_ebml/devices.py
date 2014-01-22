'''
Created on Dec 4, 2013

@author: dstokes
'''

from ebml.schema.mide import MideDocument

def importDeviceInfo(stream, ignore=('Void')):
    
    def _readElement(el):
        if len(el.children) == 0:
            return el.value
        subtree = {}
        for c in el.value:
            if c.name not in ignore:
                subtree[c.name] = _readElement(c)
        return subtree 
    
    result = {}
    stream.seek(0)
    doc = MideDocument(stream)
    for r in doc.iterroots():
        if r.name not in ignore:
            result[r.name] = _readElement(r)
    return result