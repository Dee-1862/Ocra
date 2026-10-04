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
"""
from __future__ import annotations

import argparse
import csv
import queue
import sys
import time

from .mag_accel import (ACCEL_CHANGE_MG, MAG_CHANGE_UT, PHASES, classify, norm, raw_to_ut,
                        simulate_phase, summarize, vector_change_rms)
from .mag_link import MagLink
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


def run_watch(args) -> bool:
    """Two live meters, one line a second, for testing each sensor on its own.

    The accelerometer and the magnetometer are judged separately, so they do not have
    to be fixed together: move one and keep the other still, then swap.
    """
    og_port, mag_port = pick_ports(args)
    events: queue.Queue = queue.Queue()
    OgLink(og_port, events, role="og", on_connect=("STREAM 50",)).start()
    MagLink(mag_port, events, role="mag").start()
    print(f"Accelerometer on {og_port}, magnetometer on {mag_port}. One line a second; Ctrl-C stops.")
    print(f"'moving' means the accelerometer changed by {ACCEL_CHANGE_MG:.0f} mg or more, "
          f"or the magnetometer by {MAG_CHANGE_UT:.0f} uT or more, within that second.")
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
                a_text = "no data" if not accel else (
                    f"{vector_change_rms(accel):5.0f} mg  "
                    f"{'MOVING' if vector_change_rms(accel) >= ACCEL_CHANGE_MG else 'still '}")
                m_text = "no data" if not mag else (
                    f"{vector_change_rms(mag):5.1f} uT  "
                    f"{'MOVING' if vector_change_rms(mag) >= MAG_CHANGE_UT else 'still '}")
                strength = (sum(norm(v) for v in mag) / len(mag)) if mag else float("nan")
                print(f"accelerometer {a_text:>20} | magnetometer {m_text:>20} | "
                      f"|B| {strength:5.1f} uT | readings {len(accel):3d} / {len(mag):3d}")
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
    ap.add_argument("--watch", action="store_true",
                    help="live meters for each sensor on its own (they need not be fixed together)")
    args = ap.parse_args()
    ok = run_simulated() if args.simulate else run_watch(args) if args.watch else run_live(args)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
