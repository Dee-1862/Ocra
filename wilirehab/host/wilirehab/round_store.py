"""Finished-round rows: always saved to a local file first, then sent to Supabase when it can.

Offline-first: `add()` only appends a line to a local queue file, so a lost connection never
loses a row and never stalls a game. `flush()` sends what is queued in one request and
removes it only if the server accepted it. Numbers only (see orchestrator_core): no video
and no names.

Supabase's REST interface is a plain HTTPS POST to {SUPABASE_URL}/rest/v1/<table>, so this
needs no extra package. SUPABASE_KEY should be the project's anon (public) key together with
an insert-only policy (see supabase_schema.sql); the powerful service_role key must not go on
this machine.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

QUEUE_FILE = Path(__file__).resolve().parents[1] / "agents_queue.jsonl"      # git-ignored
TABLE = "rounds"


def post_rows(url: str, key: str, table: str, rows: list) -> None:
    """Send rows to Supabase. Raises on any failure (the caller keeps the rows queued)."""
    headers = {"apikey": key, "Content-Type": "application/json", "Prefer": "return=minimal"}
    if key.startswith("eyJ"):                 # a JWT-style key also goes in Authorization
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{url.rstrip('/')}/rest/v1/{table}",
                                 data=json.dumps(rows).encode("utf-8"), headers=headers,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        # Supabase explains itself in the body (for example "Could not find the table
        # 'public.rounds'"); show that instead of a bare status code. The key is never in it.
        body = exc.read().decode("utf-8", "replace")[:300]
        raise OSError(f"HTTP {exc.code} {body}") from None


class RoundStore:
    def __init__(self, url: str = None, key: str = None, path=QUEUE_FILE, sender=post_rows,
                 table: str = TABLE):
        self.url, self.key, self.table = url, key, table
        self._path, self._send = Path(path), sender
        self._lock = threading.Lock()
        self.last_error = None

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def add(self, row: dict) -> None:
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    def _read(self) -> list:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows = []
        for line in lines:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass                      # a torn line is dropped, not allowed to block the queue
        return rows

    def pending(self) -> int:
        with self._lock:
            return len(self._read())

    def flush(self) -> int:
        """Send everything queued. Returns how many rows the server accepted."""
        if not self.configured:
            return 0
        with self._lock:
            rows = self._read()
        if not rows:
            return 0
        try:
            self._send(self.url, self.key, self.table, rows)
        except Exception as exc:            # kept queued; shown on the Agents page
            self.last_error = f"{type(exc).__name__}: {exc}"
            return 0
        self.last_error = None
        with self._lock:
            rest = self._read()[len(rows):]           # rows added while we were sending
            self._path.write_text("".join(json.dumps(r, separators=(",", ":"), default=str) + "\n"
                                          for r in rest), encoding="utf-8")
        return len(rows)

    def status_text(self) -> str:
        if not self.configured:
            return "not configured"
        if self.last_error:
            return "error: " + self.last_error[:200]
        return f"{self.pending()} queued"
