"""Combine frames: side-by-side comparisons, grids, and short clips/GIFs."""

import math
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from filmspotting.core.ffmpeg import ffmpeg, has_filter
from filmspotting.core.subtitles import _font


def stack(
    images: list[Image.Image],
    layout: str = "horizontal",
    labels: list[str] | None = None,
    gap: int = 8,
    background: str = "black",
) -> Image.Image:
    """Place images side by side ("horizontal"), on top of each other ("vertical") or in a "grid".

    Images are scaled to a common height (horizontal/grid) or width (vertical) so they line up.
    """
    if not images:
        raise ValueError("Nothing to compose")
    if labels:
        images = [_label(img, text) for img, text in zip(images, labels, strict=False)] + images[len(labels):]

    if layout == "vertical":
        width = min(img.width for img in images)
        images = [img.resize((width, round(img.height * width / img.width)), Image.LANCZOS) for img in images]
        canvas = Image.new("RGB", (width, sum(i.height for i in images) + gap * (len(images) - 1)), background)
        y = 0
        for img in images:
            canvas.paste(img, (0, y))
            y += img.height + gap
        return canvas

    height = min(img.height for img in images)
    images = [img.resize((round(img.width * height / img.height), height), Image.LANCZOS) for img in images]
    if layout == "grid":
        cols = math.ceil(math.sqrt(len(images)))
        rows = math.ceil(len(images) / cols)
        cell_w = max(img.width for img in images)
        canvas = Image.new("RGB", (cols * cell_w + gap * (cols - 1), rows * height + gap * (rows - 1)), background)
        for i, img in enumerate(images):
            r, c = divmod(i, cols)
            canvas.paste(img, (c * (cell_w + gap) + (cell_w - img.width) // 2, r * (height + gap)))
        return canvas

    canvas = Image.new("RGB", (sum(i.width for i in images) + gap * (len(images) - 1), height), background)
    x = 0
    for img in images:
        canvas.paste(img, (x, 0))
        x += img.width + gap
    return canvas


def _label(image: Image.Image, text: str) -> Image.Image:
    image = image.copy()
    draw = ImageDraw.Draw(image)
    size = max(12, image.height // 22)
    font = _font(size)
    pad = size // 2
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.rectangle((0, 0, right - left + 2 * pad, bottom - top + 2 * pad), fill=(0, 0, 0))
    draw.text((pad - left, pad - top), text, font=font, fill="white")
    return image


def make_clip(
    video: Path,
    start: float,
    end: float,
    output: Path,
    width: int = 480,
    fps: int = 12,
    subtitle_file: Path | None = None,
) -> Path:
    """Export ``start``..``end`` as an optimised GIF (palette-based) or MP4, depending on ``output``'s suffix."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        filters = ["setsar=1"]
        if subtitle_file and has_filter("subtitles"):
            subs = Path(tmp) / f"subs{Path(subtitle_file).suffix.lower()}"
            shutil.copy(subtitle_file, subs)
            # Seeking resets timestamps to 0; shift them back so subtitle timing lines up.
            filters += [f"setpts=PTS+{start:.3f}/TB", f"subtitles={subs}", "setpts=PTS-STARTPTS"]
        filters.append(f"scale={width}:-2:flags=lanczos")
        seek = ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(video)]
        if output.suffix.lower() == ".gif":
            filters.append(f"fps={fps},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a")
            ffmpeg(*seek, "-vf", ",".join(filters), "-loop", "0", str(output))
        else:
            ffmpeg(*seek, "-vf", ",".join(filters), "-c:v", "libx264", "-crf", "18",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(output))
    return output
