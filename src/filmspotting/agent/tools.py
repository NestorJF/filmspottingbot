"""LangChain tools: thin wrappers over the same executor the CLI uses."""

from typing import Literal

from langchain_core.tools import StructuredTool, tool
from langgraph.types import interrupt
from pydantic import create_model

from filmspotting.commands.executor import execute
from filmspotting.commands.schemas import ClipCommand, CommandResult, CompareCommand, FrameCommand, SearchCommand


def _report(result: CommandResult) -> tuple[str, list[str]]:
    """Tool content for the model + the produced files as an artifact (not shown to the model)."""
    return result.model_dump_json(exclude={"files"}, exclude_defaults=True), result.files


@tool(response_format="content_and_artifact")
def search_library(
    query: str,
    target: Literal["titles", "quotes"] = "titles",
    language: str | None = None,
) -> tuple[str, list[str]]:
    """Search the local library. target="titles" finds movies/series by name;
    target="quotes" finds lines of dialogue in the subtitles (returns the media id and timestamp)."""
    return _report(execute(SearchCommand(query=query, target=target, language=language)))


def _command_tool(model, name: str, description: str) -> StructuredTool:
    # The tool name already picks the command, so hide the `action` discriminator from the model:
    # small models tend to fill it with made-up values that fail validation.
    fields = {n: (f.annotation, f) for n, f in model.model_fields.items() if n != "action"}
    args_schema = create_model(f"{model.__name__}Args", __doc__=model.__doc__, **fields)

    def run(**kwargs) -> tuple[str, list[str]]:
        return _report(execute(model(**kwargs)))

    return StructuredTool.from_function(
        func=run, name=name, description=description, args_schema=args_schema,
        response_format="content_and_artifact",
    )


render_frame = _command_tool(
    FrameCommand, "render_frame",
    "Extract one high-quality still from a movie/episode, optionally with subtitles, a caption, "
    "a new aspect ratio and size. Locate the moment by timestamp or by a quote from the dialogue.",
)
compare_frames = _command_tool(
    CompareCommand, "compare_frames",
    "Build a side-by-side / stacked / grid comparison of 2-9 moments, from the same or different titles.",
)
render_clip = _command_tool(
    ClipCommand, "render_clip",
    "Export a short GIF or MP4 clip starting at a moment (or centred on a quote).",
)


@tool
def ask_user(question: str, options: list[str] | None = None) -> str:
    """Ask the user to choose or clarify (ambiguous title, several matching quotes, missing info).
    Execution pauses until the user answers; the answer is returned."""
    return str(interrupt({"question": question, "options": options or []}))


TOOLS = [search_library, render_frame, compare_frames, render_clip, ask_user]
