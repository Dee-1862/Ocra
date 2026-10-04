import numpy as np
import pytest

from wilirehab.face_strain import mean_rgb
from wilirehab.live_face import Baseline, resample
from wilirehab.face_strain import FaceMeasures


def test_resample_makes_an_even_grid_from_uneven_times():
    t = [0.0, 0.05, 0.13, 0.2, 0.31, 0.4]
    v = [[x * 10, x * 20, x * 30] for x in t]
    out = resample(t, v, fs=10.0)
    assert out.shape == (4, 3)
    assert out[1] == pytest.approx([1.0, 2.0, 3.0], abs=1e-9)


def test_resample_of_too_few_samples_is_empty():
    assert resample([0.0], [[1, 2, 3]]).shape == (0, 3)


def test_patch_average_is_less_noisy_than_one_pixel():
    rng = np.random.default_rng(0)
    frame = 100.0 + rng.normal(0, 10, (40, 40, 3))
    lm = [(20.0, 20.0)] * 468
    single = mean_rgb(frame, lm, (10,), radius=0)
    patch = mean_rgb(frame, lm, (10,), radius=5)
    assert abs(patch - 100).max() < abs(single - 100).max()


def test_patch_is_clipped_at_the_edge():
    frame = np.ones((10, 10, 3)) * 7
    lm = [(0.0, 0.0)] * 468
    assert mean_rgb(frame, lm, (10,), radius=4) == pytest.approx([7, 7, 7])


def test_baseline_waits_for_its_window_and_takes_the_median():
    b = Baseline(seconds=2.0)
    for k in range(30):
        b.add(k * 0.1, FaceMeasures(0.3, 0.5, 0.4))
    assert b.face is not None
    assert b.face.ear == pytest.approx(0.3)


def test_baseline_not_ready_before_the_window():
    b = Baseline(seconds=5.0)
    for k in range(20):
        b.add(k * 0.1, FaceMeasures(0.3, 0.5, 0.4))
    assert b.face is None
