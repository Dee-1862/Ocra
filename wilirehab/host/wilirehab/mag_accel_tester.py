"""Tester: shows how the magnetometer and the accelerometer respond differently.

Fix the BMM350 board to the OG (tape or a rubber band) so they always move
together, with the BMM350 wired as in Card 20 and the WiliRehab firmware running.
Then, from wilirehab/host:

    python -m wilirehab.mag_accel_tester --og-port COM5 --mag-port COM4

COM5 is the OG's display CPU (product ID 2055: the accelerometer) and COM4 its
main CPU (2054: the magnetometer). If you omit --mag-port and exactly one main CPU
is found, it is used; with --devices devices.json the OG is found by its hand role.

It asks for five actions in turn: still, spun flat, tilted, shaken, and a magnet or
steel object brought near. For each it measures how much each sensor's reading
changed and prints a table. The expected pattern is in mag_accel.py; the table says
whether each action looked the way it should.

    python -m wilirehab.mag_accel_tester --simulate

shows the expected table from simulated data, with no hardware at all.
Add --csv-out file.csv to keep every paired reading.

    python -m wilirehab.mag_accel_tester --calibrate --mag-port COM4
    python -m wilirehab.mag_accel_tester --watch --og-port COM5 --mag-port COM4

--calibrate finds the magnetometer's fixed offset (turn the board through every
orientation for 25 s) and saves it. --watch then says once a second whether the board
is sliding up/down, sliding sideways, turning/tilting, or still, using both sensors.
"""
from __future__ import annotations

import argparse
import csv
import json
import queue
import sys
import time
from pathlib import Path

from .mag_accel import (ACCEL_CHANGE_MG, MAG_CHANGE_UT, PHASES, classify, norm, raw_to_ut,
                        simulate_phase, summarize, vector_change_rms)
from .mag_link import MagLink
from .motion_split import (TURN_DEG, describe_motion, estimate_tilt_mg, fit_sphere_offset,
                           mag_turn_deg, split_accel_motion)
from .og_link import OgLink
from .tilt import raw_to_mg


def print_table(results) -> bool:
    head = (f"{'action':8} {'accel change':>13} {'mag change':>11} {'|B| uT':>8} "
            f"{'|B| change':>11}  {'looked like':<22} {'expected':<22} ok")
    print("\n" + head)
    print("-" * len(head))
    all_ok = True
    for name, summary, expected in results:
        if not summary.get("n"):
            print(f"{name:8} no data")
            all_ok = False
            continue
        label = classify(summary)
        ok = label == expected
        all_ok = all_ok and ok
        print(f"{name:8} {summary['accel_change_mg']:10.0f} mg {summary['mag_change_ut']:8.1f} uT "
              f"{summary['mag_strength_ut']:8.1f} {summary['mag_strength_change_pct']:9.0f} %  "
              f"{label:<22} {expected:<22} {'yes' if ok else 'NO'}")
    print("\n'change' is how far the reading moves about its own average. Accelerometer: "
          "gravity direction and shaking. Magnetometer: field direction and strength.")
    return all_ok


def run_simulated() -> bool:
    print("SIMULATED data (no hardware): the pattern a working pair should show.")
    results = [(name, summarize(simulate_phase(name)), expected)
               for name, _text, _secs, expected in PHASES]
    return print_table(results)


def collect(events: queue.Queue, seconds: float, latest_accel: list, writer, stats=None) -> list:
    """Pair each magnetometer sample with the newest accelerometer sample for a while.
    `stats`, if given, counts what arrived: acc lines, mag lines and status messages."""
    samples = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            kind, value, _role = events.get(timeout=0.1)
        except queue.Empty:
            continue
        if stats is not None:
            stats[kind] = stats.get(kind, 0) + 1
        if kind == "acc":
            _seq, _t_ms, x, y, z = value
            latest_accel[:] = [(raw_to_mg(x), raw_to_mg(y), raw_to_mg(z))]
        elif kind == "mag" and latest_accel:
            mag = raw_to_ut(*value["raw"])
            samples.append((latest_accel[0], mag))
            if writer:
                writer.writerow([time.monotonic(), *latest_accel[0], *mag])
        elif kind == "status":
            print("  ", value)
    return samples


def drain(events: queue.Queue, latest_accel: list) -> None:
    while True:
        try:
            kind, value, _role = events.get_nowait()
        except queue.Empty:
            return
        if kind == "acc":
            _s, _t, x, y, z = value
            latest_accel[:] = [(raw_to_mg(x), raw_to_mg(y), raw_to_mg(z))]


def pick_ports(args):
    from serial.tools import list_ports
    from .devices import find_og_displays, find_og_mains
    ports = list_ports.comports()
    og = args.og_port
    if not og:
        displays = find_og_displays(ports)
        if len(displays) == 1:
            og = displays[0][0]
        elif displays:
            sys.exit("More than one OG found: pass --og-port COMx.")
    mag = args.mag_port
    if og and mag and og == mag:
        sys.exit(f"--og-port and --mag-port are both {og}. They are different CPUs on the "
                 f"OG with different ports (display 2055, main 2054).")
    if not mag:
        mains = find_og_mains(ports)
        if len(mains) == 1:
            mag = mains[0][0]
        else:
            sys.exit(f"Found {len(mains)} OG main CPUs: pass --mag-port COMx.")
    if not og:
        sys.exit("No OG display CPU found: pass --og-port COMx.")
    return og, mag


def run_live(args) -> bool:
    og_port, mag_port = pick_ports(args)
    events: queue.Queue = queue.Queue()
    OgLink(og_port, events, role="og", on_connect=("STREAM 50",)).start()
    MagLink(mag_port, events, role="mag").start()
    latest_accel: list = []
    out = open(args.csv_out, "w", newline="", encoding="utf-8") if args.csv_out else None
    writer = csv.writer(out) if out else None
    if writer:
        writer.writerow(["t", "ax_mg", "ay_mg", "az_mg", "mx_ut", "my_ut", "mz_ut"])

    print(f"Accelerometer on {og_port}, magnetometer on {mag_port}. Checking both are streaming...")
    stats: dict = {}
    warm = collect(events, 5.0, latest_accel, None, stats)
    if not warm:
        n_acc, n_mag, n_msg = stats.get("acc", 0), stats.get("mag", 0), stats.get("status", 0)
        print(f"No paired readings. In 5 s: {n_acc} accelerometer lines, {n_mag} magnetometer "
              f"lines, {n_msg} status messages.")
        if n_acc == 0:
            print("  - No accelerometer lines from", og_port, ": it must be the OG's DISPLAY CPU "
                  "(product ID 2055) running the WiliRehab firmware. Re-list ports with "
                  "python -m serial.tools.list_ports -v: port numbers can change after a flash.")
        if n_mag == 0:
            print("  - No magnetometer lines from", mag_port, ": it must be the OG's MAIN CPU "
                  "(product ID 2054) running the NEW wilirehab_main firmware. Check with "
                  "python tools/fw.py console --port", mag_port, "- you should see 'I2C0 devices' "
                  "lines every 2 s and then 'BMM350 running'. No lines at all usually means the "
                  "new main firmware has not been flashed.")
        return False
    strength = sum(sum(c * c for c in m) ** 0.5 for _a, m in warm) / len(warm)
    accel_strength = sum(sum(c * c for c in a) ** 0.5 for a, _m in warm) / len(warm)
    print(f"Sanity: gravity {accel_strength:.0f} mg (about 1000 expected when still), "
          f"field {strength:.0f} uT (roughly 25 to 65 expected, uncompensated).")

    results = []
    for name, text, seconds, expected in PHASES:
        reply = input(f"\n[{name}] {text}\n  Press Enter to start ({seconds:.0f} s), or type s to skip: ")
        if reply.strip().lower() == "s":
            continue
        drain(events, latest_accel)
        print("  GO")
        samples = collect(events, seconds, latest_accel, writer)
        print(f"  done ({len(samples)} readings)")
        results.append((name, summarize(samples), expected))
    if out:
        out.close()
    return print_table(results)


OFFSET_FILE = "mag_offset.json"


def load_offset(path=OFFSET_FILE):
    """The saved magnetometer offset as (x, y, z) in uT, or None if there is none."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        o = json.loads(p.read_text(encoding="utf-8"))["offset"]
        return (float(o[0]), float(o[1]), float(o[2]))
    except (ValueError, KeyError, TypeError, IndexError):
        return None


def pick_mag_port(args):
    from serial.tools import list_ports
    from .devices import find_og_mains
    if args.mag_port:
        return args.mag_port
    mains = find_og_mains(list_ports.comports())
    if len(mains) == 1:
        return mains[0][0]
    sys.exit(f"Found {len(mains)} OG main CPUs: pass --mag-port COMx.")


def run_calibrate(args) -> bool:
    """Turn the board through every orientation; the centre of the readings is the offset."""
    mag_port = pick_mag_port(args)
    events: queue.Queue = queue.Queue()
    MagLink(mag_port, events, role="mag").start()
    print(f"Magnetometer on {mag_port}.")
    print("Keep it away from the laptop, metal and magnets. When it says GO, turn the board")
    print("slowly through EVERY orientation for 25 seconds: flip it over, spin it, point each")
    print("edge up and down. Aim to cover all directions, not just a few.")
    input("Press Enter to start: ")
    print("GO")
    readings = []
    end = time.monotonic() + 25.0
    next_note = time.monotonic() + 5.0
    while time.monotonic() < end:
        try:
            kind, value, _role = events.get(timeout=0.1)
        except queue.Empty:
            kind = None
        if kind == "mag":
            readings.append(raw_to_ut(*value["raw"]))
        elif kind == "status":
            print("  ", value)
        if time.monotonic() >= next_note:
            next_note += 5.0
            print(f"  {int(end - time.monotonic())} s left, {len(readings)} readings")
    try:
        offset, radius, err = fit_sphere_offset(readings)
    except ValueError as exc:
        print("Could not calibrate:", exc)
        return False
    print(f"Offset (uT): x {offset[0]:.1f}  y {offset[1]:.1f}  z {offset[2]:.1f}")
    print(f"Field strength after removing it: {radius:.1f} uT (Earth's is roughly 25 to 65)")
    print(f"Fit error: {err:.1f} uT")
    if not 15.0 <= radius <= 90.0:
        print("That strength is outside the normal range: there may be a magnet or steel close "
              "by, or not all orientations were covered. Try again somewhere clearer.")
    if err > 0.2 * radius:
        print("The fit is poor (the readings do not lie on a sphere): turn it through more "
              "orientations and keep it away from metal.")
    Path(OFFSET_FILE).write_text(json.dumps({"offset": list(offset), "radius_ut": radius}),
                                 encoding="utf-8")
    print(f"Saved {OFFSET_FILE}. --watch uses it from now on.")
    return True


def run_watch(args) -> bool:
    """Live: one line a second saying whether the board is sliding up/down, sliding
    sideways, turning, or still, using both sensors. They need not be fixed together
    to read each on its own, but they must be for the phrase to be meaningful."""
    og_port, mag_port = pick_ports(args)
    offset = load_offset()
    events: queue.Queue = queue.Queue()
    OgLink(og_port, events, role="og", on_connect=("STREAM 50",)).start()
    MagLink(mag_port, events, role="mag").start()
    print(f"Accelerometer on {og_port}, magnetometer on {mag_port}. One line a second; Ctrl-C stops.")
    if offset is None:
        print("No magnetometer calibration yet (run with --calibrate once). Until then, turning is "
              "judged from how much the field readings change, which is much less sensitive.")
    else:
        print(f"Using the saved magnetometer offset from {OFFSET_FILE}.")
    print("Fix the two boards together, then try: slide it up and down; slide it sideways; turn it.")
    print("A slide is only felt while it speeds up or slows down; a slow smooth move is hard to see.")
    print()
    accel, mag = [], []
    next_report = time.monotonic() + 1.0
    try:
        while True:
            try:
                kind, value, _role = events.get(timeout=0.1)
            except queue.Empty:
                kind = None
            if kind == "acc":
                _s, _t, x, y, z = value
                accel.append((raw_to_mg(x), raw_to_mg(y), raw_to_mg(z)))
            elif kind == "mag":
                mag.append(raw_to_ut(*value["raw"]))
            elif kind == "status":
                print("  ", value)
            if time.monotonic() >= next_report:
                next_report += 1.0
                if accel and mag:
                    vertical, horizontal = split_accel_motion(accel)
                    if offset is not None:
                        turn = mag_turn_deg(mag, offset)
                        turned = turn >= TURN_DEG
                        mag_text = f"field turned {turn:5.1f} deg"
                    else:
                        change = vector_change_rms(mag)
                        turned = change >= MAG_CHANGE_UT
                        mag_text = f"field changed {change:5.1f} uT"
                    tilt = estimate_tilt_mg(turn if offset is not None else None,
                                            None if offset is not None else change)
                    phrase = describe_motion(vertical, horizontal, tilt, turned)
                    print(f"accelerometer: up/down {vertical:4.0f} mg, sideways {horizontal:4.0f} mg"
                          f" | {mag_text} | turn explains ~{tilt:3.0f} mg | {phrase}")
                else:
                    print(f"no data this second (accelerometer {len(accel)}, magnetometer {len(mag)})")
                accel, mag = [], []
    except KeyboardInterrupt:
        print()
        print("Stopped.")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Magnetometer vs accelerometer tester")
    ap.add_argument("--simulate", action="store_true", help="show the expected table, no hardware")
    ap.add_argument("--og-port", help="OG display CPU serial port (accelerometer)")
    ap.add_argument("--mag-port", help="OG main CPU serial port (magnetometer)")
    ap.add_argument("--csv-out", help="write every paired reading to this CSV")
    ap.add_argument("--calibrate", action="store_true",
                    help="find the magnetometer's fixed offset by turning it through every direction")
    ap.add_argument("--watch", action="store_true",
                    help="live meters for each sensor on its own (they need not be fixed together)")
    args = ap.parse_args()
    if args.calibrate:
        ok = run_calibrate(args)
    elif args.simulate:
        ok = run_simulated()
    elif args.watch:
        ok = run_watch(args)
    else:
        ok = run_live(args)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
