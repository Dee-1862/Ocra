"""The OG button map: which colour does what on each screen.

Pure data, no GUI and no serial. The mapping demo draws its legend from this
table, and the tests check it, so there is one place to change a label.

Buttons are listed in the BSP's order (bsp/display_cpu/input/buttons.h:
gray, yellow, green, blue, red). Every action is a single short press: red is
never a long press because a 6 s red hold powers the OG off.
"""
from __future__ import annotations

from dataclasses import dataclass

BUTTONS = ("gray", "yellow", "green", "blue", "red")

COLORS = {
    "gray": "#9aa0a6",
    "yellow": "#f5c400",
    "green": "#22c55e",
    "blue": "#3b82f6",
    "red": "#ef4444",
}

MAX_LABEL_CHARS = 10
MAX_LABEL_WORDS = 2


@dataclass(frozen=True)
class Screen:
    key: str
    title: str
    hint: str
    actions: dict  # button name -> short label, or None when unused here

    def label(self, button: str):
        return self.actions.get(button)


def _screen(key, title, hint, gray, yellow, green, blue, red) -> Screen:
    return Screen(key, title, hint, {
        "gray": gray, "yellow": yellow, "green": green, "blue": blue, "red": red,
    })


SCREENS = (
    _screen("hand", "Hand select", "Which hand plays this game?",
            None, "Left hand", "Confirm", "Right hand", "Back"),
    _screen("calibration", "Calibration", "Move through your comfortable range",
            "Restart", "Prev step", "Capture", "Skip", "Cancel"),
    # Pausing turns Pause into Resume and End into Restart, so the same two buttons stay the
    # "go on" and "start over" buttons. Face and Hand open a readings page, which pauses the
    # game; Resume closes it. Re-zero needs a still hand, so it lives on the paused screen.
    _screen("play", "Gameplay", "Follow the target",
            "Face", "Hand", "Pause", "Pain now", "End"),
    # Same title as Gameplay: pausing stays on the game screen (the game is veiled and says
    # "Paused"), instead of looking like a different page.
    _screen("paused", "Gameplay", "Paused: green to resume",
            "Face", "Hand", "Resume", "Re-zero", "Restart"),
    _screen("end", "End session?", "This stops the current session",
            None, None, "End now", None, "Keep going"),
    _screen("pain", "Pain check-in", "How much does it hurt? 0 to 10",
            "-2", "-1", "OK", "+1", "+2"),       # less pain on the left, more on the right
    _screen("summary", "Session summary", "Well done",
            None, None, "Restart", None, "Menu"),
)

SCREENS_BY_KEY = {s.key: s for s in SCREENS}

# The Hand select screen's two choices, as the role each one means (used by game_base).
HAND_LABELS = {"Left hand": "left_hand", "Right hand": "right_hand"}

# While a readings page is open, gray and yellow become page controls (Next page flips Hand
# and Face, Close returns to the veiled game); green stays "go on" and red stops. Same key
# as "paused" on purpose: the game treats it as the paused screen. It is not in SCREENS (the
# demo's screen list); the game swaps it in only while a page is open.
PAGE_OPEN = _screen("paused", "Gameplay", "Reading a page: green to resume",
                    "Next page", "Close", "Resume", "Re-zero", "End")

# The Colour Reflex game uses all five buttons as answers, so while it plays its
# legend names the colours instead of Face / Hand / Pause / Pain now / End.
# Pausing and ending are done by the therapist with the p and e keys.
REFLEX_PLAY = _screen("play", "Colour reflex", "Press the colour that lights",
                      "Gray", "Yellow", "Green", "Blue", "Red")


def problems() -> list:
    """Everything wrong with the table, as readable strings. Empty means fine."""
    out = []
    keys = [s.key for s in SCREENS]
    if len(set(keys)) != len(keys):
        out.append("duplicate screen keys")
    for s in SCREENS:
        if set(s.actions) != set(BUTTONS):
            out.append(f"{s.key}: must define exactly the five buttons")
            continue
        used = [b for b in BUTTONS if s.actions[b]]
        if not used:
            out.append(f"{s.key}: no button does anything")
        for b in used:
            label = s.actions[b]
            if len(label) > MAX_LABEL_CHARS or len(label.split()) > MAX_LABEL_WORDS:
                out.append(f"{s.key}/{b}: label {label!r} is too long")
            if "hold" in label.lower() or "double" in label.lower():
                out.append(f"{s.key}/{b}: holds and double-clicks are not allowed")
        # Every screen needs a way forward or out.
        if not s.actions["green"] and not s.actions["red"]:
            out.append(f"{s.key}: neither green nor red leads anywhere")
    return out
