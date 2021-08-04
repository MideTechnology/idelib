import os.path
import tempfile

import pytest  # type: ignore

from idelib import importer
from idelib import util
from testing.file_streams import makeStreamLike


# ==============================================================================
#
# ==============================================================================

class TestExtractTime:

    @classmethod
    def setup_class(cls):
        cls.dataset = importer.openFile(os.path.join(os.path.dirname(__file__), "SSX66115.IDE"))
        importer.readData(cls.dataset)

        cls.extractionStart = cls.dataset.sessions[0].lastTime * .33
        cls.extractionEnd = cls.extractionStart * 2


    @classmethod
    def teardown_class(cls):
        cls.dataset.close()


    def extractTime2tempfile(self, **kwargs):
        """
        Helper to do the busywork of running `extractTime()`, extracting to a
        temporary file, and importing the extracted data as a new `Dataset`.
        Keyword arguments are passed to `extractTime()`.
        """
        out = tempfile.SpooledTemporaryFile(suffix=".ide")
        util.extractTime(self.dataset, out, **kwargs)
        out.seek(0)
        extracted = importer.openFile(out)
        importer.readData(extracted)

        return extracted


    def test_extractTime_start(self):
        """
        Test extraction with only start time specified.
        """
        extracted = self.extractTime2tempfile(startTime=self.extractionStart,
                                              endTime=None,
                                              channels=None)

        for channel in extracted.channels.values():
            data = channel.getSession()
            assert data[0][0] <= self.extractionStart


    def test_extractTime_end(self):
        """
        Test extraction with only end time specified.
        """
        extracted = self.extractTime2tempfile(startTime=0,
                                              endTime=self.extractionEnd,
                                              channels=None)

        for channel in extracted.channels.values():
            data = channel.getSession()
            assert data[-1][0] >= self.extractionEnd


    def test_extractTime_start_end(self):
        """
        Test extraction with both start and end times specified.
        """
        extracted = self.extractTime2tempfile(startTime=self.extractionStart,
                                              endTime=self.extractionEnd,
                                              channels=None)

        for channel in extracted.channels.values():
            data = channel.getSession()
            assert data[0][0] <= self.extractionStart
            assert data[-1][0] >= self.extractionEnd


    def test_extractTime_channels(self):
        """
        Test that only data from specified channels is extracted.
        """
        extracted = self.extractTime2tempfile(startTime=self.extractionStart,
                                              endTime=self.extractionEnd,
                                              channels=[8, 36])

        assert len(extracted.channels[8].getSession()) > 0
        assert len(extracted.channels[36].getSession()) > 0
        assert len(extracted.channels[32].getSession()) == 0
