"""Application service for bounded proposal review requests."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import uuid4

from .artifact_store import ReviewArtifactStore
from .document_parser import fetch_html_document, fetch_local_html_document
from .requirements import extract_requirements
from .review_graph import ProposalReviewGraph


class ReviewRequestError(ValueError):
    pass


def _requirement_kind_info(value: Mapping[str, Any]) -> tuple[str, str, str]:
    raw_kind = str(value.get("kind", "")).strip().lower()
    raw_id = str(value.get("requirement_id", "")).strip().upper()
    if raw_kind in {"acceptance", "acceptance_criteria", "ac"} or raw_id.startswith("AC-"):
        return "acceptance", "AC", "Acceptance Criteria: a concrete and verifiable condition for deciding completion"
    return "requirement", "REQ", "Requirement: a functional, quality, or operational capability the system must provide or preserve"


class ProposalReviewService:
    MAX_CONTEXT_BYTES = 160_000
    MAX_EVIDENCE_BYTES = 96_000
    MAX_EVIDENCE_ITEMS = 120

    def __init__(
        self,
        store: ReviewArtifactStore,
        *,
        tracer: Any | None = None,
        graph: ProposalReviewGraph | None = None,
        local_file_host_root: str | None = None,
        local_file_mounted_root: str | None = None,
        editor_file_root: str | None = None,
    ) -> None:
        self.store = store
        self.graph = graph or ProposalReviewGraph(store, tracer=tracer)
        self.tracer = tracer or getattr(self.graph, "tracer", None)
        self.local_file_host_root = local_file_host_root
        self.local_file_mounted_root = local_file_mounted_root
        self.editor_file_root = editor_file_root

    def catalog(self) -> dict[str, Any]:
        catalog = {
            "product": "AI Change Impact Workbench",
            "modes": ["implementation", "impact"],
            "requirement_kinds": {
                "REQ": "Requirement: a functional, quality, or operational capability",
                "AC": "Acceptance Criteria: a verifiable condition for deciding completion",
            },
            "analysis": ["document_sections", "git_manifest", "symbols", "imports", "bounded_evidence"],
            "provider_budget": {"langchain_max_calls": 1, "jev_max_calls": 1},
            "no_code_execution": True,
            "document_types": ["text/html", "text/markdown", "text/plain", "application/pdf"],
        }
        tracer_status = getattr(self.tracer, "status", None)
        catalog["observability"] = tracer_status() if callable(tracer_status) else {"enabled": False, "provider": "none"}
        if self.editor_file_root:
            catalog["editor_file_root"] = self.editor_file_root
        return catalog

    def start(self, tenant_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        document = body.get("document")
        repository = body.get("repository")
        requirements = body.get("requirements", [])
        evidence = body.get("evidence", [])
        mode = str(body.get("mode", "impact")).strip().lower()
        if mode not in {"implementation", "impact"}:
            raise ReviewRequestError("mode must be implementation or impact")
        if not isinstance(document, Mapping) or not isinstance(repository, Mapping):
            raise ReviewRequestError("document and repository context are required")
        if not isinstance(requirements, list) or not isinstance(evidence, list):
            raise ReviewRequestError("requirements and evidence must be lists")
        forbidden = {"command", "shell", "build_command", "test_command", "raw_repository", "repository_bytes", "file_content"}
        if forbidden.intersection(body.keys()):
            raise ReviewRequestError("review accepts analysis context, not commands or raw repository data")
        raw_size = len(json.dumps(body, sort_keys=True, default=str).encode("utf-8"))
        known_fields = {"review_id", "tenant_id", "mode", "document", "repository", "requirements", "evidence"}
        if raw_size > self.MAX_CONTEXT_BYTES and set(body).difference(known_fields):
            raise ReviewRequestError("review context is too large")
        review_id = str(body.get("review_id") or f"review-{uuid4().hex}")
        try:
            return self.store.get(review_id, tenant_id)
        except KeyError:
            pass
        sanitized_requirements = [self._requirement(item) for item in requirements[:40]]
        sanitized_evidence = [item for item in (self._evidence(value) for value in evidence[:200]) if item is not None]
        sanitized_evidence = self._bound_evidence(sanitized_evidence)
        initial = {
            "review_id": review_id,
            "tenant_id": tenant_id,
            "mode": mode,
            "stage": "created",
            "document": {key: document.get(key) for key in ("name", "media_type", "sha256", "extraction_confidence")},
            "repository": {key: repository.get(key) for key in ("root_name", "branch", "head", "fingerprint", "unknowns")},
            "requirements": sanitized_requirements,
            "evidence": sanitized_evidence,
        }
        encoded = json.dumps(initial, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > self.MAX_CONTEXT_BYTES:
            raise ReviewRequestError("review context is too large after bounded evidence extraction")
        result = self.graph.run(initial)
        return self.store.get(review_id, tenant_id) | {"graph": {"stage": result.get("stage")}}

    def fetch_document(self, url: str) -> dict[str, Any]:
        document = (
            fetch_local_html_document(url, host_root=self.local_file_host_root, mounted_root=self.local_file_mounted_root)
            if urlsplit(url.strip()).scheme == "file"
            else fetch_html_document(url)
        )
        return {"document": document.public(), "requirements": [item.public() for item in extract_requirements(document)]}

    def detail(self, review_id: str, tenant_id: str) -> dict[str, Any]:
        return self.store.get(review_id, tenant_id)

    def resume(self, review_id: str, tenant_id: str) -> dict[str, Any]:
        self.graph.resume(review_id, tenant_id)
        return self.store.get(review_id, tenant_id)

    def decide(self, review_id: str, tenant_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        decision = body.get("decision")
        reason = body.get("reason", "")
        reviewer = body.get("reviewer", tenant_id)
        if not all(isinstance(value, str) for value in (decision, reason, reviewer)):
            raise ReviewRequestError("decision, reason, and reviewer must be strings")
        return self.store.decide(review_id, tenant_id, decision=decision, reason=reason, reviewer=reviewer)

    @staticmethod
    def _requirement(value: Any) -> dict[str, str]:
        if not isinstance(value, Mapping) or not isinstance(value.get("requirement_id"), str) or not isinstance(value.get("text"), str):
            raise ReviewRequestError("invalid requirement context")
        kind, kind_code, kind_description = _requirement_kind_info(value)
        return {"requirement_id": value["requirement_id"][:64], "text": value["text"][:500], "source": str(value.get("source", "unknown"))[:128], "kind": kind, "kind_code": kind_code, "kind_label": "Acceptance Criteria" if kind_code == "AC" else "Requirement", "kind_description": kind_description}

    @classmethod
    def _bound_evidence(cls, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        bounded: list[dict[str, Any]] = []
        total = 0
        for index, value in enumerate(values[: cls.MAX_EVIDENCE_ITEMS], start=1):
            compact = {
                **value,
                "evidence_id": f"E-{index:03d}",
                "excerpt": str(value.get("excerpt", ""))[:480],
                "rationale": str(value.get("rationale", ""))[:420],
            }
            size = len(json.dumps(compact, sort_keys=True, ensure_ascii=False).encode("utf-8"))
            if bounded and total + size > cls.MAX_EVIDENCE_BYTES:
                continue
            bounded.append(compact)
            total += size
        return bounded

    @staticmethod
    def _evidence(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, Mapping) or not isinstance(value.get("requirement_id"), str) or not isinstance(value.get("path"), str):
            raise ReviewRequestError("invalid evidence context")
        try:
            start_line = int(value.get("start_line", value.get("line", 0)))
            end_line = int(value.get("end_line", start_line))
        except (TypeError, ValueError) as exc:
            raise ReviewRequestError("invalid evidence line range") from exc
        if start_line < 1 or end_line < start_line or end_line - start_line + 1 > 3:
            raise ReviewRequestError("evidence line range must contain one to three lines")
        rationale = str(value.get("rationale", "")).strip()
        if end_line == start_line or not re.search(r"[.!?。！？]\s*$", rationale):
            return None
        return {"requirement_id": value["requirement_id"][:64], "path": value["path"][:300], "start_line": start_line, "end_line": end_line, "excerpt": str(value.get("excerpt", ""))[:720], "score": int(value.get("score", 0)), "rationale": rationale[:600]}
