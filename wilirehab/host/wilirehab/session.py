"""Session log: numbers only, never video.

The privacy claim on Page 1 ("no video stored") is enforced here rather than
promised: records accept only scalars and short strings, so a frame, a
landmark array or a face crop cannot be written by accident.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

MAX_STR = 64


class SessionLog:
    def __init__(self, path: str | Path, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._f = open(self.path, "a", encoding="utf-8")

    def record(self, kind: str, **fields) -> None:
        row = {"t": round(self._clock(), 3), "kind": kind}
        for k, v in fields.items():
            if isinstance(v, bool) or v is None:
                row[k] = v
            elif isinstance(v, (int, float)):
                row[k] = None if (isinstance(v, float) and not math.isfinite(v)) else v
            elif isinstance(v, str) and len(v) <= MAX_STR:
                row[k] = v
            else:
                raise TypeError(
                    f"session log field {k!r}: only numbers and short strings "
                    f"are stored, got {type(v).__name__}")
        self._f.write(json.dumps(row) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
