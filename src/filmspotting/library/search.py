"""Read-side queries over the indexed library."""

import re
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel

from filmspotting.library.db import connect


class Media(BaseModel):
    id: int
    path: str
    title: str
    year: int | None = None
    kind: str
    season: int | None = None
    episode: int | None = None
    duration: float
    width: int
    height: int
    fps: float
    is_hdr: bool
    interlaced: bool

    @property
    def label(self) -> str:
        if self.kind == "episode" and self.season is not None and self.episode is not None:
            return f"{self.title} S{self.season:02d}E{self.episode:02d}"
        return f"{self.title} ({self.year})" if self.year else self.title


class SubtitleTrack(BaseModel):
    id: int
    media_id: int
    language: str | None
    format: str
    path: str


class QuoteHit(BaseModel):
    media_id: int
    media_label: str
    text: str
    start_ms: int
    end_ms: int
    language: str | None

    @property
    def midpoint_seconds(self) -> float:
        return (self.start_ms + self.end_ms) / 2000


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def get_media(media_id: int, db_path: Path | None = None) -> Media | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
    return Media(**dict(row)) if row else None


def search_media(
    query: str,
    season: int | None = None,
    episode: int | None = None,
    limit: int = 10,
    db_path: Path | None = None,
) -> list[Media]:
    """Fuzzy title search, optionally filtered by season/episode."""
    with connect(db_path) as conn:
        rows = [Media(**dict(r)) for r in conn.execute("SELECT * FROM media")]
    wanted = _normalize(query)

    def score(media: Media) -> float:
        title = _normalize(media.title)
        if wanted and wanted in title:
            return 1.0 + len(wanted) / max(len(title), 1)
        return SequenceMatcher(None, wanted, title).ratio()

    candidates = [
        m for m in rows
        if (season is None or m.season == season) and (episode is None or m.episode == episode)
    ]
    ranked = sorted(candidates, key=score, reverse=True)
    return [m for m in ranked if score(m) >= 0.5][:limit]


def subtitle_tracks(media_id: int, db_path: Path | None = None) -> list[SubtitleTrack]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, media_id, language, format, path FROM subtitle_tracks WHERE media_id = ?",
            (media_id,),
        ).fetchall()
    return [SubtitleTrack(**dict(r)) for r in rows]


def find_track(media_id: int, language: str | None, db_path: Path | None = None) -> SubtitleTrack | None:
    tracks = subtitle_tracks(media_id, db_path)
    if not tracks:
        return None
    if language:
        lang = language.lower()
        for track in tracks:
            if track.language and track.language.lower().startswith(lang[:2]):
                return track
        return None
    return tracks[0]


def search_quote(
    text: str,
    media_id: int | None = None,
    language: str | None = None,
    limit: int = 10,
    db_path: Path | None = None,
) -> list[QuoteHit]:
    """Full-text search of subtitle lines. Words are matched as a phrase-ish AND query."""
    terms = [t for t in re.findall(r"\w+", text, flags=re.UNICODE) if len(t) > 1]
    if not terms:
        return []
    fts_query = " ".join(f'"{t}"' for t in terms)
    sql = """
        SELECT l.text, l.media_id, l.start_ms, l.end_ms, t.language, m.*
        FROM subtitle_lines l
        JOIN subtitle_tracks t ON t.id = l.track_id
        JOIN media m ON m.id = l.media_id
        WHERE subtitle_lines MATCH ?
    """
    params: list = [fts_query]
    if media_id is not None:
        sql += " AND l.media_id = ?"
        params.append(media_id)
    if language:
        sql += " AND t.language LIKE ?"
        params.append(f"{language[:2]}%")
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    hits = []
    for row in rows:
        data = dict(row)
        media = Media(**{k: data[k] for k in Media.model_fields})
        hits.append(QuoteHit(
            media_id=data["media_id"], media_label=media.label, text=data["text"],
            start_ms=int(data["start_ms"]), end_ms=int(data["end_ms"]), language=data["language"],
        ))
    return hits
