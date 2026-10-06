"""Aspect ratio changes, resizing and export."""

from pathlib import Path

from PIL import Image, ImageFilter

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:5": 4 / 5, "4:3": 4 / 3, "21:9": 21 / 9, "2.39:1": 2.39}
FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}


def parse_aspect(aspect: str) -> float:
    if aspect in ASPECTS:
        return ASPECTS[aspect]
    w, _, h = aspect.partition(":")
    return float(w) / float(h or 1)


def change_aspect(image: Image.Image, aspect: str, mode: str = "crop", focus: float = 0.5) -> Image.Image:
    """Fit ``image`` to ``aspect``.

    mode="crop" cuts the excess (``focus`` 0..1 picks the horizontal/vertical centre of the crop),
    mode="pad" adds black bars, mode="blur" fills the bars with a blurred, zoomed copy (reels-style).
    """
    target = parse_aspect(aspect)
    w, h = image.size
    current = w / h
    if abs(current - target) < 1e-3:
        return image

    if mode == "crop":
        if current > target:
            new_w = round(h * target)
            x = round((w - new_w) * focus)
            return image.crop((x, 0, x + new_w, h))
        new_h = round(w / target)
        y = round((h - new_h) * focus)
        return image.crop((0, y, w, y + new_h))

    canvas_size = (w, round(w / target)) if current > target else (round(h * target), h)
    if mode == "blur":
        background = _cover(image, canvas_size).filter(ImageFilter.GaussianBlur(radius=max(canvas_size) // 40))
    else:
        background = Image.new("RGB", canvas_size, "black")
    background.paste(image, ((canvas_size[0] - w) // 2, (canvas_size[1] - h) // 2))
    return background


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    scale = max(size[0] / image.width, size[1] / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    x, y = (resized.width - size[0]) // 2, (resized.height - size[1]) // 2
    return resized.crop((x, y, x + size[0], y + size[1]))


def resize(image: Image.Image, width: int | None = None, height: int | None = None) -> Image.Image:
    if not width and not height:
        return image
    if width and not height:
        height = round(image.height * width / image.width)
    elif height and not width:
        width = round(image.width * height / image.height)
    return image.resize((width, height), Image.LANCZOS)


def save(image: Image.Image, path: Path, fmt: str = "png", quality: int = 95) -> Path:
    fmt = fmt.lower()
    path = Path(path).with_suffix(f".{'jpg' if fmt == 'jpeg' else fmt}")
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {} if fmt == "png" else {"quality": quality}
    if fmt == "webp":
        options["method"] = 6
    image.convert("RGB").save(path, FORMATS[fmt], **options)
    return path
