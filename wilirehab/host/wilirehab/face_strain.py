"""Skin colour, and action-unit proxies from face-landmark positions.

PSPI (see `pspi.py`) needs FACS action-unit intensities. A trained AU
detector would supply all of them; this module does not load one. It
implements four units as landmark distances, against the same person's rest
face. They were picked because each is one direct distance between mesh
landmarks, not because a paper validates them (see
`notebook/face-signals.md`, "Why these action units"):

    AU4  brow lowerer    brow-to-upper-lid gap shrinks
    AU7  lid tightener   eye opening narrows
    AU10 upper lip raise nose-to-upper-lip distance shrinks
    AU43 eye closure     eye opening nearly gone

AU6 (cheek raiser) and AU9 (nose wrinkler) are not implemented and are left
at 0. PSPI takes max(AU6, AU7) and max(AU9, AU10), so the result can only
under-read: it is a lower bound on the FACS-coded value, never an upper one.
Head pose is not corrected for, so turning or tilting the head moves these
distances too.

The `*_FULL` constants say how large a geometric change counts as intensity
5. They are placeholders chosen by eye, not fitted to FACS-coded video, and
the landmark indices are the MediaPipe Face Mesh topology written from the
published map and checked only on synthetic points, not on a real face.
Nothing is stored: callers keep numbers, never the points.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .pspi import AU_MAX, pspi

# Forehead and both cheeks: the skin sites the rPPG trace averages.
FOREHEAD = (10, 67, 69, 104, 108, 109, 151, 338, 337, 297, 332, 284)
LEFT_CHEEK = (50, 101, 36, 205, 207, 187)
RIGHT_CHEEK = (280, 330, 266, 425, 427, 411)
SKIN = FOREHEAD + LEFT_CHEEK + RIGHT_CHEEK

# Eye landmarks in the order the eye-aspect ratio expects:
# outer corner, upper-1, upper-2, inner corner, lower-2, lower-1.
LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (263, 387, 385, 362, 380, 373)
# Brow point, then the upper-lid point beneath it.
BROWS = ((70, 159), (300, 386))
# Under-nose point, then the top of the upper lip.
NOSE_LIP = (2, 0)
# Outer eye corners, used only to scale every distance.
SCALE = (33, 263)

# Fractional change that counts as maximum intensity (5). Placeholders.
AU4_FULL = 0.30
AU7_FULL = 0.60
AU10_FULL = 0.25
# Eye opening below this fraction of rest counts as closed (AU43 = 1).
CLOSED_FRACTION = 0.25


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _eye_aspect(landmarks, eye) -> float:
    p1, p2, p3, p4, p5, p6 = (landmarks[i] for i in eye)
    horiz = _dist(p1, p4)
    if horiz == 0:
        return 0.0
    return (_dist(p2, p6) + _dist(p3, p5)) / (2.0 * horiz)


@dataclass(frozen=True)
class FaceMeasures:
    """Scale-free distances for one frame."""

    ear: float          # eye opening, mean of both eyes
    brow: float         # brow-to-upper-lid gap
    nose_lip: float     # under-nose to upper-lip distance


def measures(landmarks) -> FaceMeasures:
    """`landmarks` is a sequence of (x, y), at least 468 points, any unit."""
    scale = _dist(landmarks[SCALE[0]], landmarks[SCALE[1]])
    if scale == 0:
        scale = 1.0
    ear = 0.5 * (_eye_aspect(landmarks, LEFT_EYE) + _eye_aspect(landmarks, RIGHT_EYE))
    brow = sum(_dist(landmarks[a], landmarks[b]) for a, b in BROWS) / (2.0 * scale)
    nose_lip = _dist(landmarks[NOSE_LIP[0]], landmarks[NOSE_LIP[1]]) / scale
    return FaceMeasures(ear, brow, nose_lip)


@dataclass(frozen=True)
class ActionUnits:
    """PSPI inputs. au6 and au9 are always 0 here (see the module docstring)."""

    au4: float
    au6: float
    au7: float
    au9: float
    au10: float
    au43: int

    def pspi(self) -> float:
        return pspi(self.au4, self.au6, self.au7, self.au9, self.au10, self.au43)


def _shrink_to_intensity(rest: float, now: float, full: float) -> float:
    """0..5 from how far `now` has shrunk below `rest`, as a fraction of it."""
    if rest <= 0:
        return 0.0
    shrink = (rest - now) / rest
    return float(max(0.0, min(AU_MAX, AU_MAX * shrink / full)))


def estimate_aus(rest: FaceMeasures, now: FaceMeasures) -> ActionUnits:
    """Lower-bound action units for `now`, against the same face at `rest`."""
    closed = rest.ear > 0 and now.ear < CLOSED_FRACTION * rest.ear
    return ActionUnits(
        au4=_shrink_to_intensity(rest.brow, now.brow, AU4_FULL),
        au6=0.0,
        au7=_shrink_to_intensity(rest.ear, now.ear, AU7_FULL),
        au9=0.0,
        au10=_shrink_to_intensity(rest.nose_lip, now.nose_lip, AU10_FULL),
        au43=1 if closed else 0,
    )


def mean_rgb(frame, landmarks, indices=SKIN, radius: int = 0):
    """Mean R,G,B around the landmark pixels that fall inside `frame`.

    `frame` is H x W x 3 in RGB order (not OpenCV's BGR). `landmarks` are
    pixel coordinates (x, y). Each point contributes the mean of a
    (2*radius+1) square patch, clipped to the image; radius 0 is the single
    pixel. A pulse needs a patch: one pixel is mostly sensor noise. Returns a
    length-3 array, or None when no listed point lands on the image. The
    frame itself is not retained.
    """
    image = np.asarray(frame)
    height, width = image.shape[:2]
    samples = []
    for i in indices:
        x, y = landmarks[i][0], landmarks[i][1]
        col, row = int(round(x)), int(round(y))
        if 0 <= col < width and 0 <= row < height:
            patch = image[max(0, row - radius):row + radius + 1,
                          max(0, col - radius):col + radius + 1, :3]
            samples.append(patch.reshape(-1, patch.shape[-1]).mean(axis=0))
    if not samples:
        return None
    return np.mean(np.asarray(samples, float), axis=0)
