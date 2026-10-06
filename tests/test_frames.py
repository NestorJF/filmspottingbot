import numpy as np

from filmspotting.core.frames import extract_frame, parse_timestamp
from filmspotting.library.search import search_media


def test_parse_timestamp():
    assert parse_timestamp("01:02:03.5") == 3723.5
    assert parse_timestamp("1:30") == 90
    assert parse_timestamp(12) == 12.0


def test_extract_exact_frame(library):
    [media] = search_media("sample")
    frame = extract_frame(media.path, 3.0, best=False)
    assert frame.image.size == (640, 360)
    r, g, b = np.asarray(frame.image).reshape(-1, 3).mean(axis=0)
    assert r > 200 and g < 40 and b < 40  # second shot is solid red


def test_best_frame_stays_in_same_shot(library):
    [media] = search_media("sample")
    # Window crosses the cut at 2s; the chosen frame must stay in the first shot.
    frame = extract_frame(media.path, 1.95, window=0.25)
    assert frame.timestamp < 2.0
    r, g, b = np.asarray(frame.image).reshape(-1, 3).mean(axis=0)
    assert not (r > 200 and g < 40)
