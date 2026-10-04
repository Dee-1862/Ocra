"""The OG's own menu: which screen it is on, what each button does, nothing drawn.

Pure logic, no Tk, no Pillow, no serial, so it is tested without a board. og_render draws
it and og_shell connects it to the OG.

Button use follows AGENTS.md ("Porting a FreeWili 2 app"): gray up, red down, green
select, yellow back. Blue switches dark and light from any menu screen. Every action is a
single short press (red is never held: a 6 s red hold powers the OG off).

Screens:
    home      the games, "Face view", "Agents" yellow opens settings
    settings  theme, brightness, sound, ...    yellow goes back
    face      live camera preview              yellow goes back
    agents    live agent network (see og_render.render_agents)    yellow goes back

`press()` returns None, or an action tuple for the shell to carry out:
    ("launch", module)   start that game
    ("face_start",)      open the camera preview
    ("face_stop",)       close it
    ("brightness", pct)  set the OG backlight
    ("sound", level)     the sound level changed (the shell plays a sample beep)
"""
from __future__ import annotations

from dataclasses import dataclass

from .button_map import BUTTONS
from .og_theme import other

HOME, SETTINGS, FACE, AGENTS = "home", "settings", "face", "agents"

VISIBLE_ROWS = 4          # list rows that fit between the header and the legend

BRIGHTNESS_STEPS = (25, 50, 75, 100)             # percent; the OG itself never goes below 10
SOUND_LEVELS = ("off", "low", "medium", "high")
SOUND_VOLUME = {"off": 0, "low": 3, "medium": 6, "high": 9}      # the speaker's own 0..10 scale

TITLES = {HOME: "Choose a game", SETTINGS: "Settings", FACE: "Face view", AGENTS: "Agents"}
HINTS = {
    HOME: "Up and down, then green to play",
    SETTINGS: "Green changes the highlighted row",
    FACE: "Live preview, nothing is saved",
    AGENTS: "The agent network, live",      # the shell replaces this with the live status
}

# screen -> button -> short label (at most 8 characters so it fits under its circle).
LEGENDS = {
    HOME: {"gray": "Up", "yellow": "Settings", "green": "Open", "blue": "Theme", "red": "Down"},
    SETTINGS: {"gray": "Up", "yellow": "Back", "green": "Change", "blue": "Theme", "red": "Down"},
    FACE: {"yellow": "Back", "blue": "Theme"},
    AGENTS: {"yellow": "Back", "blue": "Theme"},
}


@dataclass(frozen=True)
class Row:
    key: str            # game module, "face", or a settings key
    title: str
    sub: str = ""       # second line, dimmer
    value: str = ""     # right-aligned, for settings


class Menu:
    def __init__(self, games, theme: str = "dark", face_in_games: bool = False,
                 brightness: int = 100, sound: str = "medium"):
        """`games` is a sequence of (module, name, what, ...) tuples, like launcher.GAMES."""
        self.games = tuple(games)
        self.theme = theme
        self.face_in_games = face_in_games
        self.brightness = brightness if brightness in BRIGHTNESS_STEPS else 100
        self.sound = sound if sound in SOUND_LEVELS else "medium"
        self.screen = HOME
        self.cursor = {HOME: 0, SETTINGS: 0}
        self.top = {HOME: 0, SETTINGS: 0}       # first visible row

    # ---- what to show ---------------------------------------------------

    @property
    def title(self) -> str:
        return TITLES[self.screen]

    @property
    def hint(self) -> str:
        return HINTS[self.screen]

    def legend(self) -> dict:
        """button -> label, or None for a button that does nothing on this screen."""
        labels = LEGENDS[self.screen]
        return {b: labels.get(b) for b in BUTTONS}

    def rows(self) -> list:
        if self.screen == HOME:
            rows = [Row(g[0], g[1], g[2]) for g in self.games]
            rows.append(Row("face", "Face view", "See the camera on this screen"))
            rows.append(Row("agents", "Agents", "Live view of the agent network"))
            return rows
        if self.screen == SETTINGS:
            return [
                Row("theme", "Theme", value=self.theme),
                Row("brightness", "Brightness", "The OG backlight", f"{self.brightness}%"),
                Row("sound", "Sound", "Beeps on the OG speaker", self.sound),
                Row("face_games", "Face numbers in games",
                    "Uses the webcam while you play", "on" if self.face_in_games else "off"),
            ]
        return []

    def visible(self) -> tuple:
        """(first visible index, the visible rows, total row count)."""
        rows = self.rows()
        top = self.top.get(self.screen, 0)
        return top, rows[top:top + VISIBLE_ROWS], len(rows)

    def selected(self) -> int:
        return self.cursor.get(self.screen, 0)

    # ---- input ----------------------------------------------------------

    def press(self, button: str):
        label = LEGENDS[self.screen].get(button)
        if label is None:
            return None
        if button == "blue":
            self.theme = other(self.theme)
            return None
        if self.screen in (FACE, AGENTS):
            return self._go(HOME) if button == "yellow" else None
        if button == "gray":
            self._move(-1)
        elif button == "red":
            self._move(1)
        elif button == "yellow":
            return self._go(SETTINGS if self.screen == HOME else HOME)
        elif button == "green":
            return self._select()
        return None

    def _move(self, step: int) -> None:
        n = len(self.rows())
        cur = (self.cursor[self.screen] + step) % n          # wraps round the ends
        self.cursor[self.screen] = cur
        top = self.top[self.screen]
        if cur < top:
            top = cur
        elif cur >= top + VISIBLE_ROWS:
            top = cur - VISIBLE_ROWS + 1
        self.top[self.screen] = max(0, min(top, max(0, n - VISIBLE_ROWS)))

    def _go(self, screen: str):
        leaving_face = self.screen == FACE
        self.screen = screen
        if screen == FACE:
            return ("face_start",)
        return ("face_stop",) if leaving_face else None

    def _select(self):
        row = self.rows()[self.cursor[self.screen]]
        if self.screen == HOME:
            if row.key == "face":
                return self._go(FACE)
            if row.key == "agents":
                return self._go(AGENTS)
            return ("launch", row.key)
        if row.key == "theme":
            self.theme = other(self.theme)
        elif row.key == "brightness":
            self.brightness = _next(BRIGHTNESS_STEPS, self.brightness)
            return ("brightness", self.brightness)
        elif row.key == "sound":
            self.sound = _next(SOUND_LEVELS, self.sound)
            return ("sound", self.sound)
        elif row.key == "face_games":
            self.face_in_games = not self.face_in_games
        return None


def _next(options: tuple, current):
    """The option after `current`, wrapping round."""
    return options[(options.index(current) + 1) % len(options)]
