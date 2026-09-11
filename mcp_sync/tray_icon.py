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


_WHITE = (255, 255, 255, 255)
_OUTLINE = (0, 0, 0, 255)


def _draw_sync_glyph_outlined(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    r: int,
    fill,
    outline,
    width: int,
    outline_width: int,
    arrow_size: float = 6,
) -> None:
    """Same two-arc sync-arrows glyph as _draw_sync_glyph, but with a solid
    outline drawn behind the fill (a wider stroke/enlarged triangle in
    `outline`, then the normal-size shape in `fill` on top) so the glyph
    stays visible against any background color - light panel or dark - with
    no dependency on the desktop theme reporting itself correctly."""
    bbox = (cx - r, cy - r, cx + r, cy + r)
    outline_stroke = width + 2 * outline_width
    for start, end in ((200, 340), (20, 160)):
        draw.arc(bbox, start=start, end=end, fill=outline, width=outline_stroke)
    for start, end in ((200, 340), (20, 160)):
        draw.arc(bbox, start=start, end=end, fill=fill, width=width)

    def point_on_circle(deg: float) -> tuple[float, float]:
        rad = math.radians(deg)
        return (cx + r * math.cos(rad), cy + r * math.sin(rad))

    def arrow_points(end_deg: float, arc_dir: int):
        tangent = end_deg + 90 * arc_dir
        back = point_on_circle(end_deg - 18 * arc_dir)
        tip = point_on_circle(end_deg)
        left = (
            back[0] + arrow_size * math.cos(math.radians(tangent + 90)),
            back[1] + arrow_size * math.sin(math.radians(tangent + 90)),
        )
        right = (
            back[0] + arrow_size * math.cos(math.radians(tangent - 90)),
            back[1] + arrow_size * math.sin(math.radians(tangent - 90)),
        )
        return [tip, left, right]

    def scale_from_centroid(points, factor: float):
        ccx = sum(p[0] for p in points) / 3
        ccy = sum(p[1] for p in points) / 3
        return [(ccx + (px - ccx) * factor, ccy + (py - ccy) * factor) for px, py in points]

    outline_scale = 1 + (outline_width * 2.2) / arrow_size
    for arc_end_deg, arc_dir in ((340, -1), (160, -1)):
        base = arrow_points(arc_end_deg, arc_dir)
        draw.polygon(scale_from_centroid(base, outline_scale), fill=outline)
    for arc_end_deg, arc_dir in ((340, -1), (160, -1)):
        draw.polygon(arrow_points(arc_end_deg, arc_dir), fill=fill)


_TRAY_HEIGHT = 22  # a conventional Linux/Windows panel icon height - macOS
# doesn't use this path (see build_icon(): it hands AppKit the full-size
# wordmark plus an explicit point-height, so it's scaled correctly
# regardless of raw pixel size). AppIndicator/Windows have no such hint and
# render close to the image's own pixel size, so build_icon()'s 44px-tall
# image shows up oversized there - this stays proportional to it but at a
# panel-appropriate height.


_SUPERSAMPLE = 4  # draw this many times larger, then downscale - see below


def build_tray_icon(active: bool = False, height: int = _TRAY_HEIGHT) -> Image.Image:
    """The sync-arrows glyph + "MCP" wordmark, same layout as build_icon(),
    but filled white with a black outline instead of build_icon()'s flat
    black, and sized for a conventional panel height instead of build_icon's
    44px (see _TRAY_HEIGHT). Linux (AppIndicator/StatusNotifierItem panels)
    and Windows don't get macOS's "template image" auto-invert-for-theme
    treatment either (see build_icon()'s docstring) - a flat-color icon
    there is only ever visible against one of light/dark, invisible on the
    other (a solid black glyph blends into a dark Ubuntu top bar, only
    showing up when the panel's own hover-highlight lightens the row behind
    it). A white fill with a black border has contrast against both without
    needing the shell to cooperate on recoloring it.

    Rendered via supersampling - drawn at _SUPERSAMPLE x the target size and
    downscaled with LANCZOS - because Pillow's arc/polygon primitives don't
    antialias. Drawing a ~22px glyph (with ~1px outlines) directly gives hard
    aliased stair-steps on every curve and arrowhead; the downscale is what
    turns those into smooth edges."""
    fill = _GREEN if active else _WHITE
    target_height = height
    height = target_height * _SUPERSAMPLE
    scale = height / _HEIGHT
    glyph_size = round(_GLYPH_SIZE * scale)
    text_size = round(_TEXT_SIZE * scale)
    padding = round(_PADDING * scale)
    gap = round(_GAP * scale)
    outline_width = max(1, round(scale))
    font = _load_font(text_size)

    scratch = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    text_bbox = ImageDraw.Draw(scratch).textbbox((0, 0), "MCP", font=font, stroke_width=outline_width * 2)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    width = padding + glyph_size + gap + text_w + padding
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cy = height // 2
    _draw_sync_glyph_outlined(
        draw,
        padding + glyph_size // 2,
        cy,
        glyph_size // 2 - max(1, round(3 * scale)),
        fill,
        _OUTLINE,
        width=max(2, round(4 * scale)),
        outline_width=outline_width,
        arrow_size=max(2.5, 6 * scale),
    )

    text_x = padding + glyph_size + gap - text_bbox[0]
    text_y = cy - text_h // 2 - text_bbox[1]
    draw.text((text_x, text_y), "MCP", font=font, fill=fill, stroke_width=outline_width * 2, stroke_fill=_OUTLINE)

    target_width = max(1, round(width / _SUPERSAMPLE))
    return img.resize((target_width, target_height), Image.LANCZOS)


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


_APP_ICON_BG = (37, 99, 235, 255)  # a plain, brand-neutral blue badge


def build_app_icon(size: int = 256) -> Image.Image:
    """A standalone square app icon (rounded-square blue badge + white sync
    glyph, no "MCP" wordmark) - for surfaces that need a real app icon
    rather than a menu-bar/tray glyph: the GNOME Activities/app-grid
    launcher (see autostart.ensure_application_launcher()) and its .desktop
    entry's Icon= field. The tray glyph (build_tray_icon) is sized and
    outlined for a ~22px-tall panel; this is sized for a large, single
    launcher icon instead."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size * 0.06
    draw.rounded_rectangle((margin, margin, size - margin, size - margin), radius=size * 0.22, fill=_APP_ICON_BG)
    _draw_sync_glyph(draw, size / 2, size / 2, size * 0.27, _WHITE, width=int(size * 0.09))
    return img
