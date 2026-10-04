"""Prkachin and Solomon Pain Intensity (PSPI).

    PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43

AU4 brow lowerer, AU6 cheek raiser, AU7 lid tightener, AU9 nose wrinkler,
AU10 upper lip raiser: each scored 0 (absent) to 5 (maximum). AU43 eye
closure is 0 or 1. The sum therefore runs 0 to 16, a 16-point scale.

Prkachin KM, Solomon PE. The structure, reliability and validity of pain
expression: evidence from patients with shoulder pain. Pain 2008;139:267-274.
The frame-by-frame form used here is the one in Lucey et al., Painful data:
the UNBC-McMaster shoulder pain expression archive database, IEEE FG 2011.

The formula takes FACS-coded intensities. It says nothing about how to get
them from a camera; see `face_strain.estimate_aus` for what this repo can
and cannot supply.
"""
from __future__ import annotations

import math

AU_MAX = 5.0
PSPI_MAX = 16.0


def _intensity(name: str, value: float) -> float:
    if not math.isfinite(value) or not 0.0 <= value <= AU_MAX:
        raise ValueError(f"{name} must be between 0 and {AU_MAX:g}, got {value!r}")
    return float(value)


def pspi(au4: float, au6: float, au7: float, au9: float, au10: float,
         au43: float) -> float:
    """PSPI from five 0..5 intensities and the 0/1 eye-closure flag."""
    if au43 not in (0, 1):
        raise ValueError(f"au43 is binary (0 or 1), got {au43!r}")
    return (_intensity("au4", au4)
            + max(_intensity("au6", au6), _intensity("au7", au7))
            + max(_intensity("au9", au9), _intensity("au10", au10))
            + float(au43))


def unit_scale(score: float) -> float:
    """PSPI as a 0..1 fraction of its maximum."""
    return max(0.0, min(1.0, score / PSPI_MAX))
