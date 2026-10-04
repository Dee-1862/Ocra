"""The OG as the screen: a menu on the OG, games that show on it, a face view.

    python -m wilirehab.og_shell                 # the one OG that is plugged in
    python -m wilirehab.og_shell --port COM11    # a named display-CPU port
    python -m wilirehab.og_shell --no-og         # no OG: try the menu on the laptop alone

The laptop still runs everything (games, filters, logging); the OG is its screen and its
buttons. This program owns the OG's serial port, so the games run inside it, one at a
time, in their own window, borrowing its link (cli.SHELL). Only one program can open the
port, which is why you start games from here and not from the launcher while it runs.

On the OG:   gray up, red down, green open, yellow back or settings, blue dark/light.
In a game:   the OG shows exactly what the game window shows (a picture of its canvas),
             so keep that window on your main monitor and uncovered. At the end of a
             game, green plays again and red goes back to this menu.
On the laptop: keys 1-5 or the arrow keys and Enter press the same buttons, and the
             window here shows what the OG shows.
"""
from __future__ import annotations

import argparse
import importlib
import json
import queue
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageGrab, ImageTk

from . import cli
from .face_view import FacePreview
from .launcher import GAMES
from .og_display import OgDisplay
from .og_link import OgLink
from .og_menu import FACE, SOUND_VOLUME, Menu
from .og_render import (CIRCLE_X, LEGEND_Y, OG_H, OG_W, RADIUS, flashing, render_face,
                        render_menu, render_message)
from .og_theme import THEMES, light_variant

TICK_MS = 100                     # screen update rate while a game is mirrored
ROLE = "right_hand"               # the games name their one OG by role
KEYS = (("<Up>", "gray"), ("<Left>", "yellow"), ("<Return>", "green"),
        ("<Right>", "blue"), ("<Down>", "red"))
DIGITS = {"1": "gray", "2": "yellow", "3": "green", "4": "blue", "5": "red"}

_scale = None                     # screenshot pixels per Tk pixel (differs on scaled displays)
SETTINGS_FILE = Path(__file__).resolve().parents[1] / "og_settings.json"      # wilirehab/host


def load_settings() -> dict:
    """What the Settings screen saved last time, or {} (first run, or an unreadable file)."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def settings_of(menu: Menu) -> dict:
    return {"theme": menu.theme, "brightness": menu.brightness, "sound": menu.sound,
            "face_in_games": menu.face_in_games}


def grab_widget(widget):
    """A 320x240 picture of what `widget` shows on the screen, or None if it is not visible.

    It copies the screen, so the widget must be on the main monitor and nothing may cover it."""
    global _scale
    widget.update_idletasks()
    if not widget.winfo_viewable():
        return None
    if _scale is None:
        _scale = ImageGrab.grab().width / widget.winfo_screenwidth()
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    box = tuple(round(v * _scale) for v in (x, y, x + widget.winfo_width(),
                                            y + widget.winfo_height()))
    return ImageGrab.grab(bbox=box).convert("RGB").resize((OG_W, OG_H), Image.LANCZOS)


def find_port(args):
    if args.no_og:
        return None
    if args.port:
        return args.port
    from serial.tools import list_ports
    from .devices import find_og_displays
    found = find_og_displays(list_ports.comports())
    if len(found) > 1:
        raise SystemExit("More than one OG is plugged in; the shell uses one. "
                         "Unplug the other or pass --port COMx.")
    return found[0][0] if found else None


class Shell:
    def __init__(self, root: tk.Tk, port, camera: int = 0, theme: str = None):
        self.root, self.camera = root, camera
        saved = load_settings()
        chosen = theme or saved.get("theme")
        self.menu = Menu(GAMES, theme=chosen if chosen in THEMES else "dark",
                         face_in_games=bool(saved.get("face_in_games", False)),
                         brightness=saved.get("brightness", 100), sound=saved.get("sound", "medium"))
        self._saved = settings_of(self.menu)
        self.events: queue.Queue = queue.Queue()
        self.link = OgLink(port, self.events, role=ROLE) if port else None
        self.display = None
        self._display_retry = 0.0
        self.preview = None
        self.game = None
        self._flash = None
        self._sig = None
        self._photo = None

        root.title("WiliRehab OG screen")
        root.configure(bg="#0b0e12")
        self.picture = tk.Label(root, bg="#0b0e12", bd=0, cursor="hand2")
        self.picture.pack(padx=12, pady=(12, 4))
        self.picture.bind("<Button-1>", self._click)
        self.status = tk.Label(root, text="", bg="#0b0e12", fg="#8b95a1", anchor="w",
                               justify="left", wraplength=620)
        self.status.pack(fill="x", padx=14)
        tk.Label(root, bg="#0b0e12", fg="#5a6572", anchor="w", justify="left",
                 text="This is what the OG shows. Keys 1-5 or arrows + Enter press its buttons; "
                      "click the circles too.").pack(fill="x", padx=14, pady=(0, 10))
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self._quit)
        if self.link:
            self.link.start()
            self._say(f"Connecting to the OG on {port}...")
        else:
            self._say("No OG: showing the menu on the laptop only.")
        root.after(20, self._poll)
        root.after(TICK_MS, self._tick)

    # ---- input ----------------------------------------------------------

    def _bind_keys(self) -> None:
        self.root.bind_all("<Key>", self._on_key)
        for seq, button in KEYS:
            self.root.bind_all(seq, lambda e, b=button: self.press(b, "key"))

    def _on_key(self, event) -> None:
        if event.char in DIGITS:
            self.press(DIGITS[event.char], "key")

    def _click(self, event) -> None:
        for i, button in enumerate(self.menu.legend()):
            dx, dy = event.x - CIRCLE_X[i], event.y - LEGEND_Y     # the picture is shown at 640x480
            if dx * dx + dy * dy <= (RADIUS + 8) ** 2:
                self.press(button, "click")
                return

    def press(self, button: str, source: str) -> None:
        if self.game is not None:            # the game has its own buttons while it runs
            return
        self._flash = (button, time.monotonic())
        action = self.menu.press(button)
        self._remember()
        if action and action[0] == "brightness" and self.link:
            self.link.send(f"BRIGHT {action[1]}")
        # A tick for every press, or a sample beep at the new level when it was changed.
        if action and action[0] == "sound":
            self._beep(800, 90)
        elif not (action and action[0] == "launch"):
            self._beep(1500, 25)
        if not action:
            return
        if action[0] == "launch":
            self._launch(action[1])
        elif action[0] == "face_start":
            self.preview = FacePreview(self.camera)
            self.preview.start()
        elif action[0] == "face_stop" and self.preview is not None:
            self.preview.stop()
            self.preview = None

    def _beep(self, hz: int, ms: int) -> None:
        volume = SOUND_VOLUME[self.menu.sound]
        if volume and self.link is not None and self.link.connected:
            self.link.send(f"BEEP {hz} {ms} {volume}")

    def _remember(self) -> None:
        """Save the settings when one changed, so the next start looks the same."""
        now = settings_of(self.menu)
        if now == self._saved:
            return
        self._saved = now
        try:
            SETTINGS_FILE.write_text(json.dumps(now, indent=2), encoding="utf-8")
        except OSError as exc:
            self._say(f"Could not save settings: {exc}")

    def _poll(self) -> None:
        try:
            while True:
                kind, value, _role = self.events.get_nowait()
                if kind == "press":
                    self.press(value, "OG")
                elif kind == "status":
                    self._say(value)
        except queue.Empty:
            pass
        self.root.after(20, self._poll)

    def _say(self, text: str) -> None:
        self.status.configure(text=text)

    # ---- games ----------------------------------------------------------

    def _launch(self, module: str) -> None:
        top = None
        try:
            mod = importlib.import_module(f"{__package__ or 'wilirehab'}.{module}")
            args = mod.parser().parse_args([])
            top = tk.Toplevel(self.root)
            cli.SHELL.update(link=self.link, on_exit=self._game_closed)
            cli.FACE["camera"] = self.camera if self.menu.face_in_games else None
            ports = {ROLE: self.link.port} if self.link else {}
            self.game = mod.build(top, ports, args)
            # The OG shows a picture of this window, so it must be on the main monitor and on
            # top of everything (a window behind the editor made the OG show the editor).
            top.geometry("+24+24")
            top.attributes("-topmost", True)
            top.lift()
            top.focus_force()
            self._say(f"Playing {module}. Keep its window on the main monitor, uncovered: "
                      "the OG shows a picture of it.")
        except Exception as exc:             # shown, and the menu stays usable
            cli.SHELL.update(link=None, on_exit=None)
            if self.link:
                self.link.detach()
            if top is not None:
                try:
                    top.destroy()
                except tk.TclError:
                    pass
            self._say(f"Could not start {module}: {type(exc).__name__}: {exc}")

    def _game_closed(self) -> None:
        self.game = None
        cli.SHELL.update(link=None, on_exit=None)
        cli.FACE["camera"] = None
        self._sig = None                     # draw the menu again
        self._bind_keys()                    # the game took the key bindings
        self.root.deiconify()
        self.root.lift()
        self._say("Back at the menu.")

    # ---- the screen -----------------------------------------------------

    def _frame(self):
        """The picture the OG should show now, or None if it has not changed."""
        m = self.menu
        if self.game is not None:
            img = grab_widget(self.game.canvas)
            if img is None:
                return None
            return light_variant(img) if m.theme == "light" else img
        live = flashing(self._flash)
        if m.screen == FACE:
            got = self.preview.latest() if self.preview else None
            problem = self.preview.error if self.preview and self.preview.error else ""
            sig = (FACE, got[1] if got else 0, problem, m.theme, live)
            if sig == self._sig and not live:
                return None
            self._sig = sig
            return render_face(m, got[0] if got else None, problem, self._flash)
        sig = (m.screen, m.selected(), m.top[m.screen], m.theme, m.face_in_games, live)
        if sig == self._sig and not live:
            return None
        self._sig = sig
        return render_menu(m, flash=self._flash)

    def _tick(self) -> None:
        try:
            self._ensure_display()
            frame = self._frame()
            if frame is not None:
                if self.display is not None:
                    self.display.present(frame)
                self._photo = ImageTk.PhotoImage(frame.resize((OG_W * 2, OG_H * 2), Image.BILINEAR))
                self.picture.configure(image=self._photo)
        except Exception as exc:             # shown in the window, once per tick at most
            self._say(f"Screen update failed: {type(exc).__name__}: {exc}")
        self.root.after(TICK_MS, self._tick)

    def _ensure_display(self) -> None:
        """Create the picture sender once the link is up; rebuild it if it died."""
        if self.link is None or not self.link.connected:
            return
        if self.display is not None and self.display.error is not None:
            self._say(f"The OG stopped taking pictures: {self.display.error}")
            self.display, self._display_retry = None, time.monotonic() + 2.0
        if self.display is None and time.monotonic() >= self._display_retry:
            self.display = OgDisplay(self.link.send_raw)
            self._sig = None                 # nothing is known about the screen: send it all
            self.link.send(f"BRIGHT {self.menu.brightness}")

    # ---- leaving --------------------------------------------------------

    def _quit(self) -> None:
        if self.game is not None:
            self.game._close()
        if self.preview is not None:
            self.preview.stop()
        if self.display is not None:
            self.display.present(render_message(self.menu.theme, "WiliRehab", "closed on the laptop"))
            self.display.flush(3.0)
            self.display.close()
        if self.link is not None:
            self.link.close()
        self.root.destroy()


def main() -> None:
    ap = argparse.ArgumentParser(description="WiliRehab: the OG as the screen")
    ap.add_argument("--port", help="the OG display CPU's serial port, e.g. COM11")
    ap.add_argument("--no-og", action="store_true", help="no OG: laptop window only")
    ap.add_argument("--camera", type=int, default=0, help="camera number for the face view")
    ap.add_argument("--theme", choices=sorted(THEMES),
                    help="overrides the saved theme for this run")
    args = ap.parse_args()
    port = find_port(args)
    root = tk.Tk()
    Shell(root, port, camera=args.camera, theme=args.theme)
    root.mainloop()


if __name__ == "__main__":
    main()
