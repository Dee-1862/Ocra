"""Beat Flick: blocks fall in time with a song; flick each one the way its arrow points.

A Beat Saber-style game for two OGs, one per hand. Left-hand blocks are red and fall in the
left lane, right-hand blocks are blue and fall in the right lane; only the matching hand's OG
counts. With one OG (or none) any hand takes any block. Hits score for the direction and the
timing, with a combo multiplier; a miss or a wrong-way flick breaks the combo; a flick with the
wrong hand costs nothing. When the song ends the game goes to the pain check-in.

Built on rhythm_flick (same flick detection and hand lanes) and game_base (same screens, legend,
pause / pain / summary flow and logging). The notes come from beat_map, the one built-in song
from beat_song, and the sound from song_player.

Input, any of:
    OG tilt flick   fast tilt in the arrow's direction (diagonals accept either direction)
    keys a / s      flick left / right    keys u / d   flick up / down
Pause stops the song too; Resume carries on from where it was.

Run from orca/host:
    python -m orca.beat_flick                              # keyboard and clicks
    python -m orca.beat_flick --port COM5                  # one OG (any hand takes any block)
    python -m orca.beat_flick --devices devices.json       # two OGs, one per hand
    python -m orca.beat_flick --no-sound                   # without the music
"""
from __future__ import annotations

import time
import tkinter as tk

from . import ui
from .beat_map import (BPM, SONG_SECONDS, Scorer, demo_map, judge_flick, notes_from_map,
                       verdict)
from .beat_song import ensure_song
from .bilateral import LEFT, RIGHT
from .cli import parse_roles, resolve_ports
from .game_base import FIELD, GameApp, build_game_args
from .mapping_demo import DIM, FG, PANEL, blend
from .rhythm_flick import LANE_X, RhythmApp
from .song_player import SongPlayer

LEAD = 2.0                  # seconds a block takes to fall to the hit line
WINDOW = 0.35               # seconds either side of the beat that count (generous: it is rehab)
OUTRO_S = 1.5               # after the last note, wait this long, then finish
HAND_COLORS = {LEFT: "#f87171", RIGHT: "#60a5fa"}     # red left, blue right
GOOD, BAD = "#34d399", "#ef4444"


class BeatApp(RhythmApp):
    TITLE = "Orca beat flick"
    OG_NAME = "BEAT FLICK"
    PERF = ("Hit accuracy", "%", 100.0, 2.0, True)

    def __init__(self, root: tk.Tk, ports: dict, log_dir, axis="y", invert_roles=(),
                 invert_fwd_roles=(), flick_dps=150.0, hands="auto", driver="right_hand",
                 sound=True):
        # Set before the base class builds the first round (which calls _new_round and _select).
        self._notes_master = notes_from_map(demo_map(), BPM)
        self._song = None
        self._song_live = False
        if sound:
            self._song = SongPlayer(ensure_song())
        super().__init__(root, ports, log_dir, axis=axis, invert_roles=invert_roles,
                         invert_fwd_roles=invert_fwd_roles, dirs="all", bpm=BPM,
                         flick_dps=flick_dps, hands=hands, driver=driver)
        if self._song is not None and self._song.error:
            self.status.configure(text=f"No sound: {self._song.error}")

    @property
    def two_hands(self) -> bool:
        return self.hand_roles != (None,)

    # ---- round and song ---------------------------------------------------

    def _new_round(self) -> None:
        super()._new_round()
        if self._song is not None:
            self._song.stop()
        self._song_live = False
        self.scorer = Scorer()
        self.notes = [type(n)(t=n.t, hand=n.hand, accepts=n.accepts, glyph=n.glyph)
                      for n in self._notes_master]          # fresh copies: a round changes them
        self.flash = ("", 0.0, FG)

    def _select(self, index: int) -> None:
        super()._select(index)
        self._sync_song()

    def _sync_song(self) -> None:
        """Keep the music in step with the screen: plays while playing, holds while paused."""
        song = getattr(self, "_song", None)
        if song is None:
            return
        key = self.screen.key
        if key == "play":
            if self._song_live:
                song.resume()
            else:
                song.start(getattr(self, "play_seconds", 0.0))
                self._song_live = True
        elif key == "paused":
            if self._song_live:
                song.pause()
        else:
            song.stop()
            self._song_live = False

    def _close(self) -> None:
        if self._song is not None:
            self._song.stop()
        super()._close()

    def _end_fields(self) -> dict:
        s = self.scorer
        return {"score": s.score, "hits": s.hits, "misses": s.misses, "best_combo": s.best_combo,
                "accuracy": None if s.accuracy is None else round(s.accuracy, 1),
                "song": "built-in 84 BPM"}

    # ---- input ------------------------------------------------------------

    def _apply(self, label) -> None:
        GameApp._apply(self, label)              # no tempo to slow here: Pain now just logs

    def _on_key(self, event) -> None:
        if event.char in ("a", "s") and self.screen.key == "play":
            self._on_flick("left" if event.char == "a" else "right", None)
            return
        super()._on_key(event)

    def _on_flick(self, direction: str, hand) -> None:
        if self.screen.key != "play":
            return
        now = self.play_seconds + (time.monotonic() - self._last)
        result, note = judge_flick(self.notes, direction, now, WINDOW,
                                   hand=hand if self.two_hands else None)
        if result == "none":
            self.session.record("flick", role=hand, dir=direction, result="none")
            return
        if result == "wrong_hand":
            self._say("WRONG HAND", "#f5a524")
            self.session.record("wrong_hand", role=hand, dir=direction)
            return
        note.state = "done"
        err = now - note.t
        if result == "hit":
            earned = self.scorer.hit(err, WINDOW)
            self._attempt(note.hand, True)
            self._perf(1)
            self._say(f"{verdict(err)}  +{earned}", GOOD)
            self.session.record("hit", role=hand, dir=direction, err_ms=int(err * 1000),
                                points=earned, combo=self.scorer.combo)
        else:
            self.scorer.miss()
            self._attempt(note.hand, False)
            self._perf(0)
            self._say("WRONG WAY", BAD)
            self.session.record("wrong", role=hand, want="/".join(note.accepts), got=direction)

    # ---- the game ------------------------------------------------------------

    def _advance(self, dt: float) -> None:
        self.play_seconds += dt
        for note in self.notes:
            if note.state == "live" and self.play_seconds > note.t + WINDOW:
                note.state = "done"
                self.scorer.miss()
                self._attempt(note.hand, False)
                self._perf(0)
                self._say("MISS", BAD)
                self.session.record("miss", role=note.hand, want="/".join(note.accepts))
        if self.play_seconds >= self.notes[-1].t + OUTRO_S and self.play_seconds >= SONG_SECONDS:
            self.session.record("song_end", at_s=round(self.play_seconds, 1))
            self._end_session()                  # same as End now, without asking
            self._go("pain")

    def _acc_text(self) -> str:
        acc = self.scorer.accuracy
        return "--" if acc is None else f"{acc:.0f}"

    def _points(self) -> list:
        s = self.scorer
        return [("Score", str(s.score), ""), ("Combo", str(s.combo), f"x{s.multiplier}"),
                ("Accuracy", self._acc_text(), "%")]

    def _og_lines(self) -> list:
        return [f"Score {self.scorer.score}", f"Combo {self.scorer.combo}",
                f"Acc {self._acc_text()}%"]

    # ---- drawing -------------------------------------------------------------

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        width = x1 - x0
        line_y = y1 - 34
        top = y0 + 36
        self._arena()
        # Song progress along the top of the arena.
        c.create_line(x0 + 30, y0 + 13, x1 - 30, y0 + 13, fill=ui.LINE, width=3, tags="body")
        frac = min(1.0, self.play_seconds / SONG_SECONDS)
        if frac > 0:
            c.create_line(x0 + 30, y0 + 13, x0 + 30 + (width - 60) * frac, y0 + 13,
                          fill=ui.ACCENT, width=3, tags="body")
        ui.rrect(c, x0 + 30, line_y - 1, x1 - 30, line_y + 2, r=1, top=ui.ACCENT, bottom=ui.ACCENT,
                 border=None, alpha=0.9)
        for hand in (LEFT, RIGHT):
            lx = x0 + LANE_X[hand] * width
            c.create_line(lx, y0 + 26, lx, line_y - 30, fill=ui.LINE, dash=(2, 5), tags="body")
            ui.ring(c, lx, line_y, 30, blend(HAND_COLORS[hand], PANEL, 0.55), thick=2)
            c.create_text(lx, line_y + 22, text={LEFT: "LEFT", RIGHT: "RIGHT"}[hand],
                          fill=ui.FAINT, font=ui.font(9, True), tags="body")
        for note in self.notes:
            if note.state != "live" or note.t - self.play_seconds > LEAD:
                continue
            progress = 1.0 - (note.t - self.play_seconds) / LEAD
            y = top + progress * (line_y - top)
            cx = x0 + LANE_X[note.hand] * width
            color = HAND_COLORS[note.hand]
            if dim:
                color = blend(color, PANEL, 0.6)
            ui.rrect(c, cx - 25, y - 25, cx + 25, y + 25, r=13, top=ui.lighten(color, 0.08),
                     bottom=ui.darken(color, 0.06), border=None)
            c.create_text(cx, y - 1, text=note.glyph, fill=ui.BG, font=ui.font(24, True),
                          tags="body")
        s = self.scorer
        self._hud([("Score", s.score), ("Combo", f"{s.combo} x{s.multiplier}"),
                   ("Acc", f"{self._acc_text()}%")])
        text, until, color = self.flash
        if text and time.monotonic() < until and not dim:
            c.create_text((x0 + x1) / 2, y0 + 30, text=text, fill=color, font=ui.font(16, True),
                          tags="body")
        self._paused_overlay()

    def _summary_lines(self) -> list:
        s = self.scorer
        return [
            f"Score  {s.score}",
            f"Accuracy  {self._acc_text()}%",
            f"Best combo  {s.best_combo}",
            f"Hit  {s.hits} of {s.hits + s.misses}",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
            f"Time  {self.play_seconds:.0f} s",
        ]


def parser():
    ap = build_game_args("Orca beat flick")
    ap.add_argument("--hands", choices=("auto", "one", "both"), default="auto",
                    help="both = one OG per hand, matching colour only; "
                         "auto = both when two OGs are connected")
    ap.add_argument("--flick-dps", type=float, default=150.0,
                    help="flick speed threshold in degrees per second (lower = easier)")
    ap.add_argument("--no-sound", action="store_true", help="play without the music")
    return ap


def build(root, ports: dict, args) -> BeatApp:
    """The game in `root` (a Tk or Toplevel). The OG shell calls this with default arguments."""
    return BeatApp(root, ports, args.log_dir, axis=args.axis,
                   invert_roles=parse_roles(args.invert_roles),
                   invert_fwd_roles=parse_roles(args.invert_fwd_roles),
                   flick_dps=args.flick_dps, hands=args.hands, driver=args.driver,
                   sound=not args.no_sound)


def main() -> None:
    args = parser().parse_args()
    ports = resolve_ports(args, max_ports=2)
    root = tk.Tk()
    build(root, ports, args)
    root.mainloop()


if __name__ == "__main__":
    main()
