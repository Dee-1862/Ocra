import math

import pytest

from wilirehab import tilt


def raw_for_mg(mg: int) -> int:
    return (int(mg) // 4) << 6


def gravity(pitch_deg, roll_deg):
    """Raw sample for an OG tilted `pitch` about y and `roll` about x (1 g)."""
    p, r = math.radians(pitch_deg), math.radians(roll_deg)
    x = 1000 * math.sin(p)
    y = 1000 * math.cos(p) * math.sin(r)
    z = 1000 * math.cos(p) * math.cos(r)
    return raw_for_mg(round(x)), raw_for_mg(round(y)), raw_for_mg(round(z))


def test_pitch_does_not_change_when_the_og_is_rolled():
    for roll in (0, 20, 40, 60):
        x, y, z = gravity(10.0, roll)
        t = tilt.TiltTracker(axis="x", alpha=1.0, median_len=1)
        t.update(x, y, z)
        assert t.absolute == pytest.approx(10.0, abs=0.5), roll


def test_roll_does_not_change_when_the_og_is_pitched():
    # The y axis elevation is cos(pitch) * sin(roll): it shrinks a little with pitch,
    # which is real geometry, but it must not swing wildly.
    x, y, z = gravity(15.0, 30.0)
    t = tilt.TiltTracker(axis="y", alpha=1.0, median_len=1)
    t.update(x, y, z)
    assert 27.0 < t.absolute < 30.0


def test_the_old_formula_really_was_coupled():
    # What atan2(x, z) would have said for pitch 10 with roll 40: about 13 degrees.
    x, y, z = gravity(10.0, 40.0)
    old = math.degrees(math.atan2(tilt.raw_to_mg(x), tilt.raw_to_mg(z)))
    assert old > 12.0


def test_free_fall_does_not_crash():
    assert tilt.tilt_deg(0, 0, 0) == 0.0


def test_the_euro_tracker_is_calm_when_still():
    t = tilt.TiltTracker(axis="y", median_len=3, euro=(0.5, 0.02))
    t.update(*gravity(0, 0), t=0.0)
    out = []
    for i in range(1, 200):
        wobble = 0.6 if i % 2 else -0.6
        out.append(t.update(*gravity(0, wobble), t=i * 0.02))
    assert max(abs(v) for v in out[100:]) < 0.25


def test_the_euro_tracker_follows_a_real_move_faster_than_the_old_smoothing():
    old = tilt.TiltTracker(axis="y", median_len=3)               # EMA 0.12
    new = tilt.TiltTracker(axis="y", median_len=3, euro=(0.5, 0.02))
    for tr in (old, new):
        tr.update(*gravity(0, 0), t=0.0)
    for i in range(1, 10):                                        # settle at 0
        for tr in (old, new):
            tr.update(*gravity(0, 0), t=i * 0.02)
    for i in range(10, 17):                                       # then a 20 degree move
        o = old.update(*gravity(0, 20), t=i * 0.02)
        n = new.update(*gravity(0, 20), t=i * 0.02)
    assert n > o + 3.0


def test_the_dead_band_ignores_a_tiny_change():
    t = tilt.TiltTracker(axis="y", alpha=1.0, median_len=1, band_deg=0.5)
    t.update(*gravity(0, 0))
    assert t.update(*gravity(0, 0.4)) == pytest.approx(0.0, abs=0.01)
    assert t.update(*gravity(0, 3.0)) == pytest.approx(2.5, abs=0.3)


def test_zero_still_works_with_the_euro_filter():
    t = tilt.TiltTracker(axis="y", median_len=1, euro=(0.5, 0.02))
    for i in range(30):
        t.update(*gravity(0, 10), t=i * 0.02)
    t.zero()
    assert t.update(*gravity(0, 10), t=30 * 0.02) == pytest.approx(0.0, abs=0.01)
