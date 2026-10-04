import json
from types import SimpleNamespace

import pytest

from wilirehab import devices


def port(device, serial, vid=0x093C, pid=0x2055):
    return SimpleNamespace(device=device, serial_number=serial, vid=vid, pid=pid)


def test_only_og_display_cpus_are_found():
    ports = [
        port("COM4", "MAIN1", pid=0x2054),        # main CPU: not the display
        port("COM5", "DISP1"),
        port("COM6", "FTDI", vid=0x0403, pid=0x6014),
        port("COM7", "DISP2"),
        port("COM8", None),                       # no serial number: cannot be identified
    ]
    assert devices.find_og_displays(ports) == [("COM5", "DISP1"), ("COM7", "DISP2")]


def test_assign_by_serial_not_by_port_number():
    mapping = {"left_hand": "DISP2", "right_hand": "DISP1"}
    found = [("COM5", "DISP1"), ("COM9", "DISP2")]
    ports, problems = devices.assign_roles(mapping, found)
    assert ports == {"left_hand": "COM9", "right_hand": "COM5"}
    assert problems == []


def test_a_missing_og_is_a_problem_not_a_crash():
    mapping = {"left_hand": "DISP2", "right_hand": "DISP1"}
    ports, problems = devices.assign_roles(mapping, [("COM5", "DISP1")])
    assert ports == {"right_hand": "COM5"}
    assert len(problems) == 1 and "left_hand" in problems[0]


def test_an_unassigned_og_is_reported():
    ports, problems = devices.assign_roles({"right_hand": "DISP1"},
                                           [("COM5", "DISP1"), ("COM6", "NEW")])
    assert ports == {"right_hand": "COM5"}
    assert any("COM6" in p and "--setup" in p for p in problems)


def test_config_round_trip(tmp_path):
    path = tmp_path / "devices.json"
    devices.save_config(path, {"left_hand": "A", "right_hand": "B"})
    assert devices.load_config(path) == {"left_hand": "A", "right_hand": "B"}


def test_missing_config_is_empty(tmp_path):
    assert devices.load_config(tmp_path / "nope.json") == {}


def test_bad_configs_are_rejected(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"middle_hand": "A"}))
    with pytest.raises(ValueError):
        devices.load_config(path)
    path.write_text(json.dumps({"left_hand": "A", "right_hand": "A"}))
    with pytest.raises(ValueError):
        devices.load_config(path)
    path.write_text(json.dumps({"left_hand": ""}))
    with pytest.raises(ValueError):
        devices.load_config(path)


def test_press_detection_in_a_byte_stream():
    assert devices.press_in(b"OK pong\r\nBTN green down\r\n")
    assert not devices.press_in(b"BTN green up\r\n")
    assert not devices.press_in(b"ACC 1 2 3 4 5\r\n")
    assert not devices.press_in(b"")
