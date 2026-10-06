from pathlib import Path

from PIL import Image

from filmspotting.core import compose, formats, subtitles
from filmspotting.core.frames import extract_frame
from filmspotting.library.search import find_track, search_media


def _blank(w=640, h=360, color="gray"):
    return Image.new("RGB", (w, h), color)


def test_change_aspect_modes():
    img = _blank()
    assert formats.change_aspect(img, "9:16", "crop").size == (202, 360)
    assert formats.change_aspect(img, "1:1", "pad").size == (640, 640)
    assert formats.change_aspect(img, "9:16", "blur").size == (640, 1138)


def test_render_text_changes_pixels():
    img = _blank()
    out = subtitles.render_text(img, "Hola mundo")
    assert out.size == img.size and out.tobytes() != img.tobytes()


def test_render_track_only_when_line_on_screen(library):
    [media] = search_media("sample")
    track = find_track(media.id, "es")
    frame = extract_frame(Path(media.path), 1.0, best=False).image
    with_line = subtitles.render_track(frame, Path(track.path), 1.0)
    assert with_line.tobytes() != frame.tobytes()
    gap = extract_frame(Path(media.path), 2.2, best=False).image
    assert subtitles.render_track(gap, Path(track.path), 2.2).tobytes() == gap.tobytes()


def test_stack_layouts():
    a, b = _blank(640, 360), _blank(320, 240, "red")
    assert compose.stack([a, b], "horizontal", gap=0).size == (427 + 320, 240)
    assert compose.stack([a, b], "vertical", gap=0).size == (320, 180 + 240)
    assert compose.stack([a, b, a, b], "grid", gap=0).size[1] == 480


def test_make_gif(library, tmp_path):
    [media] = search_media("sample")
    track = find_track(media.id, "es")
    out = compose.make_clip(Path(media.path), 0.5, 1.5, tmp_path / "clip.gif", subtitle_file=Path(track.path))
    with Image.open(out) as gif:
        assert gif.n_frames >= 10
