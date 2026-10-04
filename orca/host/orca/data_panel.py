"""The data sidebar: live values on top, a scrolling timeline underneath.

Reads from a DataTable; knows nothing about the OG or the games.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import ui
from .ui import BG, DIM, FG, PANEL

REFRESH_MS = 200
STALE_S = 2.0           # a live value older than this is greyed out
TIMELINE_ROWS = 200

# Hardware the design still plans but that is not connected. It shows as
# "not connected" until something calls table.add() with that source. The
# force, forearm and IMU sensors were dropped from the plan, so they are gone.
PLANNED = (
    ("haptic", "buzz", "haptic driver, Maestro, later"),
)


def short_role(role) -> str:
    """left_hand -> L, right_hand -> R, anything else as is, none -> blank."""
    return {"left_hand": "L", "right_hand": "R"}.get(role, role or "")


class DataPanel(tk.Frame):
    def __init__(self, parent, table):
        super().__init__(parent, bg=BG)
        self.table = table
        self.freeze = tk.BooleanVar(value=False)
        self._style()

        tk.Label(self, text="LIVE SENSORS", bg=BG, fg=ui.FAINT,
                 font=ui.font(8, True)).pack(anchor="w", padx=2)
        box = ui.framed(self)
        box.pack(fill="x", pady=(4, 14))
        self.live = ttk.Treeview(box, style="Data.Treeview", show="headings",
                                 columns=("hand", "source", "channel", "value", "age"), height=8)
        for name, width in (("hand", 36), ("source", 50), ("channel", 84), ("value", 190), ("age", 44)):
            self.live.heading(name, text=name)
            self.live.column(name, width=width, anchor="w", stretch=False)
        self.live.tag_configure("stale", foreground=ui.FAINT)
        self.live.pack(fill="x")

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="TIMELINE", bg=BG, fg=ui.FAINT,
                 font=ui.font(8, True)).pack(side="left", padx=2)
        tk.Checkbutton(head, text="freeze", variable=self.freeze, bg=BG, fg=DIM,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       highlightthickness=0, takefocus=0, font=ui.font(9)).pack(side="right")
        box2 = ui.framed(self)
        box2.pack(fill="both", expand=True, pady=(4, 0))
        self.timeline = ttk.Treeview(box2, style="Data.Treeview", show="headings",
                                     columns=("t", "hand", "source", "channel", "value"), height=14)
        for name, width, label in (("t", 50, "time s"), ("hand", 36, "hand"),
                                   ("source", 50, "source"), ("channel", 80, "channel"),
                                   ("value", 190, "value")):
            self.timeline.heading(name, text=label)
            self.timeline.column(name, width=width, anchor="w", stretch=False)
        self.timeline.pack(fill="both", expand=True)

        self.after(REFRESH_MS, self._refresh)

    @staticmethod
    def _style() -> None:
        ui.style_tables()

    def _refresh(self) -> None:
        now = self.table.now()
        self._refresh_live(now)
        if not self.freeze.get():
            for row in self.table.drain_ui():
                self.timeline.insert("", 0, values=(f"{row['t']:.2f}", short_role(row["role"]),
                                                    row["source"], row["channel"], row["text"]))
            children = self.timeline.get_children()
            for iid in children[TIMELINE_ROWS:]:
                self.timeline.delete(iid)
        self.after(REFRESH_MS, self._refresh)

    def _refresh_live(self, now: float) -> None:
        shown = set()
        for (source, channel, role), row in self.table.latest.items():
            self._set_live(f"{source}/{channel}/{role}", short_role(role), source,
                           channel, row["text"], now - row["t"])
            shown.add((source, channel))
        for source, channel, label in PLANNED:
            if (source, channel) not in shown:
                self._set_live(f"{source}/{channel}/planned", "", source, channel,
                               f"not connected ({label})", None)

    def _set_live(self, iid, hand, source, channel, text, age) -> None:
        age_text = "" if age is None else f"{age:.1f}s"
        stale = age is None or age > STALE_S
        values = (hand, source, channel, text, age_text)
        tags = ("stale",) if stale else ()
        if self.live.exists(iid):
            self.live.item(iid, values=values, tags=tags)
        else:
            self.live.insert("", "end", iid=iid, values=values, tags=tags)
