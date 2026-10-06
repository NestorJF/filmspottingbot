"""HTTP API. Run with `filmspotting serve` or `uvicorn filmspotting.api.main:app`."""

import uuid
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


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ResumeRequest(BaseModel):
    answer: str


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    files: list[str]
    question: str | None = None
    options: list[str] = []


def _chat_response(reply) -> ChatResponse:
    return ChatResponse(
        thread_id=reply.thread_id, reply=reply.reply, question=reply.question, options=reply.options,
        files=[f"/outputs/{Path(f).name}" for f in reply.files],
    )


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    """Natural language request. Reuse `thread_id` for follow-ups ("ahora en vertical")."""
    from filmspotting.agent import graph

    return _chat_response(graph.chat(body.message, body.thread_id or uuid.uuid4().hex))


@app.post("/chat/{thread_id}/resume", response_model=ChatResponse)
def resume_chat(thread_id: str, body: ResumeRequest) -> ChatResponse:
    """Answer a question the agent asked (when a /chat response has `question` set)."""
    from filmspotting.agent import graph

    return _chat_response(graph.resume(body.answer, thread_id))
