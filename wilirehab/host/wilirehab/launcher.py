"""One window to start any game, and to see which OGs are connected.

    python -m wilirehab.launcher

Each game opens in its own window. If devices.json exists the games use the OGs
it names; otherwise they run on keyboard and clicks. The "options" box adds
extra command-line options for the next game you start, for example
    --invert-roles left_hand --driver left_hand
"""
from __future__ import annotations

import shlex
import subprocess
import sys
import tkinter as tk
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parents[1]      # wilirehab/host

BG = "#0d1117"
PANEL = "#161b22"
FG = "#e6edf3"
DIM = "#8b949e"
GREEN = "#22c55e"

# (module, name, what you do, movement or measure it uses)
GAMES = (
    ("catch_game", "Catch", "Move a basket under falling stars.",
     "Forearm rotation (roll). Add --tilt to steer with the OG."),
    ("brick_break", "Brick Break", "Bounce a ball off a paddle to break a wall of bricks.",
     "Wrist flexion/extension (pitch) moves the paddle; --movement roll for rotation."),
    ("rhythm_flick", "Rhythm Flick", "Flick the wrist in the arrow's direction as it lands.",
     "Fast flicks on both axes. Two OGs: L and R lanes, matching hand only."),
    ("steady_hand", "Steady Hand", "Hold a cursor inside a ring, then the next ring.",
     "Roll and pitch together. Measures steadiness and tremor."),
    ("color_reflex", "Colour Reflex", "Press the button whose colour lights up.",
     "Buttons only, no tilt. Measures reaction time and how long buttons are held."),
    ("dial_game", "Dial", "Roll the needle to a target angle and hold it.",
     "Forearm rotation (roll), wide range."),
    ("mirror_hand", "Mirror Hand", "One hand turns a drawn hand; the other side mirrors it.",
     "Roll shown as a drawn hand. Mirror view; the other OG's real tilt is compared."),
)


def device_summary() -> str:
    """Which OGs are plugged in and which hand each is assigned to."""
    try:
        from serial.tools import list_ports
        from .devices import DEFAULT_CONFIG, assign_roles, find_og_displays, load_config
        found = find_og_displays(list_ports.comports())
        config = HOST_DIR / DEFAULT_CONFIG
        mapping = load_config(config)
        ports, problems = assign_roles(mapping, found)
    except Exception as exc:                        # shown, not hidden
        return f"Could not check devices: {exc}"
    lines = [f"OGs found: {len(found)}"]
    for role in ("left_hand", "right_hand"):
        lines.append(f"  {role}: {ports.get(role, 'not connected')}")
    if not mapping:
        lines.append("No devices.json yet: run python -m wilirehab.devices --setup")
    lines += [f"  {p}" for p in problems]
    return "\n".join(lines)


class Launcher:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("WiliRehab games")
        root.configure(bg=BG)
        tk.Label(root, text="WiliRehab games", bg=BG, fg=FG,
                 font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3,
                                                     sticky="w", padx=16, pady=(14, 6))
        for i, (module, name, what, movement) in enumerate(GAMES):
            row = i + 1
            tk.Button(root, text=name, width=14, bg=PANEL, fg=FG, activebackground=GREEN,
                      relief="flat", font=("Segoe UI", 11, "bold"),
                      command=lambda m=module: self.start(m)).grid(
                row=row, column=0, padx=(16, 8), pady=4, sticky="w")
            tk.Label(root, text=what, bg=BG, fg=FG, font=("Segoe UI", 10),
                     anchor="w").grid(row=row, column=1, sticky="w", padx=4)
            tk.Label(root, text=movement, bg=BG, fg=DIM, font=("Segoe UI", 9),
                     anchor="w", wraplength=330, justify="left").grid(
                row=row, column=2, sticky="w", padx=(8, 16))
        last = len(GAMES) + 1
        tk.Label(root, text="Options for the next game:", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).grid(row=last, column=0, columnspan=2, sticky="w",
                                            padx=16, pady=(12, 0))
        self.options = tk.Entry(root, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                                font=("Consolas", 10))
        self.options.grid(row=last + 1, column=0, columnspan=3, sticky="ew", padx=16)
        self.devices = tk.Label(root, text=device_summary(), bg=BG, fg=DIM, justify="left",
                                font=("Consolas", 9), anchor="w")
        self.devices.grid(row=last + 2, column=0, columnspan=2, sticky="w", padx=16, pady=10)
        tk.Button(root, text="Check devices again", bg=PANEL, fg=FG, relief="flat",
                  font=("Segoe UI", 9),
                  command=lambda: self.devices.configure(text=device_summary())).grid(
            row=last + 2, column=2, sticky="e", padx=16)
        self.message = tk.Label(root, text="", bg=BG, fg=DIM, font=("Segoe UI", 9))
        self.message.grid(row=last + 3, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 10))
        root.columnconfigure(2, weight=1)

    def start(self, module: str) -> None:
        try:
            extra = shlex.split(self.options.get())
        except ValueError as exc:
            self.message.configure(text=f"Options not understood: {exc}")
            return
        cmd = [sys.executable, "-m", f"wilirehab.{module}", *extra]
        try:
            subprocess.Popen(cmd, cwd=HOST_DIR)
        except OSError as exc:
            self.message.configure(text=f"Could not start: {exc}")
            return
        self.message.configure(text="Started: " + " ".join(cmd[2:]))


def main() -> None:
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
