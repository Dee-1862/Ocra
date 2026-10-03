"""Catch game: the first game, steered by the OG buttons.

Stars fall; move the basket under them. It is the button-map demo with a game
drawn in its body area, so the legend, ring animation, banner, log and the
real-OG input are all inherited from mapping_demo.

Controls (see button_map.py, Gameplay screen):
    yellow = Left   blue = Right   green = Pause   gray = Pain now   red = End
Press flow: play -> (pause) -> end? -> pain check-in -> summary -> new round.

Difficulty adapts in two small steps so it stays easy to follow:
  - every 5 catches in a row it speeds up a little
  - a miss, or a "Pain now" press, slows it down

Only numbers are logged (session.py), to sessions/session-<time>.jsonl.

Run from wilirehab/host:
    python -m wilirehab.catch_game
    python -m wilirehab.catch_game --port COM5     # steer with the real OG
Keys while testing without the OG: 1 gray, 2 yellow, 3 green, 4 blue, 5 red.
"""
from __future__ import annotations

import argparse
import queue
import random
import time
import tkinter as tk
from pathlib import Path

from .button_map import SCREENS, SCREENS_BY_KEY
from .mapping_demo import App, BG, DIM, FG, PANEL, W, blend
from .og_link import OgLink
from .session import SessionLog
from .tilt import TiltTracker, to_position

FIELD = (24, 104, W - 24, 282)    # x0, y0, x1, y1 on the canvas
STEP = 0.10                       # basket move per press, as a fraction of the field
CATCH_HALF = 0.09                 # half the basket width, same units
BASE_SPEED = 0.45                 # fall speed, field heights per second
MIN_SPEED, MAX_SPEED = 0.20, 1.20
BASE_GAP, MIN_GAP, MAX_GAP = 1.4, 0.7, 2.2   # seconds between stars
TICK_MS = 33
TILT_SLEW = 2.5                   # fastest the basket may move when tilt-steered, field widths/s

STAR = "#f5c400"
BASKET = "#22c55e"

# (screen, label pressed) -> screen to go to.
NEXT = {
    ("play", "Pause"): "paused",
    ("play", "End"): "end",
    ("paused", "Resume"): "play",
    ("paused", "End"): "end",
    ("end", "Keep going"): "play",
}


class GameApp(App):
    def __init__(self, root: tk.Tk, port, log_dir, tilt=False, axis="y",
                 invert=False, range_deg=12.0):
        # Set up before App.__init__, which renders straight away.
        self._new_round()
        self.last_pain = None
        self.link = None
        self.tilt_mode = tilt
        self.tracker = TiltTracker(axis=axis, invert=invert)
        self.left_deg = range_deg       # full-left and full-right tilt; press l / r to set
        self.right_deg = range_deg
        self.target_x = 0.5
        self.tilt_angle = 0.0
        self._last_tilt_log = 0.0
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self.session = SessionLog(Path(log_dir) / time.strftime("session-%Y%m%d-%H%M%S.jsonl"))
        self._last = time.monotonic()
        # The base class would start its own button-only reader; we use OgLink,
        # which also carries tilt and can send commands.
        super().__init__(root, None)
        root.title("WiliRehab catch game")
        if port:
            self.link = OgLink(port, self.events,
                               on_connect=("STREAM 50",) if tilt else ())
            self.link.start()
        self._go("play")
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(TICK_MS, self._game_tick)

    # ---- round state -------------------------------------------------

    def _new_round(self) -> None:
        self.bx = 0.5
        self.items: list[dict] = []
        self.caught = 0
        self.missed = 0
        self.streak = 0
        self.pain_events = 0
        self.speed = BASE_SPEED
        self.gap = BASE_GAP
        self.since_spawn = 0.0
        self.play_seconds = 0.0

    def _go(self, key: str) -> None:
        self._select(SCREENS.index(SCREENS_BY_KEY[key]))

    def _close(self) -> None:
        if self.link:
            self.link.close()
        self.session.close()
        self.root.destroy()

    # ---- input from the OG -------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "press":
                    self.press(value, "OG")
                elif kind == "acc":
                    self._on_acc(value)
                else:
                    self.status.configure(text=value)
        except queue.Empty:
            pass
        self.root.after(20, self._poll)

    def _on_acc(self, sample) -> None:
        _seq, _t_ms, x, y, z = sample
        self.tilt_angle = self.tracker.update(x, y, z)
        if self.tilt_mode and self.screen.key == "play":
            self.target_x = to_position(self.tilt_angle, self.left_deg, self.right_deg)
            now = time.monotonic()
            if now - self._last_tilt_log >= 0.1:        # 10 lines a second at most
                self._last_tilt_log = now
                self.session.record("tilt", deg=round(self.tilt_angle, 1),
                                    steady=self.tracker.steady)

    def _on_key(self, event) -> None:
        if event.char == "z":
            self.tracker.zero()             # next sample becomes neutral
            self.status.configure(text="Neutral set to the current pose")
            return
        if event.char in ("l", "r") and self.tilt_mode:
            self._set_extreme(event.char)
            return
        super()._on_key(event)

    def _set_extreme(self, side: str) -> None:
        """Remember how far the player can comfortably tilt each way."""
        angle = self.tilt_angle
        if side == "l" and angle < -3.0:
            self.left_deg = -angle
        elif side == "r" and angle > 3.0:
            self.right_deg = angle
        else:
            self.status.configure(
                text="Tilt fully " + ("left" if side == "l" else "right")
                     + " first (at least 3 degrees), then press " + side)
            return
        self.status.configure(
            text=f"Range set: left {self.left_deg:.0f} deg, right {self.right_deg:.0f} deg")

    # ---- what each press does ---------------------------------------

    def _apply(self, label) -> None:
        if not label:
            return
        key = self.screen.key

        if key == "pain":
            if label in ("+1", "-1"):
                super()._apply(label)
            elif label == "Confirm":
                self.last_pain = self.pain          # _go() resets self.pain
                self.session.record("pain_score", value=self.pain)
                self._go("summary")
            return

        if key == "play":
            if label == "Left":
                if not self.tilt_mode:          # tilt steers; buttons then do nothing
                    self.bx = max(0.0, self.bx - STEP)
            elif label == "Right":
                if not self.tilt_mode:
                    self.bx = min(1.0, self.bx + STEP)
            elif label == "Pain now":
                self.pain_events += 1
                self.speed = max(MIN_SPEED, self.speed * 0.8)
                self.session.record("pain_now", at_s=round(self.play_seconds, 1))
                return
            elif label in ("Pause", "End"):
                self.session.record(label.lower(), at_s=round(self.play_seconds, 1))

        if key == "end" and label == "End now":
            self.session.record("session_end", caught=self.caught, missed=self.missed,
                                seconds=round(self.play_seconds, 1))
            self._go("pain")
            return
        if key == "summary" and label == "Done":
            self._new_round()
            self._go("play")
            return

        target = NEXT.get((key, label))
        if target:
            self._go(target)

    # ---- the game ----------------------------------------------------

    def _game_tick(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        if self.screen.key == "play":
            if self.tilt_mode:
                step = TILT_SLEW * dt
                self.bx += max(-step, min(step, self.target_x - self.bx))
            self._advance(dt)
            self._draw_body()
        self.root.after(TICK_MS, self._game_tick)

    def _advance(self, dt: float) -> None:
        self.play_seconds += dt
        self.since_spawn += dt
        if self.since_spawn >= self.gap:
            self.since_spawn = 0.0
            self.items.append({"x": random.uniform(0.08, 0.92), "y": 0.0})
        still_falling = []
        for it in self.items:
            it["y"] += self.speed * dt
            if it["y"] < 1.0:
                still_falling.append(it)
            elif abs(it["x"] - self.bx) <= CATCH_HALF:
                self._on_catch()
            else:
                self._on_miss()
        self.items = still_falling

    def _on_catch(self) -> None:
        self.caught += 1
        self.streak += 1
        if self.streak % 5 == 0:
            self.speed = min(MAX_SPEED, self.speed * 1.1)
            self.gap = max(MIN_GAP, self.gap * 0.95)
        self.session.record("catch", n=self.caught, speed=round(self.speed, 2))

    def _on_miss(self) -> None:
        self.missed += 1
        self.streak = 0
        self.speed = max(MIN_SPEED, self.speed * 0.9)
        self.gap = min(MAX_GAP, self.gap * 1.05)
        self.session.record("miss", n=self.missed, speed=round(self.speed, 2))

    # ---- drawing -----------------------------------------------------

    def _draw_body(self) -> None:
        key = self.screen.key
        if key == "pain":
            super()._draw_body()
            return
        self.canvas.delete("body")
        if key in ("play", "paused", "end"):
            self._draw_field(dim=(key != "play"))
        elif key == "summary":
            self._draw_summary()

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        w = x1 - x0
        basket_y = y1 - 14
        top = y0 + 10
        bottom = basket_y - 12
        c.create_rectangle(x0, y0, x1, y1, outline="#30363d", tags="body")
        star = blend(STAR, PANEL, 0.6) if dim else STAR
        for it in self.items:
            cx = x0 + it["x"] * w
            cy = top + it["y"] * (bottom - top)
            c.create_oval(cx - 9, cy - 9, cx + 9, cy + 9, fill=star, outline="", tags="body")
        bx = x0 + self.bx * w
        half = CATCH_HALF * w
        c.create_rectangle(bx - half, basket_y - 7, bx + half, basket_y + 7,
                           fill=blend(BASKET, PANEL, 0.6) if dim else BASKET,
                           outline="", tags="body")
        c.create_text(x0 + 8, y0 + 6, anchor="nw", fill=DIM, font=("Segoe UI", 11),
                      text=f"Caught {self.caught}    Missed {self.missed}    "
                           f"Speed {self.speed / BASE_SPEED:.1f}x"
                           + (f"    Tilt {self.tilt_angle:+.0f} deg"
                              + ("" if self.tracker.steady else " (shaky)")
                              if self.tilt_mode else ""),
                      tags="body")
        if self.screen.key == "paused":
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="PAUSED", fill=FG,
                          font=("Segoe UI", 34, "bold"), tags="body")

    def _draw_summary(self) -> None:
        lines = [
            f"Caught  {self.caught}",
            f"Missed  {self.missed}",
            f"Pain-now presses  {self.pain_events}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
            f"Time  {self.play_seconds:.0f} s",
        ]
        for i, text in enumerate(lines):
            self.canvas.create_text(W / 2, 140 + 30 * i, text=text, fill=FG,
                                    font=("Segoe UI", 18), tags="body")


def main() -> None:
    ap = argparse.ArgumentParser(description="WiliRehab catch game")
    ap.add_argument("--port", help="serial port of the OG display CPU, e.g. COM5")
    ap.add_argument("--log-dir", default="sessions", help="where session logs go")
    ap.add_argument("--tilt", action="store_true",
                    help="steer by tilting the OG (needs --port); press z to set neutral")
    ap.add_argument("--axis", choices=("x", "y"), default="y",
                    help="which OG axis is sideways when it is worn (default y)")
    ap.add_argument("--invert", action="store_true", help="flip left and right")
    ap.add_argument("--range-deg", type=float, default=12.0,
                    help="starting tilt that reaches each edge (default 12); "
                         "press l and r in the window to set your own")
    args = ap.parse_args()
    if args.tilt and not args.port:
        ap.error("--tilt needs --port, e.g. --port COM5")
    root = tk.Tk()
    GameApp(root, args.port, args.log_dir, args.tilt, args.axis, args.invert,
            args.range_deg)
    root.mainloop()


if __name__ == "__main__":
    main()
