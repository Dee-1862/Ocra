"""Rhythm Flick: arrows fall on the beat, flick the wrist that way as one lands.

Built on game_base (same screens, legend, pause / pain / summary flow,
OG links, data table and numbers-only log). Only the play area differs.

With two OGs (one per hand) each arrow is marked L or R and falls in that
hand's lane: a flick only counts from the matching hand's OG. A flick from the
other hand shows WRONG HAND and costs nothing. With one OG, or none, arrows
fall in the middle and any hand will do.

Input, any of:
    OG tilt flick   (OGs connected; wear or hold them, flick)
    yellow / blue   OG buttons or keys 2 / 4  = flick left / right (any hand)
    keys u / d      flick up / down (testing without the OG)
Gray "Pain now" slows the tempo.

Tempo adapts: 8 hits in a row = +5 BPM, 3 misses in a row = -5 BPM.
Hits are judged against the laptop clock when the flick arrives, so USB adds a
few milliseconds of jitter; the hit window is generous (+-0.35 s) for that
reason and because it is a rehab game.

Run from wilirehab/host:
    python -m wilirehab.rhythm_flick                     # buttons and keys only
    python -m wilirehab.rhythm_flick --port COM5         # one OG
    python -m wilirehab.rhythm_flick --devices devices.json --hands both
"""
from __future__ import annotations

import random
import time
import tkinter as tk

from .bilateral import LEFT, RIGHT
from .game_base import FIELD, GameApp, build_game_args
from .cli import parse_roles, resolve_ports
from .flick import FlickDetector, match_flick
from .mapping_demo import DIM, FG, PANEL, W, blend
from .tilt import TiltTracker

LEAD = 2.0            # seconds a block takes to fall to the hit line
WINDOW = 0.35         # seconds either side of the beat that count
START_BPM, MIN_BPM, MAX_BPM = 50, 30, 90

ARROWS = {"left": "←", "right": "→", "up": "↑", "down": "↓"}
DIR_COLORS = {"left": "#f5c400", "right": "#3b82f6", "up": "#22c55e", "down": "#ef4444"}
LANE_X = {LEFT: 0.27, RIGHT: 0.73, None: 0.5}     # fraction of the field width
BADGE = {LEFT: "L", RIGHT: "R"}


class RhythmApp(GameApp):
    TITLE = "WiliRehab rhythm flick"

    def __init__(self, root: tk.Tk, ports: dict, log_dir, axis="y", invert_roles=(),
                 invert_fwd_roles=(), dirs="all", bpm=START_BPM, flick_dps=150.0,
                 hands="auto", driver="right_hand"):
        # Set before GameApp.__init__, which builds the first round straight away.
        self._start_bpm = bpm
        self.allowed = ("left", "right") if dirs == "lr" else ("left", "right", "up", "down")
        both = hands == "both" or (hands == "auto" and len(ports) >= 2)
        self.hand_roles = (LEFT, RIGHT) if both else (None,)
        fwd_axis = "x" if axis == "y" else "y"
        self.fwd = {r: TiltTracker(axis=fwd_axis, invert=r in set(invert_fwd_roles),
                                   alpha=0.5, median_len=3, hold_shaky=False)
                    for r in ports}
        self.detectors = {r: FlickDetector(threshold_dps=flick_dps) for r in ports}
        super().__init__(root, ports, log_dir, tilt=False, axis=axis,
                         invert_roles=invert_roles, driver=driver, stream=True,
                         invert_fwd_roles=invert_fwd_roles)

    # ---- round state ---------------------------------------------------

    def _new_round(self) -> None:
        super()._new_round()
        self.blocks: list[dict] = []
        self.bpm = self._start_bpm
        self.since_beat = 0.0
        self.hits = 0
        self.misses = 0
        self.hit_streak = 0
        self.miss_streak = 0
        self.flash = ("", 0.0, FG)          # text, show until (monotonic), colour

    def _end_fields(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "bpm": self.bpm}

    # ---- input ---------------------------------------------------------

    def _apply(self, label) -> None:
        if self.screen.key == "play":
            if label in ("Left", "Right"):
                self._on_flick(label.lower(), None)      # buttons act as flicks, any hand
                return
            if label == "Pain now":
                self.bpm = max(MIN_BPM, self.bpm - 10)
        super()._apply(label)

    def _on_key(self, event) -> None:
        if event.char in ("u", "d") and self.screen.key == "play":
            self._on_flick("up" if event.char == "u" else "down", None)
            return
        super()._on_key(event)

    def _on_acc(self, sample, role) -> None:
        super()._on_acc(sample, role)            # per-hand tilt and stats
        _seq, t_ms, x, y, z = sample
        fwd_tracker = self.fwd[role]
        fwd_tracker.update(x, y, z)
        # Absolute angles: only the change matters, so a "zero" press cannot fake a flick.
        side, fwd = self.fast[role].absolute, fwd_tracker.absolute
        self.data.add("og", "flick_angles", role=role,
                      side_deg=round(side, 1), fwd_deg=round(fwd, 1))
        direction = self.detectors[role].update(t_ms / 1000.0, side, fwd)
        if direction and direction in self.allowed and self.screen.key == "play":
            self._on_flick(direction, role)

    def _on_flick(self, direction: str, hand) -> None:
        if direction not in self.allowed:
            return
        now = self.play_seconds + (time.monotonic() - self._last)
        result, block = match_flick(self.blocks, direction, now, WINDOW, hand=hand)
        if result == "none":
            self.session.record("flick", role=hand, dir=direction, result="none")
            return
        if result == "wrong_hand":
            self._say("WRONG HAND", "#f5a524")
            self.session.record("wrong_hand", role=hand, dir=direction)
            return
        err_ms = int((now - block["t_hit"]) * 1000)
        self.blocks.remove(block)
        owner = block.get("hand")
        if result == "hit":
            self._score(True, owner)
            self._say("HIT", DIR_COLORS[direction])
            self.session.record("hit", role=hand, n=self.hits, dir=direction, err_ms=err_ms)
        else:
            self._score(False, owner)
            self._say("WRONG WAY", "#ef4444")
            self.session.record("wrong", role=hand, n=self.misses,
                                want=block["dir"], got=direction)

    # ---- the game ------------------------------------------------------

    def _score(self, hit: bool, owner) -> None:
        self._attempt(owner, hit)
        self._perf(1 if hit else 0)
        if hit:
            self.hits += 1
            self.hit_streak += 1
            self.miss_streak = 0
            if self.hit_streak >= 8:
                self.bpm = min(MAX_BPM, self.bpm + 5)
                self.hit_streak = 0
        else:
            self.misses += 1
            self.miss_streak += 1
            self.hit_streak = 0
            if self.miss_streak >= 3:
                self.bpm = max(MIN_BPM, self.bpm - 5)
                self.miss_streak = 0

    def _say(self, text: str, color: str) -> None:
        self.flash = (text, time.monotonic() + 0.5, color)

    def _advance(self, dt: float) -> None:
        self.play_seconds += dt
        self.since_beat += dt
        period = 60.0 / self.bpm
        if self.since_beat >= period:
            self.since_beat -= period
            self.blocks.append({"dir": random.choice(self.allowed),
                                "hand": random.choice(self.hand_roles),
                                "t_hit": self.play_seconds + LEAD, "state": "live"})
        for b in list(self.blocks):
            if self.play_seconds > b["t_hit"] + WINDOW:
                self.blocks.remove(b)
                self._score(False, b.get("hand"))
                self._say("MISS", "#ef4444")
                self.session.record("miss", role=b.get("hand"), n=self.misses, want=b["dir"])

    # ---- drawing -------------------------------------------------------

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        width = x1 - x0
        line_y = y1 - 34
        top = y0 + 24
        c.create_rectangle(x0, y0, x1, y1, outline="#30363d", tags="body")
        c.create_line(x0 + 30, line_y, x1 - 30, line_y, fill=DIM, width=3, tags="body")
        if self.hand_roles != (None,):
            for hand in (LEFT, RIGHT):
                lx = x0 + LANE_X[hand] * width
                c.create_line(lx, y0 + 20, lx, line_y, fill="#21262d", tags="body")
                c.create_text(lx, line_y + 14, text={LEFT: "LEFT", RIGHT: "RIGHT"}[hand],
                              fill=DIM, font=("Segoe UI", 10, "bold"), tags="body")
        for b in self.blocks:
            progress = 1.0 - (b["t_hit"] - self.play_seconds) / LEAD
            y = top + progress * (line_y - top)
            cx = x0 + LANE_X[b.get("hand")] * width
            color = DIR_COLORS[b["dir"]]
            if dim:
                color = blend(color, PANEL, 0.6)
            c.create_rectangle(cx - 26, y - 26, cx + 26, y + 26, fill=color,
                               outline="", tags="body")
            c.create_text(cx, y, text=ARROWS[b["dir"]], fill="#0d1117",
                          font=("Segoe UI", 26, "bold"), tags="body")
            badge = BADGE.get(b.get("hand"))
            if badge:
                c.create_text(cx - 20, y - 20, text=badge, fill="#0d1117",
                              font=("Segoe UI", 10, "bold"), tags="body")
        c.create_text(x0 + 8, y0 + 6, anchor="nw", fill=DIM, font=("Segoe UI", 11),
                      text=f"Hits {self.hits}    Misses {self.misses}    "
                           f"Tempo {self.bpm} BPM", tags="body")
        text, until, color = self.flash
        if text and time.monotonic() < until and not dim:
            c.create_text((x0 + x1) / 2, y0 + 40, text=text, fill=color,
                          font=("Segoe UI", 20, "bold"), tags="body")
        if self.screen.key == "paused":
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="PAUSED", fill=FG,
                          font=("Segoe UI", 34, "bold"), tags="body")

    def _summary_lines(self) -> list:
        total = self.hits + self.misses
        accuracy = f"{100 * self.hits / total:.0f}%" if total else "-"
        return [
            f"Hits  {self.hits}",
            f"Misses  {self.misses}",
            f"Accuracy  {accuracy}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
            f"Time  {self.play_seconds:.0f} s",
        ]


def main() -> None:
    ap = build_game_args("WiliRehab rhythm flick")
    ap.add_argument("--dirs", choices=("lr", "all"), default="all",
                    help="all = left, right, up and down flicks (default); lr = sideways only")
    ap.add_argument("--hands", choices=("auto", "one", "both"), default="auto",
                    help="both = arrows marked L and R, one OG per hand; "
                         "auto = both when two OGs are connected")
    ap.add_argument("--bpm", type=int, default=START_BPM, help="starting tempo")
    ap.add_argument("--flick-dps", type=float, default=150.0,
                    help="flick speed threshold in degrees per second (lower = easier)")
    args = ap.parse_args()
    ports = resolve_ports(args)
    root = tk.Tk()
    RhythmApp(root, ports, args.log_dir, axis=args.axis,
              invert_roles=parse_roles(args.invert_roles),
              invert_fwd_roles=parse_roles(args.invert_fwd_roles), dirs=args.dirs,
              bpm=args.bpm, flick_dps=args.flick_dps, hands=args.hands,
              driver=args.driver)
    root.mainloop()


if __name__ == "__main__":
    main()
