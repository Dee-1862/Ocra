"""The data sidebar: live values on top, a scrolling timeline underneath.

Reads from a DataTable; knows nothing about the OG or the games.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#0d1117"
PANEL = "#161b22"
FG = "#e6edf3"
DIM = "#6e7681"

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

        tk.Label(self, text="Live sensors", bg=BG, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.live = ttk.Treeview(self, style="Data.Treeview", show="headings",
                                 columns=("hand", "source", "channel", "value", "age"), height=10)
        for name, width in (("hand", 36), ("source", 50), ("channel", 84), ("value", 190), ("age", 44)):
            self.live.heading(name, text=name)
            self.live.column(name, width=width, anchor="w", stretch=False)
        self.live.tag_configure("stale", foreground=DIM)
        self.live.pack(fill="x", pady=(4, 10))

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="Timeline", bg=BG, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Checkbutton(head, text="freeze", variable=self.freeze, bg=BG, fg=DIM,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       highlightthickness=0, takefocus=0).pack(side="right")
        self.timeline = ttk.Treeview(self, style="Data.Treeview", show="headings",
                                     columns=("t", "hand", "source", "channel", "value"), height=15)
        for name, width, label in (("t", 50, "time s"), ("hand", 36, "hand"),
                                   ("source", 50, "source"), ("channel", 80, "channel"),
                                   ("value", 190, "value")):
            self.timeline.heading(name, text=label)
            self.timeline.column(name, width=width, anchor="w", stretch=False)
        self.timeline.pack(fill="both", expand=True, pady=(4, 0))

        self.after(REFRESH_MS, self._refresh)

    @staticmethod
    def _style() -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")      # the native Windows theme ignores colours
        except tk.TclError:
            pass
        style.configure("Data.Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=FG, borderwidth=0, rowheight=20,
                        font=("Consolas", 9))
        style.configure("Data.Treeview.Heading", background="#21262d", foreground=FG,
                        relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Data.Treeview", background=[("selected", "#30363d")])

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
