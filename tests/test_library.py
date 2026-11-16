import pytest

from filmspotting.library.languages import normalize_language
from filmspotting.library.search import find_track, search_media, search_quote, subtitle_tracks


def test_search_media_by_fuzzy_title(library):
    [media] = search_media("sample movie")
    assert media.title == "Sample Movie"
    assert media.year == 2020
    assert media.width == 640 and round(media.duration) == 4


def test_quote_search_is_accent_insensitive(library):
    [hit] = search_quote("como estas")
    assert hit.text == "Hola, ¿cómo estás?"
    assert hit.language == "es"
    assert 0.9 < hit.midpoint_seconds < 1.1


def test_subtitle_tracks(library):
    [media] = search_media("sample")
    [track] = subtitle_tracks(media.id)
    assert track.language == "es" and track.format == "srt"


@pytest.mark.parametrize(
    ("code", "expected"),
    [("es", "es"), ("spa", "es"), ("es-ES", "es"), ("Spanish", "es"), ("ger", "de"), ("dut", "nl"),
     ("und", None), (None, None), ("xx", "xx")],
)
def test_normalize_language(code, expected):
    assert normalize_language(code) == expected


@pytest.mark.parametrize("code", ["es", "spa", "es-ES", "spanish"])
def test_language_codes_match_in_any_form(library, code):
    """Matroska tags embedded subtitles with ISO 639-2 codes ("spa"); users type "es"."""
    [media] = search_media("sample")
    assert find_track(media.id, code) is not None
    assert search_quote("como estas", language=code)
    assert find_track(media.id, "en") is None
