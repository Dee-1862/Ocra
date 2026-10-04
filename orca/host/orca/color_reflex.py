"""Colour Reflex: one of five coloured circles lights up; press that colour's button.

A different kind of game from the tilt games: no wrist angle at all. It
measures how fast a person reacts and how long they hold each button, which
are two cheap, indirect measures of response speed and finger release control.

With two OGs, a press is credited to the hand whose OG it came from, so the
summary compares the left and right median reaction times.

Controls: the OG's five buttons (or keys 1 to 5, or click the circles in the
legend). Pausing and ending are for the therapist: key p pauses, key e ends.
All five buttons are answers here, so there is no "Pain now" button; the pain
check-in still comes at the end of the session.

The time allowed shrinks a little after each correct press and grows after a
slow one.

Run from orca/host:
    python -m orca.color_reflex
    python -m orca.color_reflex --devices devices.json
"""
from __future__ import annotations

import random
import time
import tkinter as tk
from statistics import median

from . import ui
from .bilateral import LEFT, RIGHT
from .button_map import BUTTONS, COLORS, REFLEX_PLAY
from .game_base import FIELD, GameApp, build_game_args
from .cli import parse_roles, resolve_ports
from .mapping_demo import DIM, FG, PANEL, blend
from .measures import ReactionStats

WAIT_RANGE_S = (1.0, 2.5)        # random pause before each prompt
START_WINDOW_S, MIN_WINDOW_S, MAX_WINDOW_S = 3.0, 1.2, 5.0
LABELS = {"Gray": "gray", "Yellow": "yellow", "Green": "green", "Blue": "blue", "Red": "red"}


class ReflexApp(GameApp):
    TITLE = "Orca colour reflex"
    OG_NAME = "COLOUR REFLEX"
    USES_BUTTONS = True           # the five OG buttons are the answers, so they always count
    PERF = ("Reaction time", "ms", 1.0, 10.0, False)        # lower is better

    def __init__(self, root: tk.Tk, ports: dict, log_dir, axis="y", invert_roles=(),
                 invert_fwd_roles=(), driver="right_hand"):
        super().__init__(root, ports, log_dir, tilt=False, axis=axis,
                         invert_roles=invert_roles, driver=driver, stream=bool(ports),
                         invert_fwd_roles=invert_fwd_roles)

    # ---- screens ---------------------------------------------------------

    def _select(self, index: int) -> None:
        """Same as the base, except the play screen shows the five colour names."""
        super()._select(index)
        if self.screen.key == "play":
            self.screen = REFLEX_PLAY
            self._render()

    # ---- round state -----------------------------------------------------

    def _new_round(self) -> None:
        super()._new_round()
        self.phase = "wait"                    # "wait" for a prompt, "show" one
        self.wait_left = random.uniform(*WAIT_RANGE_S)
        self.target = None
        self.stim_t = 0.0
        self.window = START_WINDOW_S
        self.rt = ReactionStats()
        self.rt_hand = {LEFT: ReactionStats(), RIGHT: ReactionStats()}
        self.correct = 0
        self.wrong = 0
        self.slow_count = 0                    # prompts nobody answered in time
        self.early = 0
        self.flash = ("", 0.0, FG)

    def _end_fields(self) -> dict:
        s = self.rt.summary()
        return {"correct": self.correct, "wrong": self.wrong, "too_slow": self.slow_count,
                "median_ms": None if s is None else int(s["median"])}

    # ---- input -----------------------------------------------------------

    def _on_key(self, event) -> None:
        if event.char == "p" and self.screen.key == "play":
            self._go("paused")
            return
        if event.char == "e" and self.screen.key == "play":
            self._go("end")
            return
        super()._on_key(event)

    def _apply(self, label) -> None:
        if self.screen.key == "play" and label in LABELS:
            self._on_color(LABELS[label])
            return
        super()._apply(label)

    def _on_color(self, color: str) -> None:
        hand = self._press_role                # which OG, or None for keyboard / click
        if self.phase != "show":               # pressed before anything lit up
            self.early += 1
            self.wait_left += 0.5
            self._say("TOO EARLY", "#f5a524")
            self.session.record("early", role=hand, color=color)
            return
        now = self.play_seconds + (time.monotonic() - self._last)
        ms = int((now - self.stim_t) * 1000)
        if color == self.target:
            self.correct += 1
            self.rt.add(ms)
            if hand in self.rt_hand:
                self.rt_hand[hand].add(ms)
            self._attempt(hand, True)
            self._perf(ms)
            self.window = max(MIN_WINDOW_S, self.window * 0.95)
            self._say(f"{ms} ms", COLORS[color])
            self.session.record("reaction", role=hand, color=color, ms=ms)
        else:
            self.wrong += 1
            self._attempt(hand, False)
            self._say("WRONG COLOUR", "#ef4444")
            self.session.record("wrong_colour", role=hand, want=self.target, got=color)
        self._next_prompt()

    def _say(self, text: str, color: str) -> None:
        self.flash = (text, time.monotonic() + 0.7, color)

    def _next_prompt(self) -> None:
        self.phase = "wait"
        self.target = None
        self.wait_left = random.uniform(*WAIT_RANGE_S)

    # ---- the game --------------------------------------------------------

    def _advance(self, dt: float) -> None:
        self.play_seconds += dt
        if self.phase == "wait":
            self.wait_left -= dt
            if self.wait_left <= 0:
                options = [b for b in BUTTONS if b != self.target]
                self.target = random.choice(options)
                self.phase = "show"
                self.stim_t = self.play_seconds
                self.session.record("prompt", color=self.target)
        elif self.play_seconds - self.stim_t > self.window:
            self.slow_count += 1
            self.window = min(MAX_WINDOW_S, self.window + 0.2)
            self._say("TOO SLOW", "#f5a524")
            self.session.record("too_slow", color=self.target)
            self._next_prompt()

    def _points(self) -> list:
        s = self.rt.summary()
        return [("Correct", str(self.correct), ""),
                ("Wrong / slow", f"{self.wrong} / {self.slow_count}", ""),
                ("Median", "--" if s is None else str(int(s["median"])), "ms")]

    def _og_lines(self) -> list:
        s = self.rt.summary()
        return [f"Correct {self.correct}", f"Wrong {self.wrong} Slow {self.slow_count}",
                "Median --" if s is None else f"Median {int(s['median'])} ms"]

    # ---- drawing ---------------------------------------------------------

    def _draw_field(self, dim: bool) -> None:
        c = self.canvas
        x0, y0, x1, y1 = FIELD
        cy = (y0 + y1) / 2 + 12
        radius = 30
        self._arena()
        for i, color in enumerate(BUTTONS):
            cx = x0 + (x1 - x0) * (2 * i + 1) / (2 * len(BUTTONS))
            lit = self.phase == "show" and color == self.target and not dim
            base = COLORS[color]
            if lit:
                ui.orb(c, cx, cy, radius, base, glow=22)
            else:
                ui.orb(c, cx, cy, radius, blend(base, ui.SURFACE, 0.80))
                ui.ring(c, cx, cy, radius, blend(base, ui.SURFACE, 0.55), thick=2)
            c.create_text(cx, cy + radius + 18, text=color, fill=ui.FG if lit else ui.FAINT,
                          font=ui.font(9, lit), tags="body")
        s = self.rt.summary()
        median_text = "-" if s is None else f"{int(s['median'])} ms"
        self._hud([("Correct", self.correct), ("Wrong", self.wrong), ("Slow", self.slow_count),
                   ("Median", median_text), ("Allowed", f"{self.window:.1f} s")])
        text, until, color = self.flash
        if text and time.monotonic() < until and not dim:
            c.create_text((x0 + x1) / 2, y0 + 30, text=text, fill=color, font=ui.font(18, True),
                          tags="body")
        elif self.phase == "wait" and not dim:
            c.create_text((x0 + x1) / 2, y0 + 30, text="Get ready\u2026", fill=ui.DIM,
                          font=ui.font(14), tags="body")
        self._paused_overlay()

    def _summary_lines(self) -> list:
        s = self.rt.summary()
        total = self.correct + self.wrong + self.slow_count
        hands = []
        for role, tag in ((LEFT, "L"), (RIGHT, "R")):
            hs = self.rt_hand[role].summary()
            hands.append(f"{tag} {int(hs['median'])}" if hs else f"{tag} -")
        held = [ms for values in self.held_ms.values() for ms in values]
        median_ms = None if s is None else int(s["median"])
        return [
            f"Median reaction  {'-' if median_ms is None else f'{median_ms} ms'}",
            f"Correct  {self.correct} of {total}",
            f"Left / right median  {hands[0]}  {hands[1]} ms",
            f"Button held  {'-' if not held else f'{int(median(held))} ms'} (median)",
            f"Pain score  {self.last_pain if self.last_pain is not None else '-'}",
        ]


def parser():
    return build_game_args("Orca colour reflex")


def build(root, ports: dict, args) -> ReflexApp:
    """The game in `root` (a Tk or Toplevel). The OG shell calls this with default arguments."""
    return ReflexApp(root, ports, args.log_dir, axis=args.axis,
                     invert_roles=parse_roles(args.invert_roles),
                     invert_fwd_roles=parse_roles(args.invert_fwd_roles), driver=args.driver)


def main() -> None:
    args = parser().parse_args()
    ports = resolve_ports(args)
    root = tk.Tk()
    build(root, ports, args)
    root.mainloop()


if __name__ == "__main__":
    main()
