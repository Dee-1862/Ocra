import math

import pytest

from wilirehab.measures import (ReactionStats, describe_trend, trend_per_minute,
                                tremor_band)


# ---- reaction time ---------------------------------------------------------

def test_reaction_summary():
    r = ReactionStats()
    assert r.summary() is None
    for ms in (300, 250, 500, 350):
        r.add(ms)
    s = r.summary()
    assert s["count"] == 4 and s["median"] == 325 and s["best"] == 250 and s["worst"] == 500
    assert s["mean"] == pytest.approx(350.0)


# ---- trend -----------------------------------------------------------------

def line(slope_per_min, n=10, span_s=90.0, start=100.0):
    return [(i * span_s / (n - 1), start + slope_per_min * (i * span_s / (n - 1)) / 60.0)
            for i in range(n)]


def test_trend_recovers_the_slope():
    assert trend_per_minute(line(12.0)) == pytest.approx(12.0)
    assert trend_per_minute(line(-5.0)) == pytest.approx(-5.0)


def test_trend_needs_enough_points_and_time():
    assert trend_per_minute(line(5.0, n=4)) is None
    assert trend_per_minute(line(5.0, n=10, span_s=10.0)) is None


def test_flat_data_has_zero_trend():
    assert trend_per_minute([(i * 10.0, 7.0) for i in range(8)]) == pytest.approx(0.0)


def test_describe_trend_wording():
    assert describe_trend(None, 1, "ms", False) is None
    assert describe_trend(0.4, 1.0, "ms", False) == "steady"
    # reaction time rising is worse (lower is better)
    assert describe_trend(12.0, 1.0, "ms", False).startswith("worsening")
    assert describe_trend(-12.0, 1.0, "ms", False).startswith("improving")
    # success rate rising is better
    assert describe_trend(3.0, 1.0, "%", True).startswith("improving")


# ---- tremor ----------------------------------------------------------------

def sine(freq_hz, amp, n=256, fs=50.0, axis=0):
    t = [i / fs for i in range(n)]
    samples = []
    for ti in t:
        v = [0.0, 0.0, 1000.0]                    # gravity on z
        v[axis] += amp * math.sin(2 * math.pi * freq_hz * ti)
        samples.append(tuple(v))
    return samples, [int(ti * 1000) for ti in t]


def test_an_8hz_shake_is_found():
    samples, t_ms = sine(8.0, 20.0)
    rms, peak = tremor_band(samples, t_ms)
    assert peak == pytest.approx(8.0, abs=0.5)
    assert rms == pytest.approx(20.0 / math.sqrt(2), rel=0.2)


def test_slow_motion_is_not_tremor():
    samples, t_ms = sine(1.0, 200.0)
    rms, _peak = tremor_band(samples, t_ms)
    assert rms < 5.0


def test_a_still_hand_has_almost_no_tremor():
    samples = [(0.0, 0.0, 1000.0)] * 256
    rms, _ = tremor_band(samples, [i * 20 for i in range(256)])
    assert rms < 0.01


def test_tremor_needs_enough_data_and_a_fast_enough_rate():
    samples, t_ms = sine(8.0, 20.0, n=40)
    assert tremor_band(samples, t_ms) is None                 # too few samples
    samples, t_ms = sine(8.0, 20.0, n=256, fs=20.0)
    assert tremor_band(samples, t_ms) is None                 # too slow to see 12 Hz


def test_tremor_adds_the_three_axes():
    one, t_ms = sine(8.0, 20.0, axis=0)
    rms_x, _ = tremor_band(one, t_ms)
    two = [(a[0] + b[0] - 0.0, a[1] + 0.0, a[2]) for a, b in zip(one, one)]
    # two copies of the same shake on x double the amplitude: rms doubles
    rms_2x, _ = tremor_band(two, t_ms)
    assert rms_2x == pytest.approx(2 * rms_x, rel=0.05)
