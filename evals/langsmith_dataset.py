"""Evaluate how well the agent turns natural language into the right tool call.

No frames are rendered, so the library doesn't need these titles. A model may look a title or quote
up first (search_library gets a stubbed hit) before acting; the action it ends on is what's scored,
and the extra lookups are reported, since each one costs a model round trip.
Each run makes one to three model calls per example and provider. With LANGSMITH_API_KEY set, results are
logged as LangSmith experiments (one per provider); without it, the eval runs locally.

    uv run python evals/langsmith_dataset.py                          # current FILMSPOTTING_PROVIDER
    uv run python evals/langsmith_dataset.py anthropic google ollama  # compare providers
"""

import os
import sys
from functools import partial

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langsmith import Client, evaluate

from filmspotting.agent.graph import tool_model
from filmspotting.agent.prompts import SYSTEM_PROMPT
from filmspotting.config import get_settings

DATASET = "filmspotting-nl-to-command"

# (request, expected tool, subset of expected arguments)
EXAMPLES = [
    ("Sácame el frame de Akira en el minuto 40:10", "render_frame",
     {"source.title": "Akira", "source.timestamp": "40:10"}),
    ("Spirited Away at 1:12:33 with Spanish subtitles, vertical for Instagram stories", "render_frame",
     {"source.title": "Spirited Away", "subtitles": "es", "aspect": "9:16"}),
    ("La escena de Breaking Bad temporada 5 episodio 14 donde dice 'I am the one who knocks'", "render_frame",
     {"source.season": 5, "source.episode": 14}),
    ("Pon lado a lado Ghost in the Shell en 00:05:00 y Matrix en 00:30:00", "compare_frames",
     {"layout": "horizontal"}),
    ("Compara en vertical Evangelion S01E01 12:00 con End of Evangelion 01:20:00", "compare_frames",
     {"layout": "vertical"}),
    ("Hazme un gif de 4 segundos de Totoro en 00:20:00 con subtítulos en inglés", "render_clip",
     {"duration": 4, "output": "gif", "subtitles": "en"}),
    ("¿En qué película se dice 'que la fuerza te acompañe'?", "search_library",
     {"target": "quotes"}),
    ("¿Tengo Perfect Blue en la biblioteca?", "search_library",
     {"target": "titles"}),
    ("Frame de Your Name a 00:50:00 en cuadrado con el texto 'te busqué' arriba", "render_frame",
     {"aspect": "1:1", "caption": "te busqué", "caption_position": "top"}),
]


def _get(args: dict, dotted: str):
    for key in dotted.split("."):
        args = args.get(key) if isinstance(args, dict) else None
    return args


MAX_LOOKUPS = 2


def _stub_search(args: dict) -> str:
    if args.get("target") == "quotes":
        hit = {"media_id": 1, "label": "Matching Movie (1999)", "timestamp": 600.0, "text": args.get("query", "")}
    else:
        hit = {"media_id": 1, "label": args.get("query", "")}
    return json.dumps({"ok": True, "message": "1 resultado(s)", "files": [], "candidates": [hit]})


def final_tool_call(inputs: dict, provider: str) -> dict:
    llm = tool_model(provider)
    messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(inputs["request"])]
    last = {"name": None, "args": {}}
    searches = 0
    while True:
        message = llm.invoke(messages)
        if not message.tool_calls:
            break  # answered in text: score the last call it made, if any
        last = message.tool_calls[0]
        if last["name"] != "search_library" or searches > MAX_LOOKUPS:
            break
        searches += 1
        # Models may search in parallel (e.g. both titles of a comparison): answer every call.
        messages += [message, *(ToolMessage(_stub_search(c["args"]), tool_call_id=c["id"])
                                for c in message.tool_calls)]
    # When the search itself is the answer, it isn't an extra lookup.
    lookups = searches - (last["name"] == "search_library")
    return {"tool": last["name"], "args": last["args"], "lookups": lookups}


def correct_tool(outputs: dict, reference_outputs: dict) -> bool:
    return outputs["tool"] == reference_outputs["tool"]


# After a lookup, the media id from the hit identifies the title (and episode) as well as the name does.
RESOLVED_BY_MEDIA_ID = {"source.title", "source.season", "source.episode"}


def correct_args(outputs: dict, reference_outputs: dict) -> float:
    expected = reference_outputs["args"]
    if not expected:
        return 1.0
    args = outputs["args"]
    hits = sum(
        str(_get(args, k)).lower() == str(v).lower()
        or (k in RESOLVED_BY_MEDIA_ID and _get(args, "source.media_id") is not None)
        for k, v in expected.items()
    )
    return hits / len(expected)


def extra_lookups(outputs: dict) -> float:
    return outputs.get("lookups", 0)


def ensure_dataset(client: Client) -> None:
    if client.has_dataset(dataset_name=DATASET):
        dataset = client.read_dataset(dataset_name=DATASET)
        existing = {e.inputs["request"] for e in client.list_examples(dataset_id=dataset.id)}
    else:
        dataset = client.create_dataset(DATASET, description="Natural language → FilmSpottingBot tool call")
        existing = set()
    new = [(r, t, a) for r, t, a in EXAMPLES if r not in existing]
    if new:
        client.create_examples(
            dataset_id=dataset.id,
            inputs=[{"request": r} for r, _, _ in new],
            outputs=[{"tool": t, "args": a} for _, t, a in new],
        )


def run_local(provider: str) -> dict[str, float]:
    """Score only the examples the model answered; API failures are counted separately."""
    scores = {"correct_tool": 0.0, "correct_args": 0.0, "extra_lookups": 0.0}
    errors = 0
    for request, tool, args in EXAMPLES:
        reference = {"tool": tool, "args": args}
        try:
            outputs = final_tool_call({"request": request}, provider)
        except Exception as exc:  # outages and quota errors say nothing about model quality
            errors += 1
            print(f"  [{provider}] error on {request!r}: {str(exc)[:200]}", file=sys.stderr)
            continue
        scores["correct_tool"] += correct_tool(outputs, reference)
        scores["correct_args"] += correct_args(outputs, reference)
        scores["extra_lookups"] += extra_lookups(outputs)
    answered = len(EXAMPLES) - errors
    return {**{k: v / answered if answered else float("nan") for k, v in scores.items()}, "errors": errors}


def run_langsmith(client: Client, provider: str) -> dict[str, float]:
    results = evaluate(
        partial(final_tool_call, provider=provider),
        data=DATASET,
        evaluators=[correct_tool, correct_args, extra_lookups],
        experiment_prefix=f"nl-to-command-{provider}",
        metadata={"provider": provider},
        max_concurrency=4,
    )
    totals: dict[str, list[float]] = {}
    for row in results:
        for r in row["evaluation_results"]["results"]:
            totals.setdefault(r.key, []).append(float(r.score or 0))
    return {k: sum(v) / len(v) for k, v in totals.items()}


def model_name(provider: str) -> str:
    settings = get_settings()
    return {"anthropic": settings.model, "google": settings.google_model,
            "ollama": settings.ollama_model}.get(provider, "?")


if __name__ == "__main__":
    providers = sys.argv[1:] or [get_settings().provider]
    client = Client() if os.getenv("LANGSMITH_API_KEY") else None
    if client:
        ensure_dataset(client)
    rows = []
    for provider in providers:
        scores = run_langsmith(client, provider) if client else run_local(provider)
        rows.append((provider, model_name(provider), scores["correct_tool"], scores["correct_args"],
                     scores["extra_lookups"], scores.get("errors", 0)))

    print(f"\n| Provider | Model | Correct tool | Correct args | Extra lookups / request | API errors |  (n={len(EXAMPLES)})")
    print("|---|---|---|---|---|---|")
    for provider, model, tool, args, lookups, errors in rows:
        print(f"| {provider} | {model} | {tool:.0%} | {args:.0%} | {lookups:.2f} | {errors} |")
