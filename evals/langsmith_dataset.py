"""Evaluate how well the agent turns natural language into the right tool call.

Only the first model step runs (no frames are rendered), so the library doesn't need these titles.
Requires ANTHROPIC_API_KEY and LANGSMITH_API_KEY. Each run makes one Claude call per example.

    uv run python evals/langsmith_dataset.py            # create/update dataset and evaluate
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import Client, evaluate

from filmspotting.agent.graph import default_model
from filmspotting.agent.prompts import SYSTEM_PROMPT
from filmspotting.agent.tools import TOOLS

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


def first_tool_call(inputs: dict) -> dict:
    llm = default_model().bind_tools(TOOLS)
    message = llm.invoke([SystemMessage(SYSTEM_PROMPT), HumanMessage(inputs["request"])])
    call = message.tool_calls[0] if message.tool_calls else {"name": None, "args": {}}
    return {"tool": call["name"], "args": call["args"]}


def correct_tool(outputs: dict, reference_outputs: dict) -> bool:
    return outputs["tool"] == reference_outputs["tool"]


def correct_args(outputs: dict, reference_outputs: dict) -> float:
    expected = reference_outputs["args"]
    if not expected:
        return 1.0
    hits = sum(str(_get(outputs["args"], k)).lower() == str(v).lower() for k, v in expected.items())
    return hits / len(expected)


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


if __name__ == "__main__":
    client = Client()
    ensure_dataset(client)
    evaluate(
        first_tool_call,
        data=DATASET,
        evaluators=[correct_tool, correct_args],
        experiment_prefix="nl-to-command",
        max_concurrency=4,
    )
