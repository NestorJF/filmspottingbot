import os
from pathlib import Path

import pytest

from filmspotting.config import get_settings


@pytest.fixture(scope="session")
def settings(tmp_path_factory):
    root = tmp_path_factory.mktemp("filmspotting")
    os.environ["FILMSPOTTING_LIBRARY_DIR"] = str(root / "library")
    os.environ["FILMSPOTTING_DATA_DIR"] = str(root / "data")
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture(scope="session")
def library(settings) -> Path:
    """A tiny library: one 4s movie (cut at 2s) with Spanish subtitles."""
    from filmspotting.core.ffmpeg import ffmpeg

    movie_dir = settings.library_dir / "Sample Movie (2020)"
    movie_dir.mkdir(parents=True)
    video = movie_dir / "Sample.Movie.2020.1080p.mkv"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=2",
        "-f", "lavfi", "-i", "color=c=red:size=640x360:rate=24:duration=2",
        "-filter_complex", "[0][1]concat=n=2:v=1[v]", "-map", "[v]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
    )
    (movie_dir / "Sample.Movie.2020.1080p.es.srt").write_text(
        "1\n00:00:00,500 --> 00:00:01,500\nHola, ¿cómo estás?\n\n"
        "2\n00:00:02,500 --> 00:00:03,500\nEl tren llega tarde.\n",
        encoding="utf-8",
    )
    from filmspotting.library.scanner import scan

    assert scan() == 1
    return settings.library_dir
