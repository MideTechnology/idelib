import os.path
import tempfile

from ebmlite import loadSchema
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

        assert len(extracted.channels[8].getSession()) > 0, \
            "Extracted file did not contain data for specified channel"
        assert len(extracted.channels[36].getSession()) > 0, \
            "Extracted file did not contain data for specified channel"
        assert len(extracted.channels[32].getSession()) == 0, \
            "Extracted file contain data from excluded channel"


class TestGetLength:

    @classmethod
    def setup_class(cls):
        cls.idefile = os.path.join(os.path.dirname(__file__), "SSX66115.IDE")
        cls.dataset = importer.importFile(cls.idefile)


    @classmethod
    def teardown_class(cls):
        cls.dataset.close()


    def test_getSize(self):
        with open(self.idefile, 'rb') as fs:
            assert util._getSize(fs) == os.path.getsize(self.idefile), \
                    "_getSize() of file stream did not match actual size"

            fs.seek(100)
            assert util._getSize(fs) == os.path.getsize(self.idefile), \
                    "_getSize() of file stream (tell > 0) did not match actual size"
            assert fs.tell() == 100, \
                    "_getSize() did not restore file position"


        with makeStreamLike('./testing/SSX66115.IDE') as fs:
            assert util._getSize(fs) == os.path.getsize(self.idefile), \
                   "_getSize() of non-file stream did not match actual size"


    def test_getLastSync(self):
        # get all SyncElement offsets, since _getLastSync() doesn't get the
        # actual last sync, just one with data following it.
        syncs = []
        lastData = None
        for el in self.dataset.ebmldoc:
            if el.name == "ChannelDataBlock":
                lastData = el
            elif el.name == "Sync":
                syncs.append(el.offset)

        with open(self.idefile, 'rb') as fs:
            lastSync = util._getLastSync(fs)

            assert lastSync in syncs, \
                "_getLastSync() did not find SyncElement"
            assert lastSync < lastData.offset, \
                "_getLastSync() returned a SyncElement after all data"


    def test_getBlockSize(self):
        # Check _getBlockSize() gets the same values as the 'real' parser
        for channel in self.dataset.channels.values():
            for block in channel.getSession()._data:
                cid, start, end = util._getBlockTime(self.dataset, block.element)

                assert cid == channel.id, \
                    "_getBlockSize() parsed ChannelID wrong"
                assert start == block.startTime
                assert end == block.endTime


    def test_getLength(self):
        first, last = util.getLength(self.dataset)

        assert self.dataset.lastSession.firstTime == first, \
            "getLength() starting time did not match Dataset"
        assert self.dataset.lastSession.lastTime == last, \
            "getLength() ending time did not match Dataset"


    def test_getExitCondition(self):
        # Exit condition read when the file is fully imported.
        assert self.dataset.exitCondition == util.getExitCondition(self.idefile), \
            "getExitCondition() did not match Document.exitCondition"


