"""
Functions for reading and writing application-specific data from/to the end
of IDE files. This data is intended primarily to retain user preferences for
the display of the `Dataset`.
"""

import errno
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

def getUserDataPos(dataset: Dataset,
                   refresh: bool = False) -> Tuple[bool, int, int]:
    """ Get the offset of the start of the user data.

        :param dataset: The `Dataset` in which to locate the user data.
        :param refresh:: If `True`, ignore any cached values and re-read
            from the file.
        :return: A tuple containing a bool (wheter or not data exists),
            the offset of the user data, and the total length of the file.
            Offset and filesize will typically be the same if there is no
            user data.
    """
    if not refresh and dataset._userdataOffset and dataset._filesize:
        return bool(dataset._userdata), dataset._userdataOffset, dataset._filesize

    doc = dataset.ebmldoc
    fs = doc.stream
    hasdata = False

    oldpos = fs.tell()
    filesize = fs.seek(0, os.SEEK_END)
    offset = filesize

    # The UserDataOffset is a known, fixed size
    example = doc.schema['UserDataOffset'].encode(1, length=8, lengthSize=8)
    header = example[:-8]

    try:
        # UserDataOffset *should* be right at the end of the file, but
        # don't assume so. Start some bytes back and find the header.
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

    dataset._userdataOffset = offset
    dataset._filesize = filesize
    return hasdata, offset, filesize


#===============================================================================
#
#===============================================================================

def readUserData(dataset: Dataset,
                 refresh: bool = False) -> Union[Dict[str, Any], None]:
    """ Read application-specific user data from the end of an IDE file.

        :param dataset: The `Dataset` from which to read the user data.
        :param refresh:: If `True`, ignore any cached values and re-read
            from the file.
        :return: A dictionary of user data, or `None` if no user data
            could be read from the file (e.g., none exists).
    """
    if not refresh and dataset._userdataOffset and dataset._filesize:
        return dataset._userdata

    doc = dataset.ebmldoc
    fs = doc.stream
    oldpos = fs.tell()

    hasdata, offset, filesize = getUserDataPos(dataset, refresh=refresh)

    if not hasdata:
        logger.debug('No user data found')
        dataset._userdata = None
        return None

    try:
        fs.seek(offset, os.SEEK_SET)
        data, _next = doc.parseElement(fs)
        dump = data.dump()
        dataset._userdata = dump
        return dump

    finally:
        fs.seek(oldpos, os.SEEK_SET)


#===============================================================================
#
#===============================================================================

def writeUserData(dataset: Dataset,
                  userdata: Dict[str, Any],
                  refresh: bool = False):
    """ Write user data to the end of an IDE file.

        :param dataset: The `Dataset` from which to read the user data.
        :param userdata: A dictionary of user data, or `None` to remove
            existing user data. Note that the file will not get smaller if
            the user data is removed or the new set of user data is smaller
            than existing user data); it is just overwritten with null data
            (an EBML `Void` element).
        :param refresh: If `True`, ignore any cached values and find the
            position in the file to which to write.
    """
    schema = dataset.ebmldoc.schema
    fs = dataset.ebmldoc.stream
    oldpos = fs.tell()

    try:
        hasdata, offset, filesize = getUserDataPos(dataset, refresh=refresh)

        if userdata:
            # User data consists of a `UserData` element, a `Void`, and `UserDataOffset`
            dataBin = schema.encodes({'UserData': userdata or {}})
            offsetBin = schema['UserDataOffset'].encode(offset, length=8, lengthSize=8)
            newsize = (len(offsetBin) + len(dataBin) + offset + MIN_VOID_SIZE)
            voidBin = schema['Void'].encode(None, length=max(0, filesize - newsize),
                                            lengthSize=8)
        else:
            # No new userdata, just write 'Void' over any existing userdata
            # (or do nothing if there is no existing userdata)
            dataset._userdata = userdata
            if not hasdata:
                return
            newsize = filesize
            dataBin = offsetBin = b''
            voidBin = schema['Void'].encode(None, length=max(0, filesize - MIN_VOID_SIZE))

        userblob = dataBin + voidBin + offsetBin

        try:
            writable = fs.writable()
        except AttributeError:
            # In case file-like stream doesn't implement `writable()`
            # (e.g., older `ebmlite.threaded_file.ThreadAwareFile`)
            mode = getattr(fs, 'mode', '')
            writable = '+' in mode or 'w' in mode

        if not writable:
            # File/stream is read-only; attempt to create a new file stream.
            if not getattr(fs, 'name', None):
                raise IOError(errno.EACCES,
                              f'Could not write user data; '
                              f'Dataset stream not writable and has no filename')

            with open(fs.name, 'br+') as newfs:
                logger.debug(f'(userdata) Dataset stream read only (mode {fs.mode!r}), '
                             'using new stream')
                newfs.seek(offset, os.SEEK_SET)
                newfs.write(userblob)

        else:
            fs.seek(offset, os.SEEK_SET)
            fs.write(userblob)

        dataset._userdata = userdata
        logger.debug(f'(userdata) Wrote {len(userblob)} bytes to {dataset} '
                     f'(file was {filesize}, now {newsize})')

    finally:
        fs.seek(oldpos, os.SEEK_SET)
