"""Read the magnetometer stream from the main CPU's USB serial port.

The orca main app prints `MAG seq t_ms x y z temp drdy` lines (raw counts).
Events go on the shared queue as ("mag", sample, role), where sample is the dict
from mag_accel.parse_mag_line, or ("status", text, role).
"""
from __future__ import annotations

import queue
import threading

from .mag_accel import parse_mag_line


class MagLink:
    def __init__(self, port: str, events: queue.Queue, role: str = "mag"):
        self.port = port
        self.events = events
        self.role = role
        self._stop = threading.Event()

    def _put(self, kind, value) -> None:
        self.events.put((kind, value, self.role))

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def close(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            import serial  # pyserial
            with serial.Serial(self.port, 115200, timeout=0.2) as ser:
                self._put("status", f"Reading the magnetometer on {self.port}")
                while not self._stop.is_set():
                    line = ser.readline().decode("ascii", "replace")
                    sample = parse_mag_line(line)
                    if sample:
                        self._put("mag", sample)
                    elif line.strip().startswith("[orca_main]"):
                        self._put("status", line.strip())     # scan and start-up messages
        except Exception as exc:                 # shown, not swallowed
            self._put("status", f"Magnetometer link stopped: {exc}")
