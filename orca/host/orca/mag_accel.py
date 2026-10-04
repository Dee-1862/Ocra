"""Telling apart what an accelerometer and a magnetometer respond to. Pure logic.

The two sensors react to different physical causes:

    accelerometer   gravity's direction and any push or shake of the sensor itself
    magnetometer    the direction and strength of the magnetic field around it

So five simple actions leave different fingerprints:

    action                         accelerometer      magnetometer
    held still                     steady             steady
    spun flat, like a turntable    steady             changes direction, same strength
    tilted                         changes direction  changes direction, same strength
    shaken without turning         jolts              steady
    a magnet or steel brought near steady             changes, and the strength changes

The tester asks for each action in turn, measures both sensors, and checks the
fingerprint. No frame alignment between the two sensors is needed: every measure
here is a size of change, not a direction.

The BMM350 conversion uses Bosch's default coefficients (BMM350_SensorAPI,
bmm350.c, update_default_coefiecents) without the chip's factory trim, so values
are uncompensated: relative changes are meaningful, absolute microtesla are not.
"""
from __future__ import annotations

import math
import random

# BMM350: microtesla per raw count (Bosch default coefficients).
UT_PER_LSB_XY = 0.007069979
UT_PER_LSB_Z = 0.007174964
DEG_C_PER_LSB = 1.0 / (0.00204 * (1 / 1.5) * 0.714607238769531 * 1048576)
TEMP_OFFSET_C = 25.49

# Thresholds for deciding "this sensor changed". The accelerometer figure is about
# 4.6 degrees of tilt; the magnetometer figure is a few times the sensor noise.
ACCEL_CHANGE_MG = 80.0
MAG_CHANGE_UT = 3.0
MAG_STRENGTH_CHANGE_PCT = 25.0


def parse_mag_line(line: str):
    """'MAG seq t_ms x y z temp drdy' -> dict, or None if it is not one."""
    p = line.split()
    if len(p) != 8 or p[0] != "MAG":
        return None
    try:
        seq, t_ms, x, y, z, temp, drdy = (int(v) for v in p[1:])
    except ValueError:
        return None
    return {"seq": seq, "t_ms": t_ms, "raw": (x, y, z), "raw_temp": temp, "drdy": drdy}


def raw_to_ut(x: int, y: int, z: int):
    """Raw counts -> (x, y, z) in microtesla, uncompensated."""
    return x * UT_PER_LSB_XY, y * UT_PER_LSB_XY, z * UT_PER_LSB_Z


def raw_temp_to_c(raw_temp: int) -> float:
    return raw_temp * DEG_C_PER_LSB - TEMP_OFFSET_C


def norm(v) -> float:
    return math.sqrt(sum(c * c for c in v))


def _mean_vec(vectors):
    n = len(vectors)
    return tuple(sum(v[i] for v in vectors) / n for i in range(3))


def vector_change_rms(vectors) -> float:
    """How much a stream of 3D vectors moves about its own average (RMS size)."""
    if not vectors:
        return 0.0
    m = _mean_vec(vectors)
    return math.sqrt(sum(sum((v[i] - m[i]) ** 2 for i in range(3)) for v in vectors) / len(vectors))


def _percentile(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, int(p / 100.0 * len(s)))]


def summarize(samples) -> dict:
    """samples: list of (accel (x, y, z) in mg, mag (x, y, z) in uT)."""
    if not samples:
        return {"n": 0}
    accel = [a for a, _ in samples]
    mag = [m for _, m in samples]
    strengths = [norm(m) for m in mag]
    mean_strength = sum(strengths) / len(strengths)
    spread = _percentile(strengths, 95) - _percentile(strengths, 5)
    return {
        "n": len(samples),
        "accel_change_mg": vector_change_rms(accel),
        "mag_change_ut": vector_change_rms(mag),
        "mag_strength_ut": mean_strength,
        "mag_strength_change_pct": 100.0 * spread / mean_strength if mean_strength else 0.0,
        "accel_strength_mg": sum(norm(a) for a in accel) / len(accel),
    }


def classify(summary: dict) -> str:
    """Which action the fingerprint looks like."""
    if not summary.get("n"):
        return "no data"
    accel_moves = summary["accel_change_mg"] >= ACCEL_CHANGE_MG
    mag_moves = summary["mag_change_ut"] >= MAG_CHANGE_UT
    if not accel_moves and not mag_moves:
        return "still"
    if not accel_moves:
        if summary["mag_strength_change_pct"] >= MAG_STRENGTH_CHANGE_PCT:
            return "magnetic disturbance"
        return "turning flat"
    if not mag_moves:
        return "shaking"
    return "tilting"


# name, instruction, seconds, what it should look like
PHASES = (
    ("still", "Hold the sensors still on the table.", 6.0, "still"),
    ("spin", "Spin them flat, like a turntable. Keep them level.", 8.0, "turning flat"),
    ("tilt", "Tilt them forward, back and side to side. Do not spin them.", 8.0, "tilting"),
    ("shake", "Shake them back and forth. Keep them pointing the same way.", 6.0, "shaking"),
    ("magnet", "Move a magnet or a steel object near the magnetometer, in and out.", 8.0,
     "magnetic disturbance"),
)


# ---- a simulator, so the expected pattern can be seen without any hardware ----

def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def body_vectors(heading_deg: float, pitch_deg: float, roll_deg: float,
                 field_horizontal_ut: float = 20.0, field_vertical_ut: float = 45.0):
    """(accel in mg, mag in uT) a sensor reads when held at this attitude.

    World axes are east, north, up. The sensor's z axis is up when it lies flat, so
    it reads +1 g on z (like the OG). Heading is clockwise from north; pitch is the
    elevation of the sensor's x axis; roll is the tilt of its y axis.
    """
    h, p, r = (math.radians(v) for v in (heading_deg, pitch_deg, roll_deg))
    r0 = [[math.sin(h), -math.cos(h), 0.0],       # columns are the heading frame's axes
          [math.cos(h), math.sin(h), 0.0],
          [0.0, 0.0, 1.0]]
    ry = [[math.cos(p), 0.0, -math.sin(p)], [0.0, 1.0, 0.0], [math.sin(p), 0.0, math.cos(p)]]
    rx = [[1.0, 0.0, 0.0], [0.0, math.cos(r), -math.sin(r)], [0.0, math.sin(r), math.cos(r)]]
    rot = _matmul(_matmul(r0, ry), rx)            # sensor axes in world coordinates
    gravity_world = (0.0, 0.0, 1000.0)
    field_world = (0.0, field_horizontal_ut, -field_vertical_ut)
    accel = tuple(sum(rot[j][k] * gravity_world[j] for j in range(3)) for k in range(3))
    mag = tuple(sum(rot[j][k] * field_world[j] for j in range(3)) for k in range(3))
    return accel, mag


def simulate_phase(name: str, seconds: float = 8.0, rate: float = 50.0, seed: int = 1):
    """Samples (accel mg, mag uT) for one of the PHASES, with realistic-size noise."""
    rng = random.Random(seed)
    out = []
    for i in range(int(seconds * rate)):
        t = i / rate
        heading, pitch, roll = 40.0, 5.0, 3.0
        extra_a = (0.0, 0.0, 0.0)
        extra_m = (0.0, 0.0, 0.0)
        if name == "spin":
            heading += 60.0 * t
        elif name == "tilt":
            pitch += 30.0 * math.sin(2 * math.pi * 0.4 * t)
            roll += 25.0 * math.sin(2 * math.pi * 0.3 * t)
        elif name == "shake":
            extra_a = (400.0 * math.sin(2 * math.pi * 6.0 * t), 0.0, 0.0)
        elif name == "magnet":
            extra_m = (45.0 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.3 * t)), 0.0, 0.0)
        a, m = body_vectors(heading, pitch, roll)
        a = tuple(a[k] + extra_a[k] + rng.gauss(0, 4.0) for k in range(3))
        m = tuple(m[k] + extra_m[k] + rng.gauss(0, 0.5) for k in range(3))
        out.append((a, m))
    return out
