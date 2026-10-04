"""Live webcam readout, once a second, in the terminal.

    python -m wilirehab.live_face                 camera 0, until Ctrl-C
    python -m wilirehab.live_face --show          also open a preview window (q quits)
    python -m wilirehab.live_face --seconds 90    stop after 90 s
    python -m wilirehab.live_face --log run.jsonl numbers only, never frames

Each line prints, for the last second:

    PSPI   facial pain-expression index, 0..16, mean and peak over the second,
           with the action units it is built from (see pspi.py)
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
numbers only. The same loop feeds the games' tables (python -m
wilirehab.<game> --face).
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from .discomfort import STRAIN_EASE_SUGGESTED
from .face_monitor import DEFAULT_MODEL, FaceMonitor
from .pspi import unit_scale


def _fmt(x, spec: str, none: str = "--") -> str:
    return none if x is None else format(x, spec)


def format_row(row: dict, rest_s: float) -> str:
    state = row["state"]
    if state == "no_face":
        face_txt = "NO FACE"
    elif state == "calibrating":
        face_txt = f"calibrating neutral face ({_fmt(row['calib_left'], '.0f', '?')}s)"
    else:
        face_txt = "face ok"

    if row["pspi_mean"] is not None:
        flag = ("  <-- above ease level"
                if unit_scale(row["pspi_peak"]) >= STRAIN_EASE_SUGGESTED else "")
        pspi_txt = (f"PSPI {row['pspi_mean']:4.1f} peak {row['pspi_peak']:4.1f} "
                    f"[AU4 {row['au4']:.1f} AU7 {row['au7']:.1f} AU10 {row['au10']:.1f} "
                    f"AU43 {row['au43']}]{flag}")
    else:
        pspi_txt = "PSPI  --"

    rm_txt = f"RMSSD {_fmt(row['rmssd_ms'], '.0f')}ms"
    if row["rmssd_ratio"] is not None:
        rm_txt += f" (x{row['rmssd_ratio']:.2f})"
    lf_txt = f"LF/HF {_fmt(row['lf_hf'], '.2f')}"
    if row["lf_hf_ratio"] is not None:
        lf_txt += f" (x{row['lf_hf_ratio']:.2f})"
    hr_txt = f"HR {_fmt(row['bpm'], '.0f')} bpm q{_fmt(row['hr_quality'], '.2f')}"
    return (f"{row['elapsed']:5.0f}s {row['fps']:4.1f}fps {face_txt:<26}| {pspi_txt} | "
            f"{hr_txt} | {rm_txt} {lf_txt} beats {row['beats']}")


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

    log = None
    if args.log:
        from .session import SessionLog
        log = SessionLog(args.log)

    stop = threading.Event()
    t0 = time.monotonic()

    def emit(row: dict) -> None:
        print(format_row(row, args.rest_s), flush=True)
        if log is not None:
            log.record("live", t_s=row["elapsed"], state=row["state"],
                       pspi_mean=row["pspi_mean"], pspi_peak=row["pspi_peak"],
                       bpm=row["bpm"], hr_quality=row["hr_quality"],
                       rmssd_ms=row["rmssd_ms"], lf_hf=row["lf_hf"], method=args.method)
        if args.seconds and time.monotonic() - t0 >= args.seconds:
            stop.set()

    monitor = FaceMonitor(args.camera, args.model, args.rest_s, args.method)
    print(f"camera {args.camera}: keep a neutral face for the first {args.rest_s:g} s; "
          "stay calm for the first minute. Ctrl-C to stop.\n", flush=True)
    try:
        monitor.run(stop, emit, show=args.show)
    except KeyboardInterrupt:
        pass
    finally:
        if log is not None:
            log.close()
    if monitor.error:
        print(monitor.error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
