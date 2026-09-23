"""Checkpointable low-token proposal review graph."""

from __future__ import annotations

import os
import logging
from typing import Any, Mapping

try:
    from typing_extensions import TypedDict
except ImportError:  # pragma: no cover
    from typing import TypedDict

from agent_platform.redaction import redact
from services.observability import RedactedTraceAdapter

from .artifact_store import ReviewArtifactStore
from .jev_adapter import JEVReviewAdapter
from .workflow_adapter import LangChainReviewAdapter, _derive_assessment, normalize_review_status


logger = logging.getLogger(__name__)


class ReviewState(TypedDict, total=False):
    review_id: str
    tenant_id: str
    mode: str
    stage: str
    document: dict[str, Any]
    repository: dict[str, Any]
    requirements: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    evidence_candidates: int
    synthesis: dict[str, Any]
    jev: dict[str, Any]
    provider_calls: dict[str, int]
    report: dict[str, Any]


def _recommendation(requirements: list[dict[str, Any]], synthesis: Mapping[str, Any]) -> str:
    statuses = {normalize_review_status(item.get("status")) for item in synthesis.get("requirements", []) if isinstance(item, Mapping)}
    if not requirements:
        return "blocked"
    if statuses.intersection({"contradicted", "missing", "unknown", "partial"}):
        return "revise"
    return "ready"


class ProposalReviewGraph:
    def __init__(self, store: ReviewArtifactStore, *, tracer: RedactedTraceAdapter | None = None, synthesizer: LangChainReviewAdapter | None = None, jev: JEVReviewAdapter | None = None) -> None:
        self.store = store
        self.tracer = tracer
        self.synthesizer = synthesizer or LangChainReviewAdapter.from_env()
        self.jev = jev or JEVReviewAdapter.from_env()
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("langgraph is required for proposal review") from exc
        graph = StateGraph(ReviewState)
        graph.add_node("prepare", self._prepare)
        graph.add_node("jev", self._jev)
        graph.add_node("synthesize", self._synthesize)
        graph.add_node("finalize", self._finalize)
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "jev")
        graph.add_edge("jev", "synthesize")
        graph.add_edge("synthesize", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile(checkpointer=MemorySaver(), name="ai-change-impact-proposal-review")

    def _persist(self, state: ReviewState, *, status: str, checkpoint: str) -> None:
        payload = {key: value for key, value in state.items() if key not in {"tenant_id"}}
        self.store.put(str(state["review_id"]), str(state["tenant_id"]), payload, status=status, checkpoint={"stage": checkpoint, "state": payload})

    def _prepare(self, state: ReviewState) -> ReviewState:
        if state.get("stage") not in {None, "created"}:
            return state
        state = {**state, "stage": "prepared"}
        self._persist(state, status="running", checkpoint="prepared")
        return state

    def _synthesize(self, state: ReviewState) -> ReviewState:
        if state.get("stage") in {"synthesized", "evaluated", "complete"}:
            return state
        context = {"mode": state.get("mode", "impact"), "document": state.get("document", {}), "repository": state.get("repository", {}), "requirements": state.get("requirements", []), "evidence": state.get("evidence", [])}
        synthesis = self.synthesizer.invoke(context)
        provider_calls = {**state.get("provider_calls", {}), "langchain": 1}
        state = {**state, "stage": "synthesized", "synthesis": synthesis, "provider_calls": provider_calls}
        self._persist(state, status="running", checkpoint="synthesized")
        return state

    def _jev(self, state: ReviewState) -> ReviewState:
        if state.get("stage") in {"filtered", "evaluated", "synthesized", "complete"}:
            return state
        evidence = state.get("evidence", [])
        candidates: list[dict[str, Any]] = []
        candidate_bytes = 0
        for item in evidence:
            candidate = {
                key: item.get(key)
                for key in ("evidence_id", "requirement_id", "path", "start_line", "end_line", "excerpt", "rationale", "score")
                if key in item
            }
            candidate["excerpt"] = str(candidate.get("excerpt", ""))[:280]
            candidate["rationale"] = str(candidate.get("rationale", ""))[:280]
            size = len(str(candidate).encode("utf-8"))
            if candidates and candidate_bytes + size > 48_000:
                break
            candidates.append(candidate)
            candidate_bytes += size
        jev = self.jev.filter_context({"requirements": state.get("requirements", [])[:40], "evidence": candidates})
        selected_ids = {str(item) for item in jev.get("selected_evidence_ids", [])}
        filtered = [item for item in evidence if not selected_ids or str(item.get("evidence_id")) in selected_ids]
        provider_calls = {**state.get("provider_calls", {}), "jev": 0 if jev.get("status") == "skipped" else 1}
        jev = {**jev, "candidate_count": len(candidates), "selected_count": len(filtered), "filtered_out": max(0, len(evidence) - len(filtered))}
        state = {**state, "stage": "filtered", "evidence": filtered, "evidence_candidates": len(evidence), "jev": jev, "provider_calls": provider_calls}
        self._persist(state, status="running", checkpoint="filtered")
        return state

    def _finalize(self, state: ReviewState) -> ReviewState:
        if state.get("stage") == "complete" and state.get("report"):
            return state
        synthesis = state.get("synthesis", {})
        requirements = state.get("requirements", [])
        recommendation = _recommendation(requirements, synthesis)
        evidence_count = len(state.get("evidence", []))
        decisions = {str(item.get("requirement_id")): item for item in synthesis.get("requirements", []) if isinstance(item, Mapping)}
        report_requirements = [{**requirement, **decisions.get(str(requirement.get("requirement_id")), {})} for requirement in requirements]
        report = {
            "mode": state.get("mode", "impact"),
            "recommendation": recommendation,
            "requirements": report_requirements,
            "summary": synthesis.get("summary", ""),
            "assessment": synthesis.get("assessment") or _derive_assessment(state, report_requirements),
            "changes": synthesis.get("changes", []),
            "proposal_markdown": synthesis.get("proposal_markdown", ""),
            "evidence_count": evidence_count,
            "evidence_candidates": state.get("evidence_candidates", evidence_count),
            "requirement_count": len(requirements),
            "evidence_coverage": round(min(1.0, evidence_count / max(1, len(requirements) * 3)), 3),
            "provider_calls": {"langchain": 0, "jev": 0, **state.get("provider_calls", {})},
            "jev": state.get("jev", {}),
            "unknowns": state.get("repository", {}).get("unknowns", []),
            "no_code_execution": True,
        }
        state = {**state, "stage": "complete", "report": report}
        self._persist(state, status="complete", checkpoint="complete")
        return state

    def run(self, initial: ReviewState) -> dict[str, Any]:
        review_id = str(initial["review_id"])
        for adapter in (self.synthesizer, self.jev):
            begin_review = getattr(adapter, "begin_review", None)
            if callable(begin_review):
                begin_review()
        callbacks = self.tracer.langchain_callbacks() if self.tracer is not None else []
        trace_id = None
        if self.tracer is not None and not callbacks:
            trace_id = self.tracer.start_run("proposal.review", {"review_id": review_id, "mode": initial.get("mode", "impact"), "proposal_sha256": initial.get("document", {}).get("sha256"), "repository_fingerprint": initial.get("repository", {}).get("fingerprint")})
        config: dict[str, Any] = {
            "configurable": {"thread_id": review_id},
            "run_name": "proposal.review",
            "metadata": {
                "review_id": review_id,
                "mode": initial.get("mode", "impact"),
                "proposal_sha256": initial.get("document", {}).get("sha256"),
                "repository_fingerprint": initial.get("repository", {}).get("fingerprint"),
            },
        }
        if callbacks:
            config["callbacks"] = callbacks
        try:
            result = self._graph.invoke(dict(initial), config=config)
            if not isinstance(result, Mapping):
                raise TypeError("review graph returned invalid state")
            payload = dict(result)
            if trace_id and self.tracer is not None:
                self.tracer.finish_run(trace_id, outputs=redact(payload.get("report", {})))
            return payload
        except Exception as exc:
            logger.exception("proposal review graph failed: %s", type(exc).__name__)
            if trace_id and self.tracer is not None:
                self.tracer.finish_run(trace_id, error=f"{type(exc).__name__}: {exc}")
            raise

    def resume(self, review_id: str, tenant_id: str) -> dict[str, Any]:
        stored = self.store.get(review_id, tenant_id)
        checkpoint = stored.get("checkpoint", {}).get("state")
        if not isinstance(checkpoint, Mapping):
            raise ValueError("review checkpoint is invalid")
        return self.run(dict(checkpoint))
