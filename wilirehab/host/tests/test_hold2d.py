import random

import pytest

from wilirehab.hold2d import HoldRound2D


def make(**kw):
    return HoldRound2D(rng=random.Random(3), **kw)


def test_target_is_inside_the_range():
    for seed in range(30):
        h = HoldRound2D(range_deg=12, rng=random.Random(seed))
        assert abs(h.target[0]) <= 0.7 * 12 + 1 and abs(h.target[1]) <= 0.7 * 12 + 1


def test_holding_inside_the_ring_completes():
    h = make(hold_s=1.0, tolerance=6)
    tx, ty = h.target
    results = [h.update(tx + 1, ty - 1, 0.25) for _ in range(4)]
    assert results[-1] == "complete"
    assert h.completed == 1 and h.tolerance == 5


def test_distance_uses_both_angles():
    h = make(hold_s=1.0, tolerance=4)
    tx, ty = h.target
    h.update(tx, ty + 5, 0.5)              # right roll, wrong pitch: outside the ring
    assert not h.on_target
    h.update(tx, ty + 3, 0.5)              # inside
    assert h.on_target


def test_a_timeout_widens_the_ring():
    h = make(timeout_s=2.0, tolerance=6)
    out = [h.update(500.0, 500.0, 0.5) for _ in range(4)]
    assert out[-1] == "timeout" and h.tolerance == 8 and h.timeouts == 1


def test_steadiness_is_the_mean_distance_while_holding():
    h = make(hold_s=10.0, tolerance=6)
    tx, ty = h.target
    for _ in range(4):
        h.update(tx + 3, ty + 4, 0.1)      # distance 5 each time
    assert h.mean_distance == pytest.approx(5.0)


def test_no_distance_before_any_holding():
    assert make().mean_distance is None


def test_the_ring_never_leaves_its_limits():
    h = make(hold_s=0.1, tolerance=3)
    for _ in range(3):
        h.update(*h.target, 0.1)
    assert h.tolerance == 3
    h2 = make(timeout_s=0.5, tolerance=12)
    h2.update(900, 900, 0.5)
    assert h2.tolerance == 12
