"""Rules for the dial game: match a target angle and hold it. Pure logic.

Angle 0 is straight up; positive is clockwise (turning right).
"""
from __future__ import annotations

import math
import random

MIN_TOLERANCE, MAX_TOLERANCE = 4.0, 15.0


def needle_end(cx: float, cy: float, radius: float, angle_deg: float):
    """Where the tip of a needle at angle_deg lands on screen (y points down)."""
    a = math.radians(angle_deg)
    return cx + radius * math.sin(a), cy - radius * math.cos(a)


class DialRound:
    """One target at a time. Hold within `tolerance` degrees for `hold_s` seconds.

    It adapts: each completion tightens the tolerance by 1 degree (down to 4),
    and a target nobody reaches in `timeout_s` loosens it by 2 (up to 15).
    """

    def __init__(self, range_deg: float = 45.0, tolerance: float = 10.0,
                 hold_s: float = 1.5, timeout_s: float = 15.0, rng=None):
        self.range_deg = range_deg
        self.tolerance = tolerance
        self.hold_s = hold_s
        self.timeout_s = timeout_s
        self._rng = rng or random.Random()
        self.target = 0.0
        self.held = 0.0
        self.elapsed = 0.0
        self.completed = 0
        self.timeouts = 0
        self.new_target()

    def new_target(self) -> None:
        """A random target in the middle 80% of the range, in 5 degree steps,
        always at least 10 degrees from the previous one."""
        limit = 0.8 * self.range_deg
        for _ in range(20):
            t = round(self._rng.uniform(-limit, limit) / 5.0) * 5.0
            if abs(t - self.target) >= 10.0:
                break
        self.target = t
        self.held = 0.0
        self.elapsed = 0.0

    @property
    def on_target(self) -> bool:
        return self.held > 0.0

    def update(self, angle_deg: float, dt: float):
        """Advance by dt seconds with the dial at angle_deg.
        Returns "complete", "timeout" or None."""
        self.elapsed += dt
        if abs(angle_deg - self.target) <= self.tolerance:
            self.held += dt
        else:
            self.held = 0.0
        if self.held >= self.hold_s:
            self.completed += 1
            self.tolerance = max(MIN_TOLERANCE, self.tolerance - 1.0)
            self.new_target()
            return "complete"
        if self.elapsed >= self.timeout_s:
            self.timeouts += 1
            self.tolerance = min(MAX_TOLERANCE, self.tolerance + 2.0)
            self.new_target()
            return "timeout"
        return None
