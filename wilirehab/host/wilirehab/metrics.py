"""Movement metrics: joint angle, range of motion, smoothness, compensation.

Pure numpy, no camera, no hardware -- everything here is unit-tested on
synthetic signals. Angles are degrees; 0 means straight.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


def angle_between(u, v) -> float:
    """Unsigned angle in degrees between two vectors; 0 if either is zero."""
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu == 0 or nv == 0:
        return 0.0
    c = float(np.dot(u, v) / (nu * nv))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def wrist_flexion(elbow, wrist, middle_mcp) -> float:
    """Signed wrist deviation in the image plane, degrees.

    The angle from the forearm direction (elbow -> wrist) to the hand
    direction (wrist -> middle-finger knuckle). 0 is straight; positive is
    counter-clockwise in image coordinates. Which sign is flexion and which
    is extension depends on which hand and which way the palm faces, so the
    caller calibrates the sign (see Calibration.flexion_sign).

    This is a 2D projection: it under-reads when the forearm is not
    perpendicular to the camera axis. That is a known limit of a single
    webcam and the reason the IMU exists.
    """
    fx, fy = (np.asarray(wrist, float) - np.asarray(elbow, float))[:2]
    hx, hy = (np.asarray(middle_mcp, float) - np.asarray(wrist, float))[:2]
    if (fx == 0 and fy == 0) or (hx == 0 and hy == 0):
        return 0.0
    return math.degrees(math.atan2(fx * hy - fy * hx, fx * hx + fy * hy))


def rom(angles, trim_pct: float = 2.0) -> tuple[float, float, float]:
    """(low, high, span) of an angle trace, ignoring `trim_pct` % outliers at
    each end so one bad tracking frame does not set the patient's range."""
    a = np.asarray([x for x in angles if x is not None and not np.isnan(x)], float)
    if a.size == 0:
        return (0.0, 0.0, 0.0)
    lo, hi = np.percentile(a, [trim_pct, 100.0 - trim_pct])
    return (float(lo), float(hi), float(hi - lo))


def sparc(speed, fs: float, pad: int = 4, fc: float = 10.0,
          amp_th: float = 0.05) -> float:
    """Spectral arc length smoothness (Balasubramanian et al. 2015).

    More negative = less smooth. `speed` is the movement speed profile of a
    single movement; `fs` its sample rate in Hz. Implemented from the
    published definition -- verify against the paper before quoting numbers
    (Page 3 status for that paper is still 'to read').
    """
    v = np.asarray(speed, float)
    if v.size < 4 or not np.any(v):
        return 0.0
    nfft = int(2 ** (math.ceil(math.log2(v.size)) + pad))
    mag = np.abs(np.fft.fft(v, nfft))
    mag = mag / mag.max()
    f = np.arange(nfft) * fs / nfft
    sel = f <= fc
    f, mag = f[sel], mag[sel]
    above = np.nonzero(mag >= amp_th)[0]
    if above.size == 0:
        return 0.0
    last = above[-1]
    f, mag = f[: last + 1], mag[: last + 1]
    if f.size < 2:
        return 0.0
    fnorm = f / f[-1]
    return float(-np.sum(np.sqrt(np.diff(fnorm) ** 2 + np.diff(mag) ** 2)))


@dataclass
class Compensation:
    trunk_lean: bool = False
    elbow_drift: bool = False

    @property
    def any(self) -> bool:
        return self.trunk_lean or self.elbow_drift


class CompensationDetector:
    """Flags trunk lean and elbow drift against a calibrated rest pose.

    Inputs are 2D image points, so everything is normalised by shoulder
    width: the thresholds then do not depend on how far the patient sits
    from the camera.
    """

    def __init__(self, lean_deg: float = 8.0, elbow_frac: float = 0.25):
        self.lean_deg = lean_deg
        self.elbow_frac = elbow_frac
        self._rest = None   # (shoulder_line_angle_deg, elbow_rel, shoulder_w)

    @staticmethod
    def _shoulder_angle(ls, rs) -> float:
        d = np.asarray(rs, float)[:2] - np.asarray(ls, float)[:2]
        return math.degrees(math.atan2(d[1], d[0]))

    def calibrate(self, left_shoulder, right_shoulder, elbow) -> None:
        ls, rs = np.asarray(left_shoulder, float)[:2], np.asarray(right_shoulder, float)[:2]
        width = float(np.linalg.norm(rs - ls))
        if width == 0:
            raise ValueError("shoulders coincide; cannot calibrate")
        mid = (ls + rs) / 2
        rel = (np.asarray(elbow, float)[:2] - mid) / width
        self._rest = (self._shoulder_angle(ls, rs), rel, width)

    def check(self, left_shoulder, right_shoulder, elbow) -> Compensation:
        if self._rest is None:
            raise RuntimeError("calibrate() first")
        rest_angle, rest_rel, _ = self._rest
        ls, rs = np.asarray(left_shoulder, float)[:2], np.asarray(right_shoulder, float)[:2]
        width = float(np.linalg.norm(rs - ls))
        if width == 0:
            return Compensation()
        # Wrap the angle difference into [-180, 180) so a lean across the
        # +/-180 seam is not read as a huge swing.
        dtheta = (self._shoulder_angle(ls, rs) - rest_angle + 180.0) % 360.0 - 180.0
        rel = (np.asarray(elbow, float)[:2] - (ls + rs) / 2) / width
        drift = float(np.linalg.norm(rel - rest_rel))
        return Compensation(trunk_lean=abs(dtheta) > self.lean_deg,
                            elbow_drift=drift > self.elbow_frac)
