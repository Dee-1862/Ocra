"""The webcam loop behind both `live_face` (terminal) and the games (tables).

`FaceMonitor.run(stop, emit)` opens the camera, finds the face with MediaPipe,
and calls `emit(row)` once a second with a flat dict of numbers. Rows are
stamped `mono` with time.monotonic() at capture, so a caller on another thread
can place them on its own timeline (see DataTable.from_clock). No frame, patch
or landmark leaves this module.

Row keys: mono, elapsed, fps, state ("no_face" | "calibrating" | "ok"),
calib_left, pspi_mean, pspi_peak, au4, au7, au10, au43, bpm, hr_quality,
rmssd_ms, rmssd_ratio, lf_hf, lf_hf_ratio, beats.

Limits (also in live_face's docstring): per-frame geometry at the camera's
frame rate, not micro-expression detection; PSPI is a lower bound; webcam HRV
is noisy and fails when the head moves.
"""
from __future__ import annotations

import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np

from .face_strain import (SKIN, FaceMeasures, SmoothedAUs, estimate_aus, mean_rgb,
                          measures)
from .hrv import Hrv, change_from_rest, from_pulse
from .rppg import estimate_hr, pulse_signal

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")
DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"

FS = 30.0              # the rate the colour trace is resampled to
HR_WINDOW_S = 10.0
HRV_WINDOW_S = 180.0
HRV_EVERY_S = 5.0
FACE_LOST_S = 1.0
PATCH_RADIUS = 4


def resample(times, values, fs: float = FS):
    """Colour samples at irregular times -> an (N, 3) trace at `fs` Hz."""
    t = np.asarray(times, float)
    v = np.asarray(values, float)
    if len(t) < 2:
        return np.empty((0, 3))
    grid = np.arange(t[0], t[-1], 1.0 / fs)
    return np.stack([np.interp(grid, t, v[:, i]) for i in range(3)], axis=1)


def ensure_model(path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading the face landmark model to {path} ...", flush=True)
    urllib.request.urlretrieve(MODEL_URL, path)
    return path


class Baseline:
    """Median neutral-face measures over the first `seconds` of faces."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self.start = None
        self.samples: list[FaceMeasures] = []
        self.face: FaceMeasures | None = None

    def add(self, now: float, m: FaceMeasures) -> None:
        if self.face is not None:
            return
        if self.start is None:
            self.start = now
        self.samples.append(m)
        if now - self.start >= self.seconds and len(self.samples) >= 10:
            self.face = FaceMeasures(
                float(np.median([s.ear for s in self.samples])),
                float(np.median([s.brow for s in self.samples])),
                float(np.median([s.nose_lip for s in self.samples])))


def _r(value, digits):
    return None if value is None else round(float(value), digits)


class FaceMonitor:
    def __init__(self, camera: int = 0, model: Path = DEFAULT_MODEL, rest_s: float = 10.0,
                 method: str = "pos"):
        self.camera, self.model, self.rest_s, self.method = camera, Path(model), rest_s, method
        self.error: str | None = None

    def run(self, stop: threading.Event, emit, show: bool = False) -> None:
        """Blocks until `stop` is set (or the camera fails; see `self.error`).

        `show=True` opens a preview window and must be called from the main thread.
        """
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model(self.model))),
            running_mode=vision.RunningMode.VIDEO, num_faces=1))
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.camera, backend)
        if not cap.isOpened():
            self.error = f"cannot open camera {self.camera}"
            landmarker.close()
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        baseline = Baseline(self.rest_s)
        smoother = SmoothedAUs()
        t_buf: deque = deque()
        c_buf: deque = deque()
        sec_aus: list = []
        frames = 0
        t0 = last_tick = time.monotonic()
        last_face = None
        last_ts = -1
        last_hrv_at = -1e9
        hrv_now = Hrv(0, 0.0, None, None)
        rest_rmssd = rest_lfhf = None

        try:
            while not stop.is_set():
                ok, bgr = cap.read()
                if not ok:
                    self.error = "camera returned no frame"
                    break
                now = time.monotonic()
                frames += 1
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                height, width = rgb.shape[:2]
                ts = max(int((now - t0) * 1000), last_ts + 1)
                last_ts = ts
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

                if result.face_landmarks:
                    pts = [(p.x * width, p.y * height) for p in result.face_landmarks[0]]
                    last_face = now
                    color = mean_rgb(rgb, pts, SKIN, PATCH_RADIUS)
                    if color is not None:
                        t_buf.append(now)
                        c_buf.append(color)
                        while t_buf and now - t_buf[0] > HRV_WINDOW_S:
                            t_buf.popleft()
                            c_buf.popleft()
                    m = measures(pts)
                    baseline.add(now, m)
                    if baseline.face is not None:
                        sec_aus.append(smoother.add(estimate_aus(baseline.face, m)))
                    if show:
                        for i in SKIN:
                            cv2.circle(bgr, (int(pts[i][0]), int(pts[i][1])), 2, (0, 255, 0), -1)
                elif last_face is not None and now - last_face > FACE_LOST_S and t_buf:
                    t_buf.clear()
                    c_buf.clear()
                    smoother.reset()

                if now - last_tick >= 1.0:
                    fps = frames / (now - last_tick)
                    frames = 0
                    last_tick = now
                    face_ok = last_face is not None and now - last_face <= FACE_LOST_S

                    bpm = quality = None
                    if face_ok and len(t_buf) > 2:
                        recent = [i for i, t in enumerate(t_buf) if now - t <= HR_WINDOW_S]
                        if recent:
                            trace = resample([t_buf[i] for i in recent], [c_buf[i] for i in recent])
                            if len(trace) >= int(5 * FS):
                                hr = estimate_hr(trace, FS, self.method)
                                bpm, quality = hr.bpm, hr.quality

                    if face_ok and now - last_hrv_at >= HRV_EVERY_S and len(t_buf) > 2:
                        last_hrv_at = now
                        full = resample(list(t_buf), list(c_buf))
                        if len(full) >= int(30 * FS):
                            hrv_now = from_pulse(pulse_signal(full, FS, self.method), FS)
                            if rest_rmssd is None and hrv_now.rmssd_ms is not None:
                                rest_rmssd = hrv_now.rmssd_ms
                            if rest_lfhf is None and hrv_now.lf_hf is not None:
                                rest_lfhf = hrv_now.lf_hf
                    if not face_ok:
                        hrv_now = Hrv(0, 0.0, None, None)
                    ratios = change_from_rest(Hrv(0, 0.0, rest_rmssd, rest_lfhf), hrv_now)

                    if not face_ok:
                        state, calib_left = "no_face", None
                    elif baseline.face is None:
                        state = "calibrating"
                        calib_left = max(0.0, self.rest_s - (now - (baseline.start or now)))
                    else:
                        state, calib_left = "ok", 0.0

                    row = {"mono": now, "elapsed": _r(now - t0, 1), "fps": _r(fps, 1),
                           "state": state, "calib_left": _r(calib_left, 0),
                           "pspi_mean": None, "pspi_peak": None, "au4": None, "au7": None,
                           "au10": None, "au43": None,
                           "bpm": _r(bpm, 0), "hr_quality": _r(quality, 2),
                           "rmssd_ms": _r(hrv_now.rmssd_ms, 0),
                           "rmssd_ratio": _r(ratios["rmssd_ratio"], 2),
                           "lf_hf": _r(hrv_now.lf_hf, 2),
                           "lf_hf_ratio": _r(ratios["lf_hf_ratio"], 2),
                           "beats": hrv_now.n_beats}
                    if sec_aus:
                        scores = [a.pspi() for a in sec_aus]
                        row.update(
                            pspi_mean=_r(np.mean(scores), 1), pspi_peak=_r(np.max(scores), 1),
                            au4=_r(np.mean([a.au4 for a in sec_aus]), 1),
                            au7=_r(np.mean([a.au7 for a in sec_aus]), 1),
                            au10=_r(np.mean([a.au10 for a in sec_aus]), 1),
                            au43=int(max(a.au43 for a in sec_aus)))
                    sec_aus.clear()
                    emit(row)

                if show:
                    cv2.imshow("live_face (q to quit)", bgr)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        stop.set()
        finally:
            cap.release()
            landmarker.close()
            if show:
                cv2.destroyAllWindows()
