import csv

import pytest

from wilirehab.datatable import DataTable, format_fields


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_time_starts_at_zero_and_follows_the_clock():
    c = Clock()
    table = DataTable(clock=c)
    c.t += 2.5
    assert table.add("og", "button", color="green")["t"] == pytest.approx(2.5)


def test_latest_keeps_the_newest_row_per_channel():
    c = Clock()
    table = DataTable(clock=c)
    table.add("og", "acc", x_mg=1)
    c.t += 1
    table.add("og", "acc", x_mg=2)
    table.add("game", "hit", n=1)
    assert table.latest[("og", "acc", None)]["fields"]["x_mg"] == 2
    assert set(table.latest) == {("og", "acc", None), ("game", "hit", None)}


def test_fast_channels_are_slowed_in_the_timeline_only():
    c = Clock()
    table = DataTable(clock=c)
    for _ in range(50):                  # 50 samples in half a second
        table.add("og", "acc", x_mg=0)
        c.t += 0.01
    shown = table.drain_ui()
    assert 1 <= len(shown) <= 3          # 0.25 s spacing
    assert table.latest[("og", "acc", None)]["t"] > 0.4   # but the latest is current


def test_events_are_never_slowed():
    table = DataTable(clock=Clock())
    for i in range(5):
        table.add("game", "hit", n=i)
    assert len(table.drain_ui()) == 5


def test_drain_empties_the_queue():
    table = DataTable(clock=Clock())
    table.add("game", "hit", n=1)
    assert len(table.drain_ui()) == 1
    assert table.drain_ui() == []


def test_csv_gets_every_row_at_full_rate(tmp_path):
    c = Clock()
    path = tmp_path / "data.csv"
    table = DataTable(path, clock=c)
    for i in range(20):
        table.add("og", "acc", device_ms=1000 + i, x_mg=i)
        c.t += 0.01
    table.close()
    rows = list(csv.reader(open(path, encoding="utf-8")))
    assert rows[0] == ["t_s", "role", "source", "channel", "dev_ms", "fields"]
    assert len(rows) == 21
    assert rows[1][4] == "1000"


def test_only_numbers_and_short_text_are_stored():
    table = DataTable(clock=Clock())
    with pytest.raises(TypeError):
        table.add("cam", "frame", pixels=[1, 2, 3])
    with pytest.raises(TypeError):
        table.add("cam", "note", text="x" * 65)


def test_format_fields():
    assert format_fields({"x": 120, "deg": 3.14159, "ok": True}) == "x=120 deg=3.1 ok=yes"


def test_each_role_has_its_own_latest_row():
    table = DataTable(clock=Clock())
    table.add("og", "acc", role="left_hand", x_mg=1)
    table.add("og", "acc", role="right_hand", x_mg=2)
    assert table.latest[("og", "acc", "left_hand")]["fields"]["x_mg"] == 1
    assert table.latest[("og", "acc", "right_hand")]["fields"]["x_mg"] == 2


def test_slowing_the_timeline_is_per_role():
    table = DataTable(clock=Clock())
    table.add("og", "acc", role="left_hand", x_mg=1)
    table.add("og", "acc", role="right_hand", x_mg=2)     # same instant, other hand
    assert len(table.drain_ui()) == 2


def test_role_is_written_to_the_csv(tmp_path):
    path = tmp_path / "data.csv"
    table = DataTable(path, clock=Clock())
    table.add("og", "button", role="left_hand", color="green")
    table.add("keyboard", "button", color="green")
    table.close()
    rows = list(csv.reader(open(path, encoding="utf-8")))
    assert rows[1][1] == "left_hand"
    assert rows[2][1] == ""
