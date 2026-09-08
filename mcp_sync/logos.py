"""Badge icons shown next to each tool's name in the popover.

Real vendor logos (bundled as small PNGs under mcp_sync/assets/logos/,
sourced from https://github.com/AlyssonJalles/OmniRoute's public/providers
icon set and from thesvg.org for the couple of tools missing there) are used
when available, composited onto a plain white circular backplate for a
consistent look. Tools without a bundled logo fall back to a flat colored
monogram badge generated locally, so every tool always gets *some* icon.
"""
from __future__ import annotations

import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

_SIZE = 40
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets", "logos")

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
    "Kiro": "kiro.png",
    "Trae": "trae.png",
    "Warp": "warp.png",
    "Grok": "grok.png",
    "Amp": "Amp.jpeg",
    "Amazon Q": "amazon-q.png",
    "Goose": "goose.png",
    "LM Studio": "lm-studio.jpeg",
}

# logos whose source artwork reaches the image edge (solid-background app
# icons rather than padded transparent glyphs) get a bigger inset so they
# sit visibly inside the circular badge instead of touching/clipping at it.
_WIDE_INSET_FILES = {"amp.jpeg", "amazon-q.png", "goose.png", "lm-studio.jpeg"}

# per-tool badge backplate color, for logos whose brand color should fill
# the inset margin instead of the default white. Sampled from the source art.
_BADGE_BACKGROUNDS = {
    "Amp": (23, 38, 34, 255),
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


def _draw_monogram(tool_name: str) -> Image.Image:
    color, initials = _MONOGRAM_BADGES.get(tool_name, ((120, 120, 128), tool_name[:2].upper()))
    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, _SIZE - 1, _SIZE - 1), fill=(*color, 255))

    font = _load_font(15)
    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (_SIZE / 2 - tw / 2 - bbox[0], _SIZE / 2 - th / 2 - bbox[1]),
        initials,
        font=font,
        fill=(255, 255, 255, 255),
    )
    return img


@lru_cache(maxsize=32)
def get_badge(tool_name: str) -> Image.Image:
    filename = _LOGO_FILES.get(tool_name)
    if filename:
        path = os.path.join(_ASSETS_DIR, filename)
        if os.path.exists(path):
            img = Image.open(path).convert("RGBA")
            # Keep a small inset so logos whose artwork reaches the source
            # edge are not clipped by the circular UI mask.
            if filename.startswith("github-copilot"):
                inset = 4
            elif filename.lower() in _WIDE_INSET_FILES:
                inset = 6
            else:
                inset = 0
            content_size = _SIZE - inset * 2
            img.thumbnail((content_size, content_size), Image.LANCZOS)
            bg_color = _BADGE_BACKGROUNDS.get(tool_name, (255, 255, 255, 255))
            fitted = Image.new("RGBA", (_SIZE, _SIZE), bg_color)
            fitted.paste(img, ((_SIZE - img.width) // 2, (_SIZE - img.height) // 2), img)
            mask = Image.new("L", (_SIZE, _SIZE), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, _SIZE - 1, _SIZE - 1), fill=255)
            badge = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
            badge.paste(fitted, (0, 0), mask)
            return badge
    return _draw_monogram(tool_name)


@lru_cache(maxsize=16)
def get_company_logo(filename: str) -> "Image.Image | None":
    """Loads a company-level badge (e.g. company_anthropic.png) for the
    accordion group headers. Returns None if not bundled."""
    if not filename:
        return None
    path = os.path.join(_ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    img = Image.open(path).convert("RGBA")
    if img.size != (_SIZE, _SIZE):
        img = img.resize((_SIZE, _SIZE), Image.LANCZOS)
    return img
