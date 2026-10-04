"""Catch game, and the base class every other game builds on.

Stars fall; move the basket under them. It is the button-map demo with a game
drawn in its body area, so the legend, ring animation, banner, log and the
real-OG input are all inherited from mapping_demo.

Controls (see button_map.py, Gameplay screen):
    yellow = Left   blue = Right   green = Pause   gray = Pain now   red = End
Press flow: play -> (pause) -> end? -> pain check-in -> summary -> new round.

Difficulty adapts in two small steps so it stays easy to follow:
  - every 5 catches in a row it speeds up a little
  - a miss, or a "Pain now" press, slows it down

One or two OGs (left_hand, right_hand). Every OG's tilt is measured per hand;
with both present the summary adds a symmetry table. Only the *driver* OG
steers this game. A button on either OG acts as that button.

Only numbers are logged: sessions/session-<time>.jsonl (events) and
sessions/data-<time>.csv (every reading, with its hand).

Run from wilirehab/host:
    python -m wilirehab.catch_game
    python -m wilirehab.catch_game --port COM5 --tilt        # one OG steers
    python -m wilirehab.catch_game --tilt --driver left_hand  # two OGs, left steers
Keys while testing without the OG: 1 gray, 2 yellow, 3 green, 4 blue, 5 red;
z sets neutral; l / r set your own left / right tilt range (tilt mode).
"""
from __future__ import annotations

import argparse
import queue
import random
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from statistics import median

from .bilateral import HandStats, format_row, symmetry_report
from .button_map import SCREENS, SCREENS_BY_KEY
from .cli import add_common_args, parse_roles, resolve_ports
from .data_panel import DataPanel
from .datatable import DataTable
from .mapping_demo import App, BG, DIM, FG, PANEL, W, blend
from .measures import describe_trend, tremor_band, trend_per_minute
from .og_link import OgLink
from .session import SessionLog
from .tilt import TiltTracker, raw_to_mg, to_position

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


class TeeLog:
    """The session log, which also feeds the live data table.

    Every game event (catch, miss, hit, pain score, ...) lands in both, so the
    call sites do not change. "tilt" is skipped here because the table gets a
    richer tilt row straight from the sensor. A `role=` field names the hand.
    """

    SKIP = {"tilt"}

    def __init__(self, log: SessionLog, data: DataTable):
        self.log = log
        self.data = data

    def record(self, kind: str, **fields) -> None:
        self.log.record(kind, **fields)
        if kind not in self.SKIP:
            self.data.add("game", kind, **fields)

    def close(self) -> None:
        self.log.close()


class GameApp(App):
    TITLE = "WiliRehab catch game"
    # What the summary's fatigue line tracks, or None for no trend line:
    # (label, unit, multiply values by, "steady" below this per minute, higher is better).
    PERF = ("Success rate", "%", 100.0, 2.0, True)

    def __init__(self, root: tk.Tk, ports: dict, log_dir, tilt=False, axis="y",
                 invert_roles=(), range_deg=12.0, driver="right_hand", stream=None,
                 invert_fwd_roles=()):
        # Everything below is set before App.__init__, which renders straight away.
        self.roles = tuple(ports)
        self.driver = driver if driver in ports else (next(iter(ports)) if ports else driver)
        self.invert_roles = set(invert_roles)
        # The steady angles that steer games: median of 3, then a 1-euro filter (as calm as
        # the old fixed smoothing at rest, about a third of the delay), then a 0.4 degree
        # dead band so a still hand does not flicker.
        steady = dict(median_len=3, euro=(0.5, 0.02), band_deg=0.4)
        self.slow = {r: TiltTracker(axis=axis, invert=r in self.invert_roles, **steady)
                     for r in self.roles}
        # Light filtering for speed and flicks; no shaky-hold, fast motion is the signal.
        self.fast = {r: TiltTracker(axis=axis, invert=r in self.invert_roles, alpha=0.5,
                                    median_len=3, hold_shaky=False)
                     for r in self.roles}
        # Pitch = tilt forward/back, the other accelerometer axis. With the forearm flat
        # that is wrist flexion/extension; roll (above) is forearm rotation.
        fwd_axis = "x" if axis == "y" else "y"
        self.pitch = {r: TiltTracker(axis=fwd_axis, invert=r in set(invert_fwd_roles), **steady)
                      for r in self.roles}
        self.pitch_fast = {r: TiltTracker(axis=fwd_axis, invert=r in set(invert_fwd_roles),
                                          alpha=0.5, median_len=3, hold_shaky=False)
                           for r in self.roles}
        self.pitch_angles: dict = {}
        self._null_tracker = TiltTracker(axis=axis)
        self._acc_mg = {r: deque(maxlen=256) for r in self.roles}    # for tremor
        self._acc_ms = {r: deque(maxlen=256) for r in self.roles}
        self._tremor_next = {r: 0.0 for r in self.roles}
        self._down_at: dict = {}
        self._press_role = None
        self.angles: dict = {}
        self._statuses: dict = {}
        self.tilt_mode = tilt
        self._stream = tilt if stream is None else stream
        self.links: dict = {}
        self._new_round()
        self.last_pain = None
        self.left_deg = range_deg       # full-left and full-right tilt; press l / r to set
        self.right_deg = range_deg
        self.target_x = 0.5
        self.tilt_angle = 0.0
        self._last_tilt_log = 0.0
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.data = DataTable(Path(log_dir) / f"data-{stamp}.csv")
        self.session = TeeLog(SessionLog(Path(log_dir) / f"session-{stamp}.jsonl"), self.data)
        self._last = time.monotonic()
        # The base class would start its own button-only reader; OgLink also
        # carries tilt and can send commands.
        super().__init__(root, None)
        root.title(self.TITLE)
        self.panel = DataPanel(root, self.data)
        self.panel.grid(row=0, column=2, sticky="ns", padx=(0, 12), pady=12)
        for role, port in ports.items():
            link = OgLink(port, self.events, role=role,
                          on_connect=("STREAM 50",) if self._stream else ())
            link.start()
            self.links[role] = link
        self._go("play")
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(TICK_MS, self._game_tick)

    @property
    def tracker(self) -> TiltTracker:
        """The driver OG's steady tracker (a harmless dummy when there is none)."""
        return self.slow.get(self.driver, self._null_tracker)

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
        self.stats = {r: HandStats() for r in self.roles}
        self.perf_points: list = []                 # (play seconds, value) for the trend
        self.tremor_rms = {r: [] for r in self.roles}
        self.held_ms = {r: [] for r in self.roles}  # how long each button was held

    def _perf(self, value: float) -> None:
        """Note one performance value (what PERF says it means) for the trend line."""
        self.perf_points.append((self.play_seconds, float(value)))

    def _attempt(self, role, hit: bool) -> None:
        if role in self.stats:
            self.stats[role].attempt(hit)

    def _go(self, key: str) -> None:
        self._select(SCREENS.index(SCREENS_BY_KEY[key]))

    def _close(self) -> None:
        for link in self.links.values():
            link.close()
        self.session.close()
        self.data.close()
        self.root.destroy()

    def press(self, button: str, source: str) -> None:
        # source is "click", "key", or "OG:<role>" for a real button.
        role = source.split(":", 1)[1] if source.startswith("OG:") else None
        self._press_role = role          # games read this in _apply to know which hand
        if role:
            self._down_at[(role, button)] = time.monotonic()
        self.data.add("og" if role else "keyboard", "button", role=role,
                      color=button, action=self.screen.label(button) or "-",
                      screen=self.screen.key)
        super().press(button, source)

    # ---- input from the OGs ------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                kind, value, role = self.events.get_nowait()
                if kind == "press":
                    self.press(value, f"OG:{role}")
                elif kind == "release":
                    self._on_release(value, role)
                elif kind == "acc":
                    seq, t_ms, x, y, z = value
                    self.data.add("og", "acc", device_ms=t_ms, role=role, seq=seq,
                                  x_mg=raw_to_mg(x), y_mg=raw_to_mg(y), z_mg=raw_to_mg(z))
                    self._on_acc(value, role)
                else:
                    self._statuses[role] = value
                    self.status.configure(
                        text="\n".join(f"{r}: {s}" for r, s in self._statuses.items()))
        except queue.Empty:
            pass
        self.root.after(20, self._poll)

    def _on_release(self, button: str, role) -> None:
        """A button came up: how long was it held? (A rough finger-release measure.)"""
        started = self._down_at.pop((role, button), None)
        if started is None:
            return
        ms = int((time.monotonic() - started) * 1000)
        if self.screen.key == "play":
            self.held_ms[role].append(ms)
        self.data.add("og", "press", role=role, color=button, held_ms=ms)

    def _check_tremor(self, role, t_ms: int) -> None:
        """Every 2 s of play, the 4-12 Hz shake strength from the last ~5 s."""
        if self.screen.key != "play" or t_ms < self._tremor_next[role]:
            return
        self._tremor_next[role] = t_ms + 2000
        result = tremor_band(list(self._acc_mg[role]), list(self._acc_ms[role]))
        if result:
            rms, peak_hz = result
            self.tremor_rms[role].append(rms)
            self.data.add("og", "tremor", role=role, rms_mg=round(rms, 1),
                          peak_hz=round(peak_hz, 1))

    def _on_acc(self, sample, role) -> None:
        _seq, t_ms, x, y, z = sample
        slow_tracker, fast_tracker = self.slow[role], self.fast[role]
        when = t_ms / 1000.0                    # the OG's own clock, not USB arrival time
        slow = slow_tracker.update(x, y, z, when)
        fast_tracker.update(x, y, z)
        pitch = self.pitch[role].update(x, y, z, when)
        self.pitch_fast[role].update(x, y, z)
        self.angles[role] = slow
        self.pitch_angles[role] = pitch
        self._acc_mg[role].append((raw_to_mg(x), raw_to_mg(y), raw_to_mg(z)))
        self._acc_ms[role].append(t_ms)
        if self.screen.key == "play":
            self.stats[role].update(t_ms / 1000.0, slow, fast_tracker.absolute,
                                    pitch, self.pitch_fast[role].absolute)
        self._check_tremor(role, t_ms)
        self.data.add("og", "tilt", role=role, roll_deg=round(slow, 1),
                      pitch_deg=round(pitch, 1), steady=slow_tracker.steady)
        if role != self.driver:
            return
        self.tilt_angle = slow
        if self.tilt_mode and self.screen.key == "play":
            self.target_x = to_position(slow, self.left_deg, self.right_deg)
            now = time.monotonic()
            if now - self._last_tilt_log >= 0.1:        # 10 lines a second at most
                self._last_tilt_log = now
                self.session.record("tilt", deg=round(slow, 1),
                                    steady=slow_tracker.steady)

    def _on_key(self, event) -> None:
        if event.char == "z":
            for tracker in (*self.slow.values(), *self.fast.values(),
                            *self.pitch.values(), *self.pitch_fast.values()):
                tracker.zero()              # next sample becomes neutral
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
            self._end_session()
            self._go("pain")
            return
        if key == "summary" and label == "Done":
            self._new_round()
            self._go("play")
            return

        target = NEXT.get((key, label))
        if target:
            self._go(target)

    def _end_fields(self) -> dict:
        """Game-specific numbers for the session_end row; games override this."""
        return {"caught": self.caught, "missed": self.missed}

    def _end_session(self) -> None:
        """Log the headline numbers, one row per hand, then the comparison."""
        self.session.record("session_end", seconds=round(self.play_seconds, 1),
                            **self._end_fields())
        for role, s in self.stats.items():
            tremor = self.tremor_rms.get(role)
            held = self.held_ms.get(role)
            self.session.record(
                "hand", role=role, samples=s.samples,
                roll_range_deg=round(s.range_deg, 1),
                pitch_range_deg=round(s.pitch_range_deg, 1),
                peak_dps=round(s.peak_dps, 1), hits=s.hits, attempts=s.attempts,
                tremor_rms_mg=round(median(tremor), 1) if tremor else None,
                press_ms=int(median(held)) if held else None)
        slope = self._trend_slope()
        if slope is not None:
            self.session.record("trend", label=self.PERF[0], per_min=round(slope, 2))
        report = symmetry_report(self.stats)
        if report:
            ratio = {r.name: r for r in report}
            pitch = ratio.get("Pitch range")
            self.session.record(
                "symmetry",
                roll_ratio=_round(ratio["Roll range"].ratio),
                pitch_ratio=_round(pitch.ratio) if pitch else None,
                speed_ratio=_round(ratio["Peak deg/s"].ratio),
                hit_ratio=_round(ratio["Hit rate %"].ratio),
                weaker_roll=ratio["Roll range"].weaker,
                weaker_speed=ratio["Peak deg/s"].weaker)

    def _trend_slope(self):
        """Change of the PERF value per minute over the session, or None."""
        if not self.PERF or not self.perf_points:
            return None
        scale = self.PERF[2]
        return trend_per_minute([(t, v * scale) for t, v in self.perf_points])

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
        self._attempt(self.driver, True)
        self._perf(1)
        if self.streak % 5 == 0:
            self.speed = min(MAX_SPEED, self.speed * 1.1)
            self.gap = max(MIN_GAP, self.gap * 0.95)
        self.session.record("catch", n=self.caught, speed=round(self.speed, 2))

    def _on_miss(self) -> None:
        self.missed += 1
        self.streak = 0
        self._attempt(self.driver, False)
        self._perf(0)
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

    def _summary_lines(self) -> list:
        return [
            f"Caught  {self.caught}",
            f"Missed  {self.missed}",
            f"Pain-now presses  {self.pain_events}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
            f"Time  {self.play_seconds:.0f} s",
        ]

    def _extra_lines(self) -> list:
        """Lines every game gets: the fatigue trend and the tremor strength."""
        lines = []
        if self.PERF:
            label, unit, _scale, flat, better_high = self.PERF
            slope = self._trend_slope()
            text = describe_trend(slope, flat, unit, better_high)
            lines.append(f"{label} trend  {text if text else 'needs a longer session'}")
        shown = {r: median(v) for r, v in self.tremor_rms.items() if v}
        if shown:
            short = {"left_hand": "L", "right_hand": "R"}
            parts = "  ".join(f"{short.get(r, r)} {v:.1f}" for r, v in shown.items())
            lines.append(f"Tremor 4-12 Hz  {parts} mg")
        return lines

    def _draw_summary(self) -> None:
        lines = self._summary_lines() + self._extra_lines()
        for i, text in enumerate(lines):
            self.canvas.create_text(W / 2, 108 + 18 * i, text=text, fill=FG,
                                    font=("Segoe UI", 13), tags="body")
        report = symmetry_report(self.stats)
        if not report:
            return
        y = 108 + 18 * len(lines) + 6
        head = f"{'':<11}{'L':>6}{'R':>6}{'ratio':>6}"
        self.canvas.create_text(W / 2, y, text=head, fill=DIM,
                                font=("Consolas", 11), tags="body")
        for i, row in enumerate(report):
            self.canvas.create_text(W / 2, y + 17 * (i + 1), text=format_row(row),
                                    fill=FG, font=("Consolas", 11), tags="body")


def _round(v):
    return None if v is None else round(v, 2)


def build_game_args(description: str):
    ap = argparse.ArgumentParser(description=description)
    add_common_args(ap)
    return ap


def main() -> None:
    ap = build_game_args("WiliRehab catch game")
    ap.add_argument("--tilt", action="store_true",
                    help="steer by tilting the driver OG; press z to set neutral")
    ap.add_argument("--range-deg", type=float, default=12.0,
                    help="starting tilt that reaches each edge (default 12); "
                         "press l and r in the window to set your own")
    args = ap.parse_args()
    ports = resolve_ports(args)
    if args.tilt and not ports:
        ap.error("--tilt needs an OG: pass --port COM5 or set up devices.json")
    root = tk.Tk()
    GameApp(root, ports, args.log_dir, tilt=args.tilt, axis=args.axis,
            invert_roles=parse_roles(args.invert_roles), range_deg=args.range_deg,
            driver=args.driver, stream=bool(ports),
            invert_fwd_roles=parse_roles(args.invert_fwd_roles))
    root.mainloop()


if __name__ == "__main__":
    main()
