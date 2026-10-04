"""Draw the pictures the README shows: the OG's own screens, rendered by the project's own code.

    cd orca/host
    python ../docs/make_images.py            # writes orca/docs/images/*.png

No board, no camera and no agents program are needed. The agent pages are drawn from a made-up status
snapshot of a SIMULATED patient (the story in orca.demo_data: a bad day with rising discomfort), so every
number on those screens is sample data, not a person's. Run it again after changing a screen.
"""
from __future__ import annotations

import sys
from pathlib import Path

HOST = Path(__file__).resolve().parents[1] / "host"
sys.path.insert(0, str(HOST))

from orca import og_render as R                       # noqa: E402
from orca.agent_graph import Registry                 # noqa: E402
from orca.launcher import GAMES                       # noqa: E402
from orca.og_menu import AGENTS, SETTINGS, Menu       # noqa: E402

OUT = Path(__file__).resolve().parent / "images"
NOW = 1000.0

# Draw at the full 640x480 the renderer works in (it normally halves this for the 320x240 panel).
R._finish = lambda img: img


def snapshot() -> dict:
    """A status snapshot of the agent network mid-session, with a simulated 'bad day' decision."""
    reg = Registry(clock=lambda: NOW)
    for key in ("og", "cam", "filter", "check", "act"):
        for k in range(6):
            reg.beat(key, now=NOW - 0.5 * k)
    reg.beat("decide", now=NOW - 6.0)                 # the Decide agent only speaks once per round: idle
    reg.note("db", "insert-only key")
    snap = reg.snapshot(now=NOW)
    snap["transport"] = "Local agents (simulated patient)"
    snap["verdict"] = {"verdict": "concerning (verified)"}
    snap["decision"] = {"action": "ease the game", "reason": "all four tests pass"}
    steps = [
        ("filter", "info", "Kept 34 of 36 hand readings, dropped 2 glitches"),
        ("filter", "ok", "Face baseline set from 10 calm seconds"),
        ("check", "info", "Enough data: 30 attempts for each hand"),
        ("check", "warn", "Left hand reaches 37% of right, usual 61%"),
        ("check", "warn", "Face and pain agree: discomfort rising"),
        ("decide", "alert", "Concerning (verified): ease the game"),
        ("act", "ok", "Saved the round and 36 readings"),
        ("act", "info", "Recommended difficulty: easier"),
    ]
    snap["steps"] = [{"t": NOW - 20 + i, "agent": s, "stage": s, "level": lvl, "text": text}
                     for i, (s, lvl, text) in enumerate(steps)]
    return snap


def save(img, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / name, optimize=True)
    print("wrote", OUT / name)


def main() -> None:
    snap = snapshot()

    home = Menu(GAMES, theme="dark")
    save(R.render_menu(home), "og-menu.png")
    save(R.render_menu(Menu(GAMES, theme="light")), "og-menu-light.png")

    settings = Menu(GAMES, theme="dark")
    settings.screen = SETTINGS
    save(R.render_menu(settings), "og-settings.png")

    detail = Menu(GAMES, theme="dark")
    detail.screen, detail.agents_view, detail.agents_sel = AGENTS, "detail", 1
    save(R.render_agent_detail(detail, snap), "og-agent-detail.png")

    steps = Menu(GAMES, theme="dark")
    steps.screen, steps.agents_view = AGENTS, "all"
    save(R.render_steps(steps, snap), "og-agent-steps.png")


if __name__ == "__main__":
    main()
