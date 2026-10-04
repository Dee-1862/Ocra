"""Remote photoplethysmography: heart rate from a webcam skin-colour trace.

Two closed-form methods, neither of them trained:

- POS (Plane-Orthogonal-to-Skin), Wang, den Brinker, Stuijk and de Haan,
  IEEE TBME 2017.
- CHROM (chrominance), de Haan and Jeanne, IEEE TBME 2013.

The notebook page `face-signals.md` records the papers and the datasets those
papers used. This file does not load a model and does not read those datasets.

Input is the mean R,G,B of a skin region per frame (see `face_strain.mean_rgb`).
No video is stored -- three floats per frame.
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


def chrom(rgb, fs: float, win_s: float = 1.6) -> np.ndarray:
    """CHROM pulse signal from an (N, 3) RGB trace sampled at `fs` Hz.

    Each window is divided by its own mean, then projected to the
    chrominance pair Xs = 3R-2G, Ys = 1.5R+G-1.5B, and combined with
    alpha = std(Xs)/std(Ys), as described by de Haan and Jeanne.
    """
    c = np.asarray(rgb, float)
    n = len(c)
    w = int(round(win_s * fs))
    if n < w or w < 2:
        return np.zeros(n)
    h = np.zeros(n)
    for t in range(0, n - w + 1):
        seg = c[t:t + w]
        mean = seg.mean(axis=0)
        if np.any(mean == 0):
            continue
        nseg = seg / mean
        xs = 3.0 * nseg[:, 0] - 2.0 * nseg[:, 1]
        ys = 1.5 * nseg[:, 0] + nseg[:, 1] - 1.5 * nseg[:, 2]
        ystd = ys.std()
        alpha = xs.std() / ystd if ystd > 0 else 0.0
        p = xs - alpha * ys
        h[t:t + w] += p - p.mean()
    return h


_METHODS = {"pos": pos, "chrom": chrom}


def pulse_signal(rgb, fs: float, method: str = "pos") -> np.ndarray:
    """The raw pulse waveform for `method`, for callers that time the beats."""
    try:
        pulse = _METHODS[method]
    except KeyError:
        raise ValueError(f"unknown rPPG method {method!r}") from None
    return pulse(rgb, fs)


@dataclass
class HeartRate:
    bpm: float | None
    quality: float          # 0..1: fraction of in-band power at the peak


def estimate_hr(rgb, fs: float, method: str = "pos") -> HeartRate:
    """Heart rate from an RGB trace.

    `method` is "pos" or "chrom". Quality is the share of in-band spectral
    power within +/-0.1 Hz of the peak -- low when the trace is noise, motion
    or poor light. Callers should ignore the bpm below their own quality
    threshold.
    """
    sig = pulse_signal(rgb, fs, method)
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
