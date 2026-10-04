"""Per-hand measures and the left/right symmetry readout.

Pure logic. Each OG feeds one HandStats; `symmetry_report` compares the two.
The measures are crude (tilt from one accelerometer, no gyroscope), so they are
for comparing a person's own two sides within a session, not clinical values.
"""
from __future__ import annotations

from dataclasses import dataclass

LEFT, RIGHT = "left_hand", "right_hand"
MAX_PLAUSIBLE_DPS = 2000.0     # a larger jump is a glitch, not motion
MIN_DT_S = 0.005


class HandStats:
    def __init__(self):
        self.samples = 0
        self.min_deg = None
        self.max_deg = None
        self.pmin_deg = None        # pitch (forward/back tilt) range
        self.pmax_deg = None
        self.peak_dps = 0.0
        self.hits = 0
        self.attempts = 0
        self._prev = None
        self._prev_pitch = None

    def update(self, t_s: float, slow_deg: float, fast_abs_deg,
               slow_pitch=None, fast_pitch_abs=None) -> None:
        """slow_deg: steady roll angle relative to neutral (for range).
        fast_abs_deg: lightly filtered absolute roll angle (for speed), or None.
        slow_pitch / fast_pitch_abs: the same for pitch, if available.
        Peak speed is the larger of the roll and pitch speeds."""
        self.samples += 1
        self.min_deg = slow_deg if self.min_deg is None else min(self.min_deg, slow_deg)
        self.max_deg = slow_deg if self.max_deg is None else max(self.max_deg, slow_deg)
        if slow_pitch is not None:
            self.pmin_deg = slow_pitch if self.pmin_deg is None else min(self.pmin_deg, slow_pitch)
            self.pmax_deg = slow_pitch if self.pmax_deg is None else max(self.pmax_deg, slow_pitch)
        self._prev = self._speed(t_s, fast_abs_deg, self._prev)
        self._prev_pitch = self._speed(t_s, fast_pitch_abs, self._prev_pitch)

    def _speed(self, t_s, angle, prev):
        """Update the peak speed from one axis; returns the new 'previous'."""
        if angle is None:
            return prev
        if prev is not None:
            dt = t_s - prev[0]
            if dt >= MIN_DT_S:
                dps = abs(angle - prev[1]) / dt
                if dps <= MAX_PLAUSIBLE_DPS:
                    self.peak_dps = max(self.peak_dps, dps)
        return (t_s, angle)

    def attempt(self, hit: bool) -> None:
        self.attempts += 1
        if hit:
            self.hits += 1

    @property
    def range_deg(self) -> float:
        return 0.0 if self.min_deg is None else self.max_deg - self.min_deg

    @property
    def pitch_range_deg(self) -> float:
        return 0.0 if self.pmin_deg is None else self.pmax_deg - self.pmin_deg

    @property
    def has_pitch(self) -> bool:
        return self.pmin_deg is not None

    @property
    def hit_rate(self):
        return None if self.attempts == 0 else self.hits / self.attempts


@dataclass(frozen=True)
class SymRow:
    name: str
    left: object        # number or None
    right: object
    ratio: object       # weaker / stronger, 0..1, or None
    weaker: str         # "left", "right", "equal" or ""


def _row(name, left, right) -> SymRow:
    if left is None or right is None:
        return SymRow(name, left, right, None, "")
    hi, lo = max(left, right), min(left, right)
    ratio = (lo / hi) if hi > 0 else None
    weaker = "equal" if left == right else ("left" if left < right else "right")
    return SymRow(name, left, right, ratio, weaker)


def symmetry_report(stats: dict):
    """Rows comparing the two hands, or None unless both have data."""
    left, right = stats.get(LEFT), stats.get(RIGHT)
    if left is None or right is None or left.samples == 0 or right.samples == 0:
        return None
    pct = lambda v: None if v is None else v * 100.0
    rows = [_row("Roll range", left.range_deg, right.range_deg)]
    if left.has_pitch and right.has_pitch:
        rows.append(_row("Pitch range", left.pitch_range_deg, right.pitch_range_deg))
    rows.append(_row("Peak deg/s", left.peak_dps, right.peak_dps))
    rows.append(_row("Hit rate %", pct(left.hit_rate), pct(right.hit_rate)))
    return rows


def format_row(row: SymRow) -> str:
    def num(v):
        return "-" if v is None else f"{v:.0f}"
    ratio = "-" if row.ratio is None else f"{row.ratio:.2f}"
    weak = f"{row.weaker} weaker" if row.weaker in ("left", "right") else ""
    return f"{row.name:<11}{num(row.left):>6}{num(row.right):>6}{ratio:>6}  {weak}"
