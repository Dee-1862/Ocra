"""Serial link to an OG display CPU.

Reads the lines the wilirehab display firmware prints and turns them into
events; can also send it commands. The parsing is a plain function so it is
tested without a board. One OgLink per OG; each tags its events with a role
(left_hand, right_hand) so two can share one queue.

Lines from the OG:
    BTN <colour> down|up
    ACC <seq> <t_ms> <x> <y> <z>        raw int16 from the accelerometer
    OK ... / ERR ...                     replies, ignored here
"""
from __future__ import annotations

import queue
import threading

from .button_map import BUTTONS


def parse_line(line: str):
    """One OG line -> ("press", colour) | ("release", colour) |
    ("acc", (seq, t_ms, x, y, z)) | None.

    "press" is the down edge of a button and "release" the up edge; the gap
    between them is how long the button was held.
    """
    parts = line.split()
    if len(parts) == 3 and parts[0] == "BTN" and parts[1] in BUTTONS:
        if parts[2] == "down":
            return ("press", parts[1])
        if parts[2] == "up":
            return ("release", parts[1])
    if len(parts) == 6 and parts[0] == "ACC":
        try:
            return ("acc", tuple(int(p) for p in parts[1:]))
        except ValueError:
            return None
    return None


class OgLink:
    """Background reader. Events go onto `events` as (kind, value, role):
    ("press", colour, role), ("release", colour, role),
    ("acc", (seq, t_ms, x, y, z), role),
    ("status", text, role)."""

    def __init__(self, port: str, events: queue.Queue, role: str = "hand",
                 on_connect=()):
        self.port = port
        self.events = events
        self.role = role
        self.on_connect = tuple(on_connect)   # command lines sent once connected
        self._ser = None
        self._stop = threading.Event()

    def _put(self, kind, value) -> None:
        self.events.put((kind, value, self.role))

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, line: str) -> None:
        ser = self._ser
        if ser is None:
            self._put("status", "Not connected yet; command not sent")
            return
        try:
            ser.write((line + "\n").encode("ascii"))
        except Exception as exc:
            self._put("status", f"Send failed: {exc}")

    def close(self) -> None:
        """Ask the OG to stop streaming, then stop the reader."""
        try:
            self.send("STREAM 0")
        finally:
            self._stop.set()

    def _run(self) -> None:
        try:
            import serial  # pyserial
            with serial.Serial(self.port, 115200, timeout=0.2) as ser:
                self._ser = ser
                self._put("status", f"Listening on {self.port}")
                for line in self.on_connect:
                    self.send(line)
                while not self._stop.is_set():
                    raw = ser.readline().decode("ascii", "replace")
                    ev = parse_line(raw)
                    if ev:
                        self._put(*ev)
        except Exception as exc:  # shown in the window, not swallowed
            self._put("status", f"Serial stopped: {exc}")
        finally:
            self._ser = None
