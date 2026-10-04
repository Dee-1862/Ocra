"""Draw the OG's own screens (menu, settings, face view) as 320x240 pictures.

Everything is drawn at 640x480, the same size and positions as the PC windows
(mapping_demo: legend circles at y 384, radius 24), then halved with a smoothing filter.
Drawing at double size is what makes the circles and text soft instead of jagged.
Pillow only: no Tk, so it runs without a window and is tested without a board.
"""
from __future__ import annotations

import time
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .agent_graph import EDGES, LEVELS, NODES, edge_state
from .agent_steps import STAGE_WORDS
from .button_map import BUTTONS, COLORS
from .og_menu import Menu
from .og_theme import THEMES, Theme, mix

W2, H2 = 640, 480                 # drawing size
OG_W, OG_H = 320, 240             # what the panel shows
LEGEND_Y = 418                    # the same numbers as mapping_demo, so PC and OG agree
RADIUS = 16
LEGEND_TOP = 388
CIRCLE_X = [W2 * (2 * i + 1) / (2 * len(BUTTONS)) for i in range(len(BUTTONS))]
LIST_TOP, ROW_H, ROW_BOX = 126, 66, 58   # 4 rows fit between the header and the legend
FACE_BOX = (24, 8, 450, 328)      # where the camera picture goes, 426x320 (the legend starts at 388)
FLASH_SECONDS = 0.18              # how long a pressed button stays dark

_FONTS = {True: ("segoeuisb.ttf", "seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"),
          False: ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")}


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False):
    for name in _FONTS[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def fit_text(draw, text: str, fnt, max_w: int) -> str:
    """`text`, cut with '...' so it is at most max_w pixels wide."""
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "...", font=fnt) > max_w:
        text = text[:-1]
    return text.rstrip() + "..."


def _panel(d, box, theme: Theme, r: int = 20, fill=None, outline=None, width: int = 2) -> None:
    d.rounded_rectangle(box, radius=r, fill=fill or theme.surface, outline=outline or theme.line,
                        width=width)


def _legend(d, theme: Theme, legend: dict, flash) -> None:
    _panel(d, (16, LEGEND_TOP, W2 - 16, H2 - 12), theme, r=18)
    pressed = flash[0] if flashing(flash) else None
    for i, button in enumerate(BUTTONS):
        x, label = CIRCLE_X[i], legend.get(button)
        color = COLORS[button]
        if label:
            # Flat disc, like the real button caps. A press darkens it for a moment.
            fill = mix(color, "#000000", 0.4) if button == pressed else color
            d.ellipse((x - RADIUS, LEGEND_Y - RADIUS, x + RADIUS, LEGEND_Y + RADIUS), fill=fill)
        else:
            d.ellipse((x - RADIUS + 1, LEGEND_Y - RADIUS + 1, x + RADIUS - 1, LEGEND_Y + RADIUS - 1),
                      outline=mix(color, theme.surface, 0.72), width=3)
        text = label or "not used"
        fnt = font(21, True) if label else font(18)
        d.text((x, LEGEND_Y + RADIUS + 20), text, font=fnt, anchor="mm",
               fill=theme.fg if label else theme.faint)


def _header(d, theme: Theme, title: str, hint: str) -> None:
    d.text((30, 14), "ORCA", font=font(18, True), fill=theme.accent)
    d.text((30, 64), title, font=font(36, True), anchor="ls", fill=theme.fg)
    d.text((31, 98), hint, font=font(19), anchor="ls", fill=theme.dim)


def flashing(flash) -> bool:
    """True while a press ring is still animating (the screen needs redrawing)."""
    return bool(flash) and time.monotonic() - flash[1] < FLASH_SECONDS


def _finish(img: Image.Image) -> Image.Image:
    return img.resize((OG_W, OG_H), Image.LANCZOS)


def render_menu(menu: Menu, theme_name: str = None, flash=None) -> Image.Image:
    """The home or settings screen. `flash` is (button, time.monotonic() when pressed) or None."""
    theme = THEMES[theme_name or menu.theme]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    _header(d, theme, menu.title, menu.hint)
    first, rows, total = menu.visible()
    chosen = menu.selected()
    for k, row in enumerate(rows):
        y0 = LIST_TOP + k * ROW_H
        box = (24, y0, W2 - 44, y0 + ROW_BOX)
        on = first + k == chosen
        _panel(d, box, theme, r=14, fill=theme.raised if on else theme.surface,
               outline=theme.accent if on else theme.line)
        if on:
            d.rounded_rectangle((24, y0 + 10, 29, y0 + ROW_BOX - 10), radius=2, fill=theme.accent)
        value_w = 0
        if row.value:
            d.text((W2 - 64, y0 + ROW_BOX / 2), row.value, font=font(26, True), anchor="rm",
                   fill=theme.accent if on else theme.fg)
            value_w = int(d.textlength(row.value, font=font(26, True))) + 24
        text_w = (W2 - 44) - 46 - 20 - value_w                 # inside the box, with margins
        # Anchored by baseline ("ls"), so the two lines cannot drift into each other.
        d.text((46, y0 + 27), fit_text(d, row.title, font(26, True), text_w),
               font=font(26, True), anchor="ls", fill=theme.fg)
        if row.sub:
            d.text((46, y0 + 48), fit_text(d, row.sub, font(16), text_w),
                   font=font(16), anchor="ls", fill=theme.dim)
    if total > len(rows):                                    # a thin scroll bar
        track = (W2 - 32, LIST_TOP, W2 - 26, LIST_TOP + ROW_H * len(rows) - (ROW_H - ROW_BOX))
        d.rounded_rectangle(track, radius=3, fill=theme.line)
        span = track[3] - track[1]
        top = track[1] + span * first / total
        d.rounded_rectangle((track[0], top, track[2], top + span * len(rows) / total), radius=3,
                            fill=theme.accent)
    _legend(d, theme, menu.legend(), flash)
    return _finish(img)


def render_face(menu: Menu, picture: Image.Image = None, status: str = "", flash=None) -> Image.Image:
    """The face view. `picture` is the camera frame (426x320) or None while it is not ready."""
    theme = THEMES[menu.theme]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = FACE_BOX
    if picture is not None:
        img.paste(picture.resize((x1 - x0, y1 - y0)), (x0, y0))
    else:
        _panel(d, FACE_BOX, theme)
        d.text(((x0 + x1) / 2, (y0 + y1) / 2), status or "Opening the camera...",
               font=font(24), anchor="mm", fill=theme.dim)
    d.text((470, 26), "FACE", font=font(18, True), fill=theme.accent)
    d.text((470, 54), "Live", font=font(30, True), fill=theme.fg)
    for i, line in enumerate(("Nothing is", "saved. Only", "numbers are,", "and only in", "games.")):
        d.text((470, 110 + 26 * i), line, font=font(18), fill=theme.dim)
    _legend(d, theme, menu.legend(), flash)
    return _finish(img)


STATE_COLOR = {"ok": "#34d399", "idle": "#fbbf24", "lost": "#f87171"}     # "off" has no colour
STATE_WORDS = {"off": "no data", "idle": "idle", "lost": "lost"}
AGENT_Y = (140, 195, 250, 305, 360)   # centres of the five rows: devices, then the four agents
AGENT_BOX = (200, 42)                 # box width and height
# Devices side by side, the chain down the middle, the Act agent and Supabase side by side.
AGENT_X = {"og": 235, "cam": 485, "filter": 360, "check": 360, "decide": 360, "act": 235,
           "db": 485}


DOT_SPEED = 0.8                       # line lengths per second the transfer dots travel
DOT_R = 5


def transfer_dots(rate: float, now: float) -> list:
    """Where along a connection (0 = sender, 1 = receiver) the moving dots are at time `now`.

    None while nothing is flowing. A busier connection gets more dots (up to four), so the
    picture shows how much is moving as well as that something is."""
    if rate <= 0:
        return []
    count = min(4, 1 + int(rate))
    phase = (now * DOT_SPEED) % 1.0
    return [(phase + k / count) % 1.0 for k in range(count)]


def render_agents(menu: Menu, snap: dict = None, flash=None, now: float = None) -> Image.Image:
    """The agent network: four levels of boxes joined by lines, coloured by how alive each is.

    `snap` is an aged status snapshot (agent_graph.age_snapshot) or None when the agents program
    is not running. Green = passed something on in the last 3 s, amber = idle, red = lost,
    a grey outline = never seen. A line takes the state of the part it comes from, and while it
    is carrying messages, dots travel along it from sender to receiver. Redraw a few times a
    second (with a changing `now`) and the transfer is visible as movement."""
    now = time.time() if now is None else now
    theme = THEMES[menu.theme]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    nodes = (snap or {}).get("nodes", {})
    decision, verdict = (snap or {}).get("decision"), (snap or {}).get("verdict")
    if snap is None:
        hint = "Not running: python -m orca.agents_main"
    elif decision and verdict:                       # what was found, then what was done about it
        hint = f"{verdict['verdict']}  ->  {decision['action']} ({decision['reason']})"
    elif decision:
        hint = f"Decided: {decision['action']} ({decision['reason']})"
    else:
        hint = f"{snap.get('transport', 'Agents')}. No finished round yet"
    _header(d, theme, menu.title, fit_text(d, hint, font(19), W2 - 70))

    level_of = {key: level for key, _label, level in NODES}
    half_w, half_h = AGENT_BOX[0] / 2, AGENT_BOX[1] / 2
    labels = []                                                  # what travels on each link
    for a, b in EDGES:                                         # lines first, boxes cover the ends
        if level_of[a] == level_of[b]:                           # side by side: a horizontal link
            y = AGENT_Y[level_of[a]]
            xa, ya, xb, yb = AGENT_X[a] + half_w, y, AGENT_X[b] - half_w, y
        else:                                                    # a row down: bottom edge to top edge
            xa, ya = AGENT_X[a], AGENT_Y[level_of[a]] + half_h
            xb, yb = AGENT_X[b], AGENT_Y[level_of[b]] - half_h
        color = STATE_COLOR.get(edge_state(nodes, a))
        d.line((xa, ya, xb, yb), fill=color or theme.line, width=4)
        if color and edge_state(nodes, a) == "ok":               # carrying messages right now
            for p in transfer_dots(nodes.get(a, {}).get("rate", 0.0), now):
                x, y = xa + (xb - xa) * p, ya + (yb - ya) * p
                d.ellipse((x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R), fill=theme.fg,
                          outline=STAGE_COLOR.get(a, color), width=3)
        if (a, b) in EDGE_LABELS:
            labels.append((EDGE_LABELS[(a, b)], (xa + xb) / 2, (ya + yb) / 2, level_of[a] == level_of[b]))
    for level, name in enumerate(LEVELS):
        d.text((24, AGENT_Y[level]), name, font=font(16), anchor="lm", fill=theme.faint)
    for key, label, level in NODES:
        node = nodes.get(key, {})
        state = node.get("state", "off")
        color = STATE_COLOR.get(state)
        cx, cy = AGENT_X[key], AGENT_Y[level]
        box = (cx - AGENT_BOX[0] / 2, cy - half_h, cx + AGENT_BOX[0] / 2, cy + half_h)
        stage = STAGE_COLOR.get(key)                             # the four agents have their own colour
        if stage and key == menu.agent and menu.screen == AGENTS_SCREEN:
            # The agent that gray and red have selected: a ring around it (green opens its page).
            d.rounded_rectangle((box[0] - 5, box[1] - 5, box[2] + 5, box[3] + 5), radius=15,
                                outline=theme.fg, width=3)
        _panel(d, box, theme, r=12, outline=color or theme.line,
               fill=mix(stage, theme.surface, 0.88) if stage else None)
        if stage:
            d.rounded_rectangle((box[0], box[1] + 6, box[0] + 7, box[3] - 6), radius=3, fill=stage)
        dot = (box[2] - 26, cy - 8, box[2] - 10, cy + 8)
        if color:
            d.ellipse(dot, fill=color)
        else:
            d.ellipse(dot, outline=theme.faint, width=3)
        room = AGENT_BOX[0] - 14 - 36
        d.text((box[0] + 14, cy - 2), fit_text(d, label, font(20, True), room), font=font(20, True),
               anchor="ls", fill=theme.fg)
        if node.get("note"):
            sub = node["note"]
        elif state == "ok":
            sub = f"{node.get('rate', 0.0):.1f}/s  {node.get('count', 0)} total"
        else:
            sub = STATE_WORDS[state]
        d.text((box[0] + 14, cy + 16), fit_text(d, sub, font(15), room), font=font(15),
               anchor="ls", fill=theme.dim)
    for word, x, y, flat in labels:                              # after the boxes, so nothing covers them
        if flat:
            d.text((x, y - 14), word, font=font(14), anchor="mm", fill=theme.dim)
        else:
            d.text((x + 10, y), word, font=font(14), anchor="lm", fill=theme.dim)
    _legend(d, theme, menu.legend(), flash)
    return _finish(img)


AGENTS_SCREEN = "agents"                 # og_menu.AGENTS (not imported: render only needs the name)
STAGE_COLOR = {"filter": "#60a5fa", "check": "#fbbf24", "decide": "#34d399", "act": "#5ba4b0"}
# What each agent is for, and who it hears from and tells: the top line and the flow line of its page.
STAGE_ROLE = {"filter": "Drops readings that cannot be real, summarises each window",
              "check": "Fact-checks a possible imbalance four ways before calling it real",
              "decide": "Gives the verdict, then the difficulty and the rule behind it",
              "act": "Saves the round and the clean readings, and states the plan"}
STAGE_FLOW = {"filter": ("the OG hands and the webcam", "Check and Act"),
              "check": ("Filter", "Decide"), "decide": ("Check", "Act"),
              "act": ("Decide and Filter", "Supabase")}
DETAIL_STATE = {"ok": "running", "idle": "idle", "lost": "lost", "off": "no data yet"}
# What each link carries, drawn beside it: the data gets smaller and more meaningful going down.
EDGE_LABELS = {("og", "filter"): "readings", ("cam", "filter"): "readings",
               ("filter", "check"): "windows", ("check", "decide"): "finding",
               ("decide", "act"): "decision", ("act", "db"): "rows"}
LEVEL_TEXT = {"info": "fg", "ok": "#34d399", "warn": "#fbbf24", "alert": "#f87171"}
STEP_ROWS = 8
STEP_TOP, STEP_PITCH = 134, 32


def render_agent_detail(menu: Menu, snap: dict = None, flash=None) -> Image.Image:
    """One agent's own page: what it is for, whether it is running, who it hears from and tells, and
    ONLY its own latest steps, so one agent can be followed without the others' lines mixed in.

    The agent is the one selected on the chain (menu.agent). `snap` is the status snapshot, or None
    when the agents program is not running."""
    theme = THEMES[menu.theme]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    stage = menu.agent
    node = ((snap or {}).get("nodes") or {}).get(stage, {})
    state = node.get("state", "off")
    color = STATE_COLOR.get(state)
    _header(d, theme, menu.title, fit_text(d, STAGE_ROLE[stage], font(19), W2 - 70))

    d.rounded_rectangle((24, 118, W2 - 24, 168), radius=14, fill=theme.surface,
                        outline=color or theme.line, width=2)
    d.rounded_rectangle((24, 124, 31, 162), radius=3, fill=STAGE_COLOR[stage])
    dot = (50, 134, 68, 152)
    d.ellipse(dot, fill=color) if color else d.ellipse(dot, outline=theme.faint, width=3)
    d.text((84, 143), DETAIL_STATE[state], font=font(22, True), anchor="lm", fill=theme.fg)
    d.text((W2 - 44, 143), f"{node.get('count', 0)} messages   {node.get('rate', 0.0):.1f}/s",
           font=font(19), anchor="rm", fill=theme.dim)

    src, dst = STAGE_FLOW[stage]
    d.text((30, 204), fit_text(d, f"Hears from {src}. Tells {dst}.", font(18), W2 - 60), font=font(18),
           anchor="ls", fill=theme.dim)
    d.text((30, 232), STAGE_WORDS[stage] + " (latest):", font=font(16, True), anchor="ls",
           fill=STAGE_COLOR[stage])
    mine = [s for s in ((snap or {}).get("steps") or []) if s.get("stage") == stage][-5:]
    for i, step in enumerate(mine):
        level = LEVEL_TEXT.get(step.get("level", "info"), "fg")
        d.text((30, 266 + i * 30), fit_text(d, step.get("text", ""), font(20), W2 - 60), font=font(20),
                anchor="ls", fill=theme.fg if level == "fg" else level)
    if not mine:
        d.text((30, 270), "Nothing yet. Play a game, or run the simulated patient.", font=font(19),
               anchor="ls", fill=theme.faint)
    _legend(d, theme, menu.legend(), flash)
    return _finish(img)


def render_steps(menu: Menu, snap: dict = None, flash=None) -> Image.Image:
    """The agents' live step log: the newest lines, each tagged FILTERED, CHECKED, DECIDED or DID.

    This is the "what are they doing, step by step" view. A line's text is coloured by how serious
    it is (green fine, amber worth a look, red a verified concern). `snap` is the status snapshot,
    or None when the agents program is not running."""
    theme = THEMES[menu.theme]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    steps = (snap or {}).get("steps") or []
    verdict = (snap or {}).get("verdict")
    if snap is None:
        hint = "Not running: python -m orca.agents_main"
    elif verdict:
        hint = f"Latest verdict: {verdict['verdict']}"
    else:
        hint = "Waiting for the agents to do something"
    _header(d, theme, menu.title, fit_text(d, hint, font(19), W2 - 70))
    shown = steps[-STEP_ROWS:]
    for i, step in enumerate(shown):
        y = STEP_TOP + i * STEP_PITCH
        stage = step.get("stage", "")
        color = STAGE_COLOR.get(stage, theme.faint)
        tag = STAGE_WORDS.get(stage, stage.upper())
        d.rounded_rectangle((24, y - 14, 138, y + 12), radius=8, fill=color)
        d.text((81, y - 1), tag, font=font(15, True), anchor="mm", fill="#0b0e12")
        level = LEVEL_TEXT.get(step.get("level", "info"), "fg")
        text_color = theme.fg if level == "fg" else level
        d.text((150, y + 5), fit_text(d, step.get("text", ""), font(18), W2 - 150 - 20),
               font=font(18), anchor="ls", fill=text_color)
    if not shown:
        d.text((30, STEP_TOP + 20), "Nothing yet. Play a game with both hands.", font=font(20),
               anchor="ls", fill=theme.dim)
    _legend(d, theme, menu.legend(), flash)
    return _finish(img)


def render_setup(theme_name: str, title: str, lines, legend: dict) -> Image.Image:
    """A question card for assigning roles: a title, a few lines, and the buttons that answer it.

    `legend` is button -> label for the buttons that matter (the others are drawn as unused)."""
    theme = THEMES[theme_name]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    d.text((30, 14), "ORCA", font=font(18, True), fill=theme.accent)
    d.text((30, 80), fit_text(d, title, font(36, True), W2 - 60), font=font(36, True),
           anchor="ls", fill=theme.fg)
    for i, line in enumerate(lines):
        d.text((32, 140 + 38 * i), fit_text(d, line, font(25), W2 - 60), font=font(25),
               anchor="ls", fill=theme.dim)
    _legend(d, theme, {b: legend.get(b) for b in BUTTONS}, None)
    return _finish(img)


def render_message(theme_name: str, title: str, line: str) -> Image.Image:
    """A plain screen, for example 'Orca closed' when the laptop program stops."""
    theme = THEMES[theme_name]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    d.text((30, 14), "ORCA", font=font(18, True), fill=theme.accent)
    d.text((W2 / 2, 210), title, font=font(44, True), anchor="mm", fill=theme.fg)
    d.text((W2 / 2, 270), line, font=font(22), anchor="mm", fill=theme.dim)
    return _finish(img)
