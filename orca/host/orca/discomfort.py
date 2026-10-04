"""One discomfort reading for the adaptation engine.

Three separate pieces of evidence, not one blended score, because the weights
that would blend them have never been fitted to anyone:

- `pspi` (0..16) and `strain` (the same as a 0..1 fraction): the facial
  pain-expression index. This is the one measure here with a published
  definition and validation (`pspi.py`). It is a lower bound (see
  `face_strain.py`).
- `bpm` and `hr_quality`: pulse rate from the colour trace (`rppg.py`).
- `rmssd_ratio` and `lf_hf_ratio`: HRV now against this person's rest window
  (`hrv.py`). Supporting signals only; None when the window is too short.

This module does not open a camera and does not store a frame.
"""
from __future__ import annotations

from dataclasses import dataclass

from .face_strain import FaceMeasures, estimate_aus
from .hrv import Hrv, change_from_rest, from_pulse
from .pspi import unit_scale
from .rppg import estimate_hr, pulse_signal

# A placeholder, not a clinical cut-off: PSPI of 3 on the 0..16 scale, written
# as the fraction AdaptationEngine(strain_ease=...) expects. The engine's own
# default of 0.6 would mean PSPI 9.6, which is rare (about 0.5% of frames in
# the UNBC-McMaster archive scored 9 or more), so it would almost never fire.
STRAIN_EASE_SUGGESTED = 3.0 / 16.0


@dataclass(frozen=True)
class Discomfort:
    bpm: float | None
    hr_quality: float
    pspi: float | None
    strain: float | None
    rmssd_ms: float | None
    rmssd_ratio: float | None
    lf_hf: float | None
    lf_hf_ratio: float | None
    hrv_beats: int
    method: str


def reading(rgb, fs: float, rest_face: FaceMeasures | None = None,
            now_face: FaceMeasures | None = None, rest_hrv: Hrv | None = None,
            method: str = "pos") -> Discomfort:
    """`rgb` is an (N, 3) skin-colour trace at `fs` Hz.

    Pass `rest_face` and `now_face` for a PSPI value, and `rest_hrv` (from
    `hrv.from_pulse` on a calm window) for HRV ratios. Anything not supplied
    comes back as None rather than a guess.
    """
    hr = estimate_hr(rgb, fs, method=method)
    score = None
    if rest_face is not None and now_face is not None:
        score = estimate_aus(rest_face, now_face).pspi()
    now_hrv = from_pulse(pulse_signal(rgb, fs, method), fs)
    ratios = (change_from_rest(rest_hrv, now_hrv) if rest_hrv is not None
              else {"rmssd_ratio": None, "lf_hf_ratio": None})
    return Discomfort(
        bpm=hr.bpm, hr_quality=hr.quality,
        pspi=score, strain=None if score is None else unit_scale(score),
        rmssd_ms=now_hrv.rmssd_ms, rmssd_ratio=ratios["rmssd_ratio"],
        lf_hf=now_hrv.lf_hf, lf_hf_ratio=ratios["lf_hf_ratio"],
        hrv_beats=now_hrv.n_beats, method=method)
