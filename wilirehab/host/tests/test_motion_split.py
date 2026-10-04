import math

import pytest

from wilirehab.motion_split import (describe_motion, estimate_tilt_mg, fit_sphere_offset,
                                    mag_turn_deg, split_accel_motion, tilt_induced_mg)


def sine(amp, n=100, freq=2.0, rate=50.0):
    return [amp * math.sin(2 * math.pi * freq * i / rate) for i in range(n)]


# ---- vertical against horizontal movement -----------------------------------

def test_a_vertical_slide_moves_along_gravity():
    accel = [(0.0, 0.0, 1000.0 + z) for z in sine(200)]
    v, h = split_accel_motion(accel)
    assert v == pytest.approx(200 / math.sqrt(2), rel=0.1)
    assert h < 5


def test_a_sideways_slide_moves_across_gravity():
    accel = [(x, 0.0, 1000.0) for x in sine(200)]
    v, h = split_accel_motion(accel)
    assert h == pytest.approx(200 / math.sqrt(2), rel=0.1)
    assert v < 15


def test_gravity_does_not_have_to_point_along_z():
    # the same vertical slide with the sensor lying on its side (gravity on x)
    accel = [(1000.0 + z, 0.0, 0.0) for z in sine(200)]
    v, h = split_accel_motion(accel)
    assert v > 100 and h < 5


def test_nothing_moving_reads_zero():
    assert split_accel_motion([(0.0, 0.0, 1000.0)] * 20) == (0.0, 0.0)
    assert split_accel_motion([]) == (0.0, 0.0)


# ---- how far the field direction turns --------------------------------------

def field(theta_deg, strength=30.0):
    t = math.radians(theta_deg)
    return (strength * math.cos(t), strength * math.sin(t), 0.0)


def test_turning_changes_the_field_direction():
    turning = [field(a) for a in (-20, -10, 0, 10, 20)]
    assert mag_turn_deg(turning) == pytest.approx(20.0, abs=1.0)


def test_sliding_does_not_change_the_field_direction():
    assert mag_turn_deg([field(0)] * 20) == pytest.approx(0.0, abs=1e-6)


def test_a_big_offset_hides_a_turn_until_it_is_removed():
    offset = (300.0, 0.0, 0.0)
    turning = [tuple(f + o for f, o in zip(field(a), offset)) for a in (-20, -10, 0, 10, 20)]
    assert mag_turn_deg(turning) < 4.0                      # looks almost still
    assert mag_turn_deg(turning, offset) == pytest.approx(20.0, abs=1.0)


# ---- finding the offset -------------------------------------------------------

def sphere_points(centre, radius, n=200):
    pts = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - y * y)
        theta = golden * i
        pts.append((centre[0] + radius * r * math.cos(theta),
                    centre[1] + radius * y,
                    centre[2] + radius * r * math.sin(theta)))
    return pts


def test_the_offset_and_field_strength_are_recovered():
    offset, radius, err = fit_sphere_offset(sphere_points((300, -50, 120), 40.0))
    assert offset == pytest.approx((300, -50, 120), abs=0.5)
    assert radius == pytest.approx(40.0, abs=0.5)
    assert err < 0.5


def test_a_little_noise_still_gives_a_good_fit():
    import random
    rng = random.Random(2)
    noisy = [tuple(c + rng.gauss(0, 0.5) for c in p) for p in sphere_points((280, 20, -90), 35.0)]
    offset, radius, err = fit_sphere_offset(noisy)
    assert offset == pytest.approx((280, 20, -90), abs=1.5)
    assert radius == pytest.approx(35.0, abs=1.5)


def test_too_few_readings_are_refused():
    with pytest.raises(ValueError):
        fit_sphere_offset(sphere_points((0, 0, 0), 30.0, n=10))


def test_readings_that_are_not_on_a_sphere_fit_badly():
    line = [(float(i), 0.0, 0.0) for i in range(50)]
    _offset, _radius, err = fit_sphere_offset(line)
    assert err > 1.0                       # the caller can see this is not a sphere


# ---- the phrase -------------------------------------------------------------

def test_plain_cases():
    assert describe_motion(5, 5) == "still"
    assert describe_motion(120, 20) == "sliding up/down"
    assert describe_motion(20, 120) == "sliding sideways"
    assert describe_motion(60, 60) == "sliding up/down"           # a tie goes to up/down
    assert describe_motion(5, 5, 0.0, turned=True) == "turning / tilting"


def test_a_turn_alone_is_not_called_a_slide():
    # rows from a recorded run where the board was only turned: sideways movement
    # and field change rising together, about 25 mg per uT
    for v, h, field in ((46, 89, 7.5), (58, 302, 12.0), (141, 398, 15.4)):
        tilt = estimate_tilt_mg(field_change_ut=field)
        assert describe_motion(v, h, tilt, turned=True) == "turning / tilting", (v, h, field)


def test_a_slide_with_little_turning_is_found():
    for v, h, field in ((31, 102, 2.4), (42, 88, 1.0)):
        tilt = estimate_tilt_mg(field_change_ut=field)
        assert describe_motion(v, h, tilt, turned=field >= 3.0) == "sliding sideways"


def test_an_up_down_slide_on_top_of_a_turn_is_found():
    assert describe_motion(250, 40, 100.0, turned=True) == "sliding up/down while turning"


def test_a_sideways_slide_on_top_of_a_turn_is_found():
    assert describe_motion(10, 700, 300.0, turned=True) == "sliding sideways while turning"


def test_the_tilt_estimate_from_the_field_change():
    assert estimate_tilt_mg(field_change_ut=10.0) == pytest.approx(250.0)       # 25 mg per uT
    assert estimate_tilt_mg(field_change_ut=10.0, field_strength_ut=50.0) == pytest.approx(200.0)
    assert estimate_tilt_mg() == 0.0


def test_the_angle_is_preferred_to_the_field_change_when_known():
    assert estimate_tilt_mg(turn_deg=14.0, field_change_ut=999.0) == pytest.approx(172.0, rel=0.05)
    assert tilt_induced_mg(14.0) == pytest.approx(172.0, rel=0.05)
