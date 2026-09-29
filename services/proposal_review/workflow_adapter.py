"""One-call LangChain synthesis boundary for review reports."""

from __future__ import annotations

import os
import json
import re
from contextvars import ContextVar
from typing import Any, Mapping

from services.proposal_review.evidence_policy import is_valid_evidence_range
from services.review_comment_policy import comment_keys_for_status


class SynthesisBudgetError(RuntimeError):
    pass


_STATUS_ALIASES = {
    "implemented": {"implemented", "complete", "completed", "covered", "satisfied", "ready", "done", "fully_implemented", "fully_covered"},
    "modified": {"modified", "diverged", "alternative", "different_approach", "adapted", "equivalent", "equivalent_implementation", "deviates", "alternative_implementation"},
    "partial": {"partial", "partial_implement", "partially_implemented", "partial_implemented", "partial_implementation", "partially_covered", "partly_implemented", "in_progress", "revise"},
    "missing": {"missing", "not_implemented", "not_found", "absent"},
    "contradicted": {"contradicted", "conflict", "failed", "inconsistent"},
    "unknown": {"unknown", "unclear", "insufficient_evidence", "unproven"},
}


def normalize_review_status(value: Any) -> str:
    """Return the small, UI-safe status vocabulary used by every review artifact."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "unknown").strip().lower()).strip("_")
    for canonical, aliases in _STATUS_ALIASES.items():
        if normalized in aliases:
            return canonical
    return "unknown"


def normalize_completion_percent(value: Any) -> int | None:
    """Clamp a provider-supplied completion percentage to an int in [0, 100], or None if absent/invalid."""
    if value is None:
        return None
    try:
        percent = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, percent))


def reconcile_status_and_completion(status: str, completion_percent: int | None) -> tuple[str, int | None]:
    """A requirement cannot be "partial" at 100% completion — that is a fully
    met requirement by definition, so treat it as implemented instead of
    surfacing a self-contradictory "PARTIAL 100%" badge."""
    if status == "partial" and completion_percent is not None and completion_percent >= 100:
        return "implemented", 100
    return status, completion_percent


def review_status_label(value: Any) -> str:
    labels = {
        "implemented": "Implemented",
        "modified": "Modified",
        "partial": "Partial implementation",
        "missing": "Missing",
        "contradicted": "Contradicted",
        "unknown": "Unknown",
    }
    return labels[normalize_review_status(value)]


def _change_type(value: Any) -> str:
    normalized = re.sub(r"[^a-z]+", "_", str(value or "changed").strip().lower()).strip("_")
    return normalized if normalized in {"changed", "added", "deleted"} else "changed"


def _normalize_changes(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    changes: list[dict[str, str]] = []
    for item in value[:60]:
        if not isinstance(item, Mapping):
            continue
        before = str(item.get("before", "")).strip()
        after = str(item.get("after", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not before and not after:
            continue
        changes.append({"type": _change_type(item.get("type")), "before": before[:1_000], "after": after[:1_000], "reason": reason[:1_000]})
    return changes


def _normalize_requirement_comment(value: Any) -> str:
    """Keep each status explanation short enough for the review row and prompt."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if text.casefold() in {
        "no provider comment was returned.",
        "no review response was returned.",
        "no status comment",
        "no impact summary",
    }:
        return ""
    return text[:640]


def _derive_requirement_comments(status: str, comment: Any = "", impact: Any = "", risk: Any = "") -> dict[str, str]:
    """Provide honest labels when an older provider/fallback has no split comments."""
    primary = _normalize_requirement_comment(comment) or _normalize_requirement_comment(impact)
    risk_text = _normalize_requirement_comment(risk)
    if status == "implemented":
        return {
            "implemented_comment": primary or "The available evidence supports the requirement as implemented.",
            "not_implemented_comment": "",
            "changed_comment": "",
        }
    if status == "modified":
        return {
            "implemented_comment": "The current code provides the requirement's capability.",
            "not_implemented_comment": "",
            "changed_comment": primary or "The capability is implemented through a different approach than the proposal.",
        }
    if status == "partial":
        return {
            "implemented_comment": "Repository evidence confirms part of the requirement, but the exact completed conditions are not fully classified.",
            "not_implemented_comment": risk_text or primary or "The remaining conditions are not proven by the selected evidence.",
            "changed_comment": "",
        }
    if status == "missing":
        return {"implemented_comment": "", "not_implemented_comment": primary or "No matching repository evidence was found.", "changed_comment": ""}
    if status == "contradicted":
        return {"implemented_comment": "", "not_implemented_comment": primary or "The selected evidence conflicts with the requirement.", "changed_comment": _normalize_requirement_comment(impact) if impact else ""}
    return {"implemented_comment": "", "not_implemented_comment": primary or "The available evidence is insufficient to prove implementation.", "changed_comment": ""}


def _normalize_requirement_comments(value: Mapping[str, Any], status: str) -> dict[str, str]:
    comments = {
        "implemented_comment": _normalize_requirement_comment(value.get("implemented_comment")),
        "not_implemented_comment": _normalize_requirement_comment(value.get("not_implemented_comment")),
        "changed_comment": _normalize_requirement_comment(value.get("changed_comment")),
    }
    if not any(comments.values()):
        return _derive_requirement_comments(status, value.get("comment"), value.get("impact"), value.get("risk"))
    return comments


def _canonical_requirement_comment(decision: Mapping[str, Any], status: str) -> str:
    """Return one useful answer for metrics and the compact review summary.

    Providers may return the three colored UI comments without returning the
    legacy top-level ``comment`` field. A placeholder in that field must not
    hide the real, status-specific explanations.
    """
    direct = _normalize_requirement_comment(decision.get("comment")) or _normalize_requirement_comment(decision.get("impact"))
    if direct:
        return direct
    keys = comment_keys_for_status(status)
    return " ".join(
        dict.fromkeys(
            text
            for key in keys
            if (text := _normalize_requirement_comment(decision.get(key)))
        )
    )


def _derive_changes(value: Mapping[str, Any], decisions: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Create a conservative proposal diff when the provider does not return one."""
    original = {str(item.get("requirement_id")): item for item in value.get("requirements", []) if isinstance(item, Mapping)}
    changes: list[dict[str, str]] = []
    for decision in decisions:
        requirement_id = str(decision.get("requirement_id", ""))
        requirement = original.get(requirement_id)
        text = str((requirement or decision).get("text", "")).strip()
        if not text:
            continue
        status = normalize_review_status(decision.get("status"))
        impact = str(decision.get("impact", "")).strip()
        risk = str(decision.get("risk", "")).strip()
        if status == "partial":
            changes.append({"type": "changed", "before": text, "after": impact or "Only part of the implementation is evidenced; the remaining conditions must be completed.", "reason": risk or "Only part of the requirement is evidenced, so it is classified as partial implementation."})
        elif status == "modified":
            changes.append({"type": "changed", "before": text, "after": impact or "The requirement is met through a different implementation approach.", "reason": risk or "The current implementation is functionally equivalent but differs from the proposal."})
        elif status == "missing":
            changes.append({"type": "added", "before": "No additional implementation", "after": text, "reason": impact or "No evidence was found in the current code that satisfies this requirement."})
        elif status == "contradicted":
            changes.append({"type": "changed", "before": text, "after": impact or "The current implementation must be aligned with the requirement.", "reason": risk or "The current code contains evidence that conflicts with the requirement."})
    return changes[:60]


def _normalize_assessment(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {"pros": [], "cons": [], "limitations": []}
    normalized: dict[str, list[str]] = {}
    for key in ("pros", "cons", "limitations"):
        items = value.get(key, [])
        if not isinstance(items, list):
            normalized[key] = []
            continue
        seen: set[str] = set()
        clean: list[str] = []
        for item in items[:8]:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                clean.append(text[:500])
        normalized[key] = clean
    return normalized


def _derive_assessment(value: Mapping[str, Any], decisions: list[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Build bounded, evidence-based trade-offs without another model call."""
    mode = str(value.get("mode", "impact")).strip().lower()
    evidence_count = len([item for item in value.get("evidence", []) if isinstance(item, Mapping)])
    statuses = [normalize_review_status(item.get("status")) for item in decisions]
    implemented = statuses.count("implemented")
    modified = statuses.count("modified")
    partial = statuses.count("partial")
    unproven = sum(status in {"missing", "unknown", "contradicted"} for status in statuses)
    requirement_count = len(decisions)

    if mode == "implementation":
        pros = [
            f"The review compares {requirement_count} proposal requirement(s) against the selected repository snapshot.",
            f"It links {evidence_count} bounded one-to-three-line evidence range(s) to the review.",
        ]
        if implemented:
            pros.append(f"{implemented} requirement(s) are classified as implemented from visible code evidence.")
        if modified:
            pros.append(f"{modified} requirement(s) are functionally covered through a modified implementation approach.")
        if partial:
            pros.append("Partial implementation is reported separately, so incomplete work is not overstated as complete.")
        cons = []
        if unproven:
            cons.append(f"{unproven} requirement(s) remain missing, unknown, or contradicted by the available evidence.")
        if partial:
            cons.append(f"{partial} requirement(s) still have material conditions or acceptance criteria that are not fully evidenced.")
        if not cons:
            cons.append("The current evidence does not identify a material implementation gap, but the result still requires engineering review.")
    else:
        pros = [
            f"The review maps {requirement_count} proposal requirement(s) to bounded code evidence and affected implementation boundaries.",
            "It produces a read-only impact view and a copyable Markdown proposal without changing the repository.",
        ]
        if evidence_count:
            pros.append(f"{evidence_count} evidence range(s) provide concrete starting points for impact triage.")
        cons = []
        if unproven:
            cons.append(f"{unproven} requirement(s) have insufficient or conflicting evidence, which limits impact confidence.")
        if not evidence_count:
            cons.append("No justified one-to-three-line evidence was available, so the impact view is directional rather than code-specific.")
        if not cons:
            cons.append("The impact view identifies likely boundaries but does not decide whether the change should be implemented.")

    limitations = [
        "This is a static evidence review; it does not run tests, builds, deployments, or code modifications.",
        "Results cover only the selected proposal requirements and bounded repository evidence; unselected paths are not assessed.",
        "A status or impact statement is evidence-backed, not a guarantee of runtime behavior, compatibility, or production safety.",
    ]
    return {"pros": pros[:8], "cons": cons[:8], "limitations": limitations}


def _strong_evidence(value: Mapping[str, Any]) -> bool:
    try:
        start_line = int(value.get("start_line", 0))
        end_line = int(value.get("end_line", 0))
    except (TypeError, ValueError):
        return False
    rationale = str(value.get("rationale", "")).strip()
    return is_valid_evidence_range(start_line, end_line) and bool(re.search(r"[.!?。！？]\s*$", rationale))


def _evidence_markdown(evidence: list[Mapping[str, Any]]) -> str:
    lines = ["## Evidence map", "", "The proposal uses only the following one-to-three-line code ranges with an explicit selection rationale.", ""]
    strong = [item for item in evidence if _strong_evidence(item)]
    if not strong:
        lines.append("No code pointer was included because the available matches did not provide a justified one-to-three-line range.")
        return "\n".join(lines)
    for item in strong[:40]:
        lines.extend(
            [
                f"- `{item['path']}:{int(item['start_line'])}–{int(item['end_line'])}` — {str(item['rationale']).strip()}",
                "  ```text",
                f"  {str(item.get('excerpt', '')).replace(chr(10), chr(10) + '  ')}",
                "  ```",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _proposal_markdown(value: Mapping[str, Any], decisions: list[Mapping[str, Any]]) -> str:
    decision_by_id = {str(item.get("requirement_id")): item for item in decisions}
    base = "# Evidence-backed implementation proposal\n\n## Review basis\n\nThis proposal was generated from the selected proposal requirements, the LangChain review result, and bounded repository evidence."
    summary = str(value.get("summary", "")).strip()
    if summary:
        base += f"\n\n## Review summary\n\n{summary[:2_000]}"
    assessment = _normalize_assessment(value.get("assessment"))
    base += "\n\n## Pros\n" + "".join(f"\n- {item}" for item in assessment["pros"])
    base += "\n\n## Cons\n" + "".join(f"\n- {item}" for item in assessment["cons"])
    base += "\n\n## Limitations\n" + "".join(f"\n- {item}" for item in assessment["limitations"])
    base += "\n\n## Requirements and impact\n"
    for requirement in value.get("requirements", []):
        requirement_id = str(requirement.get("requirement_id", "Requirement"))
        decision = decision_by_id.get(requirement_id, {})
        base += f"\n### {requirement_id}\n\n- **Requirement:** {str(requirement.get('text', '')).strip()}\n- **Status:** {review_status_label(decision.get('status', 'unknown'))}\n- **Implemented:** {str(decision.get('implemented_comment', '')).strip() or 'N/A'}\n- **Not implemented:** {str(decision.get('not_implemented_comment', '')).strip() or 'N/A'}\n- **Changed:** {str(decision.get('changed_comment', '')).strip() or 'N/A'}\n- **Comment:** {str(decision.get('comment', decision.get('impact', 'No status comment'))).strip()}\n- **Impact:** {str(decision.get('impact', 'No impact summary')).strip()}\n- **Risk:** {str(decision.get('risk', 'Unknown')).strip()}\n"
    base += "\n## Proposed direction\n\nUse the cited implementation boundaries to refine the affected AI workflow before making a code change. Do not infer components that are not represented in the evidence."
    return f"{base.rstrip()}\n\n{_evidence_markdown([item for item in value.get('evidence', []) if isinstance(item, Mapping)])}\n"


def _fallback(value: Mapping[str, Any]) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for requirement in value.get("requirements", []):
        rid = str(requirement.get("requirement_id", "unknown"))
        evidence = [item for item in value.get("evidence", []) if item.get("requirement_id") == rid]
        status = "partial" if evidence else "missing"
        if status == "partial":
            comment = "Evidence was found, but deterministic matching cannot prove every acceptance condition."
        else:
            comment = "No matching repository evidence was found for this requirement."
        decisions.append({"requirement_id": rid, "status": status, "completion_percent": None, "comment": comment, "impact": comment, "risk": "Add an OpenAI API key for provider-backed requirement comments and completion estimates.", **_derive_requirement_comments(status, comment, comment, ""), "questions": []})
    assessment = _derive_assessment(value, decisions)
    proposal = {**value, "summary": "Deterministic review; provider synthesis was not enabled.", "assessment": assessment}
    return {"requirements": decisions, "summary": proposal["summary"], "assessment": assessment, "changes": _derive_changes(value, decisions), "proposal_markdown": _proposal_markdown(proposal, decisions)}


class LangChainReviewAdapter:
    """A hard one-invocation seam around a LangChain Runnable."""

    def __init__(self, runnable: Any | None = None) -> None:
        try:
            from langchain_core.runnables import RunnableLambda
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise RuntimeError("langchain-core is required for proposal review") from exc
        self._calls: ContextVar[int] = ContextVar("langchain_review_calls", default=0)
        self._runnable = runnable or RunnableLambda(_fallback)

    @property
    def calls(self) -> int:
        return self._calls.get()

    def begin_review(self) -> None:
        """Start an independent one-call budget for the current request context."""
        self._calls.set(0)

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> "LangChainReviewAdapter":
        values = {**os.environ, **(environment or {})}
        if values.get("AGENT_PROVIDER_MODE", "fake").strip().lower() != "langchain" or not values.get("OPENAI_API_KEY"):
            return cls()
        try:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.runnables import RunnableLambda
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("langchain-core and langchain-openai are required for provider-backed review") from exc
        schema = {
            "title": "ProposalReview",
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "requirements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "requirement_id": {"type": "string"},
                            "status": {"type": "string"},
                            "completion_percent": {"type": ["integer", "null"]},
                            "comment": {"type": "string"},
                            "implemented_comment": {"type": "string"},
                            "not_implemented_comment": {"type": "string"},
                            "changed_comment": {"type": "string"},
                            "impact": {"type": "string"},
                            "risk": {"type": "string"},
                        },
                        "required": ["requirement_id", "status", "completion_percent", "comment", "implemented_comment", "not_implemented_comment", "changed_comment", "impact", "risk"],
                        "additionalProperties": False,
                    },
                },
                "changes": {"type": "array", "items": {"type": "object"}},
                "assessment": {
                    "type": "object",
                    "properties": {
                        "pros": {"type": "array", "items": {"type": "string"}},
                        "cons": {"type": "array", "items": {"type": "string"}},
                        "limitations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["pros", "cons", "limitations"],
                    "additionalProperties": False,
                },
            },
            "required": ["summary", "requirements", "assessment"],
            "additionalProperties": False,
        }
        model = ChatOpenAI(model=values.get("OPENAI_MODEL", "gpt-4o-mini"), api_key=values["OPENAI_API_KEY"], temperature=0)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", """You review an AI engineering proposal against bounded repository evidence.
The context includes mode=implementation or mode=impact. In implementation mode, assess how much of each proposal requirement is already represented by the current code and use statuses implemented, modified, partial, missing, unknown, or contradicted. Use partial when some meaningful part of the requirement is present but at least one material condition, edge case, integration, or acceptance criterion is not evidenced. Do not use implemented when the evidence only covers a subset. Use modified when the requirement is functionally met but via a substantially different approach, library, or mechanism than the proposal describes (for example, the plan specifies OAuth but the code uses JWT; the plan names library X but the code uses library Y; or the API shape diverges). When the requirement's intent is satisfied by an equivalent capability, prefer modified over partial. In impact mode, describe the affected implementation boundaries and risks without claiming that a change was made.
For every requirement, return three separate evidence-grounded comments: implemented_comment, not_implemented_comment, and changed_comment. Each comment should be concise (about 2–3 UI lines, one or two sentences, no more than 240 characters); return an empty string when that category does not apply. For partial, explain the concrete portion evidenced and the concrete gap separately. For modified, explain what capability is present and how the implementation differs. Only return completion_percent when you can estimate it from the evidence; otherwise return null. Never invent a fixed fallback percentage. If you return 100, use status implemented or modified; partial must be strictly below 100.
Also return changes when the review requires a proposal adjustment. Each change must have type changed, added, or deleted, plus before, after, and a concrete reason. Do not invent a change when the bounded evidence does not support it. Return an assessment object with concise evidence-grounded pros, cons, and limitations for this mode. Limitations must mention the read-only, bounded nature of the review when applicable.
Return only the requested structured review. Do not invent implementation details that are not present in the evidence. Mark a requirement as missing or unknown when the evidence is insufficient. The application will generate the final Markdown proposal from your requirement decisions and validated one-to-three-line evidence ranges, so do not create new code pointers or claims. Do not claim that code, tests, or deployment were executed."""),
                ("human", "Review this bounded JSON context:\n{context}"),
            ]
        )
        context_input = RunnableLambda(lambda value: {"context": json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)})
        return cls(context_input | prompt | model.with_structured_output(schema))

    def invoke(self, context: Mapping[str, Any]) -> dict[str, Any]:
        if self.calls >= 1:
            raise SynthesisBudgetError("LangChain synthesis budget exhausted")
        self._calls.set(self.calls + 1)
        bounded = dict(context)
        bounded["requirements"] = list(context.get("requirements", []))[:40]
        bounded["evidence"] = list(context.get("evidence", []))[:200]
        result = self._runnable.invoke(bounded)
        if not isinstance(result, Mapping):
            raise ValueError("LangChain review output must be an object")
        requirements = result.get("requirements", [])
        if not isinstance(requirements, list):
            raise ValueError("LangChain review requirements must be a list")
        decisions = []
        for item in requirements[:40]:
            if not isinstance(item, Mapping):
                continue
            decision = dict(item)
            status = normalize_review_status(decision.get("status"))
            completion_percent = normalize_completion_percent(decision.get("completion_percent"))
            decision["status"], decision["completion_percent"] = reconcile_status_and_completion(status, completion_percent)
            decision.update(_normalize_requirement_comments(decision, decision["status"]))
            decision["comment"] = (_canonical_requirement_comment(decision, decision["status"]) or "No provider comment was returned.")[:1_000]
            decisions.append(decision)
        changes = _normalize_changes(result.get("changes")) or _derive_changes(bounded, decisions)
        derived_assessment = _derive_assessment(bounded, decisions)
        provided_assessment = _normalize_assessment(result.get("assessment"))
        assessment = {
            key: provided_assessment[key] or derived_assessment[key]
            for key in ("pros", "cons", "limitations")
        }
        proposal = {**bounded, "summary": str(result.get("summary", ""))[:2_000], "assessment": assessment}
        return {
            "summary": str(result.get("summary", ""))[:2_000],
            "requirements": decisions,
            "assessment": assessment,
            "changes": changes,
            "proposal_markdown": _proposal_markdown(proposal, decisions),
        }
