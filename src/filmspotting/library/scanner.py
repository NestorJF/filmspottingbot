"""Scan a folder of movies/series, probe them and index their subtitles."""

import logging
import re
import sqlite3
from pathlib import Path

import pysubs2
from guessit import guessit

from filmspotting.config import get_settings
from filmspotting.core.ffmpeg import FFmpegError, ffmpeg, probe
from filmspotting.library.db import connect

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".ts", ".m2ts"}
SUB_EXTS = {".srt", ".ass", ".ssa", ".vtt"}
TEXT_SUB_CODECS = {"subrip": "srt", "ass": "ass", "ssa": "ass", "mov_text": "srt", "webvtt": "vtt"}
ASS_TAGS = re.compile(r"\{[^}]*\}")


def scan(library_dir: Path | None = None, db_path: Path | None = None) -> int:
    """Index every video under ``library_dir``. Returns the number of videos indexed."""
    library_dir = Path(library_dir or get_settings().library_dir)
    count = 0
    with connect(db_path) as conn:
        for video in sorted(p for p in library_dir.rglob("*") if p.suffix.lower() in VIDEO_EXTS):
            try:
                _index_video(conn, video)
                count += 1
            except FFmpegError as exc:
                log.warning("Skipping %s: %s", video, exc)
    return count


def _index_video(conn: sqlite3.Connection, video: Path) -> None:
    info = probe(video)
    guess = guessit(video.name)
    kind = "episode" if guess.get("type") == "episode" else "movie"
    episode = guess.get("episode")
    if isinstance(episode, list):
        episode = episode[0]

    old = conn.execute("SELECT id FROM media WHERE path = ?", (str(video),)).fetchone()
    if old:
        conn.execute("DELETE FROM subtitle_lines WHERE media_id = ?", (old["id"],))
        conn.execute("DELETE FROM media WHERE id = ?", (old["id"],))
    media_id = conn.execute(
        """INSERT INTO media (path, title, year, kind, season, episode, duration,
                              width, height, fps, is_hdr, interlaced)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(video), str(guess.get("title", video.stem)), guess.get("year"), kind,
            guess.get("season"), episode, info.duration, info.width, info.height,
            info.fps, info.is_hdr, info.is_interlaced,
        ),
    ).lastrowid

    for sub_path, language in _external_subtitles(video):
        _index_track(conn, media_id, sub_path, language, stream_index=None)

    cache_dir = get_settings().data_dir / "subs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for stream in info.subtitle_streams:
        ext = TEXT_SUB_CODECS.get(stream["codec"])
        if ext is None:  # bitmap subs (PGS/VobSub) can't be indexed as text
            continue
        out = cache_dir / f"{media_id}_{stream['index']}.{ext}"
        try:
            ffmpeg("-i", str(video), "-map", f"0:{stream['index']}", str(out))
        except FFmpegError as exc:
            log.warning("Could not extract subtitle stream %s of %s: %s", stream["index"], video, exc)
            continue
        _index_track(conn, media_id, out, stream["language"], stream_index=stream["index"])


def _external_subtitles(video: Path):
    """Yield ``(path, language)`` for sidecar files like ``Movie.es.srt`` or ``Movie.srt``."""
    for candidate in video.parent.iterdir():
        if candidate.suffix.lower() not in SUB_EXTS or not candidate.name.startswith(video.stem):
            continue
        middle = candidate.name[len(video.stem):-len(candidate.suffix)].strip(".")
        language = middle.split(".")[0] if middle else None
        yield candidate, language


def _index_track(conn, media_id: int, path: Path, language: str | None, stream_index: int | None):
    try:
        subs = pysubs2.load(str(path))
    except Exception as exc:  # pysubs2 raises a variety of format errors
        log.warning("Could not parse %s: %s", path, exc)
        return
    track_id = conn.execute(
        "INSERT INTO subtitle_tracks (media_id, language, format, path, stream_index) VALUES (?, ?, ?, ?, ?)",
        (media_id, language, path.suffix.lstrip(".").lower(), str(path), stream_index),
    ).lastrowid
    rows = [
        (clean_text(event.text), media_id, track_id, event.start, event.end)
        for event in subs
        if not event.is_comment and event.text.strip()
    ]
    conn.executemany(
        "INSERT INTO subtitle_lines (text, media_id, track_id, start_ms, end_ms) VALUES (?, ?, ?, ?, ?)",
        rows,
    )


def clean_text(text: str) -> str:
    return ASS_TAGS.sub("", text).replace(r"\N", " ").replace(r"\n", " ").strip()
