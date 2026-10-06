"""Structured commands shared by the CLI parser, the HTTP API and the LLM agent."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class FrameSource(BaseModel):
    """Which moment of which title. Give a timestamp or a quote (a line of dialogue) to locate it."""

    title: str | None = Field(None, description="Movie/series title as the user wrote it")
    media_id: int | None = Field(None, description="Exact library id, if already known")
    season: int | None = None
    episode: int | None = None
    timestamp: str | None = Field(None, description="Position as HH:MM:SS(.mmm), MM:SS or seconds")
    quote: str | None = Field(None, description="Dialogue to search in the subtitles to find the moment")
    quote_language: str | None = Field(None, description="Language of the quote, e.g. 'es', 'en', 'ja'")


class Style(BaseModel):
    subtitles: str | None = Field(None, description="Burn the subtitle track in this language ('es', 'en'…) or 'auto'")
    caption: str | None = Field(None, description="Custom text drawn on the image instead of/in addition to subtitles")
    caption_position: Literal["bottom", "top", "center"] = "bottom"
    aspect: str | None = Field(None, description="Target aspect ratio: '16:9', '9:16', '1:1', '4:5', '21:9'…")
    aspect_mode: Literal["crop", "pad", "blur"] = "crop"
    width: int | None = Field(None, ge=64, le=7680, description="Output width in pixels")
    format: Literal["png", "jpg", "webp"] = "png"


class FrameCommand(Style):
    """Extract a single high-quality still."""

    action: Literal["frame"] = "frame"
    source: FrameSource
    best: bool = Field(True, description="Pick the sharpest nearby frame of the same shot; False = exact frame")


class CompareCommand(Style):
    """Put several stills side by side (split / parallel between scenes, movies or versions)."""

    action: Literal["compare"] = "compare"
    sources: list[FrameSource] = Field(min_length=2, max_length=9)
    layout: Literal["horizontal", "vertical", "grid"] = "horizontal"
    labels: bool = Field(True, description="Write each title in the corner of its panel")


class ClipCommand(BaseModel):
    """Export a short animated GIF or MP4 clip."""

    action: Literal["clip"] = "clip"
    source: FrameSource
    duration: float = Field(3.0, gt=0, le=30)
    output: Literal["gif", "mp4"] = "gif"
    subtitles: str | None = None
    width: int = Field(480, ge=64, le=1920)


class SearchCommand(BaseModel):
    """Look up titles in the library or lines of dialogue in the subtitles."""

    action: Literal["search"] = "search"
    query: str
    target: Literal["titles", "quotes"] = "titles"
    language: str | None = None


Command = Annotated[FrameCommand | CompareCommand | ClipCommand | SearchCommand, Field(discriminator="action")]


class Candidate(BaseModel):
    media_id: int
    label: str
    timestamp: float | None = None
    text: str | None = None


class CommandResult(BaseModel):
    ok: bool = True
    message: str
    files: list[str] = []
    candidates: list[Candidate] = []
