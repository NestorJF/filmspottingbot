"""Artifact-free frame extraction."""

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from filmspotting.core import quality
from filmspotting.core.ffmpeg import VideoInfo, ffmpeg, has_filter, probe

# Linearise PQ/HLG, tonemap to SDR and convert to BT.709 (requires the zimg-based zscale filter).
HDR_TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)


@dataclass
class Frame:
    image: Image.Image
    timestamp: float  # seconds into the source video


def filter_chain(info: VideoInfo) -> str:
    filters = []
    if info.is_interlaced:
        filters.append("bwdif=mode=send_frame")
    if info.is_hdr and has_filter("zscale"):
        filters.append(HDR_TONEMAP)
    # Untagged sources: guess the matrix from resolution instead of ffmpeg's BT.601 default,
    # which shifts colours on HD content.
    matrix = "auto" if info.color_space else ("bt709" if info.height >= 720 else "bt601")
    # Square the pixels (anamorphic DVDs) and convert to RGB with full chroma precision
    # to avoid chroma bleeding and banding.
    filters.append(
        "scale=w='trunc(iw*sar/2)*2':h=ih"
        f":in_color_matrix={matrix}:out_range=full"
        ":flags=lanczos+accurate_rnd+full_chroma_int"
    )
    filters.append("setsar=1,format=rgb24")
    return ",".join(filters)


def extract_frame(
    video: Path,
    timestamp: float,
    best: bool = True,
    window: float = 0.25,
    info: VideoInfo | None = None,
) -> Frame:
    """Extract the frame at ``timestamp``.

    With ``best=True`` we decode every frame within ±``window`` seconds and keep the sharpest
    one from the same shot, which avoids motion blur, fades and mid-cut frames.
    """
    info = info or probe(video)
    timestamp = min(max(timestamp, 0.0), max(info.duration - 0.05, 0.0))
    start = max(timestamp - window, 0.0) if best else timestamp
    count = max(1, round((timestamp - start + window) * (info.fps or 24))) if best else 1

    with tempfile.TemporaryDirectory() as tmp:
        ffmpeg(
            "-ss", f"{start:.3f}", "-i", str(video),
            "-vf", filter_chain(info),
            "-frames:v", str(count), "-fps_mode", "passthrough",
            str(Path(tmp) / "%04d.png"),
        )
        paths = sorted(Path(tmp).glob("*.png"))
        frames = [np.asarray(Image.open(p).convert("RGB")) for p in paths]

    if not frames:
        raise ValueError(f"No frames decoded at {timestamp:.2f}s of {video}")
    fps = info.fps or 24
    target = min(round((timestamp - start) * fps), len(frames) - 1)
    chosen = quality.best_frame_index(frames, target) if best else target
    return Frame(image=Image.fromarray(frames[chosen]), timestamp=start + chosen / fps)


def parse_timestamp(value: str | float | int) -> float:
    """Accept seconds or ``[HH:]MM:SS[.mmm]``."""
    if isinstance(value, (int, float)):
        return float(value)
    parts = [float(p) for p in value.strip().split(":")]
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds
