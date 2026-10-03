import pytest

from wilirehab import og_link, tilt


def raw_for_mg(mg: int) -> int:
    """The raw register value the LIS3DH would report for this many milli-g."""
    return (mg // 4) << 6


def plain_tracker(**kw):
    """No median, no smoothing: the angle is exactly what was fed in."""
    return tilt.TiltTracker(alpha=1.0, median_len=1, **kw)


def test_raw_to_mg_one_g():
    assert tilt.raw_to_mg(raw_for_mg(1000)) == 1000


def test_raw_to_mg_keeps_the_sign():
    assert tilt.raw_to_mg(raw_for_mg(-1000)) == -1000


def test_flat_is_zero_degrees():
    assert tilt.tilt_deg(0, 0, 1000) == pytest.approx(0.0)


def test_45_degrees():
    assert tilt.tilt_deg(0, 1000, 1000, axis="y") == pytest.approx(45.0)
    assert tilt.tilt_deg(1000, 0, 1000, axis="x") == pytest.approx(45.0)


def test_bad_axis_is_rejected():
    with pytest.raises(ValueError):
        tilt.tilt_deg(0, 0, 1000, axis="z")


def test_position_is_centred_and_clamped():
    assert tilt.to_position(0.0) == 0.5
    assert tilt.to_position(25.0) == 1.0
    assert tilt.to_position(-25.0) == 0.0
    assert tilt.to_position(90.0) == 1.0


def test_dead_zone_ignores_small_tilts():
    assert tilt.to_position(1.4) == 0.5
    assert tilt.to_position(-1.4) == 0.5
    assert tilt.to_position(3.0) > 0.5


def test_full_range_reaches_the_edges_exactly():
    assert tilt.to_position(10.0, left_deg=10.0, right_deg=10.0) == pytest.approx(1.0)
    assert tilt.to_position(-10.0, left_deg=10.0, right_deg=10.0) == pytest.approx(0.0)


def test_each_side_has_its_own_range():
    # Only 6 degrees of comfortable motion to the left, 15 to the right.
    assert tilt.to_position(-6.0, left_deg=6.0, right_deg=15.0) == pytest.approx(0.0)
    assert tilt.to_position(6.0, left_deg=6.0, right_deg=15.0) < 0.9


def test_position_never_jumps_past_the_dead_zone():
    just_out = tilt.to_position(1.6)
    assert 0.5 < just_out < 0.56


def test_tracker_first_sample_is_neutral():
    t = plain_tracker(axis="y")
    y, z = raw_for_mg(500), raw_for_mg(866)       # about 30 degrees off flat
    assert t.update(0, y, z) == pytest.approx(0.0)
    assert t.update(0, 0, raw_for_mg(1000)) == pytest.approx(-30.0, abs=1.5)


def test_tracker_zero_resets_neutral():
    t = plain_tracker()
    t.update(0, 0, raw_for_mg(1000))
    t.update(0, raw_for_mg(500), raw_for_mg(866))
    t.zero()
    assert t.update(0, raw_for_mg(500), raw_for_mg(866)) == pytest.approx(0.0)


def test_invert_flips_the_direction():
    a = plain_tracker()
    b = plain_tracker(invert=True)
    for t in (a, b):
        t.update(0, 0, raw_for_mg(1000))
    up = a.update(0, raw_for_mg(500), raw_for_mg(866))
    down = b.update(0, raw_for_mg(500), raw_for_mg(866))
    assert up == pytest.approx(-down)


def test_median_drops_a_single_spike():
    t = tilt.TiltTracker(alpha=1.0, median_len=5)
    flat = (0, 0, raw_for_mg(1000))
    for _ in range(4):
        t.update(*flat)
    spike = t.update(0, raw_for_mg(500), raw_for_mg(866))   # one 30 degree glitch
    assert abs(spike) < 1.0


def test_smoothing_calms_jitter():
    t = tilt.TiltTracker(alpha=0.12, median_len=1)
    t.update(0, 0, raw_for_mg(1000))
    wobble = []
    for i in range(40):
        y = raw_for_mg(100 if i % 2 else -100)              # about +-6 degrees flicker
        wobble.append(t.update(0, y, raw_for_mg(996)))
    assert max(abs(w) for w in wobble[-10:]) < 1.5


def test_shaky_samples_are_ignored():
    t = plain_tracker()
    t.update(0, 0, raw_for_mg(1000))
    held = t.update(0, raw_for_mg(900), raw_for_mg(1900))   # 2 g: shaking
    assert not t.steady
    assert held == pytest.approx(0.0)


def test_steady_flags_shaking():
    t = plain_tracker()
    t.update(0, 0, raw_for_mg(1000))
    assert t.steady
    t.update(0, 0, raw_for_mg(1900))
    assert not t.steady


def test_parse_button_down_only():
    assert og_link.parse_line("BTN green down") == ("press", "green")
    assert og_link.parse_line("BTN green up") is None
    assert og_link.parse_line("BTN purple down") is None


def test_parse_acc():
    assert og_link.parse_line("ACC 5 1234 10 -20 16000\r\n") == ("acc", (5, 1234, 10, -20, 16000))


def test_parse_ignores_noise():
    for line in ("", "OK", "OK pong", "ERR bad-row", "ACC 1 2 3", "ACC a b c d e"):
        assert og_link.parse_line(line) is None
