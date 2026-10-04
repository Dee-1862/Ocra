"""Turn one OG's screen half a turn (or back), straight from the command line.

    python -m orca.og_rotate COM5 180      turn it upside down
    python -m orca.og_rotate COM5 0        back to normal

COM5 is that OG's DISPLAY CPU port (USB ID 093C:2055; see python -m serial.tools.list_ports -v).
Close the shell and any game first: only one program can hold the port. This sends the same ROT
command the games send, so it also tells you whether the OG's firmware knows it. The turn lasts
until that OG restarts.
"""
from __future__ import annotations

import argparse
import time


def verdict(replies: list) -> str:
    """What the OG's answer means, in words."""
    if not replies:
        return ("No answer. Wrong port (use the 093C:2055 one), or another program has it open "
                "(close og_shell and any game), or the OG is not running the Orca firmware.")
    first = replies[0]
    if first.startswith("OK"):
        return ("The OG accepted it (its screen is cleared when it turns, so it is black until "
                "something is drawn). A test message was just drawn on it: look at its screen.")
    if "unknown-command" in first:
        return ("The OG does not know this command, so it is running OLD firmware. Run "
                "python tools\\fw.py build orca_main  and THEN  python tools\\fw.py flash "
                "orca_main  (flash does not build). One OG at a time.")
    return f"The OG answered: {first}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Turn an OG's screen half a turn")
    ap.add_argument("port", help="the OG's display-CPU port, e.g. COM5")
    ap.add_argument("degrees", type=int, choices=(0, 180))
    args = ap.parse_args()
    import serial
    replies = []
    with serial.Serial(args.port, 115200, timeout=0.3) as ser:
        ser.reset_input_buffer()
        ser.write(f"\nROT {args.degrees}\n".encode("ascii"))
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not replies:
            line = ser.readline().decode("ascii", "replace").strip()
            if line.startswith(("OK", "ERR")):
                replies.append(line)
        if replies and replies[0].startswith("OK"):
            # Turning clears the screen, so draw something to see which way up it is.
            way = "turned 180" if args.degrees == 180 else "normal"
            for row, text in enumerate(("Orca", "", f"Screen {way}", "", "Is this readable?",
                                        "Top of text = top", "of the screen")):
                if text:
                    ser.write(f"\nTXT {row} {text}\n".encode("ascii"))
                    time.sleep(0.05)
    print(verdict(replies))
    return 0 if replies and replies[0].startswith("OK") else 1


if __name__ == "__main__":
    raise SystemExit(main())
