import pytest
from PIL import Image
from typer.testing import CliRunner

from filmspotting.cli import app
from filmspotting.commands.executor import execute
from filmspotting.commands.parser import ParseError, parse, parse_source
from filmspotting.commands.schemas import ClipCommand, CompareCommand, FrameCommand, SearchCommand


def test_parse_source_variants():
    assert parse_source("Spirited Away@01:12:33").model_dump(exclude_none=True) == {
        "title": "Spirited Away", "timestamp": "01:12:33",
    }
    src = parse_source("Breaking Bad S05E14@my name is")
    assert (src.title, src.season, src.episode, src.quote) == ("Breaking Bad", 5, 14, "my name is")
    assert parse_source("#7@90").media_id == 7


def test_parse_frame_with_style():
    cmd = parse('frame "Akira@00:40:10" --subs es --aspect 9:16 --mode blur --exact --format webp')
    assert isinstance(cmd, FrameCommand)
    assert cmd.source.timestamp == "00:40:10" and cmd.best is False
    assert (cmd.subtitles, cmd.aspect, cmd.aspect_mode, cmd.format) == ("es", "9:16", "blur", "webp")


def test_parse_other_actions():
    assert isinstance(parse('compare "A@1" "B@2" --layout grid --no-labels'), CompareCommand)
    clip = parse('clip Totoro --quote "hola" --mp4 --duration 4')
    assert isinstance(clip, ClipCommand) and clip.output == "mp4" and clip.source.quote == "hola"
    assert parse('search "tren" --quotes').target == "quotes"
    assert isinstance(parse("search x"), SearchCommand)


def test_parse_errors():
    with pytest.raises(ParseError):
        parse("explode now")
    with pytest.raises(ParseError):
        parse('compare "only-one@1"')


def test_execute_frame_by_quote_with_subs(library):
    result = execute(parse('frame "Sample Movie" --quote "tren llega" --subs es --aspect 1:1 --width 300'))
    assert result.ok, result.message
    with Image.open(result.files[0]) as img:
        assert img.size == (300, 300)


def test_execute_compare(library):
    result = execute(parse('compare "Sample Movie@1" "Sample Movie@3" --layout vertical'))
    assert result.ok, result.message
    with Image.open(result.files[0]) as img:
        assert img.height > img.width


def test_execute_reports_unknown_title(library):
    result = execute(parse('frame "Nonexistent Film@1"'))
    assert not result.ok and "No encontré" in result.message


def test_cli_end_to_end(library):
    result = CliRunner().invoke(app, ["frame", "Sample Movie@00:00:01", "--format", "jpg"])
    assert result.exit_code == 0, result.output
    assert ".jpg" in result.output
