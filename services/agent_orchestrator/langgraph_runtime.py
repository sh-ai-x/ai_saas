"""Optional real LangGraph runtime with a deterministic fallback boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

try:
    from typing_extensions import TypedDict
except ImportError:  # pragma: no cover - Python 3.12 has the fallback
    from typing import TypedDict

from .graph import NODE_NAMES


NodeHandler = Callable[[dict[str, Any]], dict[str, Any]]


class LangGraphState(TypedDict, total=False):
    """Serializable state shared by the optional graph runtime.

    Product records remain in ``KernelStore``.  This state is deliberately
    small and transport-safe so a checkpoint can be inspected or resumed
    without handing LangGraph authority over tenant or lifecycle policy.
    """

    run_id: str
    tenant_id: str
    proposal: str
    mode: str
    last_node: str
    values: dict[str, Any]


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

    def invoke(self, state: Mapping[str, Any] | None, *, thread_id: str) -> Mapping[str, Any]:
        """Start a graph or continue an interrupted graph thread."""

        config = {"configurable": {"thread_id": thread_id}}
        payload = None if state is None else dict(state)
        return self.compiled.invoke(payload, config=config)

    def resume(self, *, thread_id: str, state: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        """Resume the checkpoint identified by ``thread_id``.

        Passing ``state`` is useful when an operator has explicitly amended
        an approval-bound state.  Omitting it resumes the persisted graph
        state, which is the normal interrupt/resume path.
        """

        return self.invoke(state, thread_id=thread_id)

    def snapshot(self, *, thread_id: str) -> Mapping[str, Any]:
        """Return the current graph state without changing product state."""

        snapshot = self.compiled.get_state({"configurable": {"thread_id": thread_id}})
        values = getattr(snapshot, "values", snapshot)
        if not isinstance(values, Mapping):
            raise TypeError("LangGraph checkpoint values must be a mapping")
        return dict(values)

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
    unknown_interrupts = set(interrupt_before).difference(NODE_NAMES)
    if unknown_interrupts:
        raise ValueError(f"unknown LangGraph interrupt node(s): {sorted(unknown_interrupts)}")
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    handlers = dict(handlers or {})
    graph = StateGraph(LangGraphState)

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
