import numpy as np
import pytest  # type: ignore

import idelib.dataset as dataset
from idelib import importer
from idelib import (
    matfile,
    multi_importer,
    unit_conversion,
    )

import os

from testing.file_streams import makeStreamLike

@pytest.fixture
def load_test_dataset():
    """ Open and close the test.ide file """
    testDataset = importer.openFile(makeStreamLike('./test.ide'))
    importer.readData(testDataset)
    yield testDataset
    testDataset.close()


def test_path(load_test_dataset):
    """
        Test that the path of the test ide file (which is a root) is its name.
    """
    assert load_test_dataset.path() == load_test_dataset.name


def test_channels(load_test_dataset):
    """
        The channels present in the file are 8 and 36, check that those are present.
    """
    assert list(load_test_dataset.channels.keys()) == [8, 36]


def test_add_session(load_test_dataset):
    startTime = 0.1
    endTime = 1.0
    utcStartTime = 1e6
    newSession = load_test_dataset.addSession(startTime=startTime, endTime=endTime, utcStartTime=utcStartTime)
    assert newSession == dataset.Session(load_test_dataset, sessionId=1, startTime=startTime, endTime=endTime, utcStartTime=utcStartTime)


def test_thing(load_test_dataset):
    session = load_test_dataset.channels[8].getSession()
    print(session[:])


# ==============================================================================
# Cascading Tests
# ==============================================================================


@pytest.fixture
def cascading_1():
    casc = dataset.Cascading()
    casc.name = 'parent'
    yield casc
    del casc


@pytest.fixture
def cascading_2(cascading_1):
    casc = dataset.Cascading()
    casc.name = 'child'
    casc.parent = cascading_1
    yield casc
    del casc


@pytest.fixture
def cascading_none(cascading_1):
    casc = dataset.Cascading()
    casc.name = 'null'
    casc.parent = cascading_1
    cascading_1.path = lambda: None
    yield casc
    del casc

class TestCascading:

    def test_cascading_hierarchy(self, cascading_1, cascading_2):
        assert cascading_2.hierarchy() == [cascading_1, cascading_2]

    def test_cascading_path_1(self, cascading_1):
        assert cascading_1.path() == 'parent'

    def test_cascading_path_2(self, cascading_2):
        assert cascading_2.path() == 'parent:child'

    def test_cascading_path_3(self, cascading_none):
        assert cascading_none.path() == 'null'

    def test_cascading_repr(self, cascading_1):
        assert repr(cascading_1) == "<Cascading 'parent' at 0x%x>" % (id(cascading_1,))
        pass


# ==============================================================================
# EventList Tests
# ==============================================================================


@pytest.fixture()
def channel_8_eventarray(load_test_dataset):
    yield load_test_dataset.channels[8].getSession()


@pytest.fixture()
def channel_36_eventarray(load_test_dataset):
    yield load_test_dataset.channels[36].getSession()


@pytest.fixture()
def new_event_array(load_test_dataset):
    yield dataset.EventArray(load_test_dataset.channels[8],
                            session=load_test_dataset.addSession(0, 1))

class TestEventArray:

    def test_init(self, new_event_array, channel_8_eventarray):
        assert new_event_array == channel_8_eventarray

    @pytest.mark.parametrize(
            'start, end, step, expected',
            [(None, None, None, np.arange(1000, dtype=np.float64)[np.newaxis, :]),
             (0, 100, 1, np.arange(100, dtype=np.float64)[np.newaxis, :]),
             (0, 99.9, 1, np.arange(100, dtype=np.float64)[np.newaxis, :]),
             (0.1, 99.9, 1, np.arange(100, dtype=np.float64)[np.newaxis, :]),
             (np.float(0.1), np.float(99.9), 1, np.arange(100, dtype=np.float64)[np.newaxis, :]),
             ]
            )
    def test_array_values(self, channel_8_eventarray, start, end, step, expected):
        values = channel_8_eventarray.arrayValues(start=start, end=end, step=step, subchannels=(0,))
        np.testing.assert_equal(values, expected)

    @pytest.mark.parametrize(
            'start, end, step, expected',
            [(None, None, None, np.arange(1000, dtype=np.float64)),
             (0, 100, 1, np.arange(100, dtype=np.float64)),
             (0, 99.9, 1, np.arange(100, dtype=np.float64)),
             (0.1, 99.9, 1, np.arange(100, dtype=np.float64)),
             (np.float(0.1), np.float(99.9), 1, np.arange(100, dtype=np.float64)),
             ]
            )
    def test_array_jittery_values(self, channel_8_eventarray, start, end, step, expected):
        values = channel_8_eventarray.arrayJitterySlice(start=start, end=end, step=step)[1, :]
        np.testing.assert_equal(values, expected)
