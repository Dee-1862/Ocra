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
    d.text((30, 14), "WILIREHAB", font=font(18, True), fill=theme.accent)
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
AGENT_Y = (146, 214, 282, 350)        # centres of the four levels
AGENT_BOX = (190, 44)                 # box width and height
AGENT_X = {"og": 235, "cam": 485, "hand_agent": 235, "face_agent": 485, "orch": 360, "db": 360}


def render_agents(menu: Menu, snap: dict = None, flash=None) -> Image.Image:
    """The agent network: four levels of boxes joined by lines, coloured by how alive each is.

    `snap` is an aged status snapshot (agent_graph.age_snapshot) or None when the agents program
    is not running. Green = passed something on in the last 3 s, amber = idle, red = lost,
    a grey outline = never seen. A line takes the state of the part it comes from."""
    theme = THEMES[menu.theme]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    nodes = (snap or {}).get("nodes", {})
    decision = (snap or {}).get("decision")
    if snap is None:
        hint = "Not running: python -m wilirehab.agents_main"
    elif decision:
        hint = f"Policy: {decision['action']} ({decision['reason']})"
    else:
        hint = f"{snap.get('transport', 'Agents')}. No finished round yet"
    _header(d, theme, menu.title, fit_text(d, hint, font(19), W2 - 70))

    level_of = {key: level for key, _label, level in NODES}
    half_h = AGENT_BOX[1] / 2
    for a, b in EDGES:                                           # lines first, boxes cover the ends
        d.line((AGENT_X[a], AGENT_Y[level_of[a]] + half_h, AGENT_X[b], AGENT_Y[level_of[b]] - half_h),
               fill=STATE_COLOR.get(edge_state(nodes, a), theme.line), width=4)
    for level, name in enumerate(LEVELS):
        d.text((24, AGENT_Y[level]), name, font=font(16), anchor="lm", fill=theme.faint)
    for key, label, level in NODES:
        node = nodes.get(key, {})
        state = node.get("state", "off")
        color = STATE_COLOR.get(state)
        cx, cy = AGENT_X[key], AGENT_Y[level]
        box = (cx - AGENT_BOX[0] / 2, cy - half_h, cx + AGENT_BOX[0] / 2, cy + half_h)
        _panel(d, box, theme, r=12, outline=color or theme.line)
        dot = (box[2] - 26, cy - 8, box[2] - 10, cy + 8)
        if color:
            d.ellipse(dot, fill=color)
        else:
            d.ellipse(dot, outline=theme.faint, width=3)
        room = AGENT_BOX[0] - 14 - 36
        d.text((box[0] + 14, cy - 3), fit_text(d, label, font(20, True), room), font=font(20, True),
               anchor="ls", fill=theme.fg)
        sub = node.get("note") or (f"{node.get('rate', 0.0):.1f} msg/s" if state == "ok"
                                   else STATE_WORDS[state])
        d.text((box[0] + 14, cy + 17), fit_text(d, sub, font(15), room), font=font(15),
               anchor="ls", fill=theme.dim)
    _legend(d, theme, menu.legend(), flash)
    return _finish(img)


def render_message(theme_name: str, title: str, line: str) -> Image.Image:
    """A plain screen, for example 'WiliRehab closed' when the laptop program stops."""
    theme = THEMES[theme_name]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    d.text((30, 14), "WILIREHAB", font=font(18, True), fill=theme.accent)
    d.text((W2 / 2, 210), title, font=font(44, True), anchor="mm", fill=theme.fg)
    d.text((W2 / 2, 270), line, font=font(22), anchor="mm", fill=theme.dim)
    return _finish(img)
