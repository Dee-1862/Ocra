"""Two tables side by side: the face, and the hand.

Fed by DataTable rows: ("face", "reading") from the webcam and
("hand", "motion") from the OG's accelerometer, each stamped with the table's
clock so the two can be read across. Newest row on top. Knows nothing about
the camera or the OG.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import ui
from .data_panel import BG, DIM, FG, PANEL, short_role

REFRESH_MS = 250
MAX_ROWS = 120

# (key in the row's fields, heading, width in pixels)
FACE_COLUMNS = (
    ("t", "time s", 52), ("state", "state", 72), ("pspi_mean", "PSPI", 40),
    ("pspi_peak", "peak", 40), ("au4", "AU4", 34), ("au7", "AU7", 34),
    ("au10", "AU10", 38), ("au43", "AU43", 40), ("bpm", "bpm", 38),
    ("hr_quality", "q", 34), ("rmssd_ms", "RMSSD", 48), ("rmssd_ratio", "x rest", 46),
    ("lf_hf", "LF/HF", 42), ("lf_hf_ratio", "x rest", 46), ("beats", "beats", 40),
)
HAND_COLUMNS = (
    ("t", "time s", 52), ("hand", "hand", 34), ("jerk_peak", "jerk pk", 54),
    ("jerk_mean", "jerk mn", 54), ("roll_rom", "roll RoM", 62), ("pitch_rom", "pitch RoM", 66),
    ("rom_base", "base", 42), ("rom_ratio", "x base", 48), ("roll", "roll", 44),
    ("pitch", "pitch", 44),
)


def cell(value) -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def face_values(row: dict) -> tuple:
    f = row["fields"]
    state = {"ok": "ok", "calibrating": f"calib {cell(f.get('calib_left'))}s",
             "no_face": "NO FACE"}.get(f.get("state"), cell(f.get("state")))
    out = []
    for key, _label, _width in FACE_COLUMNS:
        if key == "t":
            out.append(f"{row['t']:.1f}")
        elif key == "state":
            out.append(state)
        else:
            out.append(cell(f.get(key)))
    return tuple(out)


def hand_values(row: dict) -> tuple:
    f = row["fields"]
    out = []
    for key, _label, _width in HAND_COLUMNS:
        if key == "t":
            out.append(f"{row['t']:.1f}")
        elif key == "hand":
            out.append(short_role(row["role"]))
        else:
            out.append(cell(f.get(key)))
    return tuple(out)


class DiscomfortPanel(tk.Frame):
    def __init__(self, parent, table, face_on: bool):
        super().__init__(parent, bg=BG)
        self._pending = {"face": [], "hand": []}
        self._count = {"face": 0, "hand": 0}
        self._style()
        face_title = ("Face: PSPI, pulse and HRV, once a second" if face_on
                      else "Face: camera off \u2014 start the game with --face")
        self.face = self._table(0, face_title, FACE_COLUMNS)
        self.hand = self._table(1, "Hand: jerk (m/s\u00b3) and range of motion (deg), once a second",
                                HAND_COLUMNS)
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        table.subscribe(self._on_row)
        self.after(REFRESH_MS, self._refresh)

    def _table(self, column: int, title: str, columns):
        box = tk.Frame(self, bg=BG)
        box.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0))
        name, _, detail = title.partition(": ")
        head = tk.Frame(box, bg=BG)
        head.pack(fill="x", pady=(0, 4))
        tk.Label(head, text=name.upper(), bg=BG, fg=ui.ACCENT,
                 font=ui.font(9, True)).pack(side="left", padx=2)
        tk.Label(head, text=detail, bg=BG, fg=ui.FAINT, font=ui.font(9)).pack(side="left", padx=8)
        frame = ui.framed(box)
        frame.pack(fill="x")
        tree = ttk.Treeview(frame, style="Disc.Treeview", show="headings", height=6,
                            columns=[c[0] for c in columns])
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w", stretch=False)
        tree.tag_configure("odd", background=ui.ZEBRA)
        tree.pack(fill="x")
        return tree

    @staticmethod
    def _style() -> None:
        ui.style_tables()

    def _on_row(self, row: dict) -> None:
        if row["source"] == "face" and row["channel"] == "reading":
            self._pending["face"].append(row)
        elif row["source"] == "hand" and row["channel"] == "motion":
            self._pending["hand"].append(row)

    def _refresh(self) -> None:
        for name, tree, values in (("face", self.face, face_values),
                                   ("hand", self.hand, hand_values)):
            rows, self._pending[name] = self._pending[name], []
            for row in rows:
                self._count[name] += 1
                tree.insert("", 0, values=values(row),
                            tags=("odd",) if self._count[name] % 2 else ())
            for iid in tree.get_children()[MAX_ROWS:]:
                tree.delete(iid)
        self.after(REFRESH_MS, self._refresh)
