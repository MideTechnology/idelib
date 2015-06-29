'''
Created on Apr 15, 2015

@author: dstokes
'''
from datetime import datetime
import os
import sys
import textwrap

from ebml.core import encode_element_id
from ebml.schema.base import INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER
from ebml.schema.mide import MideDocument

from util import getSchemaModule, getSchemaDocument

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


def dumpSchema(schemaDoc=MideDocument):
    """ Create the C source for an EBML schema. This is the function that does
        all the real work.
    """
    name = schemaDoc.type.upper()
    entry = ['static const EbmlSchemaEntry ebml_schema_%s[] = {' % schemaDoc.type.lower()]
    els = []
    ids = {}
    crawlSchema(schemaDoc, 0, els, ids)
    
    els.sort()
    entry.extend(els)
    entry[-1] = entry[-1].replace('},','}')
    entry.append('};')
    
    incs = ['#ifndef EBML_SCHEMA_%s_H_' % name,
            '#define EBML_SCHEMA_%s_H_' % name,
            '',
            '#include "ebml-schema.h"',
            '']
    namelen = max([len(x) for x,_ in ids.items()]) + len(name) + 15
    for n,i in sorted(ids.items(), key=lambda x: x[-1]):
        n = n.upper()
        inc = "#define %s_ID_%s" % (name, n)
        incs.append('%s 0x%08x' % (inc.ljust(namelen), i))
        incs.append('%s %d' % ((inc+'_LEN').ljust(namelen), len(encode_element_id(i))))
    
    incs.append('')
    incs.extend(entry)
    incs.extend(['','#endif /* EBML_SCHEMA_%s_H_ */' % name])
    return '\n'.join(incs)


def makeHeaderComment(schemaMod, schemaDoc):
    stars = '*' * 76
    xmlfile = os.path.splitext(os.path.realpath(schemaMod.__file__))[0] + ".xml"
    return textwrap.dedent("""
        /*%s
         *
         * EBML schema dump of %s
         * Source: %s
         * Auto-generated %s by %s on %s
         *        
         * To recreate:
         * python %s
         *
         %s*/
        
    """.lstrip('\n') % (stars, 
                        schemaDoc.__name__, 
                        xmlfile, 
                        str(datetime.now()).rsplit('.',1)[0],
                        os.environ.get('USERNAME', '(unknown user)'),
                        os.environ.get('COMPUTERNAME', '(unknown computer'), 
                        ' '.join(sys.argv), 
                        stars))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Schema 2 C utility")
    parser.add_argument('-s', '--schema',  
                        help="The name of the schema to export")
    parser.add_argument("-o", "--output", 
                        help="The name of the file to write")
    args = parser.parse_args()
    
    if args.schema:
        schemaDoc = getSchemaDocument(args.schema)
        schemaMod = getSchemaModule(args.schema)
    else:
        schemaDoc = MideDocument
        schemaMod = getSchemaModule()


    if args.output:
        fname = args.output
    else:
        fname = '%s.c' % schemaDoc.__name__
        
    result = dumpSchema(schemaDoc)
    with open(fname, 'wb') as f:
        f.write(makeHeaderComment(schemaMod, schemaDoc))
#         f.write("/* EBML schema dump of %s */\n\n" % schema.__name__)
        f.write(result)
        
