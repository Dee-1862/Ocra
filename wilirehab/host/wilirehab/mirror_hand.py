"""Mirror hand: one hand drives a drawing, the other side shows its mirror image.

The *driver* OG's tilt turns a drawn hand. On the other side of the screen a
mirror-image hand turns by the opposite angle: that is the hand the patient is
asked to see as their own affected side (mirror therapy).

If the other hand also has an OG, its real tilt is drawn as a dashed ghost on
top of the mirror image, and the game logs how closely it follows (the
"affected side" readings). With only the driver OG, or none, it is just the
mirror view.

You choose the driver with --driver left_hand|right_hand. Angles are drawn
magnified (--gain, default 2x) so small tilts are easy to see; the table and
log hold the real angles.

Testing without an OG: yellow / blue (keys 2 / 4) nudge the driver hand 5 degrees.

Run from wilirehab/host:
    python -m wilirehab.mirror_hand
    python -m wilirehab.mirror_hand --devices devices.json --driver right_hand
"""
from __future__ import annotations

import tkinter as tk

from .bilateral import LEFT, RIGHT
from .catch_game import FIELD, GameApp, build_game_args
from .cli import parse_roles, resolve_ports
from .handshape import hand_shape, mirrored_angle
from .mapping_demo import DIM, FG, PANEL, W, blend

DRIVER_COLOR = "#22c55e"
MIRROR_COLOR = "#f5c400"
GHOST_COLOR = "#8b949e"
HAND_X = {LEFT: 0.27, RIGHT: 0.73}     # fraction of the field width
NUDGE_DEG = 5.0
LOG_EVERY_S = 0.5


class MirrorApp(GameApp):
    TITLE = "WiliRehab mirror hand"
    PERF = ("Mirror error", "deg", 1.0, 0.5, False)    # lower is better

    def __init__(self, root: tk.Tk, ports: dict, log_dir, axis="y", invert_roles=(),
                 driver="right_hand", gain=2.0, tolerance=10.0, invert_fwd_roles=()):
        self.gain = gain
        self.tolerance = tolerance
        super().__init__(root, ports, log_dir, tilt=False, axis=axis,
                         invert_roles=invert_roles, driver=driver, stream=True,
                         invert_fwd_roles=invert_fwd_roles)
        self.affected = LEFT if self.driver == RIGHT else RIGHT

    # ---- round state ---------------------------------------------------

    def _new_round(self) -> None:
        super()._new_round()
        self.manual = 0.0          # nudged angle used when the driver has no OG
        self.err_sum = 0.0
        self.err_n = 0
        self.matched_s = 0.0
        self.compared_s = 0.0
        self._since_log = 0.0

    @property
    def affected_role(self) -> str:
        return LEFT if self.driver == RIGHT else RIGHT

    def _driver_angle(self) -> float:
        a = self.angles.get(self.driver)
        return self.manual if a is None else a

    def _matched_pct(self):
        return None if self.compared_s == 0 else 100.0 * self.matched_s / self.compared_s

    def _mean_err(self):
        return None if self.err_n == 0 else self.err_sum / self.err_n

    def _end_fields(self) -> dict:
        pct, err = self._matched_pct(), self._mean_err()
        return {"matched_pct": None if pct is None else round(pct, 1),
                "mean_err_deg": None if err is None else round(err, 1)}

    # ---- input ---------------------------------------------------------

    def _apply(self, label) -> None:
        if self.screen.key == "play" and label in ("Left", "Right"):
            self.manual += NUDGE_DEG if label == "Right" else -NUDGE_DEG
            self.manual = max(-45.0, min(45.0, self.manual))
            return
        super()._apply(label)

    # ---- the game ------------------------------------------------------

    def _advance(self, dt: float) -> None:
        self.play_seconds += dt
        affected = self.angles.get(self.affected_role)
        if affected is None or self.driver not in self.angles:
            return
        target = mirrored_angle(self.angles[self.driver])
        err = abs(affected - target)
        self.err_sum += err
        self.err_n += 1
        self.compared_s += dt
        if err <= self.tolerance:
            self.matched_s += dt
        self._since_log += dt
        if self._since_log >= LOG_EVERY_S:
            self._since_log = 0.0
            self._perf(err)
            self.session.record("mirror", role=self.affected_role,
                                driver_deg=round(self.angles[self.driver], 1),
                                target_deg=round(target, 1),
                                actual_deg=round(affected, 1), err_deg=round(err, 1))

    # ---- drawing -------------------------------------------------------

    def _draw_hand(self, cx, cy, angle, left, color, dash=False, width=3) -> None:
        opts = {"dash": (4, 3)} if dash else {}
        for (x1, y1), (x2, y2) in hand_shape(angle, left):
            self.canvas.create_line(cx + x1, cy + y1, cx + x2, cy + y2, fill=color,
                                    width=width, tags="body", **opts)

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        width = x1 - x0
        wrist_y = y1 - 22
        c.create_rectangle(x0, y0, x1, y1, outline="#30363d", tags="body")
        c.create_line((x0 + x1) / 2, y0 + 10, (x0 + x1) / 2, y1 - 10, fill="#21262d",
                      dash=(2, 4), tags="body")

        def shade(color):
            return blend(color, PANEL, 0.6) if dim else color

        driver_angle = self._driver_angle() * self.gain
        mirror_angle = mirrored_angle(self._driver_angle()) * self.gain
        affected = self.affected_role
        dx = x0 + HAND_X[self.driver] * width if self.driver in HAND_X else x0 + width * 0.73
        mx = x0 + HAND_X[affected] * width
        self._draw_hand(dx, wrist_y, driver_angle, self.driver == LEFT, shade(DRIVER_COLOR))
        self._draw_hand(mx, wrist_y, mirror_angle, affected == LEFT, shade(MIRROR_COLOR))
        actual = self.angles.get(affected)
        if actual is not None:
            self._draw_hand(mx, wrist_y, actual * self.gain, affected == LEFT,
                            shade(GHOST_COLOR), dash=True, width=2)

        c.create_text(dx, y0 + 12, text="drives", fill=DIM, font=("Segoe UI", 10), tags="body")
        c.create_text(mx, y0 + 12, text="mirror", fill=DIM, font=("Segoe UI", 10), tags="body")
        pct, err = self._matched_pct(), self._mean_err()
        hud = f"Driver {self.driver.replace('_', ' ')}    Drawn at {self.gain:.0f}x"
        if pct is not None:
            hud += f"    Match {pct:.0f}%    Error {err:.0f} deg"
        c.create_text(x0 + 8, y0 + 6, anchor="nw", fill=DIM, font=("Segoe UI", 11),
                      text=hud, tags="body")
        if self.screen.key == "paused":
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="PAUSED", fill=FG,
                          font=("Segoe UI", 34, "bold"), tags="body")

    def _summary_lines(self) -> list:
        pct, err = self._matched_pct(), self._mean_err()
        return [
            f"Time  {self.play_seconds:.0f} s",
            f"Matched the mirror  {'-' if pct is None else f'{pct:.0f}%'}",
            f"Mean error  {'-' if err is None else f'{err:.0f} deg'}",
            f"Pain-now presses  {self.pain_events}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
        ]


def main() -> None:
    ap = build_game_args("WiliRehab mirror hand")
    ap.add_argument("--gain", type=float, default=2.0,
                    help="how much the drawn hands exaggerate the real angle (default 2)")
    ap.add_argument("--tolerance", type=float, default=10.0,
                    help="degrees of difference that still counts as matching (default 10)")
    args = ap.parse_args()
    ports = resolve_ports(args)
    root = tk.Tk()
    MirrorApp(root, ports, args.log_dir, axis=args.axis,
              invert_roles=parse_roles(args.invert_roles), driver=args.driver,
              gain=args.gain, tolerance=args.tolerance,
              invert_fwd_roles=parse_roles(args.invert_fwd_roles))
    root.mainloop()


if __name__ == "__main__":
    main()
