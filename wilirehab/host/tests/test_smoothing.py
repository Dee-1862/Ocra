import math

import pytest

from wilirehab.smoothing import Hysteresis, OneEuroFilter


def run(filt, values, dt=0.02):
    return [filt(i * dt, v) for i, v in enumerate(values)]


def test_a_constant_input_stays_constant():
    out = run(OneEuroFilter(), [5.0] * 50)
    assert out[-1] == pytest.approx(5.0)


def test_the_first_sample_passes_straight_through():
    assert OneEuroFilter()(0.0, 7.0) == 7.0


def test_a_still_hand_with_jitter_is_calmed():
    jitter = [0.6 * (1 if i % 2 else -1) for i in range(200)]
    out = run(OneEuroFilter(min_cutoff=0.5, beta=0.02), jitter)
    assert max(abs(v) for v in out[100:]) < 0.15            # raw jitter is 0.6


def test_a_fast_move_is_followed_quickly():
    # a 20 degree step; the output must be most of the way there within 150 ms
    out = run(OneEuroFilter(min_cutoff=0.5, beta=0.02), [0.0] * 10 + [20.0] * 40)
    assert out[10 + 7] > 12.0


def test_more_speed_means_less_delay():
    slow = run(OneEuroFilter(min_cutoff=0.5, beta=0.0), [0.0] * 10 + [20.0] * 40)
    fast = run(OneEuroFilter(min_cutoff=0.5, beta=0.05), [0.0] * 10 + [20.0] * 40)
    assert fast[14] > slow[14]


def test_it_copes_with_a_zero_time_step():
    f = OneEuroFilter()
    f(1.0, 0.0)
    assert math.isfinite(f(1.0, 5.0))


def test_hysteresis_ignores_small_wobble():
    h = Hysteresis(band=0.5)
    out = [h(v) for v in (0.0, 0.2, -0.3, 0.4, -0.4)]
    assert out == [0.0, 0.0, 0.0, 0.0, 0.0]


def test_hysteresis_follows_a_real_move_and_stays_within_the_band():
    h = Hysteresis(band=0.5)
    h(0.0)
    assert h(3.0) == pytest.approx(2.5)        # trails the input by the band
    assert h(2.8) == pytest.approx(2.5)        # a small step back inside the band is ignored
    assert h(3.2) == pytest.approx(2.7)        # a step past the band is followed
    assert h(1.0) == pytest.approx(1.5)        # moving back drags it along


def test_hysteresis_with_no_band_is_a_pass_through():
    h = Hysteresis(band=0.0)
    assert [h(v) for v in (1.0, 2.0, 1.5)] == [1.0, 2.0, 1.5]
