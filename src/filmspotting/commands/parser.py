"""Parse CLI-style command strings into structured commands.

Examples::

    frame "Spirited Away@01:12:33" --subs es --aspect 9:16
    frame "Breaking Bad S05E14" --quote "my name is" --exact
    compare "Akira@00:40:10" "Neon Genesis Evangelion S01E01@00:12:00" --layout vertical
    clip "Totoro" --quote "totoro" --duration 4 --mp4 --subs en
    search "evangelion"
    search "i am the one who knocks" --quotes
"""

import argparse
import functools
import re
import shlex

from pydantic import TypeAdapter

from filmspotting.commands.schemas import Command, FrameSource

EPISODE = re.compile(r"\s*\bS(\d{1,2})E(\d{1,3})\b\s*", re.IGNORECASE)
TIMESTAMP = re.compile(r"^\d+(:\d{1,2}){0,2}(\.\d+)?$")
COMMAND_ADAPTER = TypeAdapter(Command)


class ParseError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # don't sys.exit() inside the API
        raise ParseError(message)


def parse_source(spec: str) -> FrameSource:
    """``"Title [SxxEyy][@timestamp|@quote]"`` or ``"#<id>@..."`` → FrameSource."""
    target, _, moment = spec.rpartition("@") if "@" in spec else (spec, "", "")
    data: dict = {}
    if match := EPISODE.search(target):
        data["season"], data["episode"] = int(match[1]), int(match[2])
        target = EPISODE.sub(" ", target)
    target = target.strip()
    if target.startswith("#") and target[1:].isdigit():
        data["media_id"] = int(target[1:])
    elif target:
        data["title"] = target
    if moment:
        data["timestamp" if TIMESTAMP.match(moment.strip()) else "quote"] = moment.strip().strip('"')
    return FrameSource(**data)


def _style_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--subs", dest="subtitles")
    p.add_argument("--caption")
    p.add_argument("--caption-pos", dest="caption_position", choices=["bottom", "top", "center"])
    p.add_argument("--aspect")
    p.add_argument("--mode", dest="aspect_mode", choices=["crop", "pad", "blur"])
    p.add_argument("--width", type=int)
    p.add_argument("--format", choices=["png", "jpg", "webp"])


def _moment_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--at", dest="timestamp")
    p.add_argument("--quote")
    p.add_argument("--lang", dest="quote_language")
    p.add_argument("--season", type=int)
    p.add_argument("--episode", type=int)


def _build() -> argparse.ArgumentParser:
    root = _Parser(prog="", add_help=False)
    sub = root.add_subparsers(dest="action", required=True, parser_class=_Parser)
    sub.add_parser = functools.partial(sub.add_parser, add_help=False)  # never sys.exit() on --help

    frame = sub.add_parser("frame")
    frame.add_argument("source")
    frame.add_argument("--exact", action="store_true")
    _moment_args(frame)
    _style_args(frame)

    cmp = sub.add_parser("compare")
    cmp.add_argument("sources", nargs="+")
    cmp.add_argument("--layout", choices=["horizontal", "vertical", "grid"])
    cmp.add_argument("--no-labels", action="store_true")
    _style_args(cmp)

    clip = sub.add_parser("clip")
    clip.add_argument("source")
    clip.add_argument("--duration", type=float)
    clip.add_argument("--mp4", action="store_true")
    clip.add_argument("--subs", dest="subtitles")
    clip.add_argument("--width", type=int)
    _moment_args(clip)

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--quotes", action="store_true")
    search.add_argument("--lang", dest="language")
    return root


PARSER = _build()
MOMENT_KEYS = ("timestamp", "quote", "quote_language", "season", "episode")


def parse_args(argv: list[str]) -> Command:
    ns = {k: v for k, v in vars(PARSER.parse_args(argv)).items() if v is not None}
    action = ns["action"]

    if action in ("frame", "clip"):
        source = parse_source(ns.pop("source"))
        overrides = {k: ns.pop(k) for k in MOMENT_KEYS if k in ns}
        ns["source"] = source.model_copy(update=overrides)
    if action == "frame":
        ns["best"] = not ns.pop("exact")
    elif action == "compare":
        ns["sources"] = [parse_source(s) for s in ns["sources"]]
        ns["labels"] = not ns.pop("no_labels")
    elif action == "clip":
        ns["output"] = "mp4" if ns.pop("mp4") else "gif"
    elif action == "search":
        ns["target"] = "quotes" if ns.pop("quotes") else "titles"

    try:
        return COMMAND_ADAPTER.validate_python(ns)
    except Exception as exc:
        raise ParseError(str(exc)) from exc


def parse(text: str) -> Command:
    try:
        argv = shlex.split(text)
    except ValueError as exc:
        raise ParseError(str(exc)) from exc
    return parse_args(argv)
