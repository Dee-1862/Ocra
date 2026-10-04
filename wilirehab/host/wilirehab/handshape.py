"""A simple line drawing of a hand, for the mirror game. Pure geometry.

The wrist is the origin. +x is right, +y is down (screen coordinates), so the
hand points up the screen along -y. A positive angle turns it clockwise.

The right hand is drawn as seen from its back with the thumb on the left; the
left hand is its mirror image.
"""
from __future__ import annotations

import math

PALM = ((-30.0, 0.0), (30.0, 0.0), (30.0, -60.0), (-30.0, -60.0))
# (base x, finger length): index to little finger along the top of the palm.
FINGERS = ((-22.0, 44.0), (-7.0, 52.0), (8.0, 48.0), (23.0, 38.0))
THUMB = ((-30.0, -18.0), (-56.0, -44.0))


def _rotate(point, angle_deg):
    a = math.radians(angle_deg)
    x, y = point
    return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))


def hand_shape(angle_deg: float, left: bool = False) -> list:
    """Line segments ((x1, y1), (x2, y2)) of a hand turned by angle_deg."""
    segs = []
    for i in range(4):
        segs.append((PALM[i], PALM[(i + 1) % 4]))
    for x, length in FINGERS:
        segs.append(((x, -60.0), (x, -60.0 - length)))
    segs.append(THUMB)
    flip = -1.0 if left else 1.0
    out = []
    for a, b in segs:
        a = (a[0] * flip, a[1])
        b = (b[0] * flip, b[1])
        out.append((_rotate(a, angle_deg), _rotate(b, angle_deg)))
    return out


def mirrored_angle(angle_deg: float) -> float:
    """The angle the mirror-image hand shows. Mirroring flips the turn direction."""
    return -angle_deg
