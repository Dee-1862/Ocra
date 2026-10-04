"""One window to start any game, and to see which OGs are connected.

    python -m orca.launcher

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

HOST_DIR = Path(__file__).resolve().parents[1]      # orca/host

from . import ui
from .ui import BG, DIM, FG, PANEL

# (module, name, what you do, movement or measure it uses)
GAMES = (
    ("beat_flick", "Beat Flick", "Flick each block the way its arrow points, in time with the song.",
     "Two OGs, one per hand: red blocks for the left, blue for the right. Fast flicks; "
     "diagonals take either direction."),
    ("brick_break", "Brick Break", "Bounce a ball off a paddle to break a wall of bricks.",
     "Tilt the OG sideways (roll) to move the paddle; --movement pitch for forward/back."),
    ("rhythm_flick", "Rhythm Flick", "Flick the wrist in the arrow's direction as it lands.",
     "Fast flicks on both axes. Two OGs: L and R lanes, matching hand only."),
    ("steady_hand", "Steady Hand", "Hold a cursor inside a ring, then the next ring.",
     "Roll and pitch together. Measures steadiness and tremor."),
    ("color_reflex", "Colour Reflex", "Press the button whose colour lights up.",
     "Buttons only, no tilt. Measures reaction time and how long buttons are held."),
    ("dial_game", "Dial", "Roll the needle to a target angle and hold it.",
     "Forearm rotation (roll), wide range."),
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
        lines.append("No devices.json yet: run python -m orca.devices --setup")
    lines += [f"  {p}" for p in problems]
    return "\n".join(lines)


class Launcher:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Orca games")
        root.configure(bg=BG)
        ui.style_tables()
        self.face = tk.BooleanVar(value=False)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=24)
        tk.Label(body, text="ORCA", bg=BG, fg=ui.ACCENT,
                 font=ui.font(10, True)).pack(anchor="w")
        tk.Label(body, text="Choose a game", bg=BG, fg=FG,
                 font=ui.font(24, True)).pack(anchor="w", pady=(0, 2))
        tk.Label(body, text="Tilt, flick or press. Each game opens in its own window.", bg=BG,
                 fg=DIM, font=ui.font(11)).pack(anchor="w", pady=(0, 16))

        for module, name, what, movement in GAMES:
            self._card(body, module, name, what, movement)

        opts = tk.Frame(body, bg=BG)
        opts.pack(fill="x", pady=(16, 0))
        tk.Checkbutton(opts, text="Use the webcam for the face table (--face)",
                       variable=self.face, bg=BG, fg=FG, selectcolor=ui.SURFACE,
                       activebackground=BG, activeforeground=FG, highlightthickness=0,
                       font=ui.font(10)).pack(anchor="w")
        tk.Label(opts, text="EXTRA OPTIONS FOR THE NEXT GAME", bg=BG, fg=ui.FAINT,
                 font=ui.font(8, True)).pack(anchor="w", pady=(10, 3))
        self.options = tk.Entry(opts, bg=ui.SURFACE, fg=FG, insertbackground=FG, relief="flat",
                                font=ui.mono(10), highlightthickness=1,
                                highlightbackground=ui.LINE, highlightcolor=ui.ACCENT)
        self.options.pack(fill="x", ipady=6)

        foot = tk.Frame(body, bg=BG)
        foot.pack(fill="x", pady=(16, 0))
        self.devices = tk.Label(foot, text=device_summary(), bg=BG, fg=DIM, justify="left",
                                font=ui.mono(9), anchor="w")
        self.devices.pack(side="left")
        self._button(foot, "Check devices", lambda: self.devices.configure(text=device_summary()),
                     quiet=True).pack(side="right", anchor="n")
        self.message = tk.Label(body, text="", bg=BG, fg=DIM, font=ui.font(9), anchor="w")
        self.message.pack(fill="x", pady=(8, 0))

    @staticmethod
    def _button(parent, text, command, quiet=False):
        """A flat button that lightens on hover."""
        base, hover = (ui.RAISED, ui.SURFACE_TOP) if quiet else (ui.ACCENT, ui.lighten(ui.ACCENT, 0.18))
        label = tk.Label(parent, text=text, bg=base, fg=FG if quiet else BG, cursor="hand2",
                         font=ui.font(10, True), padx=18, pady=7)
        label.bind("<Enter>", lambda e: label.configure(bg=hover))
        label.bind("<Leave>", lambda e: label.configure(bg=base))
        label.bind("<Button-1>", lambda e: command())
        return label

    def _card(self, parent, module, name, what, movement) -> None:
        frame = ui.framed(parent)
        frame.pack(fill="x", pady=5)
        card = tk.Frame(frame, bg=ui.SURFACE)
        card.pack(fill="x")
        text = tk.Frame(card, bg=ui.SURFACE)
        text.pack(side="left", fill="x", expand=True, padx=18, pady=12)
        tk.Label(text, text=name, bg=ui.SURFACE, fg=FG, font=ui.font(14, True),
                 anchor="w").pack(anchor="w")
        tk.Label(text, text=what, bg=ui.SURFACE, fg=FG, font=ui.font(10), anchor="w").pack(anchor="w")
        tk.Label(text, text=movement, bg=ui.SURFACE, fg=ui.FAINT, font=ui.font(9), anchor="w",
                 wraplength=520, justify="left").pack(anchor="w", pady=(2, 0))
        self._button(card, "Play", lambda m=module: self.start(m)).pack(side="right", padx=18)

    def start(self, module: str) -> None:
        try:
            extra = shlex.split(self.options.get())
        except ValueError as exc:
            self.message.configure(text=f"Options not understood: {exc}")
            return
        if self.face.get() and "--face" not in extra:
            extra.append("--face")
        cmd = [sys.executable, "-m", f"orca.{module}", *extra]
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
