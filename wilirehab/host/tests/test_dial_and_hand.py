import random

import pytest

from wilirehab.dial import DialRound, needle_end


# ---- dial ----------------------------------------------------------------

def test_needle_end_points():
    assert needle_end(100, 100, 50, 0) == pytest.approx((100, 50))
    assert needle_end(100, 100, 50, 90) == pytest.approx((150, 100))
    assert needle_end(100, 100, 50, -90) == pytest.approx((50, 100))


def make(**kw):
    return DialRound(rng=random.Random(1), **kw)


def test_target_is_inside_the_range_and_in_steps_of_five():
    for seed in range(30):
        d = DialRound(range_deg=45, rng=random.Random(seed))
        assert abs(d.target) <= 36 + 1e-9
        assert d.target % 5 == 0


def test_holding_on_target_completes():
    d = make(hold_s=1.0, tolerance=10)
    target = d.target
    results = [d.update(target, 0.25) for _ in range(4)]
    assert results[-1] == "complete"
    assert d.completed == 1


def test_leaving_the_target_resets_the_hold():
    d = make(hold_s=1.0, tolerance=5)
    target = d.target
    d.update(target, 0.6)
    assert d.on_target
    d.update(target + 20, 0.1)
    assert not d.on_target
    assert d.update(target, 0.6) is None      # had to start over


def test_completing_makes_it_harder_and_picks_a_new_target():
    d = make(hold_s=0.5, tolerance=10)
    old = d.target
    d.update(old, 0.5)
    assert d.tolerance == 9
    assert abs(d.target - old) >= 10


def test_tolerance_never_goes_below_the_floor():
    d = make(hold_s=0.1, tolerance=4)
    for _ in range(5):
        d.update(d.target, 0.1)
    assert d.tolerance == 4


def test_a_timeout_loosens_the_tolerance():
    d = make(timeout_s=2.0, tolerance=10)
    out = [d.update(1000.0, 0.5) for _ in range(4)]    # never near the target
    assert out[-1] == "timeout"
    assert d.timeouts == 1 and d.tolerance == 12
