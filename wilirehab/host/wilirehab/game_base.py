"""The base class every game builds on.

It is the button-map demo with a game drawn in its body area, so the legend, ring
animation, banner, log and the real-OG input all come from mapping_demo. This class adds:
the play / pause / end / pain check-in / summary flow, the OG link (one OG), tilt trackers
for roll and pitch, per-hand statistics, tremor, the data table and the numbers-only log.

A game subclasses GameApp and overrides what it needs: _new_round, _advance, _draw_field,
_summary_lines, _end_fields, and optionally _apply, _on_key and _on_acc (call super()).

Controls (see button_map.py, Gameplay screen):
    gray = Face   yellow = Hand   green = Pause   blue = Pain now   red = End
    Paused: green = Resume   blue = Re-zero   red = Restart   (gray, yellow as above)
    Summary: green = Restart   red = Menu (under og_shell; the game window closes)
Press flow: play -> (pause) -> end? -> pain check-in -> summary -> new round.
Face and Hand open a full-size readings page over the play area and pause the game; press
the same button again to close the page, or Resume. Pain now logs "this hurts" (see
_apply). Re-zero makes the current pose neutral.

Only numbers are logged: sessions/session-<time>.jsonl (events) and
sessions/data-<time>.csv (every reading).
Keys while testing without the OG: 1 gray, 2 yellow, 3 green, 4 blue, 5 red; z sets neutral;
a / s stand in for tilting left / right (the old Left and Right buttons).
"""
from __future__ import annotations

import argparse
import queue
import threading
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from statistics import median

from PIL import ImageTk

from . import cli, ui
from .align import LagFusion
from .bilateral import HandStats, format_row, symmetry_report
from .button_map import PAGE_OPEN, SCREENS, SCREENS_BY_KEY
from .cli import add_common_args, parse_roles, resolve_ports
from .data_panel import DataPanel
from .datatable import DataTable
from .discomfort_panel import DiscomfortPanel
from .motion_discomfort import HandMonitor
from .face_view import FacePreview
from .og_screen import OgScreenWriter, buttons_live, compose, face_line, hand_line
from .mapping_demo import App, BG, DIM, FG, PAIN_STEPS, PANEL, W, blend
from .measures import describe_trend, tremor_band, trend_per_minute
from .og_link import OgLink, battery_percent
from .session import SessionLog
from .tilt import TiltTracker, raw_to_mg, to_position

FIELD = (24, 104, W - 24, 282)    # x0, y0, x1, y1 on the canvas
PANEL_BOX = (24, 96, W - 24, 380)  # a readings page: covers the field and the gap under it
STEP = 0.10                       # paddle move per press without an OG, a fraction of the field
TICK_MS = 33
TILT_SLEW = 2.5                   # fastest the basket may move when tilt-steered, field widths/s

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

    Every game event (hit, miss, pain score, ...) lands in both, so the
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
    TITLE = "WiliRehab game"
    # Shown on the OG's own screen (at most 17 characters).
    OG_NAME = "WILIREHAB"
    # True for a game that is played with the OG buttons (Colour Reflex). Every
    # other game ignores OG button presses while playing or paused, and takes
    # them again at the end of the game (see og_screen.buttons_live).
    USES_BUTTONS = False
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
        self.hand_monitors = {r: HandMonitor() for r in self.roles}
        self._last_hand: dict = {}
        self._last_face = None
        self._og_writers: dict = {}
        self._battery: dict = {}                   # role -> percent; empty until the OG reports it
        self._og_error_shown = False
        self.fusion = LagFusion()
        self._face_q: queue.Queue = queue.Queue()
        self._face_stop = threading.Event()
        self._face_thread = None
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
        self._shared_link = cli.SHELL["link"]      # the OG shell's link, or None
        self._on_exit = cli.SHELL["on_exit"]
        self._dead = False                         # set by _close; stops every timer
        self.page = None                           # None, "hand" or "face": a readings page
        # (not `panel`: that is the live-data table widget, set further down)
        self._preview = None                       # FacePreview, only while the face page shows
        self._panel_next = 0.0
        self._face_photo = None
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
        face_on = cli.FACE["camera"] is not None
        self.discomfort = DiscomfortPanel(root, self.data, face_on)
        self.discomfort.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))
        if face_on:
            self._start_face(cli.FACE["camera"], cli.FACE["rest_s"])
        root.after(100, self._poll_face)
        if self._shared_link is None:            # under the shell the whole screen is a picture
            root.after(300, self._tick_og_screen)
        for role, port in ports.items():
            on_connect = ("STREAM 50",) if self._stream else ()
            if self._shared_link is not None:
                self._shared_link.attach(self.events, role, on_connect)
                self.links[role] = self._shared_link
                continue
            link = OgLink(port, self.events, role=role, on_connect=on_connect)
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
        self.pain_events = 0
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

    def _select(self, index: int) -> None:
        super()._select(index)
        self._sync_legend()

    def _sync_legend(self) -> None:
        """While a readings page is open, the paused screen shows the page buttons."""
        if self.screen.key != "paused":
            return
        want = PAGE_OPEN if getattr(self, "page", None) else SCREENS_BY_KEY["paused"]
        if self.screen is not want:
            self.screen = want
            self._render()

    # ---- the webcam --------------------------------------------------

    def _start_face(self, camera: int, rest_s: float) -> None:
        """Run the face camera on its own thread; rows come back through a queue."""
        def work() -> None:
            try:
                from .face_monitor import FaceMonitor
                monitor = FaceMonitor(camera, rest_s=rest_s)
                monitor.run(self._face_stop, lambda row: self._face_q.put(("row", row)))
                if monitor.error:
                    self._face_q.put(("error", monitor.error))
            except Exception as exc:        # shown in the window, not swallowed
                self._face_q.put(("error", f"{type(exc).__name__}: {exc}"))

        self._face_thread = threading.Thread(target=work, daemon=True)
        self._face_thread.start()

    def _poll_face(self) -> None:
        if self._dead:
            return
        try:
            while True:
                kind, value = self._face_q.get_nowait()
                if kind == "error":
                    self.status.configure(text=f"Face camera stopped: {value}")
                    continue
                at = self.data.from_clock(value.pop("mono"))
                self.data.add("face", "reading", at=at, **value)
                self.fusion.add_face(at, value)
                self._last_face = value
        except queue.Empty:
            pass
        for event in self.fusion.poll(self.data.now()):
            self.data.add("fusion", "event", **event)
        self.root.after(100, self._poll_face)

    # ---- the OG's own screen ---------------------------------------------

    def _og_lines(self) -> list:
        """Up to three short lines of game data for the OG screen. Games override this."""
        return []

    def _tick_og_screen(self) -> None:
        """Keep each connected OG showing the game name and live data."""
        if self._dead:
            return
        try:
            summary = self._summary_lines() if self.screen.key == "summary" else ()
            for role, link in self.links.items():
                if not link.connected:
                    continue
                writer = self._og_writers.get(role)
                if writer is None:
                    writer = self._og_writers[role] = OgScreenWriter(link.send)
                rows, bar = compose(
                    name=self.OG_NAME, screen_key=self.screen.key,
                    screen_title=self.screen.title, uses_buttons=self.USES_BUTTONS,
                    game_lines=self._og_lines(), hand=hand_line(self._last_hand.get(role)),
                    face=face_line(self._last_face), pain=self.pain,
                    elapsed_s=self.play_seconds, battery=self._battery.get(role),
                    summary_lines=summary)
                writer.show(rows, bar)
        except Exception as exc:        # shown in the window, once, not swallowed
            if not self._og_error_shown:
                self._og_error_shown = True
                self.status.configure(text=f"OG screen could not update: {exc}")
        self.root.after(250, self._tick_og_screen)

    def _close(self) -> None:
        if self._dead:
            return
        self._dead = True
        self.anims.clear()
        if self._preview is not None:
            self._preview.stop()
        for writer in self._og_writers.values():
            writer.idle()
        self._face_stop.set()
        if self._face_thread is not None:
            self._face_thread.join(timeout=2.0)
        for link in self.links.values():
            if self._shared_link is not None:
                link.detach()                   # the shell keeps the port
            else:
                link.close()
        self.session.close()
        self.data.close()
        if self._on_exit is not None:
            _cancel_pending(self.root)          # else Tk pops an error box for each timer
        self.root.destroy()
        if self._on_exit is not None:
            self._on_exit()

    def press(self, button: str, source: str) -> None:
        # source is "click", "key", or "OG:<role>" for a real button.
        role = source.split(":", 1)[1] if source.startswith("OG:") else None
        if role and not buttons_live(self.USES_BUTTONS, self.screen.key):
            # The OG's buttons are off during this game. The press is kept in the
            # data table so it is not lost, but nothing happens. The keyboard and
            # the on-screen buttons (the therapist) still work.
            self.data.add("og", "button", role=role, color=button, action="ignored",
                          screen=self.screen.key)
            self.status.configure(text="OG buttons are off while this game plays; "
                                       "they work again at the end of the game")
            return
        self._press_role = role          # games read this in _apply to know which hand
        if role:
            self._down_at[(role, button)] = time.monotonic()
        self.data.add("og" if role else "keyboard", "button", role=role,
                      color=button, action=self.screen.label(button) or "-",
                      screen=self.screen.key)
        super().press(button, source)

    # ---- input from the OGs ------------------------------------------

    def _poll(self) -> None:
        if self._dead:
            return
        try:
            while True:
                kind, value, role = self.events.get_nowait()
                if kind == "press":
                    self.press(value, f"OG:{role}")
                elif kind == "release":
                    self._on_release(value, role)
                elif kind == "battery":
                    mv, usb = value
                    self._battery[role] = battery_percent(mv)
                    self.data.add("og", "battery", role=role, mv=mv, usb=usb)
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
            hand_row = self.hand_monitors[role].add(
                t_ms / 1000.0, raw_to_mg(x), raw_to_mg(y), raw_to_mg(z), slow, pitch)
            if hand_row is not None:
                row = self.data.add("hand", "motion", role=role, **hand_row)
                self.fusion.add_hand(row["t"], hand_row)
                self._last_hand[role] = hand_row
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

    def _rezero(self) -> None:
        """Make the current pose neutral (key z, and the Re-zero button)."""
        for tracker in (*self.slow.values(), *self.fast.values(),
                        *self.pitch.values(), *self.pitch_fast.values()):
            tracker.zero()                  # next sample becomes neutral
        self.status.configure(text="Neutral set to the current pose")

    def _on_key(self, event) -> None:
        if event.char == "z":
            self._rezero()
            return
        if event.char in ("a", "s") and self.screen.key == "play":
            # Stand-ins for the old Left / Right buttons, for trying a game with no OG.
            # (Not "d": Steady Hand and Rhythm Flick already use u / d for up / down.)
            self._apply("Left" if event.char == "a" else "Right")
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
            if label in PAIN_STEPS:
                super()._apply(label)
            elif label == "OK":                         # no more change: keep this score
                self.last_pain = self.pain          # _go() resets self.pain
                self.session.record("pain_score", value=self.pain)
                self._go("summary")
            return

        if key in ("play", "paused"):
            if label in ("Hand", "Face"):
                mode = label.lower()
                self._set_panel(None if self.page == mode else mode, redraw=False)
                if key == "play" and self.page:           # a page to read means a game on hold
                    self.session.record("pause", at_s=round(self.play_seconds, 1))
                    self._go("paused")                    # redraws, page included
                else:
                    self._draw_body()
                return
            if label == "Next page" and key == "paused":
                self._set_panel("face" if self.page == "hand" else "hand")
                return
            if label == "Close" and key == "paused":
                self._set_panel(None)
                return
            if label == "End" and key == "paused":
                self._set_panel(None, redraw=False)
                self.session.record("end", at_s=round(self.play_seconds, 1))
                self._go("end")
                return
            if label == "Re-zero":
                self._rezero()
                return
            if label == "Restart" and key == "paused":
                # Close this round's numbers properly, then start a fresh one.
                self.session.record("restart", at_s=round(self.play_seconds, 1))
                self._end_session()
                self._new_round()
                self._set_panel(None, redraw=False)
                self._go("play")
                return
            if label == "Resume":
                self._set_panel(None, redraw=False)       # then NEXT below goes back to play

        if key == "play":
            if label == "Left":
                if not self.tilt_mode:          # tilt steers; buttons then do nothing
                    self.bx = max(0.0, self.bx - STEP)
            elif label == "Right":
                if not self.tilt_mode:
                    self.bx = min(1.0, self.bx + STEP)
            elif label == "Pain now":
                self.pain_events += 1
                self.session.record("pain_now", at_s=round(self.play_seconds, 1))
                return
            elif label in ("Pause", "End"):
                self.session.record(label.lower(), at_s=round(self.play_seconds, 1))

        if key == "end" and label == "End now":
            self._end_session()
            self._go("pain")
            return
        if key == "summary" and label == "Restart":
            self._new_round()
            self._go("play")
            return
        if key == "summary" and label == "Menu":
            if self._on_exit is not None:
                # Under the OG shell, red goes back to its menu. A moment later, so the
                # press animation finishes drawing on a window that still exists.
                self.root.after(200, self._close)
            else:
                self.status.configure(text="Close this window to leave, or start "
                                           "python -m wilirehab.og_shell for the menu")
            return

        target = NEXT.get((key, label))
        if target:
            self._go(target)

    def _end_fields(self) -> dict:
        """Game-specific numbers for the session_end row; games override this."""
        return {}

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
        if self._dead:
            return
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        try:
            if self.screen.key == "play":
                if self.tilt_mode:
                    step = TILT_SLEW * dt
                    self.bx += max(-step, min(step, self.target_x - self.bx))
                self._advance(dt)
                self._draw_body()
            elif self.screen.key == "paused" and self.page and now >= self._panel_next:
                self._panel_next = now + 0.1            # a page keeps updating while paused
                self._draw_body()
        finally:                                        # one bad frame must not stop the game
            if not self._dead:
                self.root.after(TICK_MS, self._game_tick)

    def _advance(self, dt: float) -> None:
        """Called every frame while playing. Games override this."""
        self.play_seconds += dt

    # ---- drawing -----------------------------------------------------

    def _draw_body(self) -> None:
        key = self.screen.key
        if key not in ("play", "paused") and self.page:
            self._set_panel(None, redraw=False)         # leaving the game closes any page
        if key == "pain":
            super()._draw_body()
            return
        self.canvas.delete("body")
        if key in ("play", "paused", "end"):
            self._draw_field(dim=(key != "play"))
            if self.page and key == "paused":
                self._draw_panel()
        elif key == "summary":
            self._draw_summary()

    def _draw_field(self, dim: bool) -> None:
        """Draw the play area. Games override this."""
        self._arena()

    def _arena(self) -> None:
        """The rounded, softly lit panel every game plays on."""
        x0, y0, x1, y1 = FIELD
        ui.rrect(self.canvas, x0, y0, x1, y1, r=18, top="#151d27", bottom="#0c1219",
                 border=ui.LINE, shadow=12, dots=True, tags="body")

    def _hud(self, items) -> None:
        """Stat pills on the title row, right-aligned: [(label, value[, colour])]."""
        ui.chips(self.canvas, W - 24, 24, items, tags="body", align="right")

    # ---- readings pages (the Hand and Face buttons) -------------------------

    def _set_panel(self, mode, redraw: bool = True) -> None:
        """Show the "hand" or "face" page, or None for the game. The face page starts the
        camera preview, unless the face monitor (--face) already holds the camera."""
        if mode != "face" and self._preview is not None:
            self._preview.stop()                    # frees the camera
            self._preview = None
        if mode == "face" and self._face_thread is None and self._preview is None:
            self._preview = FacePreview(cli.FACE.get("preview", 0))
            self._preview.start()
        self.page = mode
        self._sync_legend()
        if redraw:
            self._draw_body()

    def _draw_panel(self) -> None:
        c = self.canvas
        x0, y0, x1, y1 = PANEL_BOX
        # A layer over the game, not a separate section: mostly opaque, so the paused game
        # still shows faintly through it.
        ui.rrect(c, x0, y0, x1, y1, r=18, top=ui.BG, bottom=ui.BG, border=ui.LINE, alpha=0.93,
                 tags="body")
        c.create_text(x0 + 22, y0 + 24, text=self.page.upper(), anchor="w", fill=ui.ACCENT,
                      font=ui.font(12, True), tags="body")
        c.create_text(x1 - 22, y0 + 24, text="Paused. Green resumes", anchor="e", fill=DIM,
                      font=ui.font(11), tags="body")
        try:
            if self.page == "hand":
                self._draw_hand_page()
            else:
                self._draw_face_page()
        except Exception as exc:        # shown in the page itself, so it is never just blank
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, fill=ui.BAD, font=ui.font(12),
                          width=x1 - x0 - 60, tags="body",
                          text=f"This page could not be drawn:\n{type(exc).__name__}: {exc}")

    def _tiles(self, items, cols: int, top: int, bottom: int) -> None:
        """A table of (label, value, unit) rows between two heights, `cols` cells across.

        One row per reading: the label on the left, the number big on the right with a
        short unit after it. Wide and short, so nothing has to wrap or be cut off."""
        c, (x0, _y0, x1, _y1) = self.canvas, PANEL_BOX
        gap, pad = 10, 18
        rows = -(-len(items) // cols)
        w = (x1 - x0 - 2 * pad - gap * (cols - 1)) / cols
        h = (bottom - top - gap * (rows - 1)) / rows
        for i, (label, value, unit) in enumerate(items):
            tx = x0 + pad + (i % cols) * (w + gap)
            ty = top + (i // cols) * (h + gap)
            mid = ty + h / 2
            ui.rrect(c, tx, ty, tx + w, ty + h, r=12, top=ui.RAISED, bottom=ui.RAISED,
                     border=ui.LINE, tags="body")
            c.create_text(tx + 16, mid, text=label, anchor="w", fill=DIM,
                          font=ui.font(13, True), tags="body")
            c.create_text(tx + w - 68, mid, text=value, anchor="e", fill=FG,
                          font=ui.font(24 if len(value) <= 7 else 18, True), tags="body")
            c.create_text(tx + w - 60, mid + 3, text=unit, anchor="w", fill=ui.FAINT,
                          font=ui.font(11), tags="body")

    def _points(self) -> list:
        """Up to three (label, value, unit) game results for the Hand page. Games override."""
        return []

    def _cards(self, items, cols: int, top: int, bottom: int, big: int = 22) -> None:
        """Small cards in a grid: the label on top, the number under it, then its unit.

        Same surfaces and type as the rest of the window (raised card, dim label, bright
        number), but stacked, so three fit across where the row table fits two."""
        c, (x0, _y0, x1, _y1) = self.canvas, PANEL_BOX
        gap, pad = 10, 18
        rows = -(-len(items) // cols)
        w = (x1 - x0 - 2 * pad - gap * (cols - 1)) / cols
        h = (bottom - top - gap * (rows - 1)) / rows
        for i, (label, value, unit) in enumerate(items):
            tx = x0 + pad + (i % cols) * (w + gap)
            ty = top + (i // cols) * (h + gap)
            ui.rrect(c, tx, ty, tx + w, ty + h, r=12, top=ui.RAISED, bottom=ui.RAISED,
                     border=ui.LINE, tags="body")
            c.create_text(tx + 14, ty + 14, text=label, anchor="w", fill=DIM,
                          font=ui.font(11, True), tags="body")
            c.create_text(tx + 14, ty + h - 17, text=value, anchor="w", fill=FG,
                          font=ui.font(big, True), tags="body")
            if unit:
                c.create_text(tx + 22 + ui.text_width(value, big, True), ty + h - 14,
                              text=unit, anchor="w", fill=ui.FAINT, font=ui.font(10),
                              tags="body")

    def _draw_hand_page(self) -> None:
        c, (x0, y0, x1, y1) = self.canvas, PANEL_BOX
        role = self.driver
        roll, pitch = self.angles.get(role), self.pitch_angles.get(role)
        s = self.stats.get(role)
        tremor = self.tremor_rms.get(role)
        hand = self._last_hand.get(role) or {}

        def num(v, spec):
            return "--" if v is None else format(v, spec)

        # Who and how long: the game's name, and the time played so far.
        secs = int(self.play_seconds)
        c.create_text(x0 + 22, y0 + 62, text=self.OG_NAME.title(), anchor="w", fill=FG,
                      font=ui.font(20, True), tags="body")
        c.create_text(x1 - 22, y0 + 62, text=f"{secs // 60}:{secs % 60:02d}", anchor="e",
                      fill=FG, font=ui.font(26, True), tags="body")
        c.create_text(x1 - 22 - ui.text_width(f"{secs // 60}:{secs % 60:02d}", 26, True) - 8,
                      y0 + 66, text="played", anchor="e", fill=ui.FAINT, font=ui.font(10),
                      tags="body")
        # How it is going: the game's own points.
        points = self._points()
        if points:
            self._cards(points, len(points), y0 + 86, y0 + 150, big=24)
        # The hand: where it is and how it moves.
        self._cards([
            ("Roll now", num(roll, "+.1f"), "deg"),
            ("Pitch now", num(pitch, "+.1f"), "deg"),
            ("Pain presses", str(self.pain_events), ""),
            ("Roll range", num(s and s.range_deg, ".0f"), "deg"),
            ("Pitch range", num(s and s.pitch_range_deg, ".0f"), "deg"),
            ("Range of motion", num(hand.get("rom"), ".0f"), "deg"),
            ("Peak speed", num(s and s.peak_dps, ".0f"), "deg/s"),
            ("Tremor", num(tremor[-1] if tremor else None, ".1f"), "mg"),
            ("Jerk", num(hand.get("jerk_peak"), ".0f"), ""),
        ], cols=3, top=y0 + (162 if points else 86), bottom=y1 - 14)

    def _draw_face_page(self) -> None:
        c, (x0, y0, x1, y1) = self.canvas, PANEL_BOX
        monitor = self._face_thread is not None
        if monitor:                                  # the monitor has the camera: numbers only
            face = self._last_face or {}
            if face.get("state") == "no_face":
                state = "not seen"
            elif face.get("pspi_mean") is None:
                state = "learning"
            else:
                state = "tracking"
            pspi, bpm = face.get("pspi_mean"), face.get("bpm")
            self._tiles([
                ("Pain expression (PSPI)", "--" if pspi is None else f"{pspi:.1f}", ""),
                ("Heart rate", "--" if bpm is None else f"{bpm:.0f}", "bpm"),
                ("Face", state, ""),
            ], cols=1, top=y0 + 46, bottom=y1 - 62)
            c.create_text(x0 + 22, y1 - 34, anchor="w", fill=ui.FAINT, font=ui.font(11),
                          text="No video while the face monitor is using the camera.",
                          tags="body")
            return
        # Video: a live picture, nothing stored.
        vx, vy, vw, vh = x0 + 18, y0 + 46, 316, 237
        ui.rrect(c, vx, vy, vx + vw, vy + vh, r=14, top=ui.BG, bottom=ui.BG, border=ui.LINE,
                 tags="body")
        got = self._preview.latest() if self._preview is not None else None
        if got is not None:
            self._face_photo = ImageTk.PhotoImage(got[0].resize((vw - 8, vh - 8)))
            c.create_image(vx + 4, vy + 4, image=self._face_photo, anchor="nw", tags="body")
        else:
            problem = self._preview.error if self._preview is not None and self._preview.error \
                else "Opening the camera..."
            c.create_text(vx + vw / 2, vy + vh / 2, text=problem, fill=DIM, font=ui.font(12),
                          width=vw - 30, tags="body")
        c.create_text(vx + vw + 26, vy + 8, anchor="nw", fill=FG, font=ui.font(14, True),
                      text="Live picture", tags="body")
        c.create_text(vx + vw + 26, vy + 40, anchor="nw", fill=DIM, font=ui.font(12),
                      width=x1 - (vx + vw + 26) - 22, tags="body",
                      text="Nothing is saved.\n\nFor pain-expression and heart-rate numbers, "
                           "turn on Face numbers in games (Settings on the OG, or --face).")

    def _paused_overlay(self) -> None:
        """Veil the arena and say so. Called last by each game's _draw_field."""
        if self.screen.key != "paused":
            return
        x0, y0, x1, y1 = FIELD
        ui.rrect(self.canvas, x0, y0, x1, y1, r=18, top=ui.BG, bottom=ui.BG, border=None,
                 alpha=0.62, tags="body")
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ui.rrect(self.canvas, cx - 92, cy - 34, cx + 92, cy + 34, r=18, top=ui.RAISED,
                 bottom=ui.SURFACE, border=ui.LINE, shadow=10, tags="body")
        self.canvas.create_text(cx, cy - 8, text="Paused", fill=FG, font=ui.font(20, True),
                                tags="body")
        self.canvas.create_text(cx, cy + 16, text="green resumes", fill=DIM, font=ui.font(10),
                                tags="body")

    def _summary_lines(self) -> list:
        """The game's own summary lines (up to five). Games override this."""
        return [
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
        c = self.canvas
        lines = self._summary_lines() + self._extra_lines()
        report = symmetry_report(self.stats)
        row_h = 27
        height = 24 + row_h * len(lines)
        left, right = (24, 340) if report else (110, W - 110)
        ui.rrect(c, left, 98, right, 98 + height, r=20, top=ui.SURFACE_TOP, bottom=ui.SURFACE,
                 border=ui.LINE, shadow=12, tags="body")
        for i, text in enumerate(lines):
            label, _, value = text.partition("  ")
            y = 98 + 12 + row_h * i + row_h / 2
            if i:
                c.create_line(left + 18, y - row_h / 2, right - 18, y - row_h / 2,
                              fill=ui.LINE, tags="body")
            c.create_text(left + 20, y, text=label, anchor="w", fill=DIM, font=ui.font(11),
                          tags="body")
            c.create_text(right - 20, y, text=value.strip(), anchor="e", fill=FG,
                          font=ui.font(12, True), tags="body")
        if not report:
            return
        ui.rrect(c, 352, 98, W - 24, 98 + height, r=20, top=ui.SURFACE_TOP, bottom=ui.SURFACE,
                 border=ui.LINE, shadow=12, tags="body")
        c.create_text(372, 98 + 24, text="Left vs right", anchor="w", fill=ui.ACCENT,
                      font=ui.font(10, True), tags="body")
        head = f"{'':<11}{'L':>6}{'R':>6}{'ratio':>6}"
        c.create_text(372, 98 + 50, text=head, anchor="w", fill=DIM, font=ui.mono(10),
                      tags="body")
        for i, row in enumerate(report):
            c.create_text(372, 98 + 72 + 20 * i, text=format_row(row), anchor="w", fill=FG,
                          font=ui.mono(10), tags="body")


def _round(v):
    return None if v is None else round(v, 2)


def _cancel_pending(widget) -> None:
    """Cancel the `after` timers that belong to `widget` and everything inside it.

    Tk timers outlive the window that made them; when one fires after its window is
    destroyed, Tk shows an 'invalid command name' error box. The shell closes game
    windows while it keeps running, so it must cancel them first."""
    owner, stack = {}, [widget]                  # Tcl command name -> the widget that registered it
    while stack:
        w = stack.pop()
        for name in getattr(w, "_tclCommands", None) or ():
            owner[name] = w
        stack.extend(w.winfo_children())
    tk_ = widget.tk
    for after_id in tk_.splitlist(tk_.call("after", "info")):
        script = tk_.splitlist(tk_.call("after", "info", after_id))[0]
        w = owner.get(script)
        if w is not None:
            tk_.call("after", "cancel", after_id)
            w.deletecommand(script)              # through its owner, so its own list forgets it


def build_game_args(description: str):
    ap = argparse.ArgumentParser(description=description)
    add_common_args(ap)
    return ap
