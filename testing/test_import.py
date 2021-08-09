import os.path

import pytest  # type: ignore

from idelib import importer
from testing.file_streams import makeStreamLike


# ==============================================================================
#
# ==============================================================================

class TestImport:

    def test_import_updater(self):
        """
        Test importing with an updater
        """
        doc = importer.openFile(makeStreamLike("./testing/SSX66115.IDE"))
        importer.readData(doc, updater=importer.NullUpdater)


class TestImportRange:

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
