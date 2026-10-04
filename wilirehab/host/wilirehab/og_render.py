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

from .button_map import BUTTONS, COLORS
from .og_menu import Menu
from .og_theme import THEMES, Theme, mix

W2, H2 = 640, 480                 # drawing size
OG_W, OG_H = 320, 240             # what the panel shows
LEGEND_Y = 384
RADIUS = 24
CIRCLE_X = [W2 * (2 * i + 1) / (2 * len(BUTTONS)) for i in range(len(BUTTONS))]
LIST_TOP, ROW_H, ROW_BOX = 126, 68, 60   # 3 rows fit between the header and the legend (332)
FACE_BOX = (24, 8, 450, 328)      # where the camera picture goes, 426x320
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
    _panel(d, (16, 332, W2 - 16, H2 - 14), theme)
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
        d.text((x, LEGEND_Y + RADIUS + 24), text, font=fnt, anchor="mm",
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
        d.text((46, y0 + 28), fit_text(d, row.title, font(26, True), text_w),
               font=font(26, True), anchor="ls", fill=theme.fg)
        if row.sub:
            d.text((46, y0 + 50), fit_text(d, row.sub, font(16), text_w),
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


def render_message(theme_name: str, title: str, line: str) -> Image.Image:
    """A plain screen, for example 'WiliRehab closed' when the laptop program stops."""
    theme = THEMES[theme_name]
    img = Image.new("RGB", (W2, H2), theme.bg)
    d = ImageDraw.Draw(img)
    d.text((30, 14), "WILIREHAB", font=font(18, True), fill=theme.accent)
    d.text((W2 / 2, 210), title, font=font(44, True), anchor="mm", fill=theme.fg)
    d.text((W2 / 2, 270), line, font=font(22), anchor="mm", fill=theme.dim)
    return _finish(img)
