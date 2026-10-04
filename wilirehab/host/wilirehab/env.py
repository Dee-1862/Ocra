"""Read settings from wilirehab/host/.env, so keys never live in code or on a command line.

A .env file is lines of KEY=VALUE (blank lines and # comments are skipped, quotes around the
value are removed). Variables already set in the real environment win. .env is git-ignored:
never commit it, and never paste its contents into a chat or a paper.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"          # wilirehab/host/.env


def load_env(path=ENV_FILE) -> list:
    """Set variables from the file that are not already set. Returns the names it set."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
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
    return done
