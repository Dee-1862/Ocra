"""Rules for the steadiness game: hold a two-angle cursor inside a ring. Pure logic.

The cursor is (roll, pitch) in degrees from neutral. A target is a point in the
middle 70% of the range; tolerance is the ring's radius in degrees. It adapts the
same way the dial does: each success tightens the ring by 1 degree (to 3), each
timeout widens it by 2 (to 12).
"""
from __future__ import annotations

import math
import random


class HoldRound2D:
    MIN_TOL, MAX_TOL = 3.0, 12.0

    def __init__(self, range_deg: float = 12.0, tolerance: float = 6.0,
                 hold_s: float = 2.0, timeout_s: float = 15.0, rng=None):
        self.range_deg = range_deg
        self.tolerance = tolerance
        self.hold_s = hold_s
        self.timeout_s = timeout_s
        self._rng = rng or random.Random()
        self.target = (0.0, 0.0)
        self.held = 0.0
        self.elapsed = 0.0
        self.completed = 0
        self.timeouts = 0
        self.dist_sum = 0.0          # distance while holding: a steadiness measure
        self.dist_n = 0
        self.new_target()

    def new_target(self) -> None:
        limit = 0.7 * self.range_deg
        for _ in range(20):
            t = (round(self._rng.uniform(-limit, limit)),
                 round(self._rng.uniform(-limit, limit)))
            if math.hypot(t[0] - self.target[0], t[1] - self.target[1]) >= 0.4 * self.range_deg:
                break
        self.target = t
        self.held = 0.0
        self.elapsed = 0.0

    @property
    def on_target(self) -> bool:
        return self.held > 0.0

    @property
    def mean_distance(self):
        return None if self.dist_n == 0 else self.dist_sum / self.dist_n

    def update(self, roll_deg: float, pitch_deg: float, dt: float):
        """Advance by dt seconds. Returns "complete", "timeout" or None."""
        self.elapsed += dt
        dist = math.hypot(roll_deg - self.target[0], pitch_deg - self.target[1])
        if dist <= self.tolerance:
            self.held += dt
            self.dist_sum += dist
            self.dist_n += 1
        else:
            self.held = 0.0
        if self.held >= self.hold_s:
            self.completed += 1
            self.tolerance = max(self.MIN_TOL, self.tolerance - 1.0)
            self.new_target()
            return "complete"
        if self.elapsed >= self.timeout_s:
            self.timeouts += 1
            self.tolerance = min(self.MAX_TOL, self.tolerance + 2.0)
            self.new_target()
            return "timeout"
        return None
