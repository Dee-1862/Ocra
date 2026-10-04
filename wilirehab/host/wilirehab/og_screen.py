"""What the OG's own screen shows, and when its buttons count.

The OG display is a dumb terminal (apps/wilirehab/display): eight rows of 17
characters, set with `TXT <row> <text>`, and a progress bar along the bottom,
set with `BAR <0..100>`. Everything here is laptop-side and pure, so it can be
tested without a board. `OgScreenWriter` turns a finished screen into the
fewest commands.

Button rule: every OG press counts on every screen. (Tilt games used to ignore
the buttons while playing so a gripping hand could not press one by accident.
That made Pause and End unusable from the OG, so it was dropped: a stray red
press only asks "end the game?", and green must confirm it.)
"""
from __future__ import annotations

COLS = 17
ROWS = 8
PLAY_SCREENS = ("play", "paused")

STATUS = {
    "play": "PLAYING",
    "paused": "PAUSED",
    "end": "END THE GAME?",
    "pain": "PAIN CHECK-IN",
    "summary": "SUMMARY",
}


def buttons_live(uses_buttons: bool, screen_key: str) -> bool:
    """Whether a press on the OG should do anything on this screen (always: see above)."""
    return True


def fit(text) -> str:
    """One row of ASCII, spaces collapsed, cut to the screen width."""
    clean = " ".join(str(text).encode("ascii", "replace").decode("ascii").split())
    return clean[:COLS]


def fit_pair(text) -> str:
    """Like fit(), but when it is too long, shorten the label and keep the value.

    The game summaries are "label  value" with two spaces between them.
    """
    label, sep, value = str(text).partition("  ")
    label, value = " ".join(label.split()), " ".join(value.split())
    if not sep or len(label) + 1 + len(value) <= COLS:
        return fit(f"{label} {value}".strip())
    room = COLS - 1 - len(value)
    if room < 4:
        return fit(f"{label} {value}")
    return fit(f"{label[:room]} {value}")


def num(value, spec: str = ".0f", none: str = "--") -> str:
    return none if value is None else format(value, spec)


def hand_line(row) -> str:
    """The latest hand-motion row (jerk, range of motion) as one screen row."""
    if not row:
        return "Jerk -- RoM --"
    return fit(f"Jerk {num(row.get('jerk_peak'))} RoM {num(row.get('rom'))}")


def face_line(row) -> str:
    """The latest face row as one screen row, or blank when the camera is off."""
    if not row:
        return ""
    if row.get("state") == "no_face":
        return "Face: none seen"
    if row.get("pspi_mean") is None:
        return "Face: calibrating"
    return fit(f"PSPI {num(row.get('pspi_mean'), '.1f')} HR {num(row.get('bpm'))}")


def compose(*, name, screen_key, screen_title="", uses_buttons=False, game_lines=(),
            hand="", face="", pain=0, summary_lines=()):
    """-> (eight rows of text, bar percent or None)."""
    rows = [""] * ROWS
    rows[0] = fit(name)
    rows[1] = fit(STATUS.get(screen_key, screen_title.upper()))
    bar = None

    if screen_key in PLAY_SCREENS:
        for i, line in enumerate(list(game_lines)[:3]):
            rows[2 + i] = fit(line)
        rows[5] = fit(hand)
        rows[6] = fit(face)
        if screen_key == "play":
            rows[7] = "Press the colour" if uses_buttons else "Green: pause"
        else:
            rows[7] = "Green: resume"
    elif screen_key == "end":
        rows[2], rows[3] = "Green: end now", "Red: keep going"
    elif screen_key == "pain":
        rows[2] = f"Score {int(pain)} of 10"
        rows[3], rows[4], rows[5] = "Gray -2 Yellow -1", "Blue +1  Red +2", "Green: OK"
        bar = max(0, min(100, int(pain) * 10))
    elif screen_key == "summary":
        for i, line in enumerate(list(summary_lines)[:4]):
            rows[2 + i] = fit_pair(line)
        rows[7] = "Green: restart"
    return rows, bar


class OgScreenWriter:
    """Sends a screen to one OG, only the rows that changed since the last one."""

    def __init__(self, send):
        self._send = send
        self._rows = [""] * ROWS
        self._bar = 0
        self._started = False

    def show(self, rows, bar=None) -> int:
        """Returns how many commands were sent."""
        sent = 0
        if not self._started:
            self._send("CLS")
            self._started = True
            self._rows = [""] * ROWS
            self._bar = 0
            sent += 1
        for i, text in enumerate(rows):
            if text != self._rows[i]:
                self._send(f"TXT {i} {text}".rstrip())
                self._rows[i] = text
                sent += 1
        want = bar or 0
        if want != self._bar:
            self._send(f"BAR {want}")
            self._bar = want
            sent += 1
        return sent

    def idle(self) -> None:
        """Leave the OG saying the game is over, not frozen on its last frame."""
        self._send("CLS")
        self._send("TXT 0 WiliRehab")
        self._send("TXT 1 game closed")
        self._started = False
