"""Steady Hand: hold a cursor inside a ring, using two wrist movements at once.

The cursor moves with the driver OG's tilt on **both** axes: roll (forearm
rotation) sideways across the screen and pitch (tilt forward and back, wrist
up and down with the forearm flat) up and down the screen. A target ring
appears; hold the cursor inside it for 2 seconds, then a new ring appears.

This game is about steadiness rather than reaching: it records how far from the
target the cursor wanders while you hold, and the summary also shows the 4-12 Hz
shake (tremor) strength measured from the accelerometer.

The ring narrows after each success and widens after a target nobody reaches.

Controls: tilt the driver OG. Without one: yellow / blue (keys 2 / 4) nudge roll,
keys u / d nudge pitch. z sets neutral. Gray "Pain now" is logged as usual.

Run from orca/host:
    python -m orca.steady_hand
    python -m orca.steady_hand --port COM5 --range-deg 15
"""
from __future__ import annotations

import math
import tkinter as tk

from . import ui
from .game_base import FIELD, GameApp, build_game_args
from .cli import parse_roles, resolve_ports
from .hold2d import HoldRound2D
from .mapping_demo import DIM, FG, PANEL, blend

CURSOR = "#f1f5f9"
INSIDE = "#34d399"
RING = "#fbbf24"
NUDGE_DEG = 3.0


class SteadyApp(GameApp):
    TITLE = "Orca steady hand"
    OG_NAME = "STEADY HAND"
    ONE_HAND = True                  # asks which hand plays when two are connected
    PERF = ("Steadiness", "deg", 1.0, 0.2, False)       # distance from target, lower is better

    def __init__(self, root: tk.Tk, ports: dict, log_dir, axis="y", invert_roles=(),
                 invert_fwd_roles=(), driver="right_hand", range_deg=12.0):
        self.range = range_deg
        super().__init__(root, ports, log_dir, tilt=False, axis=axis,
                         invert_roles=invert_roles, range_deg=range_deg, driver=driver,
                         stream=True, invert_fwd_roles=invert_fwd_roles)

    # ---- round state ---------------------------------------------------

    def _new_round(self) -> None:
        super()._new_round()
        self.hold = HoldRound2D(range_deg=self.range)
        self.manual_roll = 0.0
        self.manual_pitch = 0.0
        self._target_sum = 0.0       # distance while inside the ring, for this target
        self._target_n = 0

    def _end_fields(self) -> dict:
        mean = self.hold.mean_distance
        return {"completed": self.hold.completed, "timeouts": self.hold.timeouts,
                "mean_dist_deg": None if mean is None else round(mean, 2)}

    def _cursor(self):
        """(roll, pitch) in degrees: the driver OG, or the nudged values without one."""
        roll = self.angles.get(self.driver)
        pitch = self.pitch_angles.get(self.driver)
        return (self.manual_roll if roll is None else roll,
                self.manual_pitch if pitch is None else pitch)

    # ---- input ---------------------------------------------------------

    def _apply(self, label) -> None:
        if self.screen.key == "play" and label in ("Left", "Right"):
            self.manual_roll += NUDGE_DEG if label == "Right" else -NUDGE_DEG
            return
        super()._apply(label)

    def _on_key(self, event) -> None:
        if event.char in ("u", "d") and self.screen.key == "play":
            self.manual_pitch += NUDGE_DEG if event.char == "u" else -NUDGE_DEG
            return
        super()._on_key(event)

    # ---- the game ------------------------------------------------------

    def _advance(self, dt: float) -> None:
        self.play_seconds += dt
        roll, pitch = self._cursor()
        h = self.hold
        dist = math.hypot(roll - h.target[0], pitch - h.target[1])
        if dist <= h.tolerance:
            self._target_sum += dist
            self._target_n += 1
        target = h.target
        event = h.update(roll, pitch, dt)
        if event == "complete":
            mean = self._target_sum / self._target_n if self._target_n else 0.0
            self._perf(mean)
            self._attempt(self.driver, True)
            self.session.record("hold_complete", tx=target[0], ty=target[1],
                                mean_dist_deg=round(mean, 2), tolerance=h.tolerance)
        elif event == "timeout":
            self._attempt(self.driver, False)
            self.session.record("hold_timeout", tx=target[0], ty=target[1],
                                tolerance=h.tolerance)
        if event:
            self._target_sum, self._target_n = 0.0, 0

    def _points(self) -> list:
        done, missed = self.hold.completed, self.hold.timeouts
        rate = "--" if done + missed == 0 else f"{100 * done / (done + missed):.0f}"
        return [("Rings held", str(done), ""), ("Missed", str(missed), ""),
                ("Success", rate, "%")]

    def _og_lines(self) -> list:
        roll, pitch = self._cursor()
        return [f"Held {self.hold.completed}", f"Missed {self.hold.timeouts}",
                f"R{roll:+.0f} P{pitch:+.0f} deg"]

    # ---- drawing -------------------------------------------------------

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + 6
        scale = 70.0 / self.range                        # pixels per degree
        h = self.hold

        def shade(color):
            return blend(color, PANEL, 0.6) if dim else color

        self._arena()
        c.create_line(cx, y0 + 16, cx, y1 - 14, fill=ui.LINE, tags="body")
        c.create_line(x0 + 16, cy, x1 - 16, cy, fill=ui.LINE, tags="body")
        tx, ty = cx + h.target[0] * scale, cy - h.target[1] * scale
        r = h.tolerance * scale
        ring_color = INSIDE if h.on_target and not dim else RING
        ui.ring(c, tx, ty, r, shade(ring_color), thick=4, glow=0 if dim else 12,
                fill_alpha=0.0 if dim else 0.10)
        roll, pitch = self._cursor()
        px = max(x0 + 14, min(x1 - 14, cx + roll * scale))
        py = max(y0 + 14, min(y1 - 14, cy - pitch * scale))
        color = INSIDE if h.on_target else CURSOR
        ui.orb(c, px, py, 9, shade(color), glow=0 if dim else 8)
        if h.on_target and not dim:
            frac = min(1.0, h.held / h.hold_s)
            ui.pill(c, cx - 70, y1 - 22, cx + 70, y1 - 14, ui.LINE)
            fill_w = int(140 * frac / 7) * 7
            if fill_w >= 8:
                ui.pill(c, cx - 70, y1 - 22, cx - 70 + fill_w, y1 - 14, shade(INSIDE))
        self._hud([("Held", h.completed), ("Missed", h.timeouts),
                   ("Ring", f"\u00b1{h.tolerance:.0f}\u00b0"),
                   ("Tilt", f"{roll:+.0f}\u00b0 / {pitch:+.0f}\u00b0")])
        self._paused_overlay()

    def _summary_lines(self) -> list:
        mean = self.hold.mean_distance
        return [
            f"Targets held  {self.hold.completed}",
            f"Timed out  {self.hold.timeouts}",
            f"Mean distance while holding  {'-' if mean is None else f'{mean:.1f} deg'}",
            f"Pain-now presses  {self.pain_events}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
        ]


def parser():
    ap = build_game_args("Orca steady hand")
    ap.add_argument("--range-deg", type=float, default=12.0,
                    help="tilt at the edge of the screen in degrees (default 12)")
    return ap


def build(root, ports: dict, args) -> SteadyApp:
    """The game in `root` (a Tk or Toplevel). The OG shell calls this with default arguments."""
    return SteadyApp(root, ports, args.log_dir, axis=args.axis,
                     invert_roles=parse_roles(args.invert_roles),
                     invert_fwd_roles=parse_roles(args.invert_fwd_roles), driver=args.driver,
                     range_deg=args.range_deg)


def main() -> None:
    args = parser().parse_args()
    ports = resolve_ports(args)
    root = tk.Tk()
    build(root, ports, args)
    root.mainloop()


if __name__ == "__main__":
    main()
