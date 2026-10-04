"""The role-assignment screen: the OGs ask, you answer with the gray button.

Started by og_shell when several OGs are plugged in and no roles are saved yet, or on request:

    python -m orca.og_shell --setup

It opens every OG's port, shows each OG its own question (role_setup.card), and watches for
button presses. When it finishes it saves devices.json and closes, and the shell starts with the
roles. The window on the laptop shows what the screen OG shows. Closing the window before it is
finished saves nothing.
"""
from __future__ import annotations

import queue
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from .devices import save_config
from .og_display import OgDisplay
from .og_link import OgLink
from .og_render import OG_H, OG_W, render_setup
from .role_setup import RoleSetup, card

DONE_SHOWN_S = 2.5            # how long the "Setup done" card stays up before the shell starts


class SetupApp:
    def __init__(self, root: tk.Tk, found: list, config_path, theme: str = "dark",
                 rotate_roles=()):
        """`found` is [(port, usb serial)] for every OG display CPU plugged in. `rotate_roles` are
        the hands whose screen is saved as turned 180 degrees: an OG given such a role has its
        picture turned the moment it is chosen, so its title reads the right way up."""
        self.root, self.theme, self.config_path = root, theme, Path(config_path)
        self.rotate_roles = set(rotate_roles)
        self._rot: dict = {}                              # serial -> the ROT line last sent
        self.setup = RoleSetup([serial for _port, serial in found])
        self.events: queue.Queue = queue.Queue()
        self.links, self.displays, self._shown = {}, {}, {}
        self._first = found[0][1] if found else None
        self._done_at = None
        self._closed = False
        self._photo = None
        for port, serial in found:                       # one link per OG, tagged by its serial
            link = OgLink(port, self.events, role=serial)
            link.start()
            self.links[serial] = link

        root.title("Orca: assign the OGs")
        root.configure(bg="#0b0e12")
        self.picture = tk.Label(root, bg="#0b0e12", bd=0)
        self.picture.pack(padx=12, pady=(12, 4))
        self.status = tk.Label(root, bg="#0b0e12", fg="#8b95a1", anchor="w", justify="left",
                               wraplength=620, text=f"Found {len(found)} OG(s). Look at their "
                               "screens: press GRAY on the OG each question asks about.")
        self.status.pack(fill="x", padx=14, pady=(0, 10))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(20, self._poll)
        root.after(150, self._tick)

    def _say(self, text: str) -> None:
        if text:
            self.status.configure(text=text)

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            while True:
                kind, value, serial = self.events.get_nowait()
                if kind == "press":
                    self._say(self.setup.on_press(serial, value))
                elif kind == "status":
                    self._say(f"OG {serial}: {value}")
        except queue.Empty:
            pass
        self.root.after(20, self._poll)

    def _tick(self) -> None:
        if self._closed:
            return
        try:
            shown = None
            screen = self.setup.assigned.get("screen") or self._first
            for serial, link in self.links.items():
                title, lines, legend = card(self.setup, serial)
                frame = render_setup(self.theme, title, lines, legend)
                if serial == screen:
                    shown = frame
                if not link.connected:
                    continue
                # Which way up this OG's picture is: turned for a hand saved as turned, else normal.
                want = "ROT 180" if self.setup.role_of(serial) in self.rotate_roles else "ROT 0"
                if self._rot.get(serial) != want:
                    self._rot[serial] = want
                    link.send(want)                       # the OG clears itself, so draw it again
                    self._shown[serial] = None
                    if serial in self.displays:
                        self.displays[serial].invalidate()
                if serial not in self.displays or self.displays[serial].error is not None:
                    self.displays[serial] = OgDisplay(link.send_raw)
                key = (title, tuple(lines), tuple(sorted(legend.items())))
                if self._shown.get(serial) != key or self.displays[serial].error is not None:
                    self._shown[serial] = key
                    self.displays[serial].present(frame)
            if shown is not None:
                self._photo = ImageTk.PhotoImage(shown.resize((OG_W * 2, OG_H * 2), Image.BILINEAR))
                self.picture.configure(image=self._photo)
            if self.setup.done:
                if self._done_at is None:
                    self._done_at = time.monotonic()
                    self._say("Roles chosen: " + ", ".join(
                        f"{role} = {serial}" for role, serial in self.setup.mapping().items()))
                elif time.monotonic() - self._done_at >= DONE_SHOWN_S:
                    self.close()
                    return
        except Exception as exc:                          # shown, not swallowed
            self._say(f"Setup screen error: {type(exc).__name__}: {exc}")
        self.root.after(150, self._tick)

    def close(self) -> None:
        """Save the roles if setup finished, release every OG, close the window."""
        if self._closed:
            return
        self._closed = True
        if self.setup.done and self.setup.assigned:
            save_config(self.config_path, self.setup.mapping())
            print(f"Saved {self.config_path}: {self.setup.mapping()}")
        else:
            print("Setup was not finished; nothing was saved.")
        for display in self.displays.values():
            display.flush(2.0)
            display.close()
        for link in self.links.values():
            link.close()
        self.root.destroy()
