from filmspotting.library.search import search_media, search_quote, subtitle_tracks


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
