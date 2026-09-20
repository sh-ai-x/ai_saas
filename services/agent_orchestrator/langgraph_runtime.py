"""Optional real LangGraph runtime with a deterministic fallback boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .graph import NODE_NAMES


NodeHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class LangGraphRuntime:
    """Compiled LangGraph plus the checkpointer it owns.

    The product run ledger remains authoritative. LangGraph stores graph state
    for interrupt/resume and debugging; it never decides tenant access or a
    user-visible terminal state.
    """

    compiled: Any
    checkpointer: Any
    backend: str = "langgraph"

    def invoke(self, state: Mapping[str, Any], *, thread_id: str) -> Mapping[str, Any]:
        return self.compiled.invoke(dict(state), config={"configurable": {"thread_id": thread_id}})

    def checkpoint(self, state: Mapping[str, Any], *, thread_id: str, node: str) -> None:
        if node not in NODE_NAMES:
            raise ValueError(f"unknown LangGraph checkpoint node: {node}")
        self.compiled.update_state({"configurable": {"thread_id": thread_id}}, dict(state), as_node=node)


def build_langgraph_runtime(handlers: Mapping[str, NodeHandler] | None = None, *, interrupt_before: tuple[str, ...] = ("patch",)) -> LangGraphRuntime | None:
    """Compile the bounded node list with the installed LangGraph package.

    Returns ``None`` when optional dependencies are absent or explicitly
    disabled. This lets Local Lite keep its zero-dependency deterministic path.
    """

    if os.getenv("AGENT_DISABLE_LANGGRAPH", "").lower() in {"1", "true", "yes"}:
        return None
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    handlers = dict(handlers or {})
    graph = StateGraph(dict)

    def make_node(name: str) -> NodeHandler:
        handler = handlers.get(name)

        def invoke(state: dict[str, Any]) -> dict[str, Any]:
            if handler is None:
                return {**state, "last_node": name}
            result = handler(dict(state))
            if not isinstance(result, dict):
                raise TypeError(f"LangGraph node {name} must return a dict")
            return {**state, **result, "last_node": name}

        return invoke

    for name in NODE_NAMES:
        graph.add_node(name, make_node(name))
    graph.add_edge(START, NODE_NAMES[0])
    for previous, current in zip(NODE_NAMES, NODE_NAMES[1:]):
        graph.add_edge(previous, current)
    graph.add_edge(NODE_NAMES[-1], END)
    saver = MemorySaver()
    compiled = graph.compile(checkpointer=saver, interrupt_before=list(interrupt_before), name="proposal-to-verified-change")
    return LangGraphRuntime(compiled, saver)
