"""LangGraph agent: natural language → tool calls → the shared command executor.

    agent ──tool calls──▶ tools ──▶ agent ──no tool calls──▶ END
                            │
                         ask_user → interrupt() (human in the loop, resumed via Command(resume=...))
"""

import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command as GraphCommand

from filmspotting.agent.prompts import SYSTEM_PROMPT
from filmspotting.agent.tools import TOOLS
from filmspotting.config import get_settings


def _gemini(model: str) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = get_settings()
    # Few retries: on an overloaded model, failing over beats burning quota on retries.
    common = {"model": model, "temperature": 0, "max_retries": 2}
    if settings.google_vertexai:
        return ChatGoogleGenerativeAI(
            **common, vertexai=True, project=settings.google_project, location=settings.google_location)
    return ChatGoogleGenerativeAI(**common, google_api_key=settings.google_api_key)


def default_model(provider: str | None = None) -> BaseChatModel:
    settings = get_settings()
    provider = provider or settings.provider
    if provider == "google":
        return _gemini(settings.google_model)
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError("Ollama support is not installed: run `uv sync --extra ollama`") from exc
        return ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0)
    if provider != "anthropic":
        raise ValueError(f"Unknown FILMSPOTTING_PROVIDER {provider!r} (use 'anthropic', 'google' or 'ollama')")
    return ChatAnthropic(
        model=settings.model,
        max_tokens=16000,
        output_config={"effort": settings.effort},
        # If a safety classifier declines, re-run the request on a fallback model chosen by the API.
        betas=["server-side-fallback-2026-07-01"],
        model_kwargs={"fallbacks": "default"},
    )


def fallback_model(provider: str | None = None) -> BaseChatModel | None:
    settings = get_settings()
    if (provider or settings.provider) == "google" and settings.google_fallback_model:
        return _gemini(settings.google_fallback_model)
    return None


def tool_model(provider: str | None = None) -> Runnable:
    """The configured model with tools bound, failing over to the fallback model on errors."""
    llm = default_model(provider).bind_tools(TOOLS)
    if fallback := fallback_model(provider):
        llm = llm.with_fallbacks([fallback.bind_tools(TOOLS)])
    return llm


def build_graph(model: BaseChatModel | None = None, checkpointer: BaseCheckpointSaver | None = None):
    llm = model.bind_tools(TOOLS) if model else tool_model()

    def agent(state: MessagesState) -> dict:
        return {"messages": [llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)


@lru_cache
def get_graph():
    conn = sqlite3.connect(get_settings().checkpoints_path, check_same_thread=False)
    return build_graph(checkpointer=SqliteSaver(conn))


@dataclass
class ChatReply:
    thread_id: str
    reply: str = ""
    files: list[str] = field(default_factory=list)
    question: str | None = None  # set when the agent is waiting for the user (interrupt)
    options: list[str] = field(default_factory=list)


def _reply(graph, thread_id: str, result: dict) -> ChatReply:
    messages = result["messages"]
    last_human = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
    turn = messages[last_human + 1:]
    files = [f for m in turn if isinstance(m, ToolMessage) and m.artifact for f in m.artifact]
    reply = ChatReply(thread_id=thread_id, files=files)
    if interrupts := result.get("__interrupt__"):
        payload = interrupts[0].value
        reply.question, reply.options = payload["question"], payload.get("options", [])
    elif turn and isinstance(turn[-1], AIMessage):
        reply.reply = turn[-1].text
    return reply


def chat(message: str, thread_id: str, graph=None) -> ChatReply:
    graph = graph or get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({"messages": [HumanMessage(message)]}, config)
    return _reply(graph, thread_id, result)


def resume(answer: str, thread_id: str, graph=None) -> ChatReply:
    graph = graph or get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(GraphCommand(resume=answer), config)
    return _reply(graph, thread_id, result)
