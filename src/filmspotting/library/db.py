"""SQLite storage for the media library and the full-text subtitle index."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from filmspotting.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    title       TEXT NOT NULL,
    year        INTEGER,
    kind        TEXT NOT NULL,          -- movie | episode
    season      INTEGER,
    episode     INTEGER,
    duration    REAL,
    width       INTEGER,
    height      INTEGER,
    fps         REAL,
    is_hdr      INTEGER DEFAULT 0,
    interlaced  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS subtitle_tracks (
    id          INTEGER PRIMARY KEY,
    media_id    INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    language    TEXT,
    format      TEXT,                   -- srt | ass | ...
    path        TEXT,                   -- external file, or cached extraction of an embedded stream
    stream_index INTEGER                -- embedded stream index, NULL for external files
);
CREATE VIRTUAL TABLE IF NOT EXISTS subtitle_lines USING fts5(
    text,
    media_id UNINDEXED,
    track_id UNINDEXED,
    start_ms UNINDEXED,
    end_ms UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


@contextmanager
def connect(db_path: Path | None = None):
    conn = sqlite3.connect(db_path or get_settings().db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
