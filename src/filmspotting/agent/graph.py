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
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command as GraphCommand

from filmspotting.agent.prompts import SYSTEM_PROMPT
from filmspotting.agent.tools import TOOLS
from filmspotting.config import get_settings


def default_model() -> BaseChatModel:
    settings = get_settings()
    return ChatAnthropic(
        model=settings.model,
        max_tokens=16000,
        output_config={"effort": settings.effort},
        # If a safety classifier declines, re-run the request on a fallback model chosen by the API.
        betas=["server-side-fallback-2026-07-01"],
        model_kwargs={"fallbacks": "default"},
    )


def build_graph(model: BaseChatModel | None = None, checkpointer: BaseCheckpointSaver | None = None):
    llm = (model or default_model()).bind_tools(TOOLS)

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
