"""Pure logic for the Rhythm Flick game: flick detection and hit matching.

A flick is a fast tilt of the OG. The OG has no gyroscope, so speed is the
change of the accelerometer's tilt angle over time. That is cruder than a real
gyro, and it is distorted while the hand accelerates, so the thresholds are
settings to tune, not constants to trust.

The detector was rebuilt after a recorded session showed 46 detections for 23
arrows: a single movement was counted twice, because the slow return stroke
crossed the speed threshold again as soon as a short timer ran out, and most
"wrong direction" results were that return stroke. It now works as a small
state machine:

    armed  --fast move that covers min_excursion_deg-->  FLICK (direction of the move)
    after a flick: cooldown, blocked until the hand has been calm
                   (below calm_dps) for calm_s seconds, so the return stroke
                   and any settling wobble are ignored
    a fast start that stops short of the excursion is dropped (tremor, a bump)
"""
from __future__ import annotations


class FlickDetector:
    """Watches two tilt angles over time and reports a flick direction.

    side angle rising = "right", falling = "left".
    forward angle rising = "up", falling = "down".
    (Which physical motion that is depends on how the OG is worn; the game's
    --invert flags flip them.)
    """

    def __init__(self, threshold_dps: float = 150.0, min_excursion_deg: float = 8.0,
                 max_burst_s: float = 0.4, calm_dps: float = 45.0, calm_s: float = 0.15,
                 min_gap_s: float = 0.25):
        self.threshold_dps = threshold_dps
        self.min_excursion_deg = min_excursion_deg
        self.max_burst_s = max_burst_s
        self.calm_dps = calm_dps
        self.calm_s = calm_s
        self.min_gap_s = min_gap_s
        self._prev = None
        self._burst = None            # (t, side, fwd) where a fast move began
        self._cooling = False
        self._calm_since = None
        self._last_flick = None

    def update(self, t_s: float, side_deg: float, fwd_deg: float):
        """Feed one sample (time in seconds, two angles in degrees).
        Returns "left", "right", "up", "down" or None."""
        prev, self._prev = self._prev, (t_s, side_deg, fwd_deg)
        if prev is None:
            return None
        dt = t_s - prev[0]
        if dt <= 0:
            return None
        speed = max(abs(side_deg - prev[1]), abs(fwd_deg - prev[2])) / dt

        if self._cooling:
            if speed < self.calm_dps:
                if self._calm_since is None:
                    self._calm_since = t_s
                settled = t_s - self._calm_since >= self.calm_s
                spaced = self._last_flick is None or t_s - self._last_flick >= self.min_gap_s
                if settled and spaced:
                    self._cooling = False
                    self._burst = None
            else:
                self._calm_since = None
            return None

        if self._burst is None:
            if speed < self.threshold_dps:
                return None
            self._burst = (prev[0], prev[1], prev[2])      # the move began at the last sample
        t0, s0, f0 = self._burst
        d_side, d_fwd = side_deg - s0, fwd_deg - f0
        if max(abs(d_side), abs(d_fwd)) >= self.min_excursion_deg:
            self._cooling = True
            self._calm_since = None
            self._last_flick = t_s
            self._burst = None
            if abs(d_side) >= abs(d_fwd):
                return "right" if d_side > 0 else "left"
            return "up" if d_fwd > 0 else "down"
        if t_s - t0 > self.max_burst_s or speed < self.calm_dps:
            self._burst = None                              # it stopped short: not a flick
        return None


def match_flick(blocks, direction: str, now: float, window: float, hand=None):
    """Which falling block does a flick at time `now` belong to?

    Returns ("hit" | "wrong" | "wrong_hand" | "none", block).
      - the block is the live one closest to `now`, within +-window seconds;
      - `hand` is the hand that flicked (None = unknown, matches any block);
      - a block marked for the other hand is ignored: if only such blocks are
        due, the result is "wrong_hand" and no block is returned;
      - "wrong" means a block was there but the flick went a different way;
      - "none" means no block was due.
    """
    due = [b for b in blocks
           if b["state"] == "live" and abs(b["t_hit"] - now) <= window]
    if not due:
        return "none", None
    if hand is not None:
        mine = [b for b in due if b.get("hand") in (None, hand)]
        if not mine:
            return "wrong_hand", None
        due = mine
    block = min(due, key=lambda b: abs(b["t_hit"] - now))
    return ("hit" if block["dir"] == direction else "wrong"), block
