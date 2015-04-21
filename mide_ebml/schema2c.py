'''
Created on Apr 15, 2015

@author: dstokes
'''
from ebml.core import encode_element_id
from ebml.schema.base import INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER
from ebml.schema.mide import MideDocument

from util import getSchemaDocument

types = {INT:       'SINT',
         UINT:      'UINT',
         FLOAT:     'FLOAT', 
         STRING:    'ASCII', 
         UNICODE:   'UTF8', 
         DATE:      'DATE', 
         BINARY:    'BINARY', 
         CONTAINER: 'MASTER'}


def dumpElement(el, depth):
    return "\t{.id=0x%08x, .level=%d, .datatype=EBML_TYPE_%-7s .mandatory=%d, .multiple=%d, .minver=%d},\t/* %s */" %\
        (el.id, depth, types.get(el.type, 'UNDEFINED')+',', el.mandatory, el.multiple, 1, el.name)
    

def crawlSchema(el, depth=0, results=None, written=None):
    if results is None:
        results = []
    if written is None:
        written = {}
    for ch in el.children:
        if ch.name not in written:
            written[ch.name] = ch.id
            results.append(dumpElement(ch, depth))
        crawlSchema(ch, depth+1, results, written)
    return results

def dumpSchema(schema=MideDocument):
    results = ['#include "ebml-schema.h"','','static const EbmlSchemaEntry ebml_schema_mide[] = {']
    els = []
    ids = {}
    crawlSchema(schema, 0, els, ids)
    
    els.sort()
    results.extend(els)
    results[-1] = results[-1].replace('},','}')
    results.append('};')
    
    incs = []
    name = schema.type.upper()
    namelen = max([len(x) for x,_ in ids.items()]) + len(name) + 15
    for n,i in sorted(ids.items(), key=lambda x: x[-1]):
        n = n.upper()
        inc = "#define %s_ID_%s" % (name, n)
        incs.append('%s 0x%08x' % (inc.ljust(namelen), i))
        incs.append('%s %d' % ((inc+'_LEN').ljust(namelen), len(encode_element_id(i))))
    
    incs.append('')
    incs.extend(results)
    return '\n'.join(incs)

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
        f.write("/* EBML schema dump of %s */\n\n" % schema.__name__)
        f.write(result)