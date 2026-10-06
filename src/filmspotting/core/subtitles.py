"""Burn subtitles or custom captions onto a still frame."""

import shutil
import tempfile
from pathlib import Path

import pysubs2
from PIL import Image, ImageDraw, ImageFont

from filmspotting.core.ffmpeg import ffmpeg, has_filter

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def render_track(image: Image.Image, subtitle_file: Path, timestamp: float) -> Image.Image:
    """Render whatever subtitle lines are on screen at ``timestamp``.

    Uses libass when available so .ass styling (anime fansubs, signs, karaoke) is preserved.
    """
    if has_filter("subtitles"):
        return _render_with_libass(image, Path(subtitle_file), timestamp)
    subs = pysubs2.load(str(subtitle_file))
    ms = timestamp * 1000
    lines = [e.plaintext for e in subs if not e.is_comment and e.start <= ms <= e.end]
    return render_text(image, "\n".join(lines)) if lines else image


def _render_with_libass(image: Image.Image, subtitle_file: Path, timestamp: float) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        # Copy to a plain filename so it needs no escaping inside the filtergraph.
        subs = tmp_dir / f"subs{subtitle_file.suffix.lower()}"
        shutil.copy(subtitle_file, subs)
        src, out = tmp_dir / "in.png", tmp_dir / "out.png"
        image.save(src)
        w, h = image.size
        ffmpeg(
            "-i", str(src),
            "-vf", f"setpts={timestamp:.3f}/TB,subtitles={subs}:original_size={w}x{h},format=rgb24",
            "-frames:v", "1", str(out),
        )
        return Image.open(out).convert("RGB")


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def render_text(
    image: Image.Image,
    text: str,
    position: str = "bottom",
    font_scale: float = 0.055,
    color: str = "white",
) -> Image.Image:
    """Draw a caption in classic subtitle style: bold text with a black outline."""
    if not text.strip():
        return image
    image = image.copy()
    draw = ImageDraw.Draw(image)
    w, h = image.size
    size = max(12, int(h * font_scale))
    font = _font(size)
    stroke = max(2, size // 12)
    lines = _wrap(draw, text, font, int(w * 0.9))
    wrapped = "\n".join(lines)
    left, top, right, bottom = draw.multiline_textbbox((0, 0), wrapped, font=font, stroke_width=stroke, align="center")
    tw, th = right - left, bottom - top
    margin = int(h * 0.05)
    y = margin if position == "top" else (h - th) // 2 if position == "center" else h - th - margin
    draw.multiline_text(
        ((w - tw) // 2 - left, y - top), wrapped, font=font, fill=color, align="center",
        stroke_width=stroke, stroke_fill="black",
    )
    return image


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines
