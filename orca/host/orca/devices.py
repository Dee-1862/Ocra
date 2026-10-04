"""Which OG is which hand.

COM port numbers change between runs, so roles are tied to the OG's USB serial
number. Each OG has two CPUs with different USB IDs; the display CPU
(VID 093C, PID 2055) is the one the games talk to.

    python -m orca.devices            list the OGs found and the saved roles
    python -m orca.devices --setup    press a button on each OG to assign it

The roles are saved in devices.json next to where you run it:
    {"left_hand": "<usb serial>", "right_hand": "<usb serial>", "screen": "<usb serial>"}
left_hand and right_hand are the OGs worn for the games (their accelerometers steer); "screen"
is the OG that shows the menu and the game and whose buttons you press (see og_shell).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

OG_VID = 0x093C
OG_DISPLAY_PID = 0x2055
ROLES = ("left_hand", "right_hand")          # the hands: what the games steer with
SCREEN = "screen"                            # the OG that is the display and button pad
ALL_ROLES = ROLES + (SCREEN,)
DEFAULT_CONFIG = "devices.json"


def find_og_displays(ports) -> list:
    """(device, usb_serial) for every OG display CPU in a list of serial ports."""
    return [(p.device, p.serial_number) for p in ports
            if p.vid == OG_VID and p.pid == OG_DISPLAY_PID and p.serial_number]


OG_MAIN_PID = 0x2054


def find_og_mains(ports) -> list:
    """(device, usb_serial) for every OG *main* CPU (the one the magnetometer is wired to)."""
    return [(p.device, p.serial_number) for p in ports
            if p.vid == OG_VID and p.pid == OG_MAIN_PID]


def load_config(path) -> dict:
    """role -> usb serial. Empty if the file is missing; ValueError if it is wrong."""
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object of role: serial")
    for role, serial in data.items():
        if role not in ALL_ROLES:
            raise ValueError(f"{path}: unknown role {role!r}; use {ALL_ROLES}")
        if not isinstance(serial, str) or not serial:
            raise ValueError(f"{path}: the serial for {role} must be text")
    if len(set(data.values())) != len(data):
        raise ValueError(f"{path}: two roles share one serial number")
    return data


def save_config(path, mapping: dict) -> None:
    Path(path).write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")


def assign_roles(mapping: dict, found: list):
    """-> (role -> serial port device, list of problems).

    `found` is [(device, usb_serial)]. A role whose OG is not plugged in is a
    problem, not a crash: the game still runs with the others.
    """
    by_serial = {serial: device for device, serial in found}
    ports, problems = {}, []
    for role, serial in mapping.items():
        if serial in by_serial:
            ports[role] = by_serial[serial]
        else:
            problems.append(f"{role}: OG with serial {serial} is not connected")
    known = set(mapping.values())
    for device, serial in found:
        if serial not in known:
            problems.append(f"{device} (serial {serial}) has no role; run "
                            f"python -m orca.devices --setup")
    return ports, problems


def plan_ports(found: list, mapping: dict, screen: str = None, left: str = None,
               right: str = None):
    """Decide which OG does what -> (screen port or None, {hand role: port}, notes).

    Explicit ports win. Otherwise the saved roles are used. With no saved roles, a single OG is
    both the screen and the controller (the original one-OG way); several OGs with no roles
    are not guessed at, because a guess would swap the hands.
    """
    if screen or left or right:
        hands = {role: port for role, port in (("left_hand", left), ("right_hand", right)) if port}
        return screen, hands, []
    if mapping:
        ports, notes = assign_roles(mapping, found)
        if SCREEN not in ports:
            notes.append("no OG has the screen role, so the menu shows on the laptop only")
        return ports.get(SCREEN), {r: ports[r] for r in ROLES if r in ports}, notes
    if len(found) == 1:
        return found[0][0], {}, []
    notes = []
    if len(found) > 1:
        notes.append("several OGs are plugged in but none has a role yet; run "
                     "python -m orca.devices --setup")
    return None, {}, notes


def press_in(buffer: bytes) -> bool:
    """True if the bytes read so far contain a button-down line."""
    text = buffer.decode("ascii", "replace")
    return any(line.split()[:1] == ["BTN"] and line.split()[-1:] == ["down"]
               for line in text.splitlines())


def identify_by_press(found: list, roles=ROLES, timeout_s: float = 30.0,
                      out=print) -> dict:
    """Ask for a button press on each role's OG in turn; returns role -> serial.

    Needs the OGs running the orca firmware (it prints BTN lines).
    """
    import serial  # pyserial
    sers = {s: serial.Serial(d, 115200, timeout=0) for d, s in found}
    mapping = {}
    try:
        for role in roles:
            out(f"Press any button on the {role.replace('_', ' ')} OG now...")
            for ser in sers.values():
                ser.reset_input_buffer()
            buffers = {s: b"" for s in sers}
            deadline = time.monotonic() + timeout_s
            winner = None
            while winner is None and time.monotonic() < deadline:
                for s, ser in sers.items():
                    buffers[s] += ser.read(4096)
                    if s not in mapping.values() and press_in(buffers[s]):
                        winner = s
                        break
                time.sleep(0.02)
            if winner is None:
                out(f"No press seen for {role}; skipping it.")
                continue
            mapping[role] = winner
            out(f"  -> {role} = serial {winner}")
    finally:
        for ser in sers.values():
            ser.close()
    return mapping


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Assign OGs to hands")
    ap.add_argument("--setup", action="store_true",
                    help="press a button on each OG to assign it, then save")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args(argv)

    from serial.tools import list_ports
    found = find_og_displays(list_ports.comports())
    print(f"OG display CPUs found: {len(found)}")
    for device, serial_no in found:
        print(f"  {device}  serial {serial_no}")

    if args.setup:
        if len(found) < 1:
            print("No OG found. Plug one in (running the Orca firmware).")
            return 1
        mapping = identify_by_press(found, ALL_ROLES[:max(1, min(len(found), len(ALL_ROLES)))])
        if not mapping:
            print("Nothing assigned; the config was not changed.")
            return 1
        save_config(args.config, mapping)
        print(f"Saved {args.config}")
    mapping = load_config(args.config)
    ports, problems = assign_roles(mapping, found)
    print(f"Roles in {args.config}:")
    for role in ALL_ROLES:
        print(f"  {role}: {ports.get(role, '-')}")
    for p in problems:
        print("  warning:", p, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
