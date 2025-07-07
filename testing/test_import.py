"""
Tests for special features of the importing functions.
"""
from io import BytesIO

import pytest  # type: ignore

from idelib import importer
from testing.file_streams import makeStreamLike


# ==============================================================================
#
# ==============================================================================

def _functionlike(cls):
    """ Decorator for a singleton callable class. """
    return cls()


@_functionlike
class NullUpdater:
    """ A progress updater stand-in that does nothing. """
    cancelled = False
    paused = False

    def __call__(self, *args, **kwargs):
        if kwargs.get('error', None) is not None:
            raise kwargs['error']


# ==============================================================================
#
# ==============================================================================

def test_bad_import():
    """
    Basic test that trying to import a non-IDE fails early in the process.
    """
    # Test importing file
    with pytest.raises(IOError, match="Not an IDE file"):
        _doc = importer.openFile(__file__)

    # Test importing from a non-file stream (w/o filename)
    with pytest.raises(IOError, match="Not an IDE file"):
        with open(__file__, 'rb') as f:
            stream = BytesIO(f.read())
            stream.seek(0)
            _doc = importer.openFile(stream)


class TestImportRange:

    def test_import_updater(self):
        """
        Test importing with an updater
        """
        doc = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
        importer.readData(doc, updater=NullUpdater)


    @classmethod
    def setup_class(cls):
        cls.dataset = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
        importer.readData(cls.dataset)

        cls.extractionStart = cls.dataset.sessions[0].lastTime * .33
        cls.extractionEnd = cls.extractionStart * 2

        cls.dataset.close()


    def test_import_startTime(self):
        """
        Test importing a range with only start time specified.
        """
        doc = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
        importer.readData(doc,
                          startTime=self.extractionStart,
                          endTime=None,
                          channels=None)

        for channel in doc.channels.values():
            data = channel.getSession()
            assert data[0][0] <= self.extractionStart


    def test_import_endTime(self):
        """
        Test importing a range with only end time specified.
        """
        doc = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
        importer.readData(doc,
                          startTime=0,
                          endTime=self.extractionEnd,
                          channels=None)

        for channel in doc.channels.values():
            data = channel.getSession()
            assert data[-1][0] >= self.extractionEnd


    def test_import_startTime_endTime(self):
        """
        Test importing a range with both start and end times specified.
        """
        doc = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
        importer.readData(doc,
                          startTime=self.extractionStart,
                          endTime=self.extractionEnd,
                          channels=None)

        for channel in doc.channels.values():
            data = channel.getSession()
            assert data[0][0] <= self.extractionStart
            assert data[-1][0] >= self.extractionEnd


    def test_import_channels(self):
        """
        Test that only data from specified channels is imported.
        """
        doc = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
        importer.readData(doc,
                          channels=[8, 36])

        assert len(doc.channels[8].getSession()) > 0, \
            "Imported file did not contain data for specified channel"
        assert len(doc.channels[36].getSession()) > 0, \
            "Imported file did not contain data for specified channel"
        assert len(doc.channels[32].getSession()) == 0, \
            "Imported file contains data from excluded channel"


def test_fingerprint():
    """ Test that fingerprints are generated correctly when a Dataset is
        opened, and aren't affected by additional file reads.
    """
    doc1 = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
    doc2 = importer.openFile(makeStreamLike("./testing/SSX70065.IDE"))

    fingerprint1 = doc1.fingerprint
    fingerprint2 = doc2.fingerprint

    assert fingerprint1 is not None
    assert fingerprint2 is not None
    assert fingerprint1 != fingerprint2

    doc3 = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
    importer.readData(doc3)
    assert doc3.fingerprint == fingerprint1
