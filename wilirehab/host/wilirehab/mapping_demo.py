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

from .button_map import BUTTONS, COLORS, SCREENS, Screen

BG = "#0d1117"
PANEL = "#161b22"
FG = "#e6edf3"
DIM = "#6e7681"

W, H = 640, 480            # the OG panel is 320x240; drawn at 2x
LEGEND_Y = 372             # circle centres
RADIUS = 26
RING_SECONDS = 0.6
BANNER_SECONDS = 1.4
FONT = "Segoe UI"


def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def blend(a: str, b: str, t: float) -> str:
    """Colour a at t=0 fading to colour b at t=1."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t),
                              round(ga + (gb - ga) * t),
                              round(ba + (bb - ba) * t))


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
        side.grid(row=0, column=0, sticky="ns", padx=(12, 6), pady=12)
        tk.Label(side, text="Screens", bg=BG, fg=FG,
                 font=(FONT, 13, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(side, bg=PANEL, fg=FG, selectbackground="#30363d",
                                  selectforeground=FG, highlightthickness=0,
                                  borderwidth=0, activestyle="none",
                                  font=(FONT, 12), width=18, height=len(SCREENS),
                                  exportselection=False, takefocus=0)
        for s in SCREENS:
            self.listbox.insert("end", s.title)
        self.listbox.pack(pady=(6, 10))
        self.listbox.bind("<<ListboxSelect>>", self._on_pick)
        tk.Label(side, text="Keys\n1 gray   2 yellow   3 green\n4 blue   5 red\nLeft/Right: screen",
                 bg=BG, fg=DIM, font=(FONT, 10), justify="left").pack(anchor="w")
        self.status = tk.Label(side, text="", bg=BG, fg=DIM, font=(FONT, 10),
                               wraplength=190, justify="left")
        self.status.pack(anchor="w", pady=(10, 0))

        main = tk.Frame(root, bg=BG)
        main.grid(row=0, column=1, padx=(6, 12), pady=12)
        self.canvas = tk.Canvas(main, width=W, height=H, bg=PANEL,
                                highlightthickness=1, highlightbackground="#30363d")
        self.canvas.pack()
        self.log = tk.Listbox(main, bg=PANEL, fg=FG, height=6, width=76,
                              highlightthickness=0, borderwidth=0, activestyle="none",
                              font=("Consolas", 10), takefocus=0)
        self.log.pack(fill="x", pady=(8, 0))

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
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.pain = 0
        self.anims.clear()
        self._render()

    def _step_screen(self, delta: int) -> None:
        self._select(SCREENS.index(self.screen) + delta)

    def _on_pick(self, _event) -> None:
        sel = self.listbox.curselection()
        if sel:
            self._select(sel[0])

    def _render(self) -> None:
        c = self.canvas
        c.delete("all")
        c.create_text(W / 2, 46, text=self.screen.title, fill=FG,
                      font=(FONT, 26, "bold"), tags="static")
        c.create_text(W / 2, 92, text=self.screen.hint, fill=DIM,
                      font=(FONT, 14), tags="static")
        self._draw_body()
        c.create_line(24, 322, W - 24, 322, fill="#30363d", tags="static")
        for i, b in enumerate(BUTTONS):
            label = self.screen.label(b)
            x = self.circle_x[i]
            if label:
                c.create_oval(x - RADIUS, LEGEND_Y - RADIUS, x + RADIUS, LEGEND_Y + RADIUS,
                              fill=COLORS[b], outline="", tags=("static", "btn_" + b))
                c.create_text(x, LEGEND_Y + RADIUS + 24, text=label, fill=FG,
                              font=(FONT, 13, "bold"), tags="static")
            else:
                c.create_oval(x - RADIUS, LEGEND_Y - RADIUS, x + RADIUS, LEGEND_Y + RADIUS,
                              fill="", outline=blend(COLORS[b], PANEL, 0.7), width=2,
                              dash=(3, 3), tags=("static", "btn_" + b))
                c.create_text(x, LEGEND_Y + RADIUS + 24, text="not used", fill=DIM,
                              font=(FONT, 11), tags="static")

    def _draw_body(self) -> None:
        self.canvas.delete("body")
        if self.screen.key == "pain":
            self.canvas.create_text(W / 2, 200, text=str(self.pain), fill=FG,
                                    font=(FONT, 88, "bold"), tags="body")
            self.canvas.create_text(W / 2, 270, text="out of 10", fill=DIM,
                                    font=(FONT, 14), tags="body")

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
            text = f"✓ {button.upper()}  {label}  recorded"
        else:
            text = f"{button.upper()}  not used on this screen"
        self.anims.append(Anim("banner", now, BANNER_SECONDS, color, W / 2, 300, 0.0, text))
        # A short flash on the circle itself.
        self.canvas.itemconfigure("btn_" + button, width=4,
                                  outline="#ffffff" if label else DIM)
        self.root.after(140, lambda b=button: self.canvas.itemconfigure(
            "btn_" + b, width=0 if self.screen.label(b) else 2,
            outline="" if self.screen.label(b) else blend(COLORS[b], PANEL, 0.7)))
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
                                                     font=(FONT, 18, "bold"), tags="banner")
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
