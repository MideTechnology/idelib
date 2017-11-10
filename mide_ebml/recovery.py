'''
Module mide_ebml.recovery: Utilities to perform basic data recovery from a 
damaged IDE file. 

Created on Nov 7, 2017

@todo: Search for the start of *any* known element, instead of just Sync or
    ChannelDataBlock? Current script won't recover non-data elements (e.g.
    calibration, self-description). Potentially slow.
@todo: Disk image recovery mode, which attempts to extract multiple files from
    a big glob of raw FAT data, like Tim's tool.
@todo: Smarter validation of ChannelDataBlocks, e.g. check the absolute time
    stamp (if present) to determine if the data belongs to the current file,
    rather than broken file system cruft.
'''

__author__ = "dstokes"
__copyright__ = "Copyright 2017 Mide Technology Corporation"

import sys

from mide_ebml.ebmlite import loadSchema, UnknownElement
from mide_ebml.ebmlite.encoding import encodeId

#===============================================================================
# 
#===============================================================================

def simpleCallback(pos, recovered, fileSize):
    """ Simple callback function for displaying recovery progress.
    """
    if recovered % 1000 == 0:
        percent = ((pos + 0.0) / fileSize) * 100
        sys.stdout.write("Read: %d%% Pos: %d recovered: %d\r" % (percent, pos, recovered))
        sys.stdout.flush()
    return False
        

#===============================================================================
# 
#===============================================================================


def getNextElement(doc, pos, sync, unknown=False, bufferSize=2**16,
                   callback=None, recovered=None, docsize=None):
    """ Get the next valid data block.
        
        @param doc: the IDE file, as an open EBML Document.
        @param pos: Offset of the possible next element.
        @param sync: The data (string) that starts a valid element.
        @keyword unknown: If `True`, unrecognized elements will be retained.
            If `False`, unknown elements will be considered bad data.
    """
    while True:
        try:
            doc.stream.seek(pos)
            el, pos = doc.parseElement(doc.stream)
            
            if not unknown and isinstance(el, UnknownElement):
                # An unknown element might be a bad element. Raise an exception
                # to trigger the Sync-seeking exception handler.
                pos = el.offset
                raise IOError()
            
            return el, pos
            
        except IOError:
            # Seek a recognizable element: Sync (if fast) or ChannelDataBlock
            # TODO: smarter exception handling. This assumes an IOError was
            # caused by bad data.
            doc.stream.seek(pos+1)
            buff = bytearray()
            while sync not in buff:
                if callback is not None:
                    callback(pos, recovered, docsize)
                data = doc.stream.read(bufferSize)
                if not data:
                    return None, doc.stream.tell()
                buff.extend(data)
                buff = buff[-2*bufferSize:]
            else:
                # sync is in buff, didn't break
                # I guess this is what 'else' in Python 'while' are good for.
                idx = buff.index(sync)
                pos = doc.stream.tell() - len(buff) + idx    


def recoverData(filename, outfile, fast=True, callback=None, bufferSize=2**16, 
                unknown=False):
    """ Attempt to recover data from an IDE file. 
    
        @param filename: The name of the damaged IDE file.
        @param outfile: The name of the output file, or an output stream.
        @keyword fast: If `True`, the recovery will use ``Sync`` elements to
            find recoverable data (occur every few blocks). If `False`, the
            recovery will look for `ChannelDataBlocks`, which may recover more
            data but will be slower.
        @keyword callback: A function called after each recovered element,
            providing a progress report. The function has three arguments:
            the current file offset, the number of recovered elements, and
            the full size of the file. The function returns `True` if 
            the recovery should be cancelled.
        @keyword unknown: If `True`, unrecognized elements will be retained.
            If `False`, unknown elements will be considered bad data. Should
            almost always be `False`.
        @return: The number of elements recovered, and the percentage of the 
            file's total size that was salvaged.
    """
    if isinstance(outfile, basestring):
        out = open(outfile, 'wb')
    else:
        out = outfile
    
    # TODO: This expects the start of the file to be valid. Should really
    # look for valid header info (EBML, RecordingProperties, etc.)
    schema = loadSchema('mide.xml')
    doc = schema.load(filename, headers=True)

    # "One-Off" elements: should only occur once. Additional instances ignored.
    # TODO: The EBML parser should recognize non-multiple root elements.
    singletonElements = {schema['EBML'].id: False, 
                         schema['RecordingProperties'].id: False, 
                         schema['RecorderConfiguration'].id: False,
                         schema['CalibrationList'].id: False}

    dataBlockId = schema['ChannelDataBlock'].id
    
    if fast:
        # If data's bad, look for the next Sync element. Easily recognized.
        sync = schema['Sync'].encode('ZZZZ')
    else:
        # Look for what might be the start of a data block. Much smaller, so
        # there will be more false positives, but could recover more data.
        sync = encodeId(dataBlockId)
    
    pos = 0
    recovered = 0
    recoveredSize = 0
    
    docsize = doc.size + 0.0
    while pos < docsize:
        el, pos = getNextElement(doc, pos, sync, unknown, bufferSize,
                                 callback, recovered, docsize)
        
        if el is None:
            break
        
        # Skip duplicated one-off elements (can be created in bad files)
        eid = el.id
        if eid != dataBlockId and el.id in singletonElements:
            if singletonElements[eid]:
                print "skipping duplicate: %r" % el
                del el
                continue
            else:
                singletonElements[eid] = True
        
        out.write(el.getRaw())
        recovered += 1
        recoveredSize += el.size
        del el
        
        if callback is not None:
            # TODO: Cancel isn't working for some reason!
            if callback(pos, recovered, docsize):
                break

    return recovered, recoveredSize / docsize


#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IDE Data Recovery Tool")
    parser.add_argument('filename', 
                        help="The name of the MIDE (*.IDE) file to import")
    parser.add_argument('output', 
                        help="The file to save the recovered data")
    args = parser.parse_args()
    
    recovered, percent = recoverData(args.filename, args.output, callback=simpleCallback)
    print "Recovery complete. Recovered %d elements (%.2f of total file)" % (recovered, percent*100)