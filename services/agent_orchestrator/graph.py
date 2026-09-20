"""Graph-compatible workflow state and durable checkpoint boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

NODE_NAMES = ("intake", "profile_validate", "inventory", "retrieve", "analyze", "plan", "human_approval", "patch", "test", "evaluate", "report")


@dataclass
class GraphState:
    run_id: str
    tenant_id: str
    values: dict[str, Any] = field(default_factory=dict)


class ExplicitStateGraph:
    """A small graph-compatible implementation that makes every node inspectable."""

    def __init__(self) -> None:
        self.nodes: dict[str, Callable[[GraphState], GraphState]] = {}

    def add_node(self, name: str, handler: Callable[[GraphState], GraphState]) -> None:
        if name not in NODE_NAMES:
            raise ValueError(f"unknown graph node: {name}")
        self.nodes[name] = handler

    def run(self, state: GraphState, *, start_at: str = "intake", stop_after: str | None = None) -> GraphState:
        if start_at not in NODE_NAMES:
            raise ValueError("invalid graph start node")
        for name in NODE_NAMES[NODE_NAMES.index(start_at) :]:
            if name not in self.nodes:
                raise ValueError(f"node {name} is not registered")
            state = self.nodes[name](state)
            if name == stop_after:
                break
        return state

