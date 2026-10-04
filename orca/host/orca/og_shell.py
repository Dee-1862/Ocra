"""The OG as the screen: a menu on the OG, games that show on it, a face view.

    python -m orca.og_shell                 # roles from devices.json; else the one OG
    python -m orca.og_shell --port COM11    # the screen OG on a named display-CPU port
    python -m orca.og_shell --port COM11 --left-port COM12 --right-port COM13
    python -m orca.og_shell --no-og         # no OG: try the menu on the laptop alone

Three OGs on cables (set up once with python -m orca.devices --setup): the left_hand and
right_hand OGs are worn and steer the games with their accelerometers; the screen OG shows the
menu and the game, and its buttons are the buttons. With no roles saved, one OG does all three.

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
from .agent_graph import age_snapshot
from .agent_link import read_status
from .devices import SCREEN
from .face_view import FacePreview
from .launcher import GAMES
from .og_display import OgDisplay
from .og_link import OgLink
from .og_menu import AGENTS, FACE, SOUND_VOLUME, Menu, invert_lists, rotated_roles
from .og_render import (CIRCLE_X, LEGEND_Y, OG_H, OG_W, RADIUS, flashing, render_agent_detail,
                        render_agents, render_face, render_menu, render_message, render_steps)
from .og_theme import THEMES, light_variant

TICK_MS = 100                     # screen update rate while a game is mirrored
ROLE = "right_hand"               # the games name their one OG by role
KEYS = (("<Up>", "gray"), ("<Left>", "yellow"), ("<Return>", "green"),
        ("<Right>", "blue"), ("<Down>", "red"))
DIGITS = {"1": "gray", "2": "yellow", "3": "green", "4": "blue", "5": "red"}

_scale = None                     # screenshot pixels per Tk pixel (differs on scaled displays)
SETTINGS_FILE = Path(__file__).resolve().parents[1] / "og_settings.json"      # orca/host


def load_settings() -> dict:
    """What the Settings screen saved last time, or {} (first run, or an unreadable file)."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def settings_of(menu: Menu) -> dict:
    return {"theme": menu.theme, "brightness": menu.brightness, "sound": menu.sound,
            "face_in_games": menu.face_in_games, "left_flip": menu.flips["left_hand"],
            "right_flip": menu.flips["right_hand"], "left_screen": menu.screens["left_hand"],
            "right_screen": menu.screens["right_hand"]}


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


HOST_DIR = Path(__file__).resolve().parents[1]        # orca/host


def find_ports(args):
    """-> (screen port or None, {hand role: port}, notes), from the options or devices.json."""
    if args.no_og:
        return None, {}, []
    from serial.tools import list_ports
    from .devices import find_og_displays, load_config, plan_ports
    found = find_og_displays(list_ports.comports())
    mapping = {}
    if not (args.port or args.left_port or args.right_port):
        try:
            mapping = load_config(args.devices)
        except ValueError as exc:
            raise SystemExit(str(exc))
    return plan_ports(found, mapping, screen=args.port, left=args.left_port, right=args.right_port)


def plan_text(screen, hands: dict, notes) -> str:
    """One readable line about which OG is doing what, for the status line."""
    parts = [f"screen {screen}" if screen else "no screen OG (menu on the laptop only)"]
    parts += [f"{role.replace('_', ' ')} {port}" for role, port in hands.items()]
    if not hands and screen:
        parts[0] += " (also the controller)"
    return "; ".join(parts) + ("".join(f"\nNote: {n}" for n in notes))


class Shell:
    def __init__(self, root: tk.Tk, port, camera: int = 0, theme: str = None, hands: dict = None,
                 driver: str = "right_hand", invert_roles: str = "", invert_fwd_roles: str = "",
                 notes=(), axis: str = "y"):
        self.root, self.camera = root, camera
        self.hands = dict(hands or {})                 # role -> port of the OGs worn for the games
        self.axis = axis
        self.driver, self.invert_roles = driver, invert_roles
        self.invert_fwd_roles = invert_fwd_roles
        self.notes = list(notes)
        saved = load_settings()
        chosen = theme or saved.get("theme")
        self.menu = Menu(GAMES, theme=chosen if chosen in THEMES else "dark",
                         face_in_games=bool(saved.get("face_in_games", False)),
                         brightness=saved.get("brightness", 100), sound=saved.get("sound", "medium"),
                         left_flip=saved.get("left_flip", "normal"),
                         right_flip=saved.get("right_flip", "normal"),
                         left_screen=saved.get("left_screen", "normal"),
                         right_screen=saved.get("right_screen", "normal"))
        self._saved = settings_of(self.menu)
        self.events: queue.Queue = queue.Queue()
        self.link = OgLink(port, self.events, role=SCREEN if self.hands else ROLE) if port else None
        self.display = None
        self._display_retry = 0.0
        self.preview = None
        self.game = None
        self._flash = None
        self._sig = None
        self._photo = None

        root.title("Orca OG screen")
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
        plan = plan_text(port, self.hands, self.notes)
        if self.link:
            self.link.start()
            self._say("Connecting. " + plan)
        else:
            self._say(plan if (self.hands or self.notes) else
                      "No OG: showing the menu on the laptop only.")
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
            mod = importlib.import_module(f"{__package__ or 'orca'}.{module}")
            args = mod.parser().parse_args([])
            # The tilt reversals saved in Settings, plus anything given on the command line.
            args.invert_roles, args.invert_fwd_roles = invert_lists(
                self.menu.flips, self.invert_roles, self.invert_fwd_roles)
            args.driver, args.axis = self.driver, self.axis
            top = tk.Toplevel(self.root)
            # With hand OGs, they steer and the screen OG only shows pictures and takes buttons
            # (screen_only); with none, the one screen OG is also the controller, as before.
            screen_only = bool(self.hands and self.link)
            cli.SHELL.update(link=self.link, on_exit=self._game_closed, screen_only=screen_only,
                             rotate=rotated_roles(self.menu.screens))
            cli.FACE["camera"] = self.camera if self.menu.face_in_games else None
            cli.FACE["preview"] = self.camera
            if self.hands:
                ports = dict(self.hands)
            else:
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
            cli.SHELL.update(link=None, on_exit=None, screen_only=False, rotate=None)
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
        cli.SHELL.update(link=None, on_exit=None, screen_only=False, rotate=None)
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
        if m.screen == AGENTS:
            # The agents program writes its status to a file; show it, redrawn once a second.
            # A file older than 5 s means the agents program is not running.
            now = time.time()
            raw = read_status()
            snap = age_snapshot(raw, now) if raw and now - raw["generated_at"] < 5.0 else None
            sig = (AGENTS, m.agents_view, m.agents_sel, int(now * 5), m.theme, live)   # 5 a second
            if sig == self._sig and not live:
                return None
            self._sig = sig
            if m.agents_view == "all":
                return render_steps(m, snap, self._flash)
            if m.agents_view == "detail":
                return render_agent_detail(m, snap, self._flash)
            return render_agents(m, snap, self._flash, now=now)
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
            self.display.present(render_message(self.menu.theme, "Orca", "closed on the laptop"))
            self.display.flush(3.0)
            self.display.close()
        if self.link is not None:
            self.link.close()
        self.root.destroy()


def main() -> None:
    ap = argparse.ArgumentParser(description="Orca: the OG as the screen")
    ap.add_argument("--port", help="the SCREEN OG's display-CPU serial port, e.g. COM11")
    ap.add_argument("--left-port", help="the left-hand OG's display-CPU port")
    ap.add_argument("--right-port", help="the right-hand OG's display-CPU port")
    ap.add_argument("--devices", default=str(HOST_DIR / "devices.json"),
                    help="roles file made by python -m orca.devices --setup (the default)")
    ap.add_argument("--no-og", action="store_true", help="no OG: laptop window only")
    ap.add_argument("--setup", action="store_true",
                    help="ask which OG is the screen and which are the hands, on the OGs' own "
                         "screens (done automatically when several OGs have no roles yet)")
    ap.add_argument("--driver", choices=("left_hand", "right_hand"), default="right_hand",
                    help="which hand steers games that use one hand (default right_hand)")
    ap.add_argument("--axis", choices=("x", "y"), default="y",
                    help="which OG axis is sideways when worn (default y)")
    ap.add_argument("--invert-roles", default="",
                    help="hands whose left/right tilt is swapped, e.g. left_hand")
    ap.add_argument("--invert-fwd-roles", default="",
                    help="hands whose forward/back tilt is swapped")
    ap.add_argument("--camera", type=int, default=0, help="camera number for the face view")
    ap.add_argument("--theme", choices=sorted(THEMES),
                    help="overrides the saved theme for this run")
    args = ap.parse_args()
    if not args.no_og:
        from serial.tools import list_ports
        from .devices import find_og_displays, load_config
        from .role_setup import needs_setup
        found = find_og_displays(list_ports.comports())
        explicit = bool(args.port or args.left_port or args.right_port)
        try:
            saved = {} if explicit else load_config(args.devices)
        except ValueError as exc:
            raise SystemExit(str(exc))
        if needs_setup(found, saved, explicit, force=args.setup):
            # The OGs ask which is which, on their own screens, and you answer with gray.
            from .og_setup import SetupApp
            setup_root = tk.Tk()
            st = load_settings()
            SetupApp(setup_root, found, args.devices,
                     theme=args.theme or st.get("theme") or "dark",
                     rotate_roles=rotated_roles({"left_hand": st.get("left_screen"),
                                                 "right_hand": st.get("right_screen")}))
            setup_root.mainloop()
            time.sleep(0.8)                     # let the OG ports close before the shell opens them
    screen, hands, notes = find_ports(args)
    print(plan_text(screen, hands, notes))
    root = tk.Tk()
    Shell(root, screen, camera=args.camera, theme=args.theme, hands=hands, driver=args.driver,
          invert_roles=args.invert_roles, invert_fwd_roles=args.invert_fwd_roles, notes=notes,
          axis=args.axis)
    root.mainloop()


if __name__ == "__main__":
    main()
