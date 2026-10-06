"""Execute structured commands against the library. No AI involved."""

import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from filmspotting.commands.schemas import (
    Candidate,
    ClipCommand,
    Command,
    CommandResult,
    CompareCommand,
    FrameCommand,
    FrameSource,
    SearchCommand,
    Style,
)
from filmspotting.config import get_settings
from filmspotting.core import compose, formats, subtitles
from filmspotting.core.frames import extract_frame, parse_timestamp
from filmspotting.library.search import Media, find_track, get_media, search_media, search_quote


class ResolutionError(Exception):
    """The request can't be resolved to a single moment; ``candidates`` lists the options."""

    def __init__(self, message: str, candidates: list[Candidate] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


@dataclass
class Moment:
    media: Media
    timestamp: float


def resolve(source: FrameSource) -> Moment:
    media = _resolve_media(source)
    if source.timestamp is not None:
        if media is None:
            raise ResolutionError("Indica qué película o serie quieres (título o id).")
        return Moment(media, parse_timestamp(source.timestamp))
    if source.quote:
        hits = search_quote(source.quote, media.id if media else None, source.quote_language)
        if not hits:
            raise ResolutionError(f"No encontré la frase «{source.quote}» en los subtítulos.")
        best = hits[0]
        if media is None and len({h.media_id for h in hits}) > 1:
            raise ResolutionError(
                f"La frase «{source.quote}» aparece en varios títulos.",
                [Candidate(media_id=h.media_id, label=h.media_label, timestamp=h.midpoint_seconds, text=h.text)
                 for h in hits],
            )
        return Moment(media or get_media(best.media_id), best.midpoint_seconds)
    raise ResolutionError("Indica un momento: un timestamp o una frase de diálogo.")


def _resolve_media(source: FrameSource) -> Media | None:
    if source.media_id is not None:
        media = get_media(source.media_id)
        if media is None:
            raise ResolutionError(f"No existe el id {source.media_id} en la biblioteca.")
        return media
    if not source.title:
        return None
    matches = search_media(source.title, source.season, source.episode)
    if not matches:
        raise ResolutionError(f"No encontré «{source.title}» en la biblioteca.")
    exact = [m for m in matches if m.title.lower() == source.title.lower()]
    if len(matches) > 1 and len(exact) != 1:
        raise ResolutionError(
            f"«{source.title}» coincide con varios títulos.",
            [Candidate(media_id=m.id, label=m.label) for m in matches],
        )
    return exact[0] if exact else matches[0]


def _still(moment: Moment, best: bool, subtitle_lang: str | None) -> Image.Image:
    frame = extract_frame(Path(moment.media.path), moment.timestamp, best=best)
    if subtitle_lang:
        track = find_track(moment.media.id, None if subtitle_lang == "auto" else subtitle_lang)
        if track is None:
            raise ResolutionError(f"{moment.media.label} no tiene subtítulos en «{subtitle_lang}».")
        return subtitles.render_track(frame.image, Path(track.path), frame.timestamp)
    return frame.image


def _finish(image: Image.Image, style: Style) -> Path:
    if style.caption:
        image = subtitles.render_text(image, style.caption, style.caption_position)
    if style.aspect:
        image = formats.change_aspect(image, style.aspect, style.aspect_mode)
    image = formats.resize(image, style.width)
    return formats.save(image, _output_path(), style.format)


def _output_path(suffix: str = "") -> Path:
    return get_settings().outputs_dir / f"{uuid.uuid4().hex[:12]}{suffix}"


def _fmt_time(seconds: float) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def execute(command: Command) -> CommandResult:
    try:
        match command:
            case FrameCommand():
                moment = resolve(command.source)
                path = _finish(_still(moment, command.best, command.subtitles), command)
                return CommandResult(
                    message=f"{moment.media.label} @ {_fmt_time(moment.timestamp)}", files=[str(path)]
                )
            case CompareCommand():
                moments = [resolve(s) for s in command.sources]
                images = [_still(m, True, command.subtitles) for m in moments]
                labels = [m.media.label for m in moments] if command.labels else None
                if command.aspect:  # apply the aspect per panel so the panels match
                    images = [formats.change_aspect(i, command.aspect, command.aspect_mode) for i in images]
                combined = compose.stack(images, command.layout, labels)
                path = _finish(combined, command.model_copy(update={"aspect": None}))
                return CommandResult(
                    message=" | ".join(f"{m.media.label} @ {_fmt_time(m.timestamp)}" for m in moments),
                    files=[str(path)],
                )
            case ClipCommand():
                moment = resolve(command.source)
                track = find_track(moment.media.id, None if command.subtitles == "auto" else command.subtitles) \
                    if command.subtitles else None
                start = max(moment.timestamp - command.duration / 2, 0) if command.source.quote else moment.timestamp
                path = compose.make_clip(
                    Path(moment.media.path), start, start + command.duration,
                    _output_path(f".{command.output}"), width=command.width,
                    subtitle_file=Path(track.path) if track else None,
                )
                return CommandResult(message=f"{moment.media.label} @ {_fmt_time(start)}", files=[str(path)])
            case SearchCommand():
                return _search(command)
    except ResolutionError as exc:
        return CommandResult(ok=False, message=str(exc), candidates=exc.candidates)
    raise TypeError(f"Unknown command {command!r}")


def _search(command: SearchCommand) -> CommandResult:
    if command.target == "quotes":
        hits = search_quote(command.query, language=command.language)
        candidates = [
            Candidate(media_id=h.media_id, label=h.media_label, timestamp=h.midpoint_seconds, text=h.text)
            for h in hits
        ]
    else:
        candidates = [Candidate(media_id=m.id, label=m.label) for m in search_media(command.query)]
    message = f"{len(candidates)} resultado(s)" if candidates else "Sin resultados"
    return CommandResult(ok=bool(candidates), message=message, candidates=candidates)
