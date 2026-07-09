import numpy as np

from modules.ui.plot_downsample import downsample_xy


def test_downsample_xy_limits_points_and_keeps_spike():
    x = np.arange(1000)
    y = np.zeros(1000)
    y[500] = 100.0

    xd, yd = downsample_xy(x, y, max_points=40)

    assert len(xd) <= 40
    assert len(yd) <= 40
    assert 100.0 in yd


def test_downsample_xy_keeps_small_inputs_unchanged():
    x = np.arange(4)
    y = np.array([1.0, 2.0, 3.0, 4.0])

    xd, yd = downsample_xy(x, y, max_points=10)

    assert xd.tolist() == [0, 1, 2, 3]
    assert yd.tolist() == [1.0, 2.0, 3.0, 4.0]
