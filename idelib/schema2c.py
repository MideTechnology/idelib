'''
Created on Sep 11, 2015

@author: dstokes
'''

from collections import namedtuple
from datetime import datetime
import os
import sys
import textwrap
from xml.dom.minidom import parse

from ebml.core import encode_element_id
# from ebml.schema.base import INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER
from ebml.schema.mide import MideDocument

from util import getSchemaModule, getSchemaDocument

Element = namedtuple("Element", ('name','level','id','type','mandatory','multiple'))

types = {'integer':  'SINT',
         'uinteger': 'UINT',
         'float':    'FLOAT', 
         'string':   'ASCII', 
         'utf-8':    'UTF8', 
         'date':     'DATE', 
         'binary':   'BINARY', 
         'master':   'MASTER'}


def getElements(xmlfile):
    els = xmlfile.getElementsByTagName('element')
    result = [Element(el.getAttribute('name'),
               int(el.getAttribute('level') or 0),
               int(el.getAttribute('id'), 16),
               types.get(el.getAttribute('type'), 'UNDEFINED'),
               int(el.getAttribute('mandatory') or 0),
               int(el.getAttribute('multiple') or 0),
#                int(el.getAttribute('minver'))
               ) for el in els]
    result = list(set(result))
    result.sort(key=lambda x: x[2])
    return result


def dumpElementDef(el, schemaName, namelen):
    inc = "#define %s_ID_%s" % (schemaName.upper(), el.name.upper())
    return ['%s 0x%08x' % (inc.ljust(namelen), el.id),
            '%s %d' % ((inc+'_LEN').ljust(namelen), len(encode_element_id(el.id)))]

def dumpElement(el):
    return "\t{.id=0x%08x, .level=%d, .datatype=EBML_TYPE_%-7s .mandatory=%d, .multiple=%d, .minver=%d},\t/* %s */" %\
        (el.id, el.level, el.type+',', el.mandatory, el.multiple, 1, el.name)
    

def dumpSchema(xmlfile, name="schema"):
    incs = ['#ifndef EBML_SCHEMA_%s_H_' % name.upper(),
            '#define EBML_SCHEMA_%s_H_' % name.upper(),
            '',
            '#include "ebml-schema.h"',
            '']
    els = getElements(xmlfile)
    entries = []
    namelen = max((len(el.name) for el in els)) + len(name) + 15
    for el in els:
        incs.extend(dumpElementDef(el, name, namelen))
        entries.append(dumpElement(el))
    entries[-1] = entries[-1].replace('},','}')
    
    incs.append('')
    incs.extend(entries)    
    
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
    schemaXml = parse(os.path.splitext(schemaMod.__file__)[0]+".xml")

    if args.output:
        fname = args.output
    else:
        fname = '%s.c' % schemaDoc.__name__
        
    result = dumpSchema(schemaXml, args.schema or "mide")
    with open(fname, 'wb') as f:
        f.write(makeHeaderComment(schemaMod, schemaDoc))
#         f.write("/* EBML schema dump of %s */\n\n" % schema.__name__)
        f.write(result)
        
