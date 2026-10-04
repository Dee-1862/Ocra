"""Button-map demo: a laptop stand-in for the OG screen.

Pick a screen on the left. The bottom row of the OG screen shows the five
buttons as coloured circles with a one or two word label. Press a button (click
it, press keys 1 to 5, or press the real OG if you pass --port) and a ring in
that button's colour expands around the circle, a banner says what was
recorded, and the press is added to the log.

Run from wilirehab/host:
    python -m wilirehab.mapping_demo
    python -m wilirehab.mapping_demo --port COM5      # also react to the real OG

Keys: 1 gray, 2 yellow, 3 green, 4 blue, 5 red.  Left/Right: change screen.
The real-OG option reads the `BTN <colour> down` lines the wilirehab display
firmware prints; it does not draw anything on the OG.
"""
from __future__ import annotations

import argparse
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass

from . import ui
from .button_map import BUTTONS, COLORS, SCREENS, Screen
from .ui import BG, DIM, FG, FONT, PANEL

W, H = 640, 480            # the OG panel is 320x240; drawn at 2x
LEGEND_Y = 384             # circle centres
RADIUS = 24
RING_SECONDS = 0.6
BANNER_SECONDS = 1.4

blend = ui.mix             # colour a at t=0 fading to colour b at t=1


@dataclass
class Anim:
    kind: str                 # "ring" or "banner"
    t0: float
    dur: float
    color: str
    cx: float = 0.0
    cy: float = 0.0
    delay: float = 0.0
    text: str = ""
    item: int = 0             # canvas item id, 0 until first drawn


class App:
    def __init__(self, root: tk.Tk, port: str | None):
        self.root = root
        self.root.title("WiliRehab button map")
        self.root.configure(bg=BG)
        self.screen: Screen = SCREENS[0]
        self.pain = 0
        self.anims: list[Anim] = []
        self.ticking = False
        self.events: queue.Queue = queue.Queue()

        side = tk.Frame(root, bg=BG)
        side.grid(row=0, column=0, sticky="ns", padx=(16, 8), pady=16)
        tk.Label(side, text="WILIREHAB", bg=BG, fg=ui.ACCENT,
                 font=ui.font(10, True)).pack(anchor="w", padx=4)
        tk.Label(side, text="Screens", bg=BG, fg=FG,
                 font=ui.font(16, True)).pack(anchor="w", padx=4, pady=(0, 10))
        self.nav = ui.NavList(side, [s.title for s in SCREENS], self._select)
        self.nav.pack()
        tk.Label(side, text="BUTTON KEYS", bg=BG, fg=ui.FAINT,
                 font=ui.font(8, True)).pack(anchor="w", padx=4, pady=(18, 2))
        tk.Label(side, text="1 gray   2 yellow   3 green\n4 blue   5 red\n\u2190 \u2192  change screen",
                 bg=BG, fg=DIM, font=ui.font(10), justify="left").pack(anchor="w", padx=4)
        self.status = tk.Label(side, text="", bg=BG, fg=DIM, font=ui.font(10),
                               wraplength=190, justify="left")
        self.status.pack(anchor="w", padx=4, pady=(12, 0))

        main = tk.Frame(root, bg=BG)
        main.grid(row=0, column=1, padx=(8, 12), pady=16)
        self.canvas = tk.Canvas(main, width=W, height=H, bg=BG, highlightthickness=0)
        self.canvas.pack()
        self.log = tk.Listbox(main, bg=BG, fg=ui.FAINT, height=3, width=76,
                              highlightthickness=0, borderwidth=0, activestyle="none",
                              selectbackground=BG, font=ui.mono(9), takefocus=0)
        self.log.pack(fill="x", pady=(8, 0))
        self.log.insert(0, "Button presses are listed here.")

        self.canvas.bind("<Button-1>", self._on_click)
        root.bind_all("<Key>", self._on_key)
        root.bind_all("<Left>", lambda e: self._step_screen(-1))
        root.bind_all("<Right>", lambda e: self._step_screen(1))

        self.circle_x = [W * (2 * i + 1) / (2 * len(BUTTONS)) for i in range(len(BUTTONS))]
        self._select(0)

        if port:
            self._start_serial(port)
        self.root.after(20, self._poll)

    # ---- screens -----------------------------------------------------

    def _select(self, index: int) -> None:
        index = index % len(SCREENS)
        self.screen = SCREENS[index]
        self.nav.select(index)
        self.pain = 0
        self.anims.clear()
        self._render()

    def _step_screen(self, delta: int) -> None:
        self._select(SCREENS.index(self.screen) + delta)

    def _render(self) -> None:
        c = self.canvas
        c.delete("all")
        ui.background(c, W, H)
        c.create_text(30, 40, text=self.screen.title, anchor="w", fill=FG,
                      font=ui.font(24, True), tags="static")
        c.create_text(31, 72, text=self.screen.hint, anchor="w", fill=DIM,
                      font=ui.font(12), tags="static")
        self._draw_body()
        ui.rrect(c, 16, 332, W - 16, H - 14, r=20, top=ui.SURFACE_TOP, bottom=ui.SURFACE,
                 border=ui.LINE, shadow=10, tags="static")
        for i, b in enumerate(BUTTONS):
            label = self.screen.label(b)
            x = self.circle_x[i]
            if label:
                ui.orb(c, x, LEGEND_Y, RADIUS, COLORS[b], tags=("static", "btn_" + b))
                c.create_text(x, LEGEND_Y + RADIUS + 22, text=label, fill=FG,
                              font=ui.font(11, True), tags="static")
            else:
                ui.ring(c, x, LEGEND_Y, RADIUS - 1, blend(COLORS[b], ui.SURFACE, 0.72), thick=2,
                        tags=("static", "btn_" + b))
                c.create_text(x, LEGEND_Y + RADIUS + 22, text="not used", fill=ui.FAINT,
                              font=ui.font(10), tags="static")

    def _draw_body(self) -> None:
        self.canvas.delete("body")
        if self.screen.key == "pain":
            self._draw_pain()

    def _draw_pain(self) -> None:
        c = self.canvas
        color = blend(blend(ui.GOOD, ui.GOLD, min(1.0, self.pain / 5.0)), ui.BAD,
                      max(0.0, (self.pain - 5) / 5.0))
        ui.rrect(c, 120, 104, W - 120, 304, r=22, top=ui.SURFACE_TOP, bottom=ui.SURFACE,
                 border=ui.LINE, shadow=12, tags="body")
        ui.halo(c, W / 2, 190, 90, color, alpha=0.20, tags="body")
        c.create_text(W / 2, 184, text=str(self.pain), fill=color,
                      font=ui.font(72, True), tags="body")
        c.create_text(W / 2, 244, text="out of 10", fill=DIM, font=ui.font(12), tags="body")
        seg_w, gap, x = 30, 6, W / 2 - (11 * 30 + 10 * 6) / 2
        for i in range(11):
            lit = i <= self.pain
            hue = blend(blend(ui.GOOD, ui.GOLD, min(1.0, i / 5.0)), ui.BAD, max(0.0, (i - 5) / 5.0))
            ui.pill(c, x, 268, x + seg_w, 278, hue if lit else ui.LINE, tags="body")
            x += seg_w + gap

    # ---- input -------------------------------------------------------

    def _on_click(self, event) -> None:
        for i, b in enumerate(BUTTONS):
            dx, dy = event.x - self.circle_x[i], event.y - LEGEND_Y
            if dx * dx + dy * dy <= (RADIUS + 8) ** 2:
                self.press(b, "click")
                return

    def _on_key(self, event) -> None:
        if event.char in "12345" and event.char:
            self.press(BUTTONS[int(event.char) - 1], "key")

    def press(self, button: str, source: str) -> None:
        label = self.screen.label(button)
        self._apply(label)
        self._animate(button, label)
        stamp = time.strftime("%H:%M:%S")
        what = label if label else "ignored (not used here)"
        self.log.insert(0, f"{stamp}  {source:<5} {self.screen.title:<16} "
                           f"{button:<6} {what}")
        if self.log.size() > 60:
            self.log.delete(60, "end")

    def _apply(self, label) -> None:
        """The only state the demo changes: the pain number."""
        if self.screen.key != "pain" or not label:
            return
        if label == "+1":
            self.pain = min(10, self.pain + 1)
        elif label == "-1":
            self.pain = max(0, self.pain - 1)
        self._draw_body()

    # ---- animation ---------------------------------------------------

    def _animate(self, button: str, label) -> None:
        i = BUTTONS.index(button)
        now = time.monotonic()
        color = COLORS[button] if label else DIM
        x = self.circle_x[i]
        for delay in (0.0, 0.14):
            self.anims.append(Anim("ring", now, RING_SECONDS, color, x, LEGEND_Y, delay))
        self.canvas.delete("banner")
        self.anims = [a for a in self.anims if a.kind != "banner"]
        if label:
            text = f"âœ“ {button.upper()}  {label}  recorded"
        else:
            text = f"{button.upper()}  not used on this screen"
        self.anims.append(Anim("banner", now, BANNER_SECONDS, color, W / 2, 316, 0.0, text))
        # A short flash on the circle itself.
        self.canvas.delete("flash")
        self.canvas.create_oval(x - RADIUS - 3, LEGEND_Y - RADIUS - 3, x + RADIUS + 3,
                                LEGEND_Y + RADIUS + 3, outline="#ffffff" if label else DIM,
                                width=3, tags="flash")
        self.root.after(140, lambda: self.canvas.delete("flash"))
        if not self.ticking:
            self.ticking = True
            self.root.after(16, self._tick)

    def _tick(self) -> None:
        now = time.monotonic()
        alive = []
        for a in self.anims:
            p = (now - a.t0 - a.delay) / a.dur
            if p < 0:
                alive.append(a)
                continue
            if p >= 1:
                if a.item:
                    self.canvas.delete(a.item)
                continue
            ease = 1 - (1 - p) ** 3
            if a.kind == "ring":
                r = RADIUS + 4 + 46 * ease
                width = max(1.0, 7 * (1 - p))
                color = blend(a.color, PANEL, p)
                box = (a.cx - r, a.cy - r, a.cx + r, a.cy + r)
                if not a.item:
                    a.item = self.canvas.create_oval(*box, outline=color, width=width)
                else:
                    self.canvas.coords(a.item, *box)
                    self.canvas.itemconfigure(a.item, outline=color, width=width)
            else:
                fade = blend(a.color, PANEL, max(0.0, (p - 0.6) / 0.4))
                if not a.item:
                    a.item = self.canvas.create_text(a.cx, a.cy, text=a.text, fill=fade,
                                                     font=ui.font(15, True), tags="banner")
                else:
                    self.canvas.itemconfigure(a.item, fill=fade)
            alive.append(a)
        self.anims = alive
        if self.anims:
            self.root.after(16, self._tick)
        else:
            self.ticking = False

    # ---- real OG -----------------------------------------------------

    def _start_serial(self, port: str) -> None:
        def reader():
            try:
                import serial  # pyserial
                with serial.Serial(port, 115200, timeout=0.2) as s:
                    self.events.put(("status", f"Listening to the OG on {port}"))
                    while True:
                        parts = s.readline().decode("ascii", "replace").split()
                        if len(parts) == 3 and parts[0] == "BTN" and parts[2] == "down" \
                                and parts[1] in BUTTONS:
                            self.events.put(("press", parts[1]))
            except Exception as exc:  # shown in the window, not swallowed
                self.events.put(("status", f"Serial stopped: {exc}"))

        threading.Thread(target=reader, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "press":
                    self.press(value, "OG")
                else:
                    self.status.configure(text=value)
        except queue.Empty:
            pass
        self.root.after(20, self._poll)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", help="serial port of the OG display CPU, e.g. COM5")
    args = ap.parse_args()
    root = tk.Tk()
    App(root, args.port)
    root.mainloop()


if __name__ == "__main__":
    main()
