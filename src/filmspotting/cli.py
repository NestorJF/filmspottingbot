"""Local command line: `filmspotting scan`, `filmspotting frame ...`, `filmspotting serve`."""

from pathlib import Path

import typer

from filmspotting.commands.executor import execute
from filmspotting.commands.parser import ParseError, parse_args
from filmspotting.commands.schemas import CommandResult

app = typer.Typer(help="FilmSpottingBot: fotogramas de películas, series y anime.", no_args_is_help=True)
PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


def print_result(result: CommandResult) -> None:
    typer.secho(result.message, fg=typer.colors.GREEN if result.ok else typer.colors.RED)
    for path in result.files:
        typer.echo(f"  → {path}")
    for c in result.candidates:
        when = f" @ {c.timestamp:.1f}s" if c.timestamp is not None else ""
        text = f"  «{c.text}»" if c.text else ""
        typer.echo(f"  #{c.media_id} {c.label}{when}{text}")


def _run(action: str, ctx: typer.Context) -> None:
    try:
        command = parse_args([action, *ctx.args])
    except ParseError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(2) from exc
    result = execute(command)
    print_result(result)
    if not result.ok:
        raise typer.Exit(1)


@app.command(context_settings=PASSTHROUGH)
def frame(ctx: typer.Context):
    """Extrae un fotograma: frame "Título@01:02:03" [--subs es] [--aspect 9:16] [--caption ...]"""
    _run("frame", ctx)


@app.command(context_settings=PASSTHROUGH)
def compare(ctx: typer.Context):
    """Compara escenas: compare "A@00:10:00" "B S01E02@frase" [--layout vertical|grid]"""
    _run("compare", ctx)


@app.command(context_settings=PASSTHROUGH)
def clip(ctx: typer.Context):
    """Exporta un GIF/MP4: clip "Título" --at 00:10:00 [--duration 3] [--mp4] [--subs es]"""
    _run("clip", ctx)


@app.command(context_settings=PASSTHROUGH)
def search(ctx: typer.Context):
    """Busca títulos o frases: search "texto" [--quotes] [--lang es]"""
    _run("search", ctx)


@app.command()
def ask(message: str = typer.Argument(..., help="Petición en lenguaje natural")):
    """Pide algo en lenguaje natural (usa Claude vía LangGraph). Conversación interactiva."""
    import uuid

    from filmspotting.agent.graph import chat, resume

    reply = chat(message, uuid.uuid4().hex)
    while True:
        for path in reply.files:
            typer.echo(f"  → {path}")
        if reply.question is None:
            typer.secho(reply.reply, fg=typer.colors.GREEN)
            return
        typer.secho(reply.question, fg=typer.colors.YELLOW)
        for i, option in enumerate(reply.options, 1):
            typer.echo(f"  {i}. {option}")
        answer = typer.prompt(">")
        if answer.isdigit() and 0 < int(answer) <= len(reply.options):
            answer = reply.options[int(answer) - 1]
        reply = resume(answer, reply.thread_id)


@app.command()
def scan(library: Path = typer.Argument(None, help="Carpeta de la biblioteca (por defecto FILMSPOTTING_LIBRARY_DIR)")):
    """Indexa la biblioteca de vídeos y sus subtítulos."""
    from filmspotting.library.scanner import scan as scan_library

    count = scan_library(library)
    typer.secho(f"{count} vídeo(s) indexados.", fg=typer.colors.GREEN)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    """Arranca la API HTTP (FastAPI)."""
    import uvicorn

    uvicorn.run("filmspotting.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
