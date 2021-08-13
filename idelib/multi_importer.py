"""
Functions for opening multiple IDE files as one.

:todo: Consider moving the rest of this into the normal `importer` module.

"""

import fnmatch
import os.path

from .importer import openFile, readData


#===============================================================================
# 
#===============================================================================

from .dataset import __DEBUG__

import logging
logger = logging.getLogger('idelib')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")

if __DEBUG__:
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.ERROR)


#===============================================================================
# 
#===============================================================================

def crawlFiles(sources, pattern="*.ide", maxDepth=-1):
    """ Recursively find all recording files in one or more paths.
        :param sources: A path (string) or a collection of paths.
        :keyword pattern: The glob-like filename pattern to match.
        :keyword maxDepth: The maximum depth to search. Makes things faster
            if you know what you want isn't more than 'n' folders deep. 
            -1 is no limit.
    """
    results = []
    if isinstance(sources, str):
        sources = [sources]
    for s in sources:
        s = os.path.abspath(s)
        if not os.path.exists(s):
            continue
        startDepth = s.count(os.path.sep)
            
        if os.path.isfile(s) and fnmatch.fnmatch(s,pattern):
            results.append(s)
            continue
        for root, dirs, files in os.walk(s):
            if root.count(os.path.sep) - startDepth == maxDepth:
                dirs[:] = []
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    fullname = os.path.abspath(os.path.join(root, f))
                    results.append(fullname)
            
            for bad in ('CVS', 'SYSTEM', '.git'):
                if bad in dirs:
                    dirs.remove(bad)

            for d in dirs:
                if d.startswith('.'):
                    dirs.remove(d)

    return [x for x in results if os.path.isfile(x)]


def multiOpen(streams, updater=None, **kwargs):
    """ Create a `Dataset` instance and read the header data (i.e. non-sample-
        data). When called by a GUI, this function should be considered 'modal,' 
        in that it shouldn't run in a background thread, unlike `readData()`. 
        
        :param streams: A set of file-like streams containing EBML recordings.
        :param updater: A function (or function-like object) to notify as
            work is done. It should take four keyword arguments: `count` (the
            current line number), `total` (the total number of samples), `error`
            (an unexpected exception, if raised during the import), and `done`
            (will be `True` when the export is complete). If the updater object
            has a `cancelled` attribute that is `True`, the import will be
            aborted. The default callback is `None` (nothing will be notified).
        :keyword parserTypes: A collection of `parsers.ElementHandler` classes.
        :keyword defaultSensors: A nested dictionary containing a default set 
            of sensors, channels, and subchannels. These will only be used if
            the dataset contains no sensor/channel/subchannel definitions. 
        :keyword name: An optional name for the Dataset. Defaults to the
            base name of the file (if applicable).
        :keyword quiet: If `True`, non-fatal errors (e.g. schema/file
            version mismatches) are suppressed. 
    """
    if updater:
        updater(0)
    
    docs = [openFile(f, **kwargs) for f in streams]
    docs.sort(key=lambda x: x.lastSession.utcStartTime)
    mainDoc = docs[0]
    mainDoc.subsets = docs[1:]
    
    return mainDoc


def multiRead(doc, updater=None, **kwargs):
    """ Import the data from a file into a Dataset, including the data from 
        its subsets.
    
        :param doc: The Dataset document into which to import the data. It
            should have `subset` Datasets.
        :param updater: A function (or function-like object) to notify as
            work is done. It should take four keyword arguments: `count` (the 
            current line number), `total` (the total number of samples), `error` 
            (an unexpected exception, if raised during the import), and `done` 
            (will be `True` when the export is complete). If the updater object 
            has a `cancelled` attribute that is `True`, the import will be 
            aborted. The default callback is `None` (nothing will be notified).
        :keyword numUpdates: The minimum number of calls to the updater to be
            made. More updates will be made if the updates take longer than
            than the specified `updateInterval`. 
        :keyword updateInterval: The maximum number of seconds between calls to 
            the updater. More updates will be made if indicated by the specified
            `numUpdates`.
        :keyword parserTypes: A collection of `parsers.ElementHandler` classes.
        :keyword defaultSensors: A nested dictionary containing a default set 
            of sensors, channels, and subchannels. These will only be used if
            the dataset contains no sensor/channel/subchannel definitions. 
    """
    kwargs['numUpdates'] = kwargs.get('numUpdates', 500) / (len(doc.subsets)+1)
    totalSize = sum([x.ebmldoc.size for x in doc.subsets])
    bytesRead = doc.ebmldoc.size
    samplesRead = readData(doc, total=totalSize, **kwargs)
    if not doc.loadCancelled:
        for f in doc.subsets:
            if doc.loadCancelled:
                break
            samplesRead += readData(doc, source=f, total=totalSize, 
                                    bytesRead=bytesRead, samplesRead=samplesRead, 
                                    **kwargs)
            bytesRead += f.ebmldoc.size
            if updater:
                updater(count=bytesRead, total=totalSize,
                        percent=bytesRead/(totalSize+0.0))

    if updater:
        updater(done=True, total=samplesRead)
    return doc
    

def multiImport(filenames='', **kwargs):
    """ Import multiple files into one Dataset.
    """
    streams = [open(f, 'rb') for f in filenames]
    return multiRead(multiOpen(streams, **kwargs), **kwargs)

