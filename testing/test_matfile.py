import struct
from io import StringIO, BytesIO
import sys
import unittest
import mock
import os

import pytest

import numpy as np  # type: ignore
import scipy.io

from idelib.dataset import (Cascading,
                            Channel,
                            Dataset,
                            EventArray,
                            Plot,
                            Sensor,
                            Session,
                            SubChannel,
                            Transformable,
                            WarningRange,
                            )
from idelib.transforms import Transform, CombinedPoly, PolyPoly
from idelib.transforms import AccelTransform, Univariate
from idelib import importer
from idelib import parsers
from idelib import matfile

from testing.utils import nullcontext

from .file_streams import makeStreamLike


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
def testIDE():
    doc = importer.openFile(_load_file('./test.ide'))
    importer.readData(doc)
    return doc


@pytest.fixture
def SSX70065IDE():
    doc = importer.openFile(_load_file('./testing/SSX70065.IDE'))
    importer.readData(doc)
    return doc


@pytest.fixture
def SSX_DataIDE():
    doc = importer.openFile(_load_file('./testing/SSX_Data.IDE'))
    importer.readData(doc)
    return doc


def testMatExport(SSX70065IDE):
    matName = './testing/SSX70065.mat'
    mat = matfile.exportMat(SSX70065IDE.channels[32].getSession(), matName)

    matfiles = [x for x in os.listdir('./testing') if '.mat' in x]

    assert len(matfiles) > 0, 'no .mat files present in testing directory'

    realMatName = matfiles[0]

    scimat = scipy.io.loadmat(f'./testing/{realMatName}')

    np.testing.assert_equal(
            scimat['Acceleration'],
            SSX70065IDE.channels[32].getSession().arraySlice(),
            )

