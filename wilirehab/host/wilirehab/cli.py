"""Command-line options shared by every game.

    (nothing)              the one OG that is plugged in is found automatically
    --port COM5            use the OG on this port
    --devices devices.json an OG found by its USB serial number (only when you ask;
                           no longer the default)
    --no-og                no OG: keyboard and the five on-screen buttons only
The games use ONE OG. If several are found only one is used.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .devices import (DEFAULT_CONFIG, ROLES, assign_roles, find_og_displays,
                      load_config)


def add_common_args(ap) -> None:
    ap.add_argument("--port", help="serial port of one OG display CPU, e.g. COM5")
    ap.add_argument("--no-og", action="store_true",
                    help="run without an OG: keyboard and clicks only")
    ap.add_argument("--role", choices=ROLES, default="right_hand",
                    help="which hand the OG on --port is on (default right_hand)")
    ap.add_argument("--devices", help="roles file, only if you want an OG picked by its USB serial")
    ap.add_argument("--driver", choices=ROLES, default="right_hand",
                    help="which hand drives the game when it needs just one")
    ap.add_argument("--axis", choices=("x", "y"), default="y",
                    help="which OG axis is sideways when worn (default y)")
    ap.add_argument("--invert-roles", default="",
                    help="comma list of hands whose left and right are swapped, "
                         "e.g. left_hand or left_hand,right_hand")
    ap.add_argument("--invert-fwd-roles", default="",
                    help="comma list of hands whose forward/back tilt (pitch) is swapped")
    ap.add_argument("--log-dir", default="sessions", help="where session logs go")


def parse_roles(text: str) -> set:
    roles = {r.strip() for r in text.split(",") if r.strip()}
    unknown = roles - set(ROLES)
    if unknown:
        raise SystemExit(f"unknown role(s) {sorted(unknown)}; use {ROLES}")
    return roles


def resolve_ports(args) -> dict:
    """role -> serial port for ONE OG (the games use a single OG). May be empty.

    Order: --no-og gives none; --port names it; --devices uses a roles file;
    otherwise, if exactly one OG display CPU is plugged in, that one."""
    if getattr(args, "no_og", False):
        return {}
    ports = _find_ports(args)
    if len(ports) > 1:
        keep = args.driver if args.driver in ports else next(iter(ports))
        print(f"note: the games use one OG; using {keep} and ignoring the rest", file=sys.stderr)
        ports = {keep: ports[keep]}
    return ports


def _find_ports(args) -> dict:
    if args.port:
        return {args.role: args.port}
    path = args.devices
    if path and not Path(path).exists():
        raise SystemExit(f"{path} does not exist; run python -m wilirehab.devices --setup")
    from serial.tools import list_ports
    found = find_og_displays(list_ports.comports())
    if path:
        ports, problems = assign_roles(load_config(path), found)
        for p in problems:
            print("warning:", p, file=sys.stderr)
        return ports
    if len(found) == 1:
        print(f"Using the OG on {found[0][0]}", file=sys.stderr)
        return {args.role: found[0][0]}
    if len(found) > 1:
        raise SystemExit("More than one OG is plugged in; the games use one. "
                         "Unplug the other or pass --port COMx.")
    return {}
