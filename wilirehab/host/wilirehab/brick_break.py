"""Brick Break: a ball bounces off a paddle and breaks a wall of bricks.

The paddle moves left and right by tilting the OG sideways (**roll**, forearm rotation),
the natural movement for left and right. `--movement pitch` steers by tilting it forward
and back instead (wrist flexion and extension). It defaulted to pitch at first; a recorded
session showed people tilt sideways, and pitch then moved against them about a third of
the time.

Built on game_base (screens, legend, pause / pain / summary flow, OG links,
data table, numbers-only log). Only the play area differs.

Controls: tilt the driver OG. yellow / blue (keys 2 / 4) also move the paddle without an OG.
The range of tilt you can manage is learned as you play and stretched over the whole field,
so a small or one-sided range still reaches both edges (key z starts the learning again;
--fixed-range gives the old fixed mapping, set with l and r).
Gray "Pain now" slows the ball.

The ball slows after a drop and speeds up each time the wall is cleared.

Run from wilirehab/host:
    python -m wilirehab.brick_break
    python -m wilirehab.brick_break --port COM5
    python -m wilirehab.brick_break --devices devices.json --driver left_hand --movement roll
"""
from __future__ import annotations

import tkinter as tk

from . import ui
from .autorange import AutoRange
from .breakout import MIN_SPEED, Breakout
from .game_base import FIELD, TILT_SLEW, GameApp, build_game_args
from .cli import parse_roles, resolve_ports
from .mapping_demo import DIM, FG, PANEL, blend
from .tilt import to_position

ROW_COLORS = ("#f87171", "#fbbf24", "#34d399")
BALL = "#f1f5f9"
PADDLE = "#60a5fa"
MOVEMENT_NAME = {"pitch": "wrist up/down (pitch)", "roll": "forearm rotation (roll)"}


class BrickApp(GameApp):
    TITLE = "WiliRehab brick break"
    OG_NAME = "BRICK BREAK"
    PERF = ("Paddle catch rate", "%", 100.0, 2.0, True)

    def __init__(self, root: tk.Tk, ports: dict, log_dir, axis="y", invert_roles=(),
                 invert_fwd_roles=(), driver="right_hand", movement="roll",
                 range_deg=18.0, speed=170.0, fixed_range=False):
        self.movement = movement
        self._fixed_range = fixed_range
        self._start_speed = speed
        super().__init__(root, ports, log_dir, tilt=False, axis=axis,
                         invert_roles=invert_roles, range_deg=range_deg, driver=driver,
                         stream=True, invert_fwd_roles=invert_fwd_roles)

    # ---- round state ---------------------------------------------------

    def _new_round(self) -> None:
        super()._new_round()
        # The ball waits on the paddle for 0.8 s before every serve, so a new ball does not
        # launch the instant the last one drops.
        self.game = Breakout(speed=self._start_speed, serve_delay=0.8)
        self.autorange = AutoRange()
        self.paddle_hits = 0

    def _og_lines(self) -> list:
        g, angle = self.game, self._angle()
        return [f"Bricks {g.score}", f"Drops {g.drops} Lv {g.levels + 1}",
                "Tilt --" if angle is None else f"Tilt {angle:+.0f} deg"]

    def _end_fields(self) -> dict:
        return {"bricks": self.game.score, "drops": self.game.drops,
                "levels": self.game.levels, "range_deg": round(self.autorange.span, 1)}

    # ---- input ---------------------------------------------------------

    def _angle(self):
        """The driver's tilt on the chosen movement, or None before any OG data."""
        source = self.pitch_angles if self.movement == "pitch" else self.angles
        return source.get(self.driver)

    def _on_key(self, event) -> None:
        if event.char == "z":
            self.autorange.reset()            # learn the range again from this pose
        if event.char in ("l", "r") and not self._fixed_range:
            self.status.configure(text="The range is learned as you play. Use --fixed-range "
                                       "if you want to set it with l and r.")
            return
        if event.char in ("l", "r"):
            angle = self._angle()
            if angle is None:
                self.status.configure(text="No OG data yet; tilt it first")
                return
            self.tilt_angle = angle          # _set_extreme reads this
            self._set_extreme(event.char)
            return
        super()._on_key(event)

    def _apply(self, label) -> None:
        if self.screen.key == "play" and label == "Pain now":
            self.game.speed = max(MIN_SPEED, self.game.speed * 0.8)
        super()._apply(label)

    # ---- the game ------------------------------------------------------

    def _advance(self, dt: float) -> None:
        self.play_seconds += dt
        angle = self._angle()
        if angle is not None:                # with an OG the tilt sets the paddle
            if self._fixed_range:
                target = to_position(angle, self.left_deg, self.right_deg)
            else:                            # learned: the person's own range fills the field
                target = self.autorange.update(angle, dt)
            step = TILT_SLEW * dt
            self.bx += max(-step, min(step, target - self.bx))
        # (without an OG, the base class's Left / Right presses move self.bx)
        for event in self.game.step(dt, self.bx * self.game.width):
            if event == "paddle":
                self.paddle_hits += 1
                self._attempt(self.driver, True)
                self._perf(1)
            elif event == "lost":
                self._attempt(self.driver, False)
                self._perf(0)
                self.session.record("drop", n=self.game.drops)
            elif event == "brick":
                self.session.record("brick", n=self.game.score)
            elif event == "cleared":
                self.session.record("level", n=self.game.levels)

    # ---- drawing -------------------------------------------------------

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        g = self.game

        def shade(color):
            return blend(color, PANEL, 0.6) if dim else color

        self._arena()
        for bx0, by0, bx1, by1, row in g.bricks:
            ui.brick(c, x0 + bx0, y0 + by0, x0 + bx1, y0 + by1, shade(ROW_COLORS[row % 3]))
        half = g.paddle_w / 2
        py = y0 + g.paddle_y
        if not dim:
            ui.halo(c, x0 + g.paddle_x, py + 2, half * 1.1, PADDLE, alpha=0.30)
        ui.pill(c, x0 + g.paddle_x - half, py - g.paddle_h / 2 - 1,
                x0 + g.paddle_x + half, py + g.paddle_h / 2 + 1, shade(PADDLE))
        ui.orb(c, x0 + g.ball_x, y0 + g.ball_y, g.ball_r + 1, shade(BALL),
               glow=0 if dim else 9)
        chips = [("Bricks", g.score), ("Drops", g.drops), ("Level", g.levels + 1)]
        if not self._fixed_range and self.autorange.span:
            chips.append(("Range", f"{self.autorange.span:.0f}\u00b0"))
        self._hud(chips)
        self._paused_overlay()

    def _summary_lines(self) -> list:
        g = self.game
        return [
            f"Bricks broken  {g.score}",
            f"Paddle hits  {self.paddle_hits}",
            f"Balls dropped  {g.drops}",
            f"Walls cleared  {g.levels}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
        ]


def main() -> None:
    ap = build_game_args("WiliRehab brick break")
    ap.add_argument("--movement", choices=("roll", "pitch"), default="roll",
                    help="roll = tilt the OG sideways (default); pitch = tilt it forward and back")
    ap.add_argument("--fixed-range", action="store_true",
                    help="use a fixed tilt range (--range-deg each way, l and r to set) instead "
                         "of learning yours as you play")
    ap.add_argument("--range-deg", type=float, default=18.0,
                    help="with --fixed-range: the tilt that reaches each edge (default 18)")
    ap.add_argument("--speed", type=float, default=170.0, help="starting ball speed, px/s")
    args = ap.parse_args()
    ports = resolve_ports(args)
    root = tk.Tk()
    BrickApp(root, ports, args.log_dir, axis=args.axis,
             invert_roles=parse_roles(args.invert_roles),
             invert_fwd_roles=parse_roles(args.invert_fwd_roles), driver=args.driver,
             movement=args.movement, range_deg=args.range_deg, speed=args.speed,
             fixed_range=args.fixed_range)
    root.mainloop()


if __name__ == "__main__":
    main()
