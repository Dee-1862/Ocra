"""Headless game logic. Rendering is someone else's job (OG screen, laptop
window); this is the part that decides what the target is and whether the
patient is on it, so it can be tested without a screen.
"""
from __future__ import annotations

import math


class WristPathGame:
    """Follow a target angle that sweeps between two comfortable limits.

    The sweep covers `fraction` of the patient's calibrated range, centred on
    the middle of it, so shrinking `fraction` (the adaptation engine's lever)
    makes the movement smaller without moving its centre.
    """

    def __init__(self, rom_low: float, rom_high: float, fraction: float,
                 period_s: float = 6.0, tolerance_deg: float = 8.0):
        if rom_high <= rom_low:
            raise ValueError("rom_high must exceed rom_low")
        self.centre = (rom_low + rom_high) / 2.0
        self.half = (rom_high - rom_low) / 2.0 * fraction
        self.period_s = period_s
        self.tolerance_deg = tolerance_deg
        self.t = 0.0
        self.samples = 0
        self.hits = 0

    def target(self, t: float | None = None) -> float:
        t = self.t if t is None else t
        return self.centre + self.half * math.sin(2 * math.pi * t / self.period_s)

    def step(self, dt: float, angle: float | None) -> bool:
        """Advance dt seconds. `angle=None` (tracking lost) counts as a miss
        in the denominator -- losing the hand must not inflate the score."""
        self.t += dt
        self.samples += 1
        hit = angle is not None and abs(angle - self.target()) <= self.tolerance_deg
        if hit:
            self.hits += 1
        return hit

    @property
    def hit_rate(self) -> float:
        return self.hits / self.samples if self.samples else 0.0
