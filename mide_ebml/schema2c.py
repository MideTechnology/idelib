'''
Created on Apr 15, 2015

@author: dstokes
'''

from ebml.schema.base import INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER
from ebml.schema.mide import MideDocument

from util import getSchemaDocument

types = {INT: 'SINT',
         UINT: 'UINT',
         FLOAT: 'FLOAT', 
         STRING: 'ASCII', 
         UNICODE: 'UTF8', 
         DATE: 'DATE', 
         BINARY: 'BINARY', 
         CONTAINER:'MASTER'}

def dumpElement(el, depth):
    return "\t{.id=0x%04x, .level=%d, .datatype=EBML_TYPE_%s, .mandatory=%d, .multiple=%d, .minver=%d},\t/* %s */" %\
        (el.id, depth, types.get(el.type, 'UNDEFINED'), el.mandatory, el.multiple, 1, el.name)
    

def crawlSchema(el, depth=0, results=None, written=None):
    if results is None:
        results = []
    if written is None:
        written = []
    for ch in el.children:
        if ch.name not in written:
            written.append(ch.name)
            results.append(dumpElement(ch, depth))
        crawlSchema(ch, depth+1, results, written)
    return results

def dumpSchema(schema=MideDocument):
    results = ['#include "ebml-schema.h"','','static const EbmlSchemaEntry ebml_schema_mide[] = {']
    els = crawlSchema(schema)
    els.sort()
    results.extend(els)
    results[-1] = results[-1].replace('},','}')
    results.append('}')
    return '\n'.join(results)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Schema 2 C utility")
    parser.add_argument('-s', '--schema',  
                        help="The name of the schema to export")
    parser.add_argument("-o", "--output", 
                        help="The name of the file to write")
    args = parser.parse_args()
    
    if args.schema:
        schema = getSchemaDocument(args.schema)
    else:
        schema = MideDocument
    result = dumpSchema(schema)
    with open('%s.c' % schema.__name__, 'wb') as f:
        f.write("/* EBML schema dump of %s */\n\n" % schema.name)
        f.write(result)