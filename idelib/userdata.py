"""
Functions for reading and writing application-specific data from/to the end
of IDE files. This data is intended primarily to retain user preferences for
the display of the `Dataset`.
"""

import os.path
import logging
from typing import Any, Dict, Optional, Tuple, Union

from .dataset import Dataset

#===============================================================================
#
#===============================================================================

MIN_VOID_SIZE = 9

logger = logging.getLogger('idelib')

#===============================================================================
#
#===============================================================================

def getUserDataPos(dataset: Dataset) -> Tuple[bool, int, int]:
    """ Get the offset of the start of the user data.

        :param dataset: The `Dataset` in which to locate the user data.
        :return: A tuple containing a bool (wheter or not data exists),
            the offset of the user data, and the total length of the file.
    """
    doc = dataset.ebmldoc
    fs = doc.stream
    hasdata = False

    oldpos = fs.tell()
    filesize = fs.seek(0, os.SEEK_END)
    offset = filesize

    example = doc.schema['UserDataOffset'].encode(1, length=8, lengthSize=8)
    header = example[:-8]

    try:
        pos = offset - int(len(example) * 1.5)
        fs.seek(pos, os.SEEK_SET)
        chunk = fs.read()
        if header in chunk:
            fs.seek(pos + chunk.index(header), os.SEEK_SET)
            el, _next = doc.parseElement(fs)
            offset = el.value
            hasdata = True

    except IndexError:
        # Problem with parsed chunk; shouldn't happen.
        pass

    finally:
        fs.seek(oldpos, os.SEEK_SET)

    return hasdata, offset, filesize


#===============================================================================
#
#===============================================================================

def readUserData(dataset: Dataset) -> Union[Dict[str, Any], None]:
    """ Read application-specific user data from the end of an IDE file.

        :param dataset: The `Dataset` from which to read the user data.
        :return: A dictionary of user data, or `None` if no user data
            could be read from the file (e.g., none exists).
    """
    doc = dataset.ebmldoc
    fs = doc.stream
    oldpos = fs.tell()

    hasdata, offset, filesize = getUserDataPos(dataset)

    if not hasdata:
        logger.debug('No user data found')
        return None

    try:
        fs.seek(offset, os.SEEK_SET)
        data, _next = doc.parseElement(fs)
        return data.dump()

    finally:
        fs.seek(oldpos, os.SEEK_SET)


#===============================================================================
#
#===============================================================================

def writeUserData(dataset: Dataset,
                  userdata: Dict[str, Any]):
    """ Write user data to the end of an IDE file.

        :param dataset: The `Dataset` from which to read the user data.
        :param userdata: A dictionary of user data, or `None` to remove
            existing user data. Note that the file will not get smaller if
            the user data is removed (or the new user data is smaller);
            it is just overwritten with null data (an EBML `Void` element).
    """
    schema = dataset.ebmldoc.schema
    fs = dataset.ebmldoc.stream
    oldpos = fs.tell()

    try:
        _hasdata, offset, filesize = getUserDataPos(dataset)

        dataBin = schema.encodes({'UserData': userdata})
        offsetBin = schema['UserDataOffset'].encode(offset, length=8, lengthSize=8)
        newsize = (len(offsetBin) + len(dataBin) + offset + MIN_VOID_SIZE)
        voidBin = schema['Void'].encode(None, length=max(0, filesize - newsize),
                                        lengthSize=8)

        userblob = dataBin + voidBin + offsetBin

        if '+' not in fs.mode and 'w' not in fs.mode:
            if not getattr(fs, 'name', None):
                logger.debug(f'(userdata) Dataset stream read only (mode {fs.mode!r}) '
                             'and has no name, not writing user data')
                return

            with open(fs.name, 'br+') as newfs:
                logger.debug(f'(userdata) Dataset stream read only (mode {fs.mode!r}), '
                             'using new stream')
                newfs.seek(offset, os.SEEK_SET)
                newfs.write(userblob)
        else:
            fs.seek(offset, os.SEEK_SET)
            fs.write(userblob)

        logger.debug(f'(userdata) Wrote {len(userblob)} bytes to {dataset} '
                     f'(file was {filesize}, now {newsize})')

    finally:
        fs.seek(oldpos, os.SEEK_SET)
