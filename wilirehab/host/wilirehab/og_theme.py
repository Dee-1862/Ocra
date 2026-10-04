"""Colours for the OG screen: a dark theme and a light one.

The dark values are the ones in ui.py (the PC windows); a test keeps them equal, so the
OG and the laptop look like one product. This module does not import ui because ui needs
Tk, and the OG screen is drawn with Pillow only.

The games are drawn by the PC window in dark colours only. `light_variant` turns such a
picture into a light one for the OG: it inverts the brightness and turns the hue back, so
a dark panel becomes a light one while red stays red and blue stays blue. It is an
approximation (a bright ball becomes a dark ball), not a second palette.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageOps


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    surface: str
    surface_top: str      # the lit top edge of a panel
    raised: str           # selected rows
    line: str             # hairlines
    fg: str
    dim: str
    faint: str
    accent: str


DARK = Theme("dark", bg="#0b0e12", surface="#12171d", surface_top="#181f27", raised="#1d252e",
             line="#2a343f", fg="#e8ecf1", dim="#8b95a1", faint="#5a6572", accent="#5ba4b0")

LIGHT = Theme("light", bg="#f1f4f8", surface="#ffffff", surface_top="#ffffff", raised="#e3e9f0",
              line="#c9d2dc", fg="#14181d", dim="#56616d", faint="#8a95a1", accent="#2b7a88")

THEMES = {"dark": DARK, "light": LIGHT}


def other(name: str) -> str:
    """The theme to switch to from `name`."""
    return "light" if name == "dark" else "dark"


def rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """Colour a at t=0 fading to colour b at t=1 (same as ui.mix)."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t), round(ga + (gb - ga) * t),
                              round(ba + (bb - ba) * t))


def light_variant(img: Image.Image) -> Image.Image:
    """A light version of a dark picture: brightness inverted, hue kept."""
    inverted = ImageOps.invert(img.convert("RGB"))
    h, s, v = inverted.convert("HSV").split()
    h = h.point(lambda x: (x + 128) % 256)          # inverting a colour also turns its hue
    return Image.merge("HSV", (h, s, v)).convert("RGB")
