"""Generates the tray/menu-bar glyph: a small sync-arrows badge next to the
"MCP" wordmark, entirely with Pillow (no bundled binary asset needed, keeps
the app tiny). Rendered as flat black shapes so macOS can use it as a
"template" image (auto-inverts for light/dark menu bars); when a sync is
actively running it's rendered in green instead (and NOT used as a template)
to give a clear, colored "working" cue.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

_HEIGHT = 44
_GLYPH_SIZE = 34
_TEXT_SIZE = 30
_PADDING = 6
_GAP = 6

_BLACK = (20, 20, 20, 255)
_GREEN = (40, 170, 90, 255)

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


@lru_cache(maxsize=4)
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_sync_glyph(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color, width: int) -> None:
    bbox = (cx - r, cy - r, cx + r, cy + r)
    # Two opposing arcs forming the classic "sync" circular-arrows glyph.
    draw.arc(bbox, start=200, end=340, fill=color, width=width)
    draw.arc(bbox, start=20, end=160, fill=color, width=width)

    def point_on_circle(deg: float) -> tuple[float, float]:
        rad = math.radians(deg)
        return (cx + r * math.cos(rad), cy + r * math.sin(rad))

    for arc_end_deg, arc_dir in ((340, -1), (160, -1)):
        tip = point_on_circle(arc_end_deg)
        tangent = arc_end_deg + 90 * arc_dir
        back = point_on_circle(arc_end_deg - 18 * arc_dir)
        left = (back[0] + 6 * math.cos(math.radians(tangent + 90)), back[1] + 6 * math.sin(math.radians(tangent + 90)))
        right = (back[0] + 6 * math.cos(math.radians(tangent - 90)), back[1] + 6 * math.sin(math.radians(tangent - 90)))
        draw.polygon([tip, left, right], fill=color)


def build_icon(active: bool = False) -> Image.Image:
    """The full menu-bar glyph: sync arrows + "MCP" wordmark side by side.
    `active=True` renders it in green while a sync pass is in progress."""
    color = _GREEN if active else _BLACK
    font = _load_font(_TEXT_SIZE)

    scratch = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    text_bbox = ImageDraw.Draw(scratch).textbbox((0, 0), "MCP", font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    width = _PADDING + _GLYPH_SIZE + _GAP + text_w + _PADDING
    img = Image.new("RGBA", (width, _HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cy = _HEIGHT // 2
    _draw_sync_glyph(draw, _PADDING + _GLYPH_SIZE // 2, cy, _GLYPH_SIZE // 2 - 3, color, width=4)

    text_x = _PADDING + _GLYPH_SIZE + _GAP - text_bbox[0]
    text_y = cy - text_h // 2 - text_bbox[1]
    draw.text((text_x, text_y), "MCP", font=font, fill=color)

    return img


def build_status_dot(color_name: str) -> Image.Image:
    """A small colored circle, used as a status indicator image (e.g. in the
    macOS popover UI). color_name: "green" | "gray" | "off"."""
    palette = {
        "green": (52, 199, 89, 255),
        "gray": (174, 174, 178, 255),
        "off": (60, 60, 60, 255),
    }
    color = palette.get(color_name, palette["gray"])
    img = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((3, 3, 17, 17), fill=color)
    return img
