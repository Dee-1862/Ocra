"""Read settings from orca/host/.env, so keys never live in code or on a command line.

A .env file is lines of KEY=VALUE (blank lines and # comments are skipped, quotes around the
value are removed). Variables already set in the real environment win. .env is git-ignored:
never commit it, and never paste its contents into a chat or a paper.

The project used to be called WiliRehab, and its settings were named WILIREHAB_*. They are ORCA_*
now. A setting still written with the old prefix (in an old .env, or typed in a terminal) keeps
working: it is copied to its ORCA_ name unless that is already set. New settings use ORCA_*.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"          # orca/host/.env
LEGACY_PREFIX, PREFIX = "WILIREHAB_", "ORCA_"


def _carry_over_old_names() -> None:
    """Make every WILIREHAB_X setting also available as ORCA_X (the new name wins if both exist)."""
    for key in list(os.environ):
        if key.startswith(LEGACY_PREFIX):
            os.environ.setdefault(PREFIX + key[len(LEGACY_PREFIX):], os.environ[key])


def load_env(path=ENV_FILE) -> list:
    """Set variables from the file that are not already set. Returns the names it set."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        _carry_over_old_names()
        return []
    done = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
            done.append(key)
    _carry_over_old_names()
    return done
