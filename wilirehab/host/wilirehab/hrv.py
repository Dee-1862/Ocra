"""Heart-rate variability from a camera pulse waveform.

Beats are timed on the pulse signal from `rppg.pulse_signal`, cleaned, then
summarised as RMSSD (time domain) and the LF/HF ratio (frequency domain), with
the standard bands LF 0.04-0.15 Hz and HF 0.15-0.40 Hz (Task Force of the ESC
and NASPE, Circulation 1996).

What these numbers are good for, and what they are not:

- Direction in acute pain: a systematic review of experimental pain in healthy
  adults found vagally mediated measures (HF, RMSSD) falling and LF measures
  and LF/HF rising (Koenig et al., Eur J Pain 2014;18:301-314). A later review
  of 71 studies found the response varies with the stimulus, breathing, sex,
  age and attention, and some cold-pain studies saw RMSSD rise (Brain Sci
  2022;12:153). So a drop in RMSSD is a hint, not a pain detector.
- LF/HF is not a "fight or flight" meter. At rest LF reflects baroreflex
  activity, not cardiac sympathetic tone (Shaffer and Ginsberg, Front Public
  Health 2017;5:258, citing Goldstein et al. 2011).
- Recording length: RMSSD needs about 60 s (30 s has been proposed); LF needs
  at least 2 min, and 2.5 min of clean data (Shaffer and Ginsberg 2017).
  Shorter windows return None rather than a number.
- Camera accuracy: at 30 fps, resting, in about 500 lux from the front,
  rPPG LF/HF tracked ECG with r near 0.9; accuracy fell sharply when the head
  moved (Tohma et al., "Evaluation of Remote Photoplethysmography Measurement
  Conditions toward Telemedicine Applications", 2021). "Robust Heart Rate
  Variability Measurement from Facial Videos" (PMC10376629) reports a best
  RMSSD error near 10 ms on UBFC-rPPG, against a typical resting range of
  19-75 ms. At 30 fps one frame is 33 ms, so beat times are interpolated
  between frames. During a game, with the head moving, treat both numbers
  as unreliable.

Inputs and outputs are numbers; no video or landmark is kept.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Wider than the heart-rate band on purpose: beat timing needs the pulse's
# upstroke harmonics, and a 0.7 Hz lower edge flattens beat-to-beat
# alternation and sits too close to a slow (50 bpm = 0.83 Hz) pulse.
PULSE_BAND_HZ = (0.5, 4.0)
MIN_BEAT_GAP_S = 0.30              # no beat closer than 200 bpm
IBI_MIN_MS = 400.0
IBI_MAX_MS = 1300.0
IBI_JUMP = 0.30                    # drop an interval 30% off the median
MIN_RMSSD_S = 60.0
MIN_LF_S = 150.0
LF_BAND = (0.04, 0.15)
HF_BAND = (0.15, 0.40)
RESAMPLE_HZ = 4.0


def bandpass(sig, fs: float, lo: float = PULSE_BAND_HZ[0], hi: float = PULSE_BAND_HZ[1]):
    """Zero-phase band-pass by masking the FFT. No scipy needed."""
    x = np.asarray(sig, float)
    if len(x) < 4:
        return x - (x.mean() if len(x) else 0.0)
    spec = np.fft.rfft(x - x.mean())
    freqs = np.fft.rfftfreq(len(x), 1.0 / fs)
    spec[(freqs < lo) | (freqs > hi)] = 0.0
    return np.fft.irfft(spec, len(x))


def beat_times(sig, fs: float) -> np.ndarray:
    """Seconds of each pulse peak, refined between frames by a parabola."""
    x = bandpass(sig, fs)
    if len(x) < 3 or not np.any(x):
        return np.empty(0)
    interior = np.arange(1, len(x) - 1)
    is_peak = (x[interior] > x[interior - 1]) & (x[interior] >= x[interior + 1]) & (x[interior] > 0)
    cands = interior[is_peak]
    if cands.size == 0:
        return np.empty(0)
    min_gap = int(round(MIN_BEAT_GAP_S * fs))
    kept: list[int] = []
    for i in cands[np.argsort(x[cands])[::-1]]:
        if all(abs(int(i) - k) >= min_gap for k in kept):
            kept.append(int(i))
    times = []
    for i in sorted(kept):
        y0, y1, y2 = x[i - 1], x[i], x[i + 1]
        denom = y0 - 2.0 * y1 + y2
        offset = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
        times.append((i + max(-0.5, min(0.5, offset))) / fs)
    return np.asarray(times)


def valid_intervals(times):
    """(ibi_ms, valid_mask) for consecutive beats.

    An interval is valid when it lies in the physiological range and within
    IBI_JUMP of the median. Invalid ones are flagged, not deleted, so that
    successive differences are never taken across a gap.
    """
    t = np.asarray(times, float)
    if len(t) < 2:
        return np.empty(0), np.empty(0, bool)
    ibi = np.diff(t) * 1000.0
    ok = (ibi >= IBI_MIN_MS) & (ibi <= IBI_MAX_MS)
    if np.any(ok):
        med = np.median(ibi[ok])
        ok &= np.abs(ibi - med) <= IBI_JUMP * med
    return ibi, ok


def rmssd(times) -> float | None:
    """Root mean square of successive differences, in ms, or None."""
    t = np.asarray(times, float)
    if len(t) < 2 or (t[-1] - t[0]) < MIN_RMSSD_S:
        return None
    ibi, ok = valid_intervals(t)
    both = ok[:-1] & ok[1:]
    if both.sum() < 10:
        return None
    d = np.diff(ibi)[both]
    return float(np.sqrt(np.mean(d ** 2)))


def lf_hf(times) -> float | None:
    """LF power divided by HF power, or None when the window is too short."""
    t = np.asarray(times, float)
    if len(t) < 2 or (t[-1] - t[0]) < MIN_LF_S:
        return None
    ibi, ok = valid_intervals(t)
    if ok.sum() < 20:
        return None
    mid = 0.5 * (t[:-1] + t[1:])
    grid = np.arange(mid[ok][0], mid[ok][-1], 1.0 / RESAMPLE_HZ)
    if len(grid) < int(MIN_LF_S * RESAMPLE_HZ * 0.8):
        return None
    series = np.interp(grid, mid[ok], ibi[ok])
    n = np.arange(len(series))
    series = series - np.polyval(np.polyfit(n, series, 1), n)
    series = series * np.hanning(len(series))
    nfft = 1 << int(np.ceil(np.log2(len(series))) + 1)
    power = np.abs(np.fft.rfft(series, nfft)) ** 2
    freqs = np.fft.rfftfreq(nfft, 1.0 / RESAMPLE_HZ)
    lf = power[(freqs >= LF_BAND[0]) & (freqs < LF_BAND[1])].sum()
    hf = power[(freqs >= HF_BAND[0]) & (freqs <= HF_BAND[1])].sum()
    if hf <= 0:
        return None
    return float(lf / hf)


@dataclass(frozen=True)
class Hrv:
    n_beats: int
    span_s: float
    rmssd_ms: float | None
    lf_hf: float | None


def from_pulse(sig, fs: float) -> Hrv:
    """RMSSD and LF/HF for a pulse waveform sampled at `fs` Hz."""
    t = beat_times(sig, fs)
    span = float(t[-1] - t[0]) if len(t) > 1 else 0.0
    return Hrv(len(t), span, rmssd(t), lf_hf(t))


def change_from_rest(rest: Hrv, now: Hrv) -> dict:
    """Ratios against the same person's rest window; None where either is missing.

    `rmssd_ratio` below 1 is the direction reported for acute pain;
    `lf_hf_ratio` above 1 is. Neither is a pain score by itself.
    """
    def ratio(a, b):
        return None if a is None or b is None or a == 0 else b / a

    return {"rmssd_ratio": ratio(rest.rmssd_ms, now.rmssd_ms),
            "lf_hf_ratio": ratio(rest.lf_hf, now.lf_hf)}
