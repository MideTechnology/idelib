"""
Test reading/writing user data to/from IDE files and streams (files and
file-like).
"""

import pytest  # type: ignore

from io import BytesIO
import os.path
import shutil

from idelib import importer
from idelib import userdata

from testing import file_streams


# ==============================================================================
#
# ==============================================================================

USERDATA = {
    'TimebaseOffset': 12345,
    'WindowLayout': bytearray(b'bogus binary blob'),
    'TimeBaseUTC': [1712769739]
}

SMALLER_USERDATA = {
    'TimebaseOffset': 54321,
}

LARGER_USERDATA = {
    'TimebaseOffset': 56789,
    'WindowLayout': bytearray(b'bogus binary blob'),
    'AnnotationList': {
        'Annotation': [{'AnnotationID': 42, 'AnnotationStartTime': 101},],
    },
    'TimeBaseUTC': [35096400]
}

FILE_WITHOUT_USERDATA = './testing/SSX_Data.IDE'
FILE_WITH_USERDATA = './testing/with_userdata.IDE'


# ==============================================================================
#
# ==============================================================================

def test_read_userdata():
    """ Test reading user data.
    """
    doc = importer.openFile(file_streams.makeStreamLike(FILE_WITH_USERDATA))
    data = userdata.readUserData(doc)
    assert data == USERDATA


def test_read_userdata_no_userdata():
    """ Test reading user data from a file without user data.
    """
    doc = importer.openFile(file_streams.makeStreamLike(FILE_WITHOUT_USERDATA))
    data = userdata.readUserData(doc)
    assert data is None


def test_write_userdata(tmp_path):
    """ Test writing (and re-reading) user data to a file without existing
        user data.
    """
    sourceFile = FILE_WITHOUT_USERDATA
    filename = tmp_path / os.path.basename(sourceFile)

    shutil.copyfile(sourceFile, filename)

    with importer.importFile(filename) as doc:
        userdata.writeUserData(doc, USERDATA)

    with importer.importFile(filename) as doc:
        data = userdata.readUserData(doc)
        assert data == USERDATA


def test_write_userdata_BytesIO():
    """ Test writing (and re-reading) user data from a non-file stream
        without existing user data.
    """
    sourceFile = FILE_WITHOUT_USERDATA

    with open(sourceFile, 'rb') as f:
        stream = BytesIO(f.read())

    with importer.openFile(stream) as doc:
        userdata.writeUserData(doc, USERDATA)

        data = userdata.readUserData(doc)
        assert data == USERDATA


def test_larger_userdata(tmp_path):
    """ Test overwriting an existing set of user data with a larger one.
    """
    sourceFile = FILE_WITH_USERDATA
    filename = tmp_path / os.path.basename(sourceFile)
    shutil.copyfile(sourceFile, filename)

    originalSize = os.path.getsize(filename)

    with importer.importFile(filename) as doc:
        userdata.writeUserData(doc, LARGER_USERDATA)

    with importer.importFile(filename) as doc:
        data = userdata.readUserData(doc)
        assert data == LARGER_USERDATA

    assert originalSize < os.path.getsize(filename)


def test_smaller_userdata(tmp_path):
    """ Test overwriting an existing set of user data with a smaller one.
    """
    sourceFile = FILE_WITH_USERDATA
    filename = tmp_path / os.path.basename(sourceFile)
    shutil.copyfile(sourceFile, filename)

    originalSize = os.path.getsize(filename)

    with importer.importFile(filename) as doc:
        userdata.writeUserData(doc, SMALLER_USERDATA)

    with importer.importFile(filename) as doc:
        data = userdata.readUserData(doc)
        assert data == SMALLER_USERDATA

    assert originalSize == os.path.getsize(filename)
