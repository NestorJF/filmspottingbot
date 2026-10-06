"""Thin wrappers around the ffmpeg/ffprobe binaries."""

import json
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from filmspotting.config import get_settings

HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


class FFmpegError(RuntimeError):
    pass


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float
    pix_fmt: str
    color_transfer: str | None
    color_primaries: str | None
    color_space: str | None
    sample_aspect_ratio: str | None
    field_order: str | None
    subtitle_streams: list[dict]

    @property
    def is_hdr(self) -> bool:
        return self.color_transfer in HDR_TRANSFERS

    @property
    def is_interlaced(self) -> bool:
        return self.field_order not in (None, "progressive", "unknown")


@lru_cache
def has_filter(name: str) -> bool:
    out = run([get_settings().ffmpeg, "-hide_banner", "-filters"]).decode()
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


def run(args: list[str]) -> bytes:
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.decode(errors="replace")[-2000:])
    return proc.stdout


def ffmpeg(*args: str) -> bytes:
    return run([get_settings().ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args])


def probe(path: Path) -> VideoInfo:
    out = run([
        get_settings().ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    data = json.loads(out)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise FFmpegError(f"No video stream in {path}")
    num, _, den = video.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    duration = float(data["format"].get("duration") or video.get("duration") or 0)
    subs = [
        {
            "index": s["index"],
            "codec": s.get("codec_name"),
            "language": s.get("tags", {}).get("language"),
            "title": s.get("tags", {}).get("title"),
        }
        for s in data["streams"]
        if s["codec_type"] == "subtitle"
    ]
    return VideoInfo(
        duration=duration,
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        pix_fmt=video.get("pix_fmt", ""),
        color_transfer=video.get("color_transfer"),
        color_primaries=video.get("color_primaries"),
        color_space=video.get("color_space"),
        sample_aspect_ratio=video.get("sample_aspect_ratio"),
        field_order=video.get("field_order"),
        subtitle_streams=subs,
    )
