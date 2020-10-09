import os.path

import pytest  # type: ignore
import idelib


@pytest.mark.parametrize('filename', [
    os.path.join('testing', 'test3.IDE'),
])
def test_integ_channels(filename):
    with idelib.importFile(filename) as ds:
        assert {i for i in ds.channels.keys()} == {8, 36, 59, 70, 80, 84}

        accel100g_ch = ds.channels[8]
        data = accel100g_ch.getSession().arraySlice()
        assert data.shape[0] == 5  # t, x, y, z, mic
        assert data.size > 0

        accel40g_ch = ds.channels[80]
        data = accel40g_ch.getSession().arraySlice()
        assert data.shape[0] == 4  # t, x, y, z
        assert data.size > 0

        rot_ch = ds.channels[84]
        data = rot_ch.getSession().arraySlice()
        assert data.shape[0] == 4  # t, x, y, z
        assert data.size > 0

        orient_ch = ds.channels[70]
        data = orient_ch.getSession().arraySlice()
        assert data.shape[0] == 5  # t, x, y, z, w
        assert data.size > 0

        pt_ch = ds.channels[36]
        data = pt_ch.getSession().arraySlice()
        assert data.shape[0] == 3  # t, press, temp
        assert data.size > 0

        pt_ctrl_ch = ds.channels[59]
        data = pt_ctrl_ch.getSession().arraySlice()
        assert data.shape[0] == 3  # t, press, temp
        assert data.size > 0
