"""Learn how far a person can tilt, and map that range onto the whole play area. Pure logic.

A fixed mapping assumes the usable range is centred on the starting pose. A recorded
Brick Break session showed it often is not: the wrist only went one way from the
starting pose, so the paddle could only reach half the field. This keeps the lowest and
highest angle seen and stretches that span over the full 0 to 1 position, so a small or
lopsided range still reaches both edges. It also adapts to a limited range of motion
instead of demanding a fixed one, and the span it settles on is itself a rough range
measure worth logging.

How it behaves:
  - it starts with a small span centred on the first angle, so the first moves already work;
  - it widens at once whenever the angle goes beyond either end;
  - both ends drift slowly back toward the angle, so a range that was only needed once
    (an early overshoot) is forgotten, within about half a minute;
  - the span never gets smaller than `min_span`, so tiny tremor cannot swing the paddle;
  - the outer `margin` of the span maps to the edge, so the edges are reachable without
    stretching to the very limit.
"""
from __future__ import annotations


class AutoRange:
    def __init__(self, initial_half_span: float = 4.0, min_span: float = 10.0,
                 decay_per_s: float = 0.04, margin: float = 0.08):
        self._initial = initial_half_span
        self.min_span = min_span
        self.decay = decay_per_s
        self.margin = margin
        self.lo = None
        self.hi = None

    def reset(self) -> None:
        self.lo = self.hi = None

    @property
    def span(self) -> float:
        return 0.0 if self.lo is None else self.hi - self.lo

    def update(self, angle: float, dt: float = 0.02) -> float:
        """Feed one angle (degrees); returns the paddle position 0..1 (0.5 = middle)."""
        if self.lo is None:
            self.lo, self.hi = angle - self._initial, angle + self._initial
        self.lo = min(self.lo, angle)
        self.hi = max(self.hi, angle)
        k = min(1.0, self.decay * dt)               # both ends drift back toward the angle
        self.lo += (angle - self.lo) * k
        self.hi += (angle - self.hi) * k
        if self.hi - self.lo < self.min_span:        # never narrower than min_span
            mid = (self.lo + self.hi) / 2.0
            self.lo, self.hi = mid - self.min_span / 2.0, mid + self.min_span / 2.0
        a = self.lo + self.margin * self.span
        b = self.hi - self.margin * self.span
        return max(0.0, min(1.0, (angle - a) / (b - a)))
