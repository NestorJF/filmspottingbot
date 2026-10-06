"""Agent wiring tests with a scripted model (no API calls)."""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from filmspotting.agent.graph import build_graph, chat, resume


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _call(name, args, id_="call_1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id_}])


def test_chat_renders_frame_and_returns_files(library):
    model = ScriptedModel(messages=iter([
        _call("render_frame", {"source": {"title": "Sample Movie", "quote": "tren llega"}, "aspect": "9:16"}),
        AIMessage(content="Listo: Sample Movie @ 00:00:03."),
    ]))
    reply = chat("la escena del tren en vertical", "t1", graph=build_graph(model, InMemorySaver()))
    assert reply.reply == "Listo: Sample Movie @ 00:00:03."
    assert len(reply.files) == 1 and reply.files[0].endswith(".png")
    assert reply.question is None


def test_ask_user_interrupts_and_resumes(library):
    model = ScriptedModel(messages=iter([
        _call("ask_user", {"question": "¿Qué escena?", "options": ["inicio", "final"]}),
        _call("render_frame", {"source": {"title": "Sample Movie", "timestamp": "00:00:03"}}, "call_2"),
        AIMessage(content="Hecho."),
    ]))
    graph = build_graph(model, InMemorySaver())
    first = chat("un frame de Sample Movie", "t2", graph=graph)
    assert first.question == "¿Qué escena?" and first.options == ["inicio", "final"]
    assert first.files == []

    second = resume("final", "t2", graph=graph)
    assert second.question is None and second.reply == "Hecho."
    assert len(second.files) == 1


def test_tool_errors_are_reported_to_the_model(library):
    model = ScriptedModel(messages=iter([
        _call("render_frame", {"source": {"title": "Nope Film", "timestamp": "1"}}),
        AIMessage(content="No lo encontré."),
    ]))
    graph = build_graph(model, InMemorySaver())
    reply = chat("frame de Nope Film", "t3", graph=graph)
    assert reply.files == []
    state = graph.get_state({"configurable": {"thread_id": "t3"}})
    tool_msg = state.values["messages"][2]
    assert '"ok":false' in tool_msg.content and "No encontré" in tool_msg.content
