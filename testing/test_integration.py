import os.path

import pytest  # type: ignore
import idelib


@pytest.mark.parametrize('filename, ch_axes', [
    (
        os.path.join('testing', 'test3.IDE'),
        {
            8: 5,  # t, x, y, z, mic
            36: 3,  # t, press, temp
            59: 3,  # t, press, temp
            70: 5,  # t, x, y, z, w
            80: 4,  # t, x, y, z
            84: 4,  # t, x, y, z
        },
    ),
])
def test_integ_channels_1(filename, ch_axes):
    with idelib.importFile(filename) as ds:
        assert set(ds.channels.keys()) == set(ch_axes.keys())

        for ch_no, axis_count in ch_axes.items():
            channel = ds.channels[ch_no]
            data = channel.getSession().arraySlice()
            assert data.shape[0] == axis_count
            assert data.size > 0
