"""Command-line options shared by every game.

    --port COM5            one OG, on the port you name (--role says which hand)
    --devices devices.json OGs found by USB serial number (the default when
                           devices.json exists); see python -m wilirehab.devices
    (neither)              no OG: keyboard and the five on-screen buttons only
"""
from __future__ import annotations

import sys
from pathlib import Path

from .devices import (DEFAULT_CONFIG, ROLES, assign_roles, find_og_displays,
                      load_config)


def add_common_args(ap) -> None:
    ap.add_argument("--port", help="serial port of one OG display CPU, e.g. COM5")
    ap.add_argument("--role", choices=ROLES, default="right_hand",
                    help="which hand the OG on --port is on (default right_hand)")
    ap.add_argument("--devices", help=f"roles file (default {DEFAULT_CONFIG} if it exists)")
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
    """role -> serial port, from --port or the devices file. May be empty."""
    if args.port:
        return {args.role: args.port}
    path = args.devices
    if path and not Path(path).exists():
        raise SystemExit(f"{path} does not exist; run python -m wilirehab.devices --setup")
    if not path and Path(DEFAULT_CONFIG).exists():
        path = DEFAULT_CONFIG
    if not path:
        return {}
    from serial.tools import list_ports
    mapping = load_config(path)
    ports, problems = assign_roles(mapping, find_og_displays(list_ports.comports()))
    for p in problems:
        print("warning:", p, file=sys.stderr)
    return ports
