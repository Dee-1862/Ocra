import math
from types import SimpleNamespace

import pytest

from wilirehab import devices
from wilirehab.mag_accel import (PHASES, UT_PER_LSB_XY, UT_PER_LSB_Z, body_vectors,
                                 classify, norm, parse_mag_line, raw_temp_to_c,
                                 raw_to_ut, simulate_phase, summarize,
                                 vector_change_rms)


# ---- the line from the firmware and the unit conversion ---------------------

def test_a_good_mag_line_is_parsed():
    s = parse_mag_line("MAG 7 1500 1000 -2000 3000 80000 1\r\n")
    assert s["seq"] == 7 and s["t_ms"] == 1500
    assert s["raw"] == (1000, -2000, 3000)
    assert s["raw_temp"] == 80000 and s["drdy"] == 1


def test_other_lines_are_not_mag_lines():
    assert parse_mag_line("") is None
    assert parse_mag_line("ACC 1 2 3 4 5") is None
    assert parse_mag_line("[wilirehab_main] I2C0 devices (1): 0x14") is None
    assert parse_mag_line("MAG 1 2 3") is None
    assert parse_mag_line("MAG a b c d e f g") is None


def test_raw_counts_convert_with_boschs_default_coefficients():
    x, y, z = raw_to_ut(1000, -1000, 1000)
    assert x == pytest.approx(1000 * UT_PER_LSB_XY) and y == pytest.approx(-1000 * UT_PER_LSB_XY)
    assert z == pytest.approx(1000 * UT_PER_LSB_Z)
    assert 7.0 < x < 7.2                       # about 0.00707 uT per count


def test_temperature_conversion_is_sensible_for_a_room():
    # about 25 C is raw 0 plus the offset: raw = (25 + 25.49) / 0.00098129
    raw = round((25.0 + 25.49) / 0.00098129)
    assert raw_temp_to_c(raw) == pytest.approx(25.0, abs=0.1)


# ---- the maths ---------------------------------------------------------------

def test_a_flat_sensor_reads_one_g_on_z_and_the_field_on_x_when_facing_north():
    a, m = body_vectors(0.0, 0.0, 0.0)
    assert a == pytest.approx((0.0, 0.0, 1000.0), abs=1e-6)
    assert m == pytest.approx((20.0, 0.0, -45.0), abs=1e-6)


def test_attitude_changes_keep_both_strengths():
    for h, p, r in ((10, 0, 0), (200, 25, -30), (300, -40, 55)):
        a, m = body_vectors(h, p, r)
        assert norm(a) == pytest.approx(1000.0, abs=1e-6)
        assert norm(m) == pytest.approx(math.hypot(20.0, 45.0), abs=1e-6)


def test_a_constant_stream_has_no_change():
    assert vector_change_rms([(1, 2, 3)] * 10) == 0.0
    assert vector_change_rms([]) == 0.0


def test_vector_change_is_the_rms_about_the_mean():
    assert vector_change_rms([(1, 0, 0), (-1, 0, 0)]) == pytest.approx(1.0)


def test_summary_of_nothing_says_so():
    assert summarize([]) == {"n": 0}
    assert classify({"n": 0}) == "no data"


# ---- the fingerprints ------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_simulated_action_looks_the_way_it_should(seed):
    for name, _text, seconds, expected in PHASES:
        summary = summarize(simulate_phase(name, seconds, seed=seed))
        assert classify(summary) == expected, (name, summary)


def test_spinning_flat_moves_only_the_magnetometer():
    s = summarize(simulate_phase("spin"))
    assert s["accel_change_mg"] < 30 and s["mag_change_ut"] > 8
    assert s["mag_strength_change_pct"] < 10         # direction changes, strength does not


def test_shaking_moves_only_the_accelerometer():
    s = summarize(simulate_phase("shake"))
    assert s["accel_change_mg"] > 150 and s["mag_change_ut"] < 2


def test_tilting_moves_both():
    s = summarize(simulate_phase("tilt"))
    assert s["accel_change_mg"] > 150 and s["mag_change_ut"] > 8


def test_a_magnet_changes_the_field_strength_and_not_gravity():
    s = summarize(simulate_phase("magnet"))
    assert s["mag_strength_change_pct"] > 25 and s["accel_change_mg"] < 30


# ---- finding the magnetometer's USB port ---------------------------------------

def port(device, serial, pid, vid=0x093C):
    return SimpleNamespace(device=device, serial_number=serial, vid=vid, pid=pid)


def test_the_main_cpu_is_found_by_its_product_id():
    ports = [port("COM4", "MAIN1", 0x2054), port("COM5", "DISP1", 0x2055),
             port("COM6", "FTDI", 0x6014, vid=0x0403)]
    assert devices.find_og_mains(ports) == [("COM4", "MAIN1")]
