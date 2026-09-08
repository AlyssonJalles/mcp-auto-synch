"""Badge icons shown next to each tool's name in the popover.

Real vendor logos (bundled as small PNGs under mcp_sync/assets/logos/,
sourced from https://github.com/AlyssonJalles/OmniRoute's public/providers
icon set and from thesvg.org for the couple of tools missing there) are used
when available, composited onto a plain white circular backplate for a
consistent look. Every badge is masked into a circle with a thin white ring
around the edge - the ring specifically matters for logos whose own artwork
is dark/near-black (e.g. Cline (CLI)'s charcoal ASCII-art logo), which would
otherwise visually disappear against a dark popover or page background.
Tools without a bundled logo fall back to a flat colored monogram badge
generated locally, so every tool always gets *some* icon.
"""
from __future__ import annotations

import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

_SIZE = 40
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets", "logos")

# Circular-frame rendering: masked+ringed at _SS times the target size, then
# downsampled, so the circle edge and ring are smooth instead of jagged.
_SS = 4
_RING_COLOR = (255, 255, 255, 235)

# tool name -> bundled PNG filename under assets/logos/
_LOGO_FILES = {
    "Codex": "codex.png",
    "Claude Code": "claude.png",
    "Claude Desktop": "claude.png",
    "Cursor": "cursor.png",
    "Gemini CLI": "gemini.png",
    "GitHub Copilot CLI": "github-copilot-cli.png",
    "GitHub Copilot Chat": "github-copilot.jpg",
    "Visual Studio Code": "visual-studio-code.png",
    "OpenCode": "opencode.png",
    "Windsurf": "windsurf.png",
    "Antigravity": "google.png",
    "Zed": "zed-hosted.png",
    "Continue": "continue.png",
    "Roo Code": "roocode.png",
    "Cline": "cline.png",
    "Cline (CLI)": "cline-cli.png",
    "Kilo Code": "kilo-code.png",
    "Zoo Code": "zoo-code.png",
    "Kiro": "kiro.png",
    "Trae": "trae.png",
    "Warp": "warp.png",
    "Grok": "grok.png",
    "Amp": "Amp.jpeg",
    "Amazon Q": "amazon-q.png",
    "Goose": "goose.png",
    "LM Studio": "lm-studio.jpeg",
}

# Uniform breathing room left around a logo's *actual* artwork (after
# autocropping away its own background/padding, see _autocrop_to_content)
# before the circular mask is applied, as a fraction of the badge size.
_CONTENT_MARGIN_RATIO = 0.08

# per-tool badge backplate color, for logos whose brand color should fill
# the inset margin instead of the default white. Sampled from the source art.
_BADGE_BACKGROUNDS = {
    "Amp": (23, 38, 34, 255),
    "LM Studio": (96, 88, 224, 255),
    # Landscape (245x168) ASCII-art logo: fitting it to the badge leaves bands
    # above and below, so they get the art's own charcoal instead of white.
    "Cline (CLI)": (30, 30, 30, 255),
}

# fallback monogram badges, only used if a bundled logo is missing above.
_MONOGRAM_BADGES = {
    "Codex": ((16, 163, 127), "CX"),
    "Claude Code": ((204, 120, 92), "CC"),
    "Cursor": ((30, 30, 32), "Cu"),
    "Gemini CLI": ((66, 133, 244), "Ge"),
    "GitHub Copilot CLI": ((137, 87, 229), "GH"),
    "Visual Studio Code": ((0, 122, 204), "VS"),
    "OpenCode": ((46, 204, 113), "OC"),
    "Windsurf": ((0, 194, 168), "Ws"),
    "Antigravity": ((91, 110, 245), "AG"),
    "Zed": ((245, 108, 74), "Ze"),
    "Continue": ((75, 123, 236), "Co"),
    "Claude Desktop": ((224, 135, 107), "CD"),
    "Roo Code": ((0, 150, 136), "RC"),
    "Amp": ((30, 30, 40), "Am"),
    "Amazon Q": ((35, 47, 62), "AQ"),
    "Goose": ((249, 115, 22), "Go"),
    "LM Studio": ((80, 80, 200), "LM"),
}

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


def _autocrop_to_content(img: Image.Image, threshold: int = 24) -> Image.Image:
    """Crops a logo down to its actual artwork, trimming away a uniform
    background border first - whether that's transparency (the common case
    for padded glyph PNGs) or a solid fill color (app-icon-style logos with
    their own background, e.g. a colored square/circle). Without this,
    swapping a logo file for one with more built-in padding, a different
    aspect ratio, or artwork closer to its own edge silently changes how
    large/cropped it ends up looking in the circular badge - this normalizes
    all of that to "the artwork" before any badge-specific sizing happens."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    bg_r, bg_g, bg_b, bg_a = max(set(corners), key=corners.count)

    def is_background(pixel: tuple) -> bool:
        r, g, b, a = pixel
        if bg_a == 0:
            return a == 0
        return (
            a > 0
            and abs(r - bg_r) <= threshold
            and abs(g - bg_g) <= threshold
            and abs(b - bg_b) <= threshold
        )

    # Scan a bounded grid rather than every pixel, for speed on large source art.
    step = max(1, min(w, h) // 200)
    minx, miny, maxx, maxy = w, h, 0, 0
    found = False
    for y in range(0, h, step):
        for x in range(0, w, step):
            if not is_background(px[x, y]):
                found = True
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    if not found or (maxx - minx) < 4 or (maxy - miny) < 4:
        return rgba  # nothing distinguishable from the background - leave as-is
    # The step-sized grid can land just inside the true edge; pad by one step.
    minx, miny = max(0, minx - step), max(0, miny - step)
    maxx, maxy = min(w - 1, maxx + step), min(h - 1, maxy + step)
    return rgba.crop((minx, miny, maxx + 1, maxy + 1))


def _apply_circular_frame(content: Image.Image, size: int) -> Image.Image:
    """Masks a size x size RGBA image into a circle and draws a thin white
    ring around its edge. Rendered at _SS times `size` and downsampled with
    LANCZOS so both the circle edge and the ring are smooth, not jagged."""
    hi = size * _SS
    bbox = (0, 0, hi - 1, hi - 1)
    content_hi = content.resize((hi, hi), Image.LANCZOS)
    mask_hi = Image.new("L", (hi, hi), 0)
    ImageDraw.Draw(mask_hi).ellipse(bbox, fill=255)
    badge_hi = Image.new("RGBA", (hi, hi), (0, 0, 0, 0))
    badge_hi.paste(content_hi, (0, 0), mask_hi)
    ring_width = max(1, round(hi / 24))
    ImageDraw.Draw(badge_hi).ellipse(bbox, outline=_RING_COLOR, width=ring_width)
    return badge_hi.resize((size, size), Image.LANCZOS)


def _draw_monogram(tool_name: str, size: int = _SIZE) -> Image.Image:
    color, initials = _MONOGRAM_BADGES.get(tool_name, ((120, 120, 128), tool_name[:2].upper()))
    content = Image.new("RGBA", (size, size), (*color, 255))
    draw = ImageDraw.Draw(content)

    font = _load_font(round(15 * size / _SIZE))
    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (size / 2 - tw / 2 - bbox[0], size / 2 - th / 2 - bbox[1]),
        initials,
        font=font,
        fill=(255, 255, 255, 255),
    )
    return _apply_circular_frame(content, size)


@lru_cache(maxsize=32)
def get_badge(tool_name: str, size: int = _SIZE) -> Image.Image:
    filename = _LOGO_FILES.get(tool_name)
    if filename:
        path = os.path.join(_ASSETS_DIR, filename)
        if os.path.exists(path):
            img = _autocrop_to_content(Image.open(path))
            inset = round(size * _CONTENT_MARGIN_RATIO)
            content_size = size - inset * 2
            img.thumbnail((content_size, content_size), Image.LANCZOS)
            bg_color = _BADGE_BACKGROUNDS.get(tool_name, (255, 255, 255, 255))
            fitted = Image.new("RGBA", (size, size), bg_color)
            fitted.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
            return _apply_circular_frame(fitted, size)
    return _draw_monogram(tool_name, size)


@lru_cache(maxsize=16)
def get_company_logo(filename: str, size: int = _SIZE) -> "Image.Image | None":
    """Loads a company-level badge (e.g. company_anthropic.png) for the
    accordion group headers, framed the same circular+ring way as
    `get_badge`. Returns None if not bundled."""
    if not filename:
        return None
    path = os.path.join(_ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    img = Image.open(path).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return _apply_circular_frame(img, size)
