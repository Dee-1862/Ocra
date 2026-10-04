"""Telling sliding from turning, with both sensors. Pure logic.

An accelerometer alone cannot say whether a movement was a slide or a tilt: both
change what it reads. A magnetometer changes when the sensor TURNS and (apart from
nearby metal or magnets) not when it slides. Together:

    slide up/down    accelerometer moves along gravity,          field direction steady
    slide sideways   accelerometer moves across gravity,         field direction steady
    turn or tilt     accelerometer moves across gravity (the     field direction turns
                     direction of gravity changes)

Neither sensor gives position. A slide is only felt while it speeds up or slows
down, so a slow, smooth move at steady speed is nearly invisible, which is a limit
of accelerometers, not a fault.

The field direction is only meaningful after the magnetometer's fixed offset is
removed (see fit_sphere_offset): that offset is much larger than Earth's field, so
without it the direction barely changes when the board turns.
"""
from __future__ import annotations

import math

TRANSLATION_MG = 35.0       # about 2 degrees of tilt, a few times the sensor's noise
TURN_DEG = 8.0              # how far the field direction must turn to count as turning


def _mean(vectors):
    n = len(vectors)
    return tuple(sum(v[i] for v in vectors) / n for i in range(3))


def _norm(v) -> float:
    return math.sqrt(sum(c * c for c in v))


def split_accel_motion(accel):
    """Within a window of accelerometer samples (x, y, z in mg), the RMS movement
    along gravity (vertical) and across it (horizontal). Gravity's direction is the
    window's mean reading, which is fine for a second or so of roughly constant attitude."""
    n = len(accel)
    if n < 2:
        return 0.0, 0.0
    mean = _mean(accel)
    g = _norm(mean)
    if g < 1e-6:
        return 0.0, 0.0
    down = tuple(c / g for c in mean)
    v2 = h2 = 0.0
    for a in accel:
        d = tuple(a[i] - mean[i] for i in range(3))
        along = sum(d[i] * down[i] for i in range(3))
        v2 += along * along
        h2 += max(0.0, sum(c * c for c in d) - along * along)
    return math.sqrt(v2 / n), math.sqrt(h2 / n)


def mag_turn_deg(mag, offset=(0.0, 0.0, 0.0)) -> float:
    """The largest angle, in degrees, between the field direction at any moment in the
    window and its average direction, after subtracting the magnetometer's offset."""
    vecs = [tuple(m[i] - offset[i] for i in range(3)) for m in mag]
    if not vecs:
        return 0.0
    mean = _mean(vecs)
    mean_n = _norm(mean)
    if mean_n < 1e-6:
        return 0.0
    worst = 0.0
    for v in vecs:
        n = _norm(v)
        if n < 1e-6:
            continue
        cosine = sum(v[i] * mean[i] for i in range(3)) / (n * mean_n)
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    return worst


def fit_sphere_offset(mag):
    """Find the fixed offset of a magnetometer from readings taken while turning it
    through every orientation.

    Away from magnets the true field has a constant strength, so the readings lie on
    a sphere; the sphere's centre is the offset. Returns (offset, radius, rms_error):
    the radius should come out near Earth's field (about 25 to 65 microtesla).
    """
    import numpy as np
    pts = np.asarray(mag, dtype=float)
    if len(pts) < 30:
        raise ValueError("need at least 30 readings; turn it through more orientations")
    a = np.hstack([2.0 * pts, np.ones((len(pts), 1))])
    b = (pts ** 2).sum(axis=1)
    sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    centre = sol[:3]
    radius_sq = sol[3] + centre @ centre
    if radius_sq <= 0:
        raise ValueError("the readings do not lie on a sphere; turn it through more orientations")
    radius = math.sqrt(radius_sq)
    err = np.sqrt(np.mean((np.linalg.norm(pts - centre, axis=1) - radius) ** 2))
    return tuple(float(c) for c in centre), float(radius), float(err)


def tilt_induced_mg(turn_deg: float) -> float:
    """How much sideways accelerometer movement a turn of `turn_deg` causes by itself.

    Turning changes the direction of gravity, which moves the reading ACROSS gravity by
    about 1000 mg times the turn angle in radians. `turn_deg` is the largest turn seen;
    for a back-and-forth turn the RMS is about 1/sqrt(2) of it.
    """
    return 1000.0 * math.sin(math.radians(turn_deg / math.sqrt(2.0)))


DEFAULT_FIELD_UT = 40.0     # Earth's field, roughly 25 to 65 uT; calibration measures the real one


def estimate_tilt_mg(turn_deg=None, field_change_ut=None,
                     field_strength_ut: float = DEFAULT_FIELD_UT) -> float:
    """How much of the accelerometer's sideways movement the TURNING alone explains.

    From the field direction if the magnetometer is calibrated (turn_deg); otherwise from
    how much the field readings changed: a turn by angle t moves the field by about
    field_strength * t and the accelerometer, across gravity, by about 1000 mg * t, so the
    ratio is 1000 / field_strength (about 25 mg per uT). A rough estimate: a turn about the
    field's own axis changes the field not at all, so it can be under-counted.
    """
    if turn_deg is not None:
        return tilt_induced_mg(turn_deg)
    if field_change_ut is not None:
        return field_change_ut * 1000.0 / field_strength_ut
    return 0.0


def describe_motion(vertical_mg: float, horizontal_mg: float, tilt_mg: float = 0.0,
                    turned: bool = False) -> str:
    """One phrase for what a window of data looks like.

    The accelerometer movement is first stripped of what turning alone would cause:
      - across gravity: turning moves it by tilt_mg, so only the remainder can be a slide;
      - along gravity: turning moves it a second-order amount (about tilt_mg squared over
        2000), so only the excess can be an up/down slide.
    What is left is called a slide only if it clearly exceeds the noise AND half the turn
    estimate (that estimate is rough, so a slide hidden inside it is not claimed).
    """
    across = math.sqrt(max(0.0, horizontal_mg ** 2 - tilt_mg ** 2))
    along = max(0.0, vertical_mg - tilt_mg ** 2 / 2000.0)
    slide = max(across, along)
    suffix = " while turning" if turned else ""
    if slide >= max(TRANSLATION_MG, 0.5 * tilt_mg):
        return ("sliding up/down" if along >= across else "sliding sideways") + suffix
    if turned:
        return "turning / tilting"
    return "still"
