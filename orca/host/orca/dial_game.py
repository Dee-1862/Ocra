"""Turn the dial: roll the OG to match a target angle and hold it.

Rest the forearm flat (a towel roll helps) with the OG on the back of the hand
or forearm, and roll the forearm to turn the needle. A yellow marker shows the
target and the band around it is how close you need to be. Hold inside the
band for 1.5 seconds to score. Each success makes the band a little narrower;
a target nobody reaches in 15 seconds makes it a little wider.

The driver OG turns the needle (--driver left_hand|right_hand). With both OGs
connected the summary also shows the left/right symmetry table.

Testing without an OG: yellow / blue (keys 2 / 4) nudge the needle 5 degrees.

Run from orca/host:
    python -m orca.dial_game
    python -m orca.dial_game --port COM5 --dial-range 45
"""
from __future__ import annotations

import tkinter as tk

from . import ui
from .game_base import FIELD, GameApp, build_game_args
from .cli import parse_roles, resolve_ports
from .dial import DialRound, needle_end
from .mapping_demo import DIM, FG, PANEL, blend

NEEDLE = "#34d399"
TARGET = "#fbbf24"
NUDGE_DEG = 5.0
RADIUS = 125


class DialApp(GameApp):
    TITLE = "Orca dial"
    OG_NAME = "DIAL"
    ONE_HAND = True                  # asks which hand plays when two are connected
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

    def _points(self) -> list:
        d = self.dial
        return [("Reached", str(d.completed), ""), ("Timed out", str(d.timeouts), ""),
                ("Target", f"{d.target:+.0f}", "deg")]

    def _og_lines(self) -> list:
        d = self.dial
        return [f"Done {d.completed}", f"Timed out {d.timeouts}",
                f"Dial {self._angle():+.0f} Tgt {d.target:+.0f}"]

    # ---- drawing -------------------------------------------------------

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        cx, cy = (x0 + x1) / 2, y1 - 12
        r = RADIUS

        def shade(color):
            return blend(color, PANEL, 0.6) if dim else color

        self._arena()
        lo, hi = -self.dial_range, self.dial_range
        ui.arc(c, cx, cy, r, lo, hi, shade(ui.LINE), width=4)
        for tick in range(-int(self.dial_range), int(self.dial_range) + 1, 15):
            a, b = needle_end(cx, cy, r - 12, tick), needle_end(cx, cy, r - 5, tick)
            ui.line(c, *a, *b, shade(ui.FAINT), width=2)
        d = self.dial
        band_lo, band_hi = max(lo, d.target - d.tolerance), min(hi, d.target + d.tolerance)
        ui.arc(c, cx, cy, r, band_lo, band_hi, shade(TARGET), width=10,
               glow=0 if dim else 10)
        tip = needle_end(cx, cy, r + 8, d.target)
        base = needle_end(cx, cy, r - 22, d.target)
        ui.line(c, *base, *tip, shade(TARGET), width=3)
        end = needle_end(cx, cy, r - 20, self._angle())
        needle = NEEDLE if d.on_target else FG
        ui.line(c, cx, cy, *end, shade(needle), width=4)
        ui.orb(c, cx, cy, 9, shade(needle), glow=0 if dim else 8)

        self._hud([("Done", d.completed), ("Timed out", d.timeouts),
                   ("Band", f"\u00b1{d.tolerance:.0f}\u00b0"), ("Target", f"{d.target:+.0f}\u00b0"),
                   ("Dial", f"{self._angle():+.0f}\u00b0")])
        if d.on_target and not dim:
            c.create_text(cx, y0 + 34, text="Hold\u2026", fill=TARGET, font=ui.font(14, True),
                          tags="body")
            frac = min(1.0, d.held / d.hold_s)
            ui.pill(c, cx - 80, y0 + 52, cx + 80, y0 + 60, ui.LINE)
            fill_w = int(160 * frac / 8) * 8
            if fill_w >= 8:
                ui.pill(c, cx - 80, y0 + 52, cx - 80 + fill_w, y0 + 60, TARGET)
        self._paused_overlay()

    def _summary_lines(self) -> list:
        mean = sum(self.times) / len(self.times) if self.times else None
        return [
            f"Targets reached  {self.dial.completed}",
            f"Timed out  {self.dial.timeouts}",
            f"Mean time to reach  {'-' if mean is None else f'{mean:.1f} s'}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
            f"Time  {self.play_seconds:.0f} s",
        ]


def parser():
    ap = build_game_args("Orca dial")
    ap.add_argument("--dial-range", type=float, default=45.0,
                    help="roll angle at each end of the dial in degrees (default 45)")
    return ap


def build(root, ports: dict, args) -> DialApp:
    """The game in `root` (a Tk or Toplevel). The OG shell calls this with default arguments."""
    return DialApp(root, ports, args.log_dir, axis=args.axis,
                   invert_roles=parse_roles(args.invert_roles), driver=args.driver,
                   dial_range=args.dial_range,
                   invert_fwd_roles=parse_roles(args.invert_fwd_roles))


def main() -> None:
    args = parser().parse_args()
    ports = resolve_ports(args)
    root = tk.Tk()
    build(root, ports, args)
    root.mainloop()


if __name__ == "__main__":
    main()
