"""Remote photoplethysmography: heart rate from a webcam skin-colour trace.

POS (Plane-Orthogonal-to-Skin, Wang et al.) written from its published
description. The plan on Page 3 is to use rPPG-Toolbox for the real
evaluation; this implementation exists so the pipeline runs end to end and is
testable, and should be cross-checked against the toolbox before any number
from it goes in the paper.

Input is the mean R,G,B of a skin region (forehead/cheeks from Face Mesh) per
frame. No video is stored or passed in -- three floats per frame.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HR_MIN_BPM = 42.0
HR_MAX_BPM = 180.0


def pos(rgb, fs: float, win_s: float = 1.6) -> np.ndarray:
    """POS pulse signal from an (N, 3) RGB trace sampled at `fs` Hz."""
    c = np.asarray(rgb, float)
    n = len(c)
    w = int(round(win_s * fs))
    if n < w or w < 2:
        return np.zeros(n)
    h = np.zeros(n)
    proj = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    for t in range(0, n - w + 1):
        seg = c[t:t + w]
        mean = seg.mean(axis=0)
        if np.any(mean == 0):
            continue
        s = proj @ (seg / mean).T          # (2, w)
        s2 = s[1].std()
        alpha = s[0].std() / s2 if s2 > 0 else 0.0
        p = s[0] + alpha * s[1]
        h[t:t + w] += p - p.mean()
    return h


@dataclass
class HeartRate:
    bpm: float | None
    quality: float          # 0..1: fraction of in-band power at the peak


def estimate_hr(rgb, fs: float) -> HeartRate:
    """Heart rate from the last window of an RGB trace.

    Quality is the share of in-band spectral power within +/-0.1 Hz of the
    peak -- low when the trace is noise, motion or poor light. Callers
    should ignore the bpm below their own quality threshold.
    """
    sig = pos(rgb, fs)
    if len(sig) < int(4 * fs) or not np.any(sig):
        return HeartRate(None, 0.0)
    sig = sig - sig.mean()
    sig = sig * np.hanning(len(sig))
    nfft = 1 << int(np.ceil(np.log2(len(sig))) + 2)
    spec = np.abs(np.fft.rfft(sig, nfft)) ** 2
    freqs = np.fft.rfftfreq(nfft, 1.0 / fs)
    band = (freqs >= HR_MIN_BPM / 60.0) & (freqs <= HR_MAX_BPM / 60.0)
    if not np.any(band) or spec[band].sum() == 0:
        return HeartRate(None, 0.0)
    fb, sb = freqs[band], spec[band]
    peak = fb[np.argmax(sb)]
    near = np.abs(fb - peak) <= 0.1
    return HeartRate(float(peak * 60.0), float(sb[near].sum() / sb.sum()))
