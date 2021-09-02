"""

"""
from io import BytesIO

import pytest
import numpy as np  # type: ignore

from idelib import importer
from idelib.matfile import exportMat

# ==============================================================================
# Fixtures
# ==============================================================================

_fileStrings = {}


def _load_file(filePath):
    if filePath not in _fileStrings:
        with open(filePath, 'rb') as f:
            _fileStrings[filePath] = f.read()
    out = BytesIO(_fileStrings[filePath])
    out.name = filePath
    return out


@pytest.fixture
def AccelEventArray():
    doc = importer.openFile(_load_file('./test.ide'))
    importer.readData(doc)
    return doc.channels[8].getSession()


# ==============================================================================
#
# ==============================================================================

class TestMatfile:

    def testExportMat(self, tmp_path, AccelEventArray):
        """ Test for matfile.exportMat() function.
            Currently rudimentary (just checks it doesn't simply crash).
        """
        filename = tmp_path / 'test.mat'
        exportMat(AccelEventArray, filename)
