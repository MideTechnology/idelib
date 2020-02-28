'''
Module bad_cal_fixer.fix_cal

Created on Oct 25, 2017
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

from glob import glob
import os
import sys
sys.path.insert(0, '..')

import idelib.ebmlite
from idelib.ebmlite import loadSchema
from idelib.ebmlite import util

idelib.ebmlite.SCHEMA_PATH.insert(0, os.path.dirname(__file__))
schema = loadSchema('mide.xml')


def fixCalRefs(filename):
    """
    """
    name,ext = os.path.splitext(filename)
    newname = name + "_fixed" + ext
    
    doc = schema.load(filename, headers=True)
    
    with open(newname, 'wb') as out:
        for el in doc:
            if el.name != "RecordingProperties":
                out.write(el.getRaw())
                continue
            
            xml = util.toXml(el, sizes=False, offsets=False)
            for ch in xml.findall('./ChannelList/Channel/SubChannel'):
                idrefs = ch.findall('SubChannelCalibrationIDRef')
                if len(idrefs) > 1:
                    for i in idrefs[1:]:
                        ch.remove(i)
                        
            util.xmlElement2ebml(xml, out, schema)


def crawl(path):
    allfiles = []
    for root, dirs, files in os.walk(path, topdown=False):
        for d in dirs:
            if d.startswith('.'):
                dirs.remove(d)
        for f in files:
            if f.lower().endswith('.ide'):
                allfiles.append(os.path.join(root, f))
    return allfiles
        
        

if __name__ == "__main__":
    files = []
    for p in sys.argv[1:]:
        files.extend(glob(p))
    
    ides = []
    for p in files:
        if os.path.isdir(p):
            ides.extend(crawl(p))
        else:
            ides.append(p)
    
    ides = filter(os.path.isfile, ides)
    for f in ides:
        fixCalRefs(f)
