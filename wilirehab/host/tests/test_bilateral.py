import pytest

from wilirehab.bilateral import (LEFT, RIGHT, HandStats, format_row,
                                 symmetry_report)


def moving(angles, dt=0.02):
    """A HandStats fed a sequence of angles (relative and absolute the same)."""
    s = HandStats()
    for i, a in enumerate(angles):
        s.update(i * dt, a, a)
    return s


def test_range_is_max_minus_min():
    assert moving([0, 10, -5, 3]).range_deg == pytest.approx(15.0)


def test_empty_stats_have_zero_range():
    assert HandStats().range_deg == 0.0


def test_peak_speed():
    # 6 degrees in 20 ms = 300 deg/s, once.
    assert moving([0, 0, 6, 6, 6]).peak_dps == pytest.approx(300.0)


def test_glitch_jumps_are_not_peak_speed():
    s = moving([0, 0, 200, 200])             # 10000 deg/s: a glitch
    assert s.peak_dps == 0.0


def test_hit_rate():
    s = HandStats()
    assert s.hit_rate is None
    for hit in (True, True, False, True):
        s.attempt(hit)
    assert s.hit_rate == pytest.approx(0.75)


def test_report_needs_both_hands_with_data():
    assert symmetry_report({LEFT: moving([0, 5])}) is None
    assert symmetry_report({LEFT: moving([0, 5]), RIGHT: HandStats()}) is None


def test_report_ratios_and_weaker_side():
    left = moving([0, 20])        # range 20
    right = moving([0, 40])       # range 40
    rows = {r.name: r for r in symmetry_report({LEFT: left, RIGHT: right})}
    rng = rows["Roll range"]
    assert rng.ratio == pytest.approx(0.5)
    assert rng.weaker == "left"


def test_equal_sides():
    both = {LEFT: moving([0, 10]), RIGHT: moving([0, 10])}
    rng = {r.name: r for r in symmetry_report(both)}["Roll range"]
    assert rng.ratio == pytest.approx(1.0)
    assert rng.weaker == "equal"


def test_hit_rate_row_is_blank_without_attempts():
    both = {LEFT: moving([0, 10]), RIGHT: moving([0, 10])}
    row = {r.name: r for r in symmetry_report(both)}["Hit rate %"]
    assert row.ratio is None and row.weaker == ""


def test_hit_rate_row_compares_hands():
    left, right = moving([0, 10]), moving([0, 10])
    for hit in (True, True, False, False):
        left.attempt(hit)
    for hit in (True, True, True, False):
        right.attempt(hit)
    row = {r.name: r for r in symmetry_report({LEFT: left, RIGHT: right})}["Hit rate %"]
    assert row.left == pytest.approx(50.0) and row.right == pytest.approx(75.0)
    assert row.ratio == pytest.approx(2 / 3)
    assert row.weaker == "left"


def test_format_row_shows_numbers_and_the_weaker_side():
    left, right = moving([0, 20]), moving([0, 40])
    row = symmetry_report({LEFT: left, RIGHT: right})[0]
    text = format_row(row)
    assert "20" in text and "40" in text and "0.50" in text and "left weaker" in text


def moving2(roll, pitch, dt=0.02):
    s = HandStats()
    for i, (r, p) in enumerate(zip(roll, pitch)):
        s.update(i * dt, r, r, p, p)
    return s


def test_pitch_range_is_tracked_separately():
    s = moving2([0, 0, 0], [0, 12, -3])
    assert s.range_deg == 0.0
    assert s.pitch_range_deg == pytest.approx(15.0)
    assert s.has_pitch


def test_without_pitch_there_is_no_pitch_range():
    assert not moving([0, 5]).has_pitch


def test_peak_speed_takes_the_faster_axis():
    s = moving2([0, 0, 0], [0, 0, 6])          # only pitch moves, 300 deg/s
    assert s.peak_dps == pytest.approx(300.0)


def test_report_includes_pitch_when_both_hands_have_it():
    left, right = moving2([0, 5], [0, 10]), moving2([0, 5], [0, 20])
    names = [r.name for r in symmetry_report({LEFT: left, RIGHT: right})]
    assert names == ["Roll range", "Pitch range", "Peak deg/s", "Hit rate %"]


def test_report_omits_pitch_when_a_hand_lacks_it():
    names = [r.name for r in symmetry_report({LEFT: moving2([0, 5], [0, 10]),
                                              RIGHT: moving([0, 5])})]
    assert "Pitch range" not in names
