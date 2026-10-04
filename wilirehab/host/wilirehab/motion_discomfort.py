"""Hand-motion measures for the discomfort table: jerk and range of motion.

Jerk is the time derivative of acceleration. Range of motion (RoM) is the
angular spread of the tilt angles over a rolling window, compared with the
same player's own earlier spread. Both are computed from the OG's own
accelerometer samples and its own clock.

What the evidence does and does not say (see notebook/face-signals.md):

- Movement during pain is not one-directional. In the EmoPain data, people
  with chronic low back pain at a high pain level moved the head and trunk
  more slowly and through a smaller range; in experimentally induced pain
  (BioVid, BP4D) head-movement speed was higher in people in pain. So a jerk
  spike or a shrunken range is a prompt to look, never a pain score.
- The OG's accelerometer reads +-2 g in 4 mg steps at about 50 Hz. A single
  step is 0.039 m/s^2, and differencing two samples 20 ms apart turns that
  into about 2 m/s^3 of pure quantisation. Smoothing over a few samples
  lowers it, but jerk below a few m/s^3 is noise.
- The sensor measures gravity as well as motion, so turning the wrist changes
  the reading even when the hand does not accelerate.
- "Baseline RoM" is the median spread over the first stretch of play, so it
  assumes the player moved normally then. The window and baseline lengths are
  placeholders.
"""
from __future__ import annotations

import math
from collections import deque
from statistics import median

G = 9.80665
MG_TO_MS2 = G / 1000.0


class JerkMeter:
    """Jerk magnitude, in m/s^3, of the 3-axis acceleration vector."""

    def __init__(self, smooth_n: int = 5, window_s: float = 1.0):
        self._recent = deque(maxlen=max(1, smooth_n))
        self._prev = None
        self._window: deque = deque()
        self.window_s = window_s

    def add(self, t_s: float, x_mg: float, y_mg: float, z_mg: float):
        """One sample (seconds on the device clock, then milli-g). Returns the jerk or None."""
        self._recent.append((x_mg * MG_TO_MS2, y_mg * MG_TO_MS2, z_mg * MG_TO_MS2))
        if len(self._recent) < self._recent.maxlen:
            return None
        n = len(self._recent)
        smooth = tuple(sum(a[i] for a in self._recent) / n for i in range(3))
        prev, self._prev = self._prev, (t_s, smooth)
        if prev is None:
            return None
        dt = t_s - prev[0]
        if dt <= 0:
            return None
        jerk = math.dist(smooth, prev[1]) / dt
        self._window.append((t_s, jerk))
        while self._window and t_s - self._window[0][0] > self.window_s:
            self._window.popleft()
        return jerk

    def peak(self):
        return max((j for _, j in self._window), default=None)

    def mean(self):
        if not self._window:
            return None
        return sum(j for _, j in self._window) / len(self._window)


class RomWindow:
    """Roll and pitch spread (max minus min, degrees) over a rolling window."""

    def __init__(self, window_s: float = 10.0, min_span_s: float = 8.0):
        self.window_s = window_s
        self.min_span_s = min_span_s
        self._points: deque = deque()

    def add(self, t_s: float, roll_deg: float, pitch_deg: float) -> None:
        self._points.append((t_s, roll_deg, pitch_deg))
        while self._points and t_s - self._points[0][0] > self.window_s:
            self._points.popleft()

    def ranges(self):
        """(roll_rom, pitch_rom), or None until the window has `min_span_s` of data."""
        if len(self._points) < 2 or self._points[-1][0] - self._points[0][0] < self.min_span_s:
            return None
        rolls = [p[1] for p in self._points]
        pitches = [p[2] for p in self._points]
        return max(rolls) - min(rolls), max(pitches) - min(pitches)


class RomBaseline:
    """The player's own RoM: the median of the spreads seen over the first `seconds`."""

    def __init__(self, seconds: float = 30.0):
        self.seconds = seconds
        self._start = None
        self._samples: list = []
        self.value = None

    def add(self, t_s: float, rom: float) -> None:
        if self.value is not None:
            return
        if self._start is None:
            self._start = t_s
        self._samples.append(rom)
        if t_s - self._start >= self.seconds and len(self._samples) >= 5:
            self.value = median(self._samples)

    def ratio(self, rom: float):
        """`rom` over the baseline; below 1 is a narrower range than usual. None if unset."""
        if self.value is None or self.value <= 0:
            return None
        return rom / self.value


class HandMonitor:
    """One row per `report_s`: jerk, RoM, and the RoM ratio against baseline."""

    def __init__(self, report_s: float = 1.0, rom_window_s: float = 10.0,
                 baseline_s: float = 30.0):
        self.report_s = report_s
        self.jerk = JerkMeter()
        self.rom = RomWindow(window_s=rom_window_s)
        self.baseline = RomBaseline(baseline_s)
        self._next = None

    def add(self, t_s: float, x_mg: float, y_mg: float, z_mg: float,
            roll_deg: float, pitch_deg: float):
        """Feed one accelerometer sample; returns a row dict once per report interval."""
        self.jerk.add(t_s, x_mg, y_mg, z_mg)
        self.rom.add(t_s, roll_deg, pitch_deg)
        if self._next is None:
            self._next = t_s + self.report_s
            return None
        if t_s < self._next:
            return None
        self._next = t_s + self.report_s
        ranges = self.rom.ranges()
        roll_rom = pitch_rom = rom = ratio = None
        if ranges is not None:
            roll_rom, pitch_rom = ranges
            rom = max(roll_rom, pitch_rom)
            self.baseline.add(t_s, rom)
            ratio = self.baseline.ratio(rom)
        return {
            "jerk_peak": _r(self.jerk.peak(), 1),
            "jerk_mean": _r(self.jerk.mean(), 1),
            "roll_rom": _r(roll_rom, 1),
            "pitch_rom": _r(pitch_rom, 1),
            "rom": _r(rom, 1),
            "rom_base": _r(self.baseline.value, 1),
            "rom_ratio": _r(ratio, 2),
            "roll": round(roll_deg, 1),
            "pitch": round(pitch_deg, 1),
        }


def _r(value, digits):
    return None if value is None else round(value, digits)
