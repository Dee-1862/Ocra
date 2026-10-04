"""Two small filters for steering signals. Pure logic.

OneEuroFilter: a low-pass filter whose cutoff rises with speed, so a still hand
is smooth and a fast hand is not delayed. (Casiez, Roussel and Vogel, "1 euro
filter", CHI 2012: cited from memory, open the paper before citing it.)

Hysteresis: the output only moves once the input has moved more than `band`
away from it, which removes the last bit of flicker when the hand is still.
"""
from __future__ import annotations

import math


class OneEuroFilter:
    def __init__(self, min_cutoff: float = 0.5, beta: float = 0.02, d_cutoff: float = 1.0):
        """min_cutoff (Hz): smoothness at rest, lower = smoother but slower.
        beta: how quickly the cutoff opens as speed grows (degrees/second units).
        d_cutoff (Hz): smoothing applied to the speed estimate itself."""
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x = None
        self._dx = 0.0
        self._t = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, t: float, value: float) -> float:
        """Filter one sample taken at time t (seconds)."""
        if self._x is None:
            self._x, self._t = value, t
            return value
        dt = max(1e-3, t - self._t)
        self._t = t
        speed = (value - self._x) / dt
        self._dx += self._alpha(self.d_cutoff, dt) * (speed - self._dx)
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        self._x += self._alpha(cutoff, dt) * (value - self._x)
        return self._x


class Hysteresis:
    def __init__(self, band: float):
        self.band = band
        self._out = None

    def __call__(self, value: float) -> float:
        if self._out is None or self.band <= 0:
            self._out = value
        elif value - self._out > self.band:
            self._out = value - self.band
        elif self._out - value > self.band:
            self._out = value + self.band
        return self._out
