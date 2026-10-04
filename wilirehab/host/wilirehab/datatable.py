"""One timestamped table for everything: OG readings, buttons, game events.

Any source adds rows with `add(source, channel, ...)`. Nothing here knows about
the OG, so a forearm accelerometer, an IMU or a force sensor can be added later
by calling the same function with its own source name.

Three views of the same data:
  - every row goes to a CSV file at full rate (for analysis);
  - `latest` holds the newest row per (source, channel, role) (the live panel);
  - `drain_ui()` hands the window a slowed-down stream of rows (the timeline),
    because a 50 Hz accelerometer would otherwise scroll too fast to read.

Numbers only, like the session log: fields may be numbers, booleans or short
strings, never frames or arrays.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

MAX_STR = 64

# Minimum seconds between timeline rows, per (source, channel). The CSV and the
# live panel are never slowed down. Anything not listed shows every row.
DEFAULT_TIMELINE_INTERVAL = {
    ("og", "acc"): 0.25,
    ("og", "tilt"): 0.25,
    ("og", "flick_angles"): 0.25,
}


def check_fields(fields: dict) -> None:
    for k, v in fields.items():
        if v is None or isinstance(v, (bool, int, float)):
            continue
        if isinstance(v, str) and len(v) <= MAX_STR:
            continue
        raise TypeError(f"data field {k!r}: only numbers and short strings are "
                        f"stored, got {type(v).__name__}")


def format_fields(fields: dict) -> str:
    """'x_mg=120 y_mg=-64' style text for the table."""
    parts = []
    for k, v in fields.items():
        if isinstance(v, bool):
            v = "yes" if v else "no"
        elif isinstance(v, float):
            v = f"{v:.1f}"
        parts.append(f"{k}={v}")
    return " ".join(parts)


class DataTable:
    def __init__(self, csv_path=None, clock=time.monotonic, timeline_interval=None):
        self._clock = clock
        self._t0 = clock()
        self._interval = dict(DEFAULT_TIMELINE_INTERVAL if timeline_interval is None
                              else timeline_interval)
        self._last_shown: dict = {}
        self._ui: list = []
        self.latest: dict = {}
        self._listeners: list = []
        self._file = None
        self._csv = None
        self._last_flush = 0.0
        if csv_path:
            path = Path(csv_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "w", newline="", encoding="utf-8")
            self._csv = csv.writer(self._file)
            self._csv.writerow(["t_s", "role", "source", "channel", "dev_ms", "fields"])

    def now(self) -> float:
        """Seconds since this table was created (the 'time' column)."""
        return self._clock() - self._t0

    def from_clock(self, clock_value: float) -> float:
        """A reading of this table's clock (time.monotonic by default) as a 'time' value.

        A background thread, such as the face camera, stamps its rows with
        the clock when it captures them; the window thread adds them later.
        This puts the capture time, not the arrival time, in the table."""
        return clock_value - self._t0

    def subscribe(self, callback) -> None:
        """Call `callback(row)` for every row added from now on, on the adding thread."""
        self._listeners.append(callback)

    def add(self, source: str, channel: str, device_ms=None, role=None, at=None,
            **fields) -> dict:
        """Record one row. `device_ms` is the sensor's own clock, if it has one.
        `role` says which device it came from (left_hand, right_hand, ...).
        `at` is the capture time in table seconds (see from_clock); omitted, it is now."""
        check_fields(fields)
        t = self.now() if at is None else at
        row = {"t": t, "role": role, "source": source, "channel": channel,
               "device_ms": device_ms, "fields": fields,
               "text": format_fields(fields)}
        key = (source, channel)
        self.latest[(source, channel, role)] = row
        if self._csv:
            self._csv.writerow([f"{t:.3f}", role or "", source, channel,
                                "" if device_ms is None else device_ms,
                                json.dumps(fields, separators=(",", ":"))])
            if t - self._last_flush >= 1.0:      # so the file can be opened mid-session
                self._file.flush()
                self._last_flush = t
        gap = self._interval.get(key, 0.0)
        shown_key = (source, channel, role)
        if t - self._last_shown.get(shown_key, -1e9) >= gap:
            self._last_shown[shown_key] = t
            self._ui.append(row)
        for callback in self._listeners:
            callback(row)
        return row

    def drain_ui(self) -> list:
        """Rows that are new for the timeline since the last call."""
        rows, self._ui = self._ui, []
        return rows

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
