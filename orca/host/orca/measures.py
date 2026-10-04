"""Indirect measures worked out from data the games already collect. Pure logic.

Nothing here is a clinical measurement. Each is a proxy (reaction time for
response speed, a trend for fatigue, a 4-12 Hz band for tremor) and needs its
own citation and, ideally, a check against a trusted instrument.
"""
from __future__ import annotations

import math
from statistics import median

import numpy as np

TREMOR_BAND_HZ = (4.0, 12.0)
MIN_TREMOR_SAMPLES = 64
MIN_TREMOR_RATE_HZ = 26.0       # must sample above twice the top of the band


class ReactionStats:
    """Reaction times in milliseconds."""

    def __init__(self):
        self.values: list = []

    def add(self, ms: float) -> None:
        self.values.append(float(ms))

    @property
    def count(self) -> int:
        return len(self.values)

    def summary(self):
        """{'count','median','mean','best','worst'} or None when empty."""
        if not self.values:
            return None
        return {"count": self.count, "median": median(self.values),
                "mean": sum(self.values) / self.count,
                "best": min(self.values), "worst": max(self.values)}


def trend_per_minute(points, min_points: int = 6, min_span_s: float = 30.0):
    """Least-squares slope of value against time, per minute.

    `points` is a list of (seconds, value). Returns None when there are too few
    points or they cover too short a time to say anything.
    """
    if len(points) < min_points:
        return None
    ts = [p[0] for p in points]
    vs = [p[1] for p in points]
    if max(ts) - min(ts) < min_span_s:
        return None
    mt, mv = sum(ts) / len(ts), sum(vs) / len(vs)
    den = sum((t - mt) ** 2 for t in ts)
    if den == 0:
        return None
    slope_per_s = sum((t - mt) * (v - mv) for t, v in points) / den
    return slope_per_s * 60.0


def describe_trend(slope, flat_below: float, unit: str, higher_is_better: bool):
    """'steady', 'improving +3.1 %/min' or 'worsening ...'; None if slope is None."""
    if slope is None:
        return None
    if abs(slope) < flat_below:
        return "steady"
    better = (slope > 0) == higher_is_better
    return f"{'improving' if better else 'worsening'} {slope:+.1f} {unit}/min"


def tremor_band(samples, t_ms, band=TREMOR_BAND_HZ):
    """Tremor strength from raw accelerometer samples.

    samples: list of (x, y, z) in milli-g; t_ms: the device timestamps (ms).
    Returns (rms_mg, peak_hz) for the band, or None if there is too little data
    or the sampling is too slow to resolve the band.

    Method: remove each axis's mean, Hann-window, FFT, add the power of the
    three axes, and read the band. The Hann window spreads a sine across about
    1.5 bins' worth of energy, so the power is divided by 1.5.
    """
    n = len(samples)
    if n < MIN_TREMOR_SAMPLES or len(t_ms) != n:
        return None
    span = (t_ms[-1] - t_ms[0]) / 1000.0
    if span <= 0:
        return None
    fs = (n - 1) / span
    if fs < MIN_TREMOR_RATE_HZ:
        return None
    arr = np.asarray(samples, dtype=float)
    arr = arr - arr.mean(axis=0)
    window = np.hanning(n)
    spec = np.fft.rfft(arr * window[:, None], axis=0)
    amp = 2.0 * np.abs(spec) / window.sum()            # sine amplitude per bin
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    mask = (freqs >= band[0]) & (freqs <= band[1])
    if not mask.any():
        return None
    power = (amp ** 2).sum(axis=1)                      # all three axes
    rms = math.sqrt(power[mask].sum() / 2.0 / 1.5)
    peak_hz = float(freqs[mask][np.argmax(power[mask])])
    return rms, peak_hz
