"""Live webcam readout, once a second, in the terminal.

    python -m wilirehab.live_face                 camera 0, until Ctrl-C
    python -m wilirehab.live_face --show          also open a preview window (q quits)
    python -m wilirehab.live_face --seconds 90    stop after 90 s
    python -m wilirehab.live_face --log run.jsonl numbers only, never frames

Each line prints, for the last second:

    PSPI   facial pain-expression index, 0..16, mean and peak over the second,
           with the four action units it is built from (see pspi.py)
    HR     pulse rate from the skin colour (POS), with a 0..1 quality figure
    RMSSD, LF/HF  heart-rate variability, with the ratio to your own rest value

The first --rest-s seconds set your neutral face: keep it relaxed. The first
RMSSD (60 s) and the first LF/HF (150 s) become your HRV rest values, so stay
calm for the first minute or the later ratios compare against a stressed rest.

What this is not: it does not detect micro-expressions. It scores each frame's
face geometry against your neutral face, at the camera's frame rate, and
reports the mean and the peak of the last second. A webcam cannot resolve the
very brief expressions that term refers to. PSPI is also a lower bound here
(AU6 and AU9 are not estimated), and HRV from a webcam is noisy and falls apart
when the head moves. Treat every number as a prompt to ask the person, not a
measurement of pain. Nothing is saved unless --log is given, and --log stores
numbers only.
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np

from .discomfort import STRAIN_EASE_SUGGESTED
from .face_strain import SKIN, FaceMeasures, estimate_aus, mean_rgb, measures
from .hrv import Hrv, change_from_rest, from_pulse
from .pspi import unit_scale
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


def _fmt(x, spec: str, none: str = "--") -> str:
    return none if x is None else format(x, spec)


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--rest-s", type=float, default=10.0,
                    help="seconds of neutral face used as the baseline")
    ap.add_argument("--seconds", type=float, default=0.0, help="stop after this long (0 = until Ctrl-C)")
    ap.add_argument("--method", choices=("pos", "chrom"), default="pos")
    ap.add_argument("--show", action="store_true", help="open a preview window")
    ap.add_argument("--log", type=Path, help="append a numbers-only line per second to this file")
    args = ap.parse_args(argv)

    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    model = ensure_model(args.model)
    landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO, num_faces=1))

    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(args.camera, backend)
    if not cap.isOpened():
        print(f"cannot open camera {args.camera}", file=sys.stderr)
        return 1
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    log = None
    if args.log:
        from .session import SessionLog
        log = SessionLog(args.log)

    baseline = Baseline(args.rest_s)
    t_buf: deque = deque()
    c_buf: deque = deque()
    sec_pspi: list[float] = []
    sec_aus: list = []
    frames = 0
    t0 = time.monotonic()
    last_tick = t0
    last_face = None
    last_ts = -1
    last_hrv_at = -1e9
    hrv_now = Hrv(0, 0.0, None, None)
    rest_rmssd = rest_lfhf = None

    print(f"camera {args.camera} open. Keep a neutral face for the first "
          f"{args.rest_s:g} s; stay calm for the first minute. Ctrl-C to stop.\n", flush=True)

    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                print("camera returned no frame", file=sys.stderr)
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
                    aus = estimate_aus(baseline.face, m)
                    sec_aus.append(aus)
                    sec_pspi.append(aus.pspi())
                if args.show:
                    for i in SKIN:
                        cv2.circle(bgr, (int(pts[i][0]), int(pts[i][1])), 2, (0, 255, 0), -1)
            elif last_face is not None and now - last_face > FACE_LOST_S and t_buf:
                t_buf.clear()
                c_buf.clear()

            if now - last_tick >= 1.0:
                fps = frames / (now - last_tick)
                frames = 0
                last_tick = now
                elapsed = now - t0
                face_ok = last_face is not None and now - last_face <= FACE_LOST_S

                hr_bpm = hr_q = None
                if face_ok and len(t_buf) > 2:
                    recent = [i for i, t in enumerate(t_buf) if now - t <= HR_WINDOW_S]
                    if recent:
                        trace = resample([t_buf[i] for i in recent], [c_buf[i] for i in recent])
                        if len(trace) >= int(5 * FS):
                            hr = estimate_hr(trace, FS, args.method)
                            hr_bpm, hr_q = hr.bpm, hr.quality

                if face_ok and now - last_hrv_at >= HRV_EVERY_S and len(t_buf) > 2:
                    last_hrv_at = now
                    full = resample(list(t_buf), list(c_buf))
                    if len(full) >= int(30 * FS):
                        hrv_now = from_pulse(pulse_signal(full, FS, args.method), FS)
                        if rest_rmssd is None and hrv_now.rmssd_ms is not None:
                            rest_rmssd = hrv_now.rmssd_ms
                        if rest_lfhf is None and hrv_now.lf_hf is not None:
                            rest_lfhf = hrv_now.lf_hf
                if not face_ok:
                    hrv_now = Hrv(0, 0.0, None, None)

                ratios = change_from_rest(Hrv(0, 0.0, rest_rmssd, rest_lfhf), hrv_now)

                if not face_ok:
                    face_txt = "NO FACE"
                elif baseline.face is None:
                    face_txt = f"calibrating neutral face ({max(0.0, args.rest_s - (now - (baseline.start or now))):.0f}s)"
                else:
                    face_txt = "face ok"

                if sec_pspi:
                    mean_p, peak_p = float(np.mean(sec_pspi)), float(np.max(sec_pspi))
                    au_txt = (f"AU4 {np.mean([a.au4 for a in sec_aus]):.1f} "
                              f"AU7 {np.mean([a.au7 for a in sec_aus]):.1f} "
                              f"AU10 {np.mean([a.au10 for a in sec_aus]):.1f} "
                              f"AU43 {int(max(a.au43 for a in sec_aus))}")
                    flag = "  <-- above ease level" if unit_scale(peak_p) >= STRAIN_EASE_SUGGESTED else ""
                    pspi_txt = f"PSPI {mean_p:4.1f} peak {peak_p:4.1f} [{au_txt}]{flag}"
                else:
                    mean_p = peak_p = None
                    pspi_txt = "PSPI  --"

                rm_txt = f"RMSSD {_fmt(hrv_now.rmssd_ms, '.0f')}ms"
                if ratios["rmssd_ratio"] is not None:
                    rm_txt += f" (x{ratios['rmssd_ratio']:.2f})"
                lf_txt = f"LF/HF {_fmt(hrv_now.lf_hf, '.2f')}"
                if ratios["lf_hf_ratio"] is not None:
                    lf_txt += f" (x{ratios['lf_hf_ratio']:.2f})"
                hr_txt = f"HR {_fmt(hr_bpm, '.0f')} bpm q{_fmt(hr_q, '.2f')}"

                line = (f"{elapsed:5.0f}s {fps:4.1f}fps {face_txt:<26}| {pspi_txt} | "
                        f"{hr_txt} | {rm_txt} {lf_txt} beats {hrv_now.n_beats}")
                print(line, flush=True)
                if log is not None:
                    log.record("live", t_s=round(elapsed, 1), face=bool(face_ok),
                               pspi_mean=mean_p, pspi_peak=peak_p, bpm=hr_bpm,
                               hr_quality=hr_q, rmssd_ms=hrv_now.rmssd_ms,
                               lf_hf=hrv_now.lf_hf, method=args.method)
                sec_pspi.clear()
                sec_aus.clear()

                if args.show:
                    cv2.putText(bgr, pspi_txt[:60], (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
                    cv2.putText(bgr, hr_txt, (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)

            if args.show:
                cv2.imshow("live_face (q to quit)", bgr)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if args.seconds and now - t0 >= args.seconds:
                break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        landmarker.close()
        if args.show:
            cv2.destroyAllWindows()
        if log is not None:
            log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
