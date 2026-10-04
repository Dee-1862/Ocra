"""Turn the dial: roll the OG to match a target angle and hold it.

Rest the forearm flat (a towel roll helps) with the OG on the back of the hand
or forearm, and roll the forearm to turn the needle. A yellow marker shows the
target and the band around it is how close you need to be. Hold inside the
band for 1.5 seconds to score. Each success makes the band a little narrower;
a target nobody reaches in 15 seconds makes it a little wider.

The driver OG turns the needle (--driver left_hand|right_hand). With both OGs
connected the summary also shows the left/right symmetry table.

Testing without an OG: yellow / blue (keys 2 / 4) nudge the needle 5 degrees.

Run from wilirehab/host:
    python -m wilirehab.dial_game
    python -m wilirehab.dial_game --port COM5 --dial-range 45
"""
from __future__ import annotations

import tkinter as tk

from .game_base import FIELD, GameApp, build_game_args
from .cli import parse_roles, resolve_ports
from .dial import DialRound, needle_end
from .mapping_demo import DIM, FG, PANEL, blend

NEEDLE = "#22c55e"
TARGET = "#f5c400"
NUDGE_DEG = 5.0
RADIUS = 125


class DialApp(GameApp):
    TITLE = "WiliRehab dial"
    PERF = ("Time to reach", "s", 1.0, 0.5, False)       # lower is better

    def __init__(self, root: tk.Tk, ports: dict, log_dir, axis="y", invert_roles=(),
                 driver="right_hand", dial_range=45.0, invert_fwd_roles=()):
        self.dial_range = dial_range
        super().__init__(root, ports, log_dir, tilt=False, axis=axis,
                         invert_roles=invert_roles, driver=driver, stream=True,
                         invert_fwd_roles=invert_fwd_roles)

    # ---- round state ---------------------------------------------------

    def _new_round(self) -> None:
        super()._new_round()
        self.dial = DialRound(range_deg=self.dial_range)
        self.manual = 0.0
        self.times: list = []
        self._since_target = 0.0

    def _angle(self) -> float:
        """Needle angle: the driver OG's roll, or the nudged value without one."""
        a = self.angles.get(self.driver)
        raw = self.manual if a is None else a
        return max(-self.dial_range, min(self.dial_range, raw))

    def _end_fields(self) -> dict:
        mean = sum(self.times) / len(self.times) if self.times else None
        return {"completed": self.dial.completed, "timeouts": self.dial.timeouts,
                "mean_s": None if mean is None else round(mean, 1)}

    # ---- input ---------------------------------------------------------

    def _apply(self, label) -> None:
        if self.screen.key == "play" and label in ("Left", "Right"):
            self.manual += NUDGE_DEG if label == "Right" else -NUDGE_DEG
            self.manual = max(-self.dial_range, min(self.dial_range, self.manual))
            return
        super()._apply(label)

    # ---- the game ------------------------------------------------------

    def _advance(self, dt: float) -> None:
        self.play_seconds += dt
        self._since_target += dt
        target = self.dial.target
        event = self.dial.update(self._angle(), dt)
        if event == "complete":
            self.times.append(self._since_target)
            self._perf(self._since_target)
            self.session.record("dial_complete", target=target,
                                took_s=round(self._since_target, 1),
                                tolerance=self.dial.tolerance)
            self._since_target = 0.0
        elif event == "timeout":
            self.session.record("dial_timeout", target=target,
                                tolerance=self.dial.tolerance)
            self._since_target = 0.0

    # ---- drawing -------------------------------------------------------

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        cx, cy = (x0 + x1) / 2, y1 - 12
        r = RADIUS

        def shade(color):
            return blend(color, PANEL, 0.6) if dim else color

        def arc(radius, a0, a1, color, width):
            # Our angle: 0 is up, clockwise is positive. Tk: 0 is 3 o'clock, anticlockwise.
            c.create_arc(cx - radius, cy - radius, cx + radius, cy + radius,
                         start=90 - a1, extent=a1 - a0, style="arc",
                         outline=color, width=width, tags="body")

        c.create_rectangle(x0, y0, x1, y1, outline="#30363d", tags="body")
        arc(r, -self.dial_range, self.dial_range, shade("#30363d"), 3)
        for tick in range(-int(self.dial_range), int(self.dial_range) + 1, 15):
            a, b = needle_end(cx, cy, r - 8, tick), needle_end(cx, cy, r + 4, tick)
            c.create_line(*a, *b, fill=shade("#6e7681"), width=2, tags="body")
        d = self.dial
        arc(r, d.target - d.tolerance, d.target + d.tolerance, shade("#7d6a14"), 12)
        tip = needle_end(cx, cy, r + 2, d.target)
        base = needle_end(cx, cy, r - 24, d.target)
        c.create_line(*base, *tip, fill=shade(TARGET), width=4, tags="body")
        end = needle_end(cx, cy, r - 12, self._angle())
        c.create_line(cx, cy, *end, fill=shade(NEEDLE), width=5, tags="body")
        c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill=shade(NEEDLE), outline="", tags="body")

        hud = (f"Done {d.completed}    Timed out {d.timeouts}    "
               f"Band +-{d.tolerance:.0f} deg    Target {d.target:+.0f}    Dial {self._angle():+.0f}")
        c.create_text(x0 + 8, y0 + 6, anchor="nw", fill=DIM, font=("Segoe UI", 11),
                      text=hud, tags="body")
        if d.on_target and not dim:
            c.create_text(cx, y0 + 50, text="Hold...", fill=TARGET,
                          font=("Segoe UI", 16, "bold"), tags="body")
            frac = min(1.0, d.held / d.hold_s)
            c.create_rectangle(cx - 80, y0 + 70, cx - 80 + 160 * frac, y0 + 78,
                               fill=TARGET, outline="", tags="body")
        if self.screen.key == "paused":
            c.create_text(cx, (y0 + y1) / 2, text="PAUSED", fill=FG,
                          font=("Segoe UI", 34, "bold"), tags="body")

    def _summary_lines(self) -> list:
        mean = sum(self.times) / len(self.times) if self.times else None
        return [
            f"Targets reached  {self.dial.completed}",
            f"Timed out  {self.dial.timeouts}",
            f"Mean time to reach  {'-' if mean is None else f'{mean:.1f} s'}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
            f"Time  {self.play_seconds:.0f} s",
        ]


def main() -> None:
    ap = build_game_args("WiliRehab dial")
    ap.add_argument("--dial-range", type=float, default=45.0,
                    help="roll angle at each end of the dial in degrees (default 45)")
    args = ap.parse_args()
    ports = resolve_ports(args)
    root = tk.Tk()
    DialApp(root, ports, args.log_dir, axis=args.axis,
            invert_roles=parse_roles(args.invert_roles), driver=args.driver,
            dial_range=args.dial_range,
            invert_fwd_roles=parse_roles(args.invert_fwd_roles))
    root.mainloop()


if __name__ == "__main__":
    main()
