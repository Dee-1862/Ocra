import math

import pytest

from wilirehab.autorange import AutoRange

DT = 0.02


def sweep(ar, lo, hi, seconds, freq=0.5, start_at_hi=True):
    """Feed a sinusoid between lo and hi; returns the last (angle, position)."""
    mid, amp = (lo + hi) / 2.0, (hi - lo) / 2.0
    sign = 1.0 if start_at_hi else -1.0
    pos = angle = None
    for i in range(int(seconds / DT)):
        angle = mid + sign * amp * math.cos(2 * math.pi * freq * i * DT)
        pos = ar.update(angle, DT)
    return angle, pos


def test_the_first_angle_is_the_middle():
    assert AutoRange().update(7.0) == pytest.approx(0.5)


def test_a_range_on_one_side_of_the_start_still_reaches_both_edges():
    # the recorded case: from 0 down to -18 degrees and never above 0
    ar = AutoRange()
    sweep(ar, -18.0, 0.0, seconds=25)
    positions = {}
    for angle in (0.0, -9.0, -18.0):
        positions[angle] = ar.update(angle, DT)
    assert positions[0.0] >= 0.95
    assert positions[-18.0] <= 0.05
    assert 0.4 <= positions[-9.0] <= 0.6                      # the middle of the range is the middle


def test_a_range_that_does_not_include_the_start_works_too():
    ar = AutoRange()
    ar.update(0.0, DT)
    sweep(ar, 5.0, 25.0, seconds=25, start_at_hi=False)
    assert ar.update(25.0, DT) >= 0.95 and ar.update(5.0, DT) <= 0.05


def test_the_range_widens_at_once_for_a_big_move():
    ar = AutoRange()
    ar.update(0.0, DT)
    ar.update(-30.0, DT)
    assert ar.lo <= -29.0 and ar.update(-30.0, DT) == pytest.approx(0.0, abs=0.05)


def test_tremor_sized_wobble_does_not_swing_the_paddle():
    ar = AutoRange()
    positions = [ar.update(0.3 * (1 if i % 2 else -1), DT) for i in range(500)]
    assert max(positions[100:]) - min(positions[100:]) < 0.12


def test_the_span_never_goes_below_the_minimum():
    ar = AutoRange(min_span=10.0)
    for _ in range(5000):                                       # 100 s of holding still
        ar.update(3.0, DT)
    assert ar.span >= 10.0 - 1e-9


def test_an_early_overshoot_is_forgotten():
    ar = AutoRange()
    ar.update(0.0, DT)
    ar.update(-40.0, DT)                                         # one big accidental swing
    sweep(ar, -6.0, 6.0, seconds=40)
    assert ar.span < 20.0


def test_positions_stay_between_zero_and_one():
    ar = AutoRange()
    for angle in (0, 50, -50, 10, -10, 200):
        assert 0.0 <= ar.update(angle, DT) <= 1.0


def test_reset_forgets_everything():
    ar = AutoRange()
    ar.update(5.0, DT)
    ar.reset()
    assert ar.span == 0.0 and ar.update(-20.0, DT) == pytest.approx(0.5)
