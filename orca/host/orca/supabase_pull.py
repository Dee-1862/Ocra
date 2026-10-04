"""Pick the data up from Supabase: print the newest rows of a table.

    python -m orca.supabase_pull rounds [limit]
    python -m orca.supabase_pull hand_readings 20
    python -m orca.supabase_pull face_readings

This is how a trusted machine (the Raspberry Pi, a cloud host, your analysis) reads what the
agents wrote. Reading needs the project's SERVICE_ROLE key, because the laptop's anon key is
deliberately insert-only. Put it in SUPABASE_SERVICE_KEY on that trusted machine only. Never
commit it, never put it in the games' .env on a shared laptop, and never share it: it can read,
change and delete everything in the project.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from .env import load_env

TABLES = ("rounds", "hand_readings", "face_readings")


def pull(url: str, key: str, table: str, limit: int = 10) -> list:
    """The newest `limit` rows of `table`, newest first. Raises OSError with Supabase's reason."""
    req = urllib.request.Request(
        f"{url.rstrip('/')}/rest/v1/{table}?select=*&order=created_at.desc&limit={int(limit)}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise OSError(f"HTTP {exc.code} {exc.read().decode('utf-8', 'replace')[:300]}") from None


def main() -> None:
    load_env()
    table = sys.argv[1] if len(sys.argv) > 1 else "rounds"
    if table not in TABLES:
        raise SystemExit(f"table must be one of {', '.join(TABLES)}")
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        raise SystemExit("Needs SUPABASE_URL and SUPABASE_SERVICE_KEY (the service_role key, on a "
                         "trusted machine only). The anon key cannot read.")
    try:
        rows = pull(url, key, table, limit)
    except OSError as exc:
        raise SystemExit(f"Supabase said: {exc}")
    print(f"{len(rows)} newest row(s) of {table}:")
    for row in rows:
        row.pop("data", None)                 # the full JSON is long; the typed columns are enough
        print(json.dumps(row, default=str))


if __name__ == "__main__":
    main()
