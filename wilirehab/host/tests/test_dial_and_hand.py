import random

import pytest

from wilirehab.dial import DialRound, needle_end
from wilirehab.handshape import hand_shape, mirrored_angle


# ---- hand drawing --------------------------------------------------------

def tips(shape):
    return [b for _a, b in shape]


def test_upright_hand_points_up():
    shape = hand_shape(0.0)
    ys = [p[1] for seg in shape for p in seg]
    assert min(ys) < -60 and max(ys) == pytest.approx(0.0)


def test_turning_90_degrees_points_the_hand_right():
    shape = hand_shape(90.0)
    xs = [p[0] for seg in shape for p in seg]
    assert max(xs) > 60 and min(xs) > -35      # the hand now lies to the right


def test_left_hand_is_the_mirror_image_of_the_right():
    right = hand_shape(0.0, left=False)
    left = hand_shape(0.0, left=True)
    for (a, b), (c, d) in zip(right, left):
        assert c == pytest.approx((-a[0], a[1]))
        assert d == pytest.approx((-b[0], b[1]))


def test_mirrored_drawing_is_the_mirror_of_the_driver():
    # Driver: right hand turned 20 degrees. Mirror: left hand at the negated angle.
    driver = hand_shape(20.0, left=False)
    mirror = hand_shape(mirrored_angle(20.0), left=True)
    for (a, b), (c, d) in zip(driver, mirror):
        assert c == pytest.approx((-a[0], a[1]))
        assert d == pytest.approx((-b[0], b[1]))


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
