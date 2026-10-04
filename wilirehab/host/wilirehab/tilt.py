"""Turn raw OG accelerometer samples into a steady tilt angle for steering.

The OG's LIS3DH reports raw 16-bit values, left-justified, 10-bit normal mode,
+-2 g: shift right by 6, then 4 mg per digit (see bsp/display_cpu/sensors/
lis3dh.h, lis3dh_raw_to_mg). Conversion is here, not in firmware, so a mistake
cannot be baked into the OG.

One accelerometer gives tilt against gravity, not a joint angle, and no yaw.
Tilt is atan2(sideways axis, z): which sideways axis ("x" or "y") depends on
how the OG sits on the hand, so it is a setting, not a guess.

Steadying, in the order it is applied:
  1. median of the last few angles   removes single-sample spikes
  2. exponential smoothing           removes small wobble
  3. hold while shaky                total acceleration far from 1 g means the
                                     angle is unreliable, so keep the last one
  4. dead zone (in to_position)      tiny tilts around neutral do nothing
"""
from __future__ import annotations

import math
from collections import deque
from statistics import median

from .smoothing import Hysteresis, OneEuroFilter

MG_PER_DIGIT = 4        # +-2 g, normal mode
RAW_SHIFT = 6

DEFAULT_RANGE_DEG = 12.0
DEFAULT_DEADBAND_DEG = 1.5


def raw_to_mg(raw: int) -> int:
    """Raw left-justified register value -> milli-g (arithmetic shift keeps the sign)."""
    return (raw >> RAW_SHIFT) * MG_PER_DIGIT


def magnitude_mg(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def tilt_deg(x_mg: float, y_mg: float, z_mg: float, axis: str = "y") -> float:
    """Elevation in degrees of the chosen OG axis above the horizontal.

    This is asin(axis reading / total), not atan2(axis, z). The difference
    matters when the OG is also tilted the other way: atan2 divides by z, which
    shrinks as the OG rolls, so rolling it leaked into the pitch reading by up
    to about 5 degrees in recorded sessions. The elevation of an axis does not
    change when the OG turns about that same axis, so roll and pitch no longer
    disturb each other. For a tilt about one axis only the two formulas agree.
    """
    if axis not in ("x", "y"):
        raise ValueError("axis must be 'x' or 'y'")
    side = x_mg if axis == "x" else y_mg
    total = math.sqrt(x_mg * x_mg + y_mg * y_mg + z_mg * z_mg)
    if total < 1e-6:
        return 0.0
    return math.degrees(math.asin(max(-1.0, min(1.0, side / total))))


def to_position(angle_deg: float, left_deg: float = DEFAULT_RANGE_DEG,
                right_deg: float = DEFAULT_RANGE_DEG,
                deadband_deg: float = DEFAULT_DEADBAND_DEG) -> float:
    """Angle relative to neutral -> 0..1 (0.5 is neutral).

    Tilts inside the dead zone map to exactly 0.5. Beyond it the angle ramps
    linearly so that -left_deg reaches 0 and +right_deg reaches 1; the two
    sides are separate because a person's range is often lopsided.
    """
    a = angle_deg
    if abs(a) <= deadband_deg:
        a = 0.0
    else:
        a -= math.copysign(deadband_deg, a)
    if a >= 0:
        frac = a / max(right_deg - deadband_deg, 1e-6)
    else:
        frac = a / max(left_deg - deadband_deg, 1e-6)
    return max(0.0, min(1.0, 0.5 + 0.5 * frac))


class TiltTracker:
    """Filters the angle and remembers what 'neutral' is.

    The first sample after construction or `zero()` becomes neutral, so the
    player holds a comfortable pose and the game centres on it.
    """

    def __init__(self, axis: str = "y", invert: bool = False,
                 alpha: float = 0.12, median_len: int = 5,
                 hold_shaky: bool = True, euro=None, band_deg: float = 0.0):
        """euro=(min_cutoff_hz, beta) replaces the fixed smoothing (alpha) with a
        1-euro filter: just as calm at rest, but about a third of the delay.
        band_deg adds a dead band: the output ignores moves smaller than that."""
        # hold_shaky=False is for flick detection, where fast motion is the
        # signal and must not be ignored.
        self.hold_shaky = hold_shaky
        self.axis = axis
        self.sign = -1.0 if invert else 1.0
        self.alpha = alpha
        self._recent = deque(maxlen=max(1, median_len))
        self._euro = OneEuroFilter(*euro) if euro else None
        self._band = Hysteresis(band_deg)
        self._auto_t = 0.0
        self._smooth = None
        self._zero = None
        self._want_zero = True
        self.last_magnitude_mg = 0.0

    def zero(self) -> None:
        """Make the next steady sample the neutral pose."""
        self._want_zero = True

    @property
    def absolute(self):
        """The filtered angle without the neutral subtracted (None before the first
        sample). Speed is measured on this so pressing 'zero' cannot fake a spike."""
        return self._smooth

    @property
    def steady(self) -> bool:
        """True when the total acceleration is close to 1 g, i.e. mostly gravity.
        Large departures mean shaking or a bad read, and the angle is then unreliable."""
        return 700.0 <= self.last_magnitude_mg <= 1300.0

    def update(self, raw_x: int, raw_y: int, raw_z: int, t=None) -> float:
        """Feed one raw sample; returns the filtered angle relative to neutral.

        `t` is the sample time in seconds (the OG's own clock is best); the
        1-euro filter needs it. Without it, 50 samples a second is assumed."""
        x, y, z = raw_to_mg(raw_x), raw_to_mg(raw_y), raw_to_mg(raw_z)
        self.last_magnitude_mg = magnitude_mg(x, y, z)
        self._auto_t += 0.02
        when = self._auto_t if t is None else t

        if self._smooth is None or self.steady or not self.hold_shaky:
            self._recent.append(self.sign * tilt_deg(x, y, z, self.axis))
            target = median(self._recent)
            if self._euro is not None:
                self._smooth = self._euro(when, target)
            else:
                self._smooth = target if self._smooth is None else (
                    self._smooth + self.alpha * (target - self._smooth))
        # else: shaky, hold the previous value.

        shown = self._band(self._smooth)
        if self._want_zero:
            self._zero = shown
            self._want_zero = False
        return shown - self._zero
