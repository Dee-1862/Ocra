"""Look and feel for the Tk windows: palette, fonts, and smooth sprites.

Tk's canvas draws hard-edged, flat shapes with no transparency. Everything
here that looks soft (rounded panels with shadows, shaded balls, glows, rings)
is a small anti-aliased image built with Pillow and numpy, cached, and placed
on the canvas with create_image. Game logic never touches this module's
internals; it asks for a sprite by size and colour.

Needs Pillow (`python -m pip install pillow`).
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

try:
    import numpy as np
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk
except ImportError as exc:                                  # pragma: no cover
    raise SystemExit(f"The game windows need Pillow and numpy: python -m pip install pillow numpy ({exc})")

# ---- palette ---------------------------------------------------------------

BG = "#0b0e12"            # window
SURFACE = "#12171d"       # panels
SURFACE_TOP = "#181f27"   # the lit top edge of a panel
RAISED = "#1d252e"        # chips, selected rows
LINE = "#2a343f"          # hairlines
FG = "#e8ecf1"
DIM = "#8b95a1"
FAINT = "#5a6572"
ACCENT = "#5ba4b0"        # muted steel-teal: no violet, not neon, apart from the OG button colours
GOLD = "#fbbf24"          # targets
GOOD = "#34d399"
BAD = "#f87171"

# Kept under the names the games already import.
PANEL = SURFACE

FONT = "Segoe UI"
FONT_SEMI = "Segoe UI Semibold"
MONO = "Cascadia Mono"
MONO_FALLBACK = "Consolas"

SS = 4                    # supersampling for rounded rectangles

# Soft halos, neon rings and the light bloom behind the window. Off: the look
# stays dark and flat. Every `glow=` argument and halo() call is a no-op while this
# is False, so turning it back on needs no other change.
GLOW = False


# ---- colour helpers ------------------------------------------------------------

def rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """Colour a at t=0 fading to colour b at t=1."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t), round(ga + (gb - ga) * t),
                              round(ba + (bb - ba) * t))


def lighten(color: str, t: float) -> str:
    return mix(color, "#ffffff", t)


def darken(color: str, t: float) -> str:
    return mix(color, "#000000", t)


# ---- fonts -----------------------------------------------------------------

_fonts: dict = {}


def font(size: int, semibold: bool = False) -> tuple:
    return (FONT_SEMI if semibold else FONT, size)


def mono(size: int) -> tuple:
    return (MONO, size) if MONO in tkfont.families() else (MONO_FALLBACK, size)


def text_width(text: str, size: int, semibold: bool = False) -> int:
    key = (size, semibold)
    f = _fonts.get(key)
    if f is None:
        f = _fonts[key] = tkfont.Font(family=FONT_SEMI if semibold else FONT, size=size)
    return f.measure(text)


# ---- sprite cache ----------------------------------------------------------------

_cache: dict = {}


def _get(key, build):
    """(PhotoImage, pad) for `key`, building it once. `build` returns (PIL image, pad)."""
    hit = _cache.get(key)
    if hit is None:
        image, pad = build()
        hit = _cache[key] = (ImageTk.PhotoImage(image), pad)
    return hit


def _to_image(arr) -> "Image.Image":
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def _composite(bottom, top):
    """Alpha-composite two float RGBA arrays (0..255) of the same shape."""
    ab = bottom[..., 3:4] / 255.0
    at = top[..., 3:4] / 255.0
    ao = at + ab * (1 - at)
    c = (top[..., :3] * at + bottom[..., :3] * ab * (1 - at)) / np.maximum(ao, 1e-6)
    return np.concatenate([c, ao * 255.0], axis=-1)


def _grid(size_w: int, size_h: int = 0):
    size_h = size_h or size_w
    ys, xs = np.mgrid[0:size_h, 0:size_w].astype(float)
    return xs - (size_w - 1) / 2.0, ys - (size_h - 1) / 2.0


# ---- round things (analytic anti-aliasing, no supersampling needed) ---------------

def _orb_image(r: float, color: str, glow: float):
    size = int(2 * (r + glow) + 4)
    dx, dy = _grid(size)
    d = np.hypot(dx, dy)
    base = np.zeros((size, size, 4))
    base[..., :3] = rgb(color)
    if glow > 0:
        g = np.clip(1 - (d - r) / glow, 0, 1) ** 2.2 * 0.55
        g[d < r - 1] = 0.0
        base[..., 3] = g * 255
    cov = np.clip(r + 0.5 - d, 0, 1)
    # A flat disc with only a faint top-to-bottom tone. No specular highlight: that is
    # what made the first version look like a glossy 2008 button.
    t = np.clip((dy + r) / (2.0 * r), 0, 1)[..., None]
    top = np.array(rgb(lighten(color, 0.14)), float)
    bottom = np.array(rgb(darken(color, 0.10)), float)
    disc = np.concatenate([top * (1 - t) + bottom * t, cov[..., None] * 255.0], axis=-1)
    return _to_image(_composite(base, disc)), size / 2.0


def orb(c, x, y, r, color, glow=0, tags="body"):
    """A flat disc centred on (x, y), optionally with a soft halo of `glow` px."""
    glow = glow if GLOW else 0
    photo, half = _get(("orb", round(r, 1), color, round(glow)), lambda: _orb_image(r, color, glow))
    return c.create_image(x, y, image=photo, tags=tags)


def _halo_image(r: float, color: str, alpha: float):
    size = int(2 * r + 2)
    dx, dy = _grid(size)
    d = np.hypot(dx, dy)
    out = np.zeros((size, size, 4))
    out[..., :3] = rgb(color)
    out[..., 3] = np.clip(1 - d / r, 0, 1) ** 2.0 * alpha * 255
    return _to_image(out), size / 2.0


def halo(c, x, y, r, color, alpha=0.5, tags="body"):
    """A soft radial glow with no solid core. Draws nothing while GLOW is off."""
    if not GLOW:
        return None
    photo, _ = _get(("halo", round(r), color, round(alpha, 2)), lambda: _halo_image(r, color, alpha))
    return c.create_image(x, y, image=photo, tags=tags)


def _ring_image(r: float, thick: float, color: str, glow: float, fill_alpha: float):
    size = int(2 * (r + thick / 2 + glow) + 4)
    dx, dy = _grid(size)
    d = np.hypot(dx, dy)
    out = np.zeros((size, size, 4))
    out[..., :3] = rgb(color)
    edge = np.abs(d - r) - thick / 2
    ring = np.clip(0.5 - edge, 0, 1)
    a = ring
    if glow > 0:
        a = np.maximum(a, np.clip(1 - np.maximum(edge, 0) / glow, 0, 1) ** 2.2 * 0.45)
    if fill_alpha > 0:
        a = np.maximum(a, np.where(d < r, fill_alpha * np.clip(1 - d / r, 0, 1) ** 0.5, 0))
    out[..., 3] = a * 255
    return _to_image(out), size / 2.0


def ring(c, x, y, r, color, thick=4, glow=0, fill_alpha=0.0, tags="body"):
    """An anti-aliased ring, optionally glowing and softly filled."""
    if not GLOW:
        glow, fill_alpha = 0, 0.0
    photo, _ = _get(("ring", round(r, 1), round(thick, 1), color, round(glow), round(fill_alpha, 2)),
                    lambda: _ring_image(r, thick, color, glow, fill_alpha))
    return c.create_image(x, y, image=photo, tags=tags)


def _line_image(dx: int, dy: int, width: float, color: str):
    pad = int(width) + 3
    w, h = abs(dx) + 2 * pad + 1, abs(dy) + 2 * pad + 1
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    ax, ay = (pad if dx >= 0 else pad + abs(dx)), (pad if dy >= 0 else pad + abs(dy))
    bx, by = ax + dx, ay + dy
    vx, vy = bx - ax, by - ay
    length2 = max(vx * vx + vy * vy, 1e-9)
    t = np.clip(((xs - ax) * vx + (ys - ay) * vy) / length2, 0, 1)
    dist = np.hypot(xs - (ax + t * vx), ys - (ay + t * vy))
    out = np.zeros((h, w, 4))
    out[..., :3] = rgb(color)
    out[..., 3] = np.clip(width / 2.0 + 0.5 - dist, 0, 1) * 255
    return _to_image(out), pad


def line(c, x0, y0, x1, y1, color, width=2, tags="body"):
    """An anti-aliased line with round ends."""
    dx, dy = int(round(x1 - x0)), int(round(y1 - y0))
    photo, pad = _get(("line", dx, dy, round(width, 1), color), lambda: _line_image(dx, dy, width, color))
    return c.create_image(min(x0, x0 + dx) - pad, min(y0, y0 + dy) - pad, image=photo,
                          anchor="nw", tags=tags)


def _arc_image(r: float, a0: float, a1: float, width: float, color: str, glow: float):
    half = r + width / 2 + glow + 2
    size = int(2 * half)
    dx, dy = _grid(size)
    d = np.hypot(dx, dy)
    ang = np.degrees(np.arctan2(dx, -dy))                 # 0 is up, clockwise is positive
    inside = (ang >= a0) & (ang <= a1)
    edge = np.abs(d - r) - width / 2
    band = np.clip(0.5 - edge, 0, 1) * inside
    a = band
    if glow > 0:
        a = np.maximum(a, np.clip(1 - np.maximum(edge, 0) / glow, 0, 1) ** 2.2 * 0.40 * inside)
    out = np.zeros((size, size, 4))
    out[..., :3] = rgb(color)
    out[..., 3] = a * 255
    return _to_image(out), size / 2.0


def arc(c, cx, cy, r, a0, a1, color, width=6, glow=0, tags="body"):
    """An anti-aliased arc about (cx, cy) from angle a0 to a1 degrees (0 up, clockwise positive)."""
    glow = glow if GLOW else 0
    photo, _ = _get(("arc", round(r), round(a0, 1), round(a1, 1), round(width, 1), color, round(glow)),
                    lambda: _arc_image(r, a0, a1, width, color, glow))
    return c.create_image(cx, cy, image=photo, tags=tags)


# ---- rounded rectangles (supersampled) -------------------------------------------

def _rrect_image(w: int, h: int, r: int, top: str, bottom: str, border, shadow: int,
                 gloss: float, dots: bool, alpha: float):
    pad = int(shadow * 1.6) if shadow else 0
    W, H = (w + 2 * pad) * SS, (h + 2 * pad) * SS
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    box = (pad * SS, pad * SS, (pad + w) * SS - 1, (pad + h) * SS - 1)
    if shadow:
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).rounded_rectangle(
            (box[0], box[1] + int(shadow * 0.35 * SS), box[2], box[3] + int(shadow * 0.35 * SS)),
            radius=r * SS, fill=150)
        sh = sh.filter(ImageFilter.GaussianBlur(shadow * SS * 0.5))
        black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        black.putalpha(sh)
        canvas = Image.alpha_composite(canvas, black)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=r * SS, fill=int(255 * alpha))
    grad = Image.linear_gradient("L").resize((W, H))
    fill = Image.composite(Image.new("RGBA", (W, H), rgb(bottom) + (255,)),
                           Image.new("RGBA", (W, H), rgb(top) + (255,)), grad)
    fill.putalpha(mask)
    canvas = Image.alpha_composite(canvas, fill)
    if gloss:
        g = Image.linear_gradient("L").resize((W, H)).point(lambda v: int(max(0, 255 - v * 2.2)))
        g = g.point(lambda v: int(v * gloss))
        white = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        white.putalpha(ImageChops.multiply(g, mask))
        canvas = Image.alpha_composite(canvas, white)
    if dots:
        d = ImageDraw.Draw(canvas)
        step = 22 * SS
        for yy in range(box[1] + step, box[3] - step // 2, step):
            for xx in range(box[0] + step, box[2] - step // 2, step):
                d.ellipse((xx - SS, yy - SS, xx + SS, yy + SS), fill=(255, 255, 255, 16))
    if border:
        ImageDraw.Draw(canvas).rounded_rectangle(box, radius=r * SS, outline=rgb(border) + (255,),
                                                 width=SS)
    return canvas.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS), pad


def rrect(c, x0, y0, x1, y1, r=14, top=SURFACE_TOP, bottom=SURFACE, border=LINE, shadow=0,
          gloss=0.0, dots=False, alpha=1.0, tags="body"):
    """A rounded rectangle with a vertical gradient, optional shadow, gloss and dot grid."""
    w, h = max(2, int(round(x1 - x0))), max(2, int(round(y1 - y0)))
    r = min(r, w // 2, h // 2)
    photo, pad = _get(("rr", w, h, r, top, bottom, border, shadow, gloss, dots, round(alpha, 2)),
                      lambda: _rrect_image(w, h, r, top, bottom, border, shadow, gloss, dots, alpha))
    return c.create_image(x0 - pad, y0 - pad, image=photo, anchor="nw", tags=tags)


def pill(c, x0, y0, x1, y1, color, tags="body", shadow=0, border=None):
    """A fully rounded bar in one flat colour (paddles, progress bars)."""
    h = int(round(y1 - y0))
    return rrect(c, x0, y0, x1, y1, r=h // 2, top=lighten(color, 0.10), bottom=darken(color, 0.06),
                 border=border, shadow=shadow, tags=tags)


def brick(c, x0, y0, x1, y1, color, tags="body"):
    """A flat rounded tile."""
    return rrect(c, x0, y0, x1, y1, r=4, top=lighten(color, 0.10), bottom=darken(color, 0.08),
                 border=None, tags=tags)


# ---- chips and HUD ------------------------------------------------------------------

def _chip_width(label: str, value: str) -> int:
    lw = text_width(label, 9) if label else 0
    return 14 + lw + (6 if label else 0) + text_width(value, 10, True) + 12


def chips(c, x, y, items, tags="body", height=24, gap=8, align="left"):
    """A row of stat pills: [(label, value[, color])]. Returns the far edge.

    align="right" treats `x` as the right edge and lays the row out leftwards from it.
    """
    if align == "right":
        total = sum(_chip_width(i[0], str(i[1])) for i in items) + gap * (len(items) - 1)
        x -= total
    for item in items:
        label, value = item[0], str(item[1])
        color = item[2] if len(item) > 2 else FG
        lw = text_width(label, 9) if label else 0
        w = _chip_width(label, value)
        rrect(c, x, y, x + w, y + height, r=height // 2, top=RAISED, bottom=SURFACE,
              border=LINE, tags=tags)
        tx = x + 14
        if label:
            c.create_text(tx, y + height / 2, text=label, anchor="w", fill=DIM,
                          font=font(9), tags=tags)
            tx += lw + 6
        c.create_text(tx, y + height / 2, text=value, anchor="w", fill=color,
                      font=font(10, True), tags=tags)
        x += w + gap
    return x


def background(c, w, h, tags="static"):
    """The window gradient with a faint light from the top."""
    def build():
        dx, dy = _grid(w, h)
        t = np.clip((dy + h / 2.0) / h, 0, 1)[..., None]
        top, bot = np.array(rgb("#10151b"), float), np.array(rgb(BG), float)
        col = top * (1 - t) + bot * t
        glow = np.clip(1 - np.hypot(dx / (w * 0.7), (dy + h / 2.0) / (h * 0.9)), 0, 1)[..., None] ** 2
        if GLOW:
            col = col + glow * np.array([18.0, 20.0, 34.0])
        return _to_image(np.concatenate([col, np.full((h, w, 1), 255.0)], axis=-1)), 0

    photo, _ = _get(("bg", w, h), build)
    return c.create_image(0, 0, image=photo, anchor="nw", tags=tags)


# ---- tables ------------------------------------------------------------------------

ZEBRA = "#0f141a"


def style_tables() -> None:
    """One flat, quiet look for every ttk.Treeview in the app. Call after Tk exists."""
    from tkinter import ttk
    style = ttk.Style()
    try:
        style.theme_use("clam")        # the native Windows theme ignores colours
    except tk.TclError:
        pass
    for name in ("Data.Treeview", "Disc.Treeview"):
        style.configure(name, background=SURFACE, fieldbackground=SURFACE, foreground=FG,
                        borderwidth=0, relief="flat", rowheight=22, font=mono(9),
                        bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE)
        style.configure(name + ".Heading", background=SURFACE_TOP, foreground=DIM,
                        relief="flat", borderwidth=0, font=font(8, True), padding=(4, 4),
                        bordercolor=SURFACE_TOP, lightcolor=SURFACE_TOP, darkcolor=SURFACE_TOP)
        style.map(name, background=[("selected", RAISED)], foreground=[("selected", FG)])
        style.map(name + ".Heading", background=[("active", SURFACE_TOP)])
    style.configure("Vertical.TScrollbar", background=RAISED, troughcolor=SURFACE,
                    bordercolor=SURFACE, arrowcolor=DIM, relief="flat")


def framed(parent) -> tk.Frame:
    """A 1px hairline border around whatever is packed inside."""
    return tk.Frame(parent, bg=LINE, padx=1, pady=1)


# ---- the side menu -----------------------------------------------------------------

class NavList(tk.Canvas):
    """A vertical menu of rounded rows. Replaces tk.Listbox."""

    ROW = 38

    def __init__(self, parent, items, on_pick, width=200):
        super().__init__(parent, width=width, height=self.ROW * len(items) + 8, bg=BG,
                         highlightthickness=0, takefocus=0)
        self.items, self.on_pick, self.selected, self.hover = list(items), on_pick, 0, None
        self._width = width
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.redraw()

    def _row_at(self, y):
        i = int((y - 4) // self.ROW)
        return i if 0 <= i < len(self.items) else None

    def _click(self, event):
        i = self._row_at(event.y)
        if i is not None:
            self.on_pick(i)

    def _move(self, event):
        self._set_hover(self._row_at(event.y))

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.redraw()

    def select(self, i):
        self.selected = i
        self.redraw()

    def redraw(self):
        self.delete("all")
        for i, text in enumerate(self.items):
            y = 4 + i * self.ROW
            active = i == self.selected
            if active:
                rrect(self, 0, y, self._width, y + self.ROW - 4, r=10, top=RAISED, bottom=RAISED,
                      border=None, tags="nav")
                rrect(self, 8, y + 9, 12, y + self.ROW - 13, r=2, top=ACCENT, bottom=ACCENT,
                      border=None, tags="nav")
            elif i == self.hover:
                rrect(self, 0, y, self._width, y + self.ROW - 4, r=10, top=SURFACE, bottom=SURFACE,
                      border=None, tags="nav")
            self.create_text(26, y + (self.ROW - 4) / 2, text=text, anchor="w",
                             fill=FG if active else DIM,
                             font=font(11, active), tags="nav")

