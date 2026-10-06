"""HTTP API. Run with `filmspotting serve` or `uvicorn filmspotting.api.main:app`."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from filmspotting.commands.executor import execute
from filmspotting.commands.parser import ParseError, parse
from filmspotting.commands.schemas import Command, CommandResult, SearchCommand
from filmspotting.config import get_settings

app = FastAPI(title="FilmSpottingBot", version="0.1.0")


class TextCommand(BaseModel):
    cmd: str


def _public(result: CommandResult) -> CommandResult:
    """Replace local file paths with download URLs."""
    return result.model_copy(update={"files": [f"/outputs/{Path(f).name}" for f in result.files]})


@app.post("/command", response_model=CommandResult)
def run_text_command(body: TextCommand) -> CommandResult:
    """CLI-style command, e.g. `frame "Akira@00:40:10" --subs es --aspect 9:16`."""
    try:
        command = parse(body.cmd)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _public(execute(command))


@app.post("/command/structured", response_model=CommandResult)
def run_structured_command(command: Command) -> CommandResult:
    """Same commands as JSON (the schema the AI agent produces)."""
    return _public(execute(command))


@app.get("/media/search", response_model=CommandResult)
def search(q: str, quotes: bool = False, language: str | None = None) -> CommandResult:
    return execute(SearchCommand(query=q, target="quotes" if quotes else "titles", language=language))


@app.post("/library/scan")
def scan_library() -> dict:
    from filmspotting.library.scanner import scan

    return {"indexed": scan()}


@app.get("/outputs/{name}")
def get_output(name: str) -> FileResponse:
    outputs = get_settings().outputs_dir.resolve()
    path = (outputs / name).resolve()
    if path.parent != outputs or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)
