from __future__ import annotations

import subprocess
import json
import sys
import threading
from types import SimpleNamespace
import urllib.request
from pathlib import Path

import pytest

from services.proposal_review.artifact_store import ReviewArtifactStore
from services.proposal_review.document_parser import fetch_html_document, fetch_local_html_document, parse_document
from services.proposal_review.evidence_retriever import retrieve_evidence
from services.proposal_review.jev_adapter import JEVReviewAdapter
from services.proposal_review.requirements import extract_requirements
from services.proposal_review.review_graph import ProposalReviewGraph
from services.proposal_review.service import ProposalReviewService, ReviewRequestError
from services.proposal_review.workflow_adapter import LangChainReviewAdapter, SynthesisBudgetError, _fallback
from services.observability import LangSmithClientAdapter
from services.agent_orchestrator import FakeStructuredModel
from services.repository_context.code_analyzer import analyze_manifest
from services.repository_context.git_manifest import build_manifest
from services.control_api.http import ControlApiConfig, build_runtime, create_server


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_manifest_uses_git_excludes_and_never_executes_source(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitignore").write_text("ignored.py\nnode_modules/\n")
    (tmp_path / "main.py").write_text("def answer():\n    return 'model trace cost'\n")
    (tmp_path / "ignored.py").write_text("def ignored(): pass\n")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=secret\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("class Dep: pass\n")
    (tmp_path / ".claude" / "worktrees" / "stale").mkdir(parents=True)
    (tmp_path / ".claude" / "worktrees" / "stale" / "copy.py").write_text("def stale(): pass\n")
    _git(tmp_path, "add", ".", "-f", "ignored.py")
    _git(tmp_path, "commit", "-qm", "fixture")
    manifest = build_manifest(tmp_path)
    paths = {item.path for item in manifest.files}
    assert "main.py" in paths
    assert "ignored.py" in paths  # tracked files remain visible to Git.
    assert ".env" not in paths
    assert "node_modules/dep.js" not in paths
    assert not any(path.startswith(".claude/worktrees/") for path in paths)
    context = analyze_manifest(manifest)
    assert any(item["name"] == "answer" for item in context.symbols)
    assert all("os.system" not in str(item) for item in context.public().values())


def test_document_and_top_k_evidence_are_deterministic() -> None:
    document = parse_document("proposal.html", b"<h1>Acceptance</h1><p>- The model must preserve trace cost.</p>")
    requirements = extract_requirements(document)
    assert requirements[0].source == "html"
    assert requirements[0].kind == "acceptance"
    assert requirements[0].requirement_id == "AC-001"
    assert requirements[0].public()["kind_code"] == "AC"
    assert "verifiable condition" in requirements[0].public()["kind_description"]
    assert document.sha256


def test_markdown_and_plain_text_proposals_are_supported() -> None:
    markdown = parse_document("proposal.md", b"# Acceptance\n\nThe model must preserve trace cost.")
    plain_text = parse_document("proposal.txt", b"The provider should preserve the trace.")

    assert markdown.media_type == "text/markdown"
    assert markdown.sections[0].title == "Acceptance"
    assert plain_text.media_type == "text/plain"
    assert plain_text.sections[0].text.startswith("The provider")


def test_remote_html_url_is_bounded_and_returns_only_parsed_document() -> None:
    class Headers:
        def get(self, name: str, default: str = "") -> str:
            return "text/html; charset=utf-8" if name == "Content-Type" else default

    class Response:
        headers = Headers()

        def geturl(self) -> str:
            return "https://example.com/proposal"

        def read(self, limit: int) -> bytes:
            assert limit == 12 * 1024 * 1024 + 1
            return b"<h1>Acceptance</h1><p>The model must preserve trace cost.</p>"

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    document = fetch_html_document(
        "https://example.com/proposal",
        opener=lambda _request, timeout: Response(),
    )
    assert document.media_type == "text/html"
    assert document.sections[0].source == "html"
    assert not hasattr(document, "data")


def test_remote_html_url_rejects_private_hosts() -> None:
    with pytest.raises(ValueError, match="public"):
        fetch_html_document("http://localhost:3019/proposal.html")


def test_file_url_reads_html_from_the_configured_repository_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    proposal = root / "docs" / "proposal.html"
    proposal.parent.mkdir()
    proposal.write_text("<h1>Acceptance</h1><p>The trace must be visible.</p>")

    document = fetch_local_html_document(f"file://{proposal}", host_root=root)

    assert document.name == "proposal.html"
    assert document.media_type == "text/html"
    assert document.sections[0].title == "Acceptance"


def test_file_url_translates_a_host_path_to_the_container_mount(tmp_path: Path) -> None:
    host_root = tmp_path / "host-repo"
    mount_root = tmp_path / "mounted-repo"
    host_root.mkdir()
    (mount_root / "docs").mkdir(parents=True)
    proposal = mount_root / "docs" / "proposal.html"
    proposal.write_text("<h1>Plan</h1><p>The model must preserve cost.</p>")

    document = fetch_local_html_document(
        f"file://{host_root / 'docs' / 'proposal.html'}",
        host_root=host_root,
        mounted_root=mount_root,
    )

    assert document.name == "proposal.html"


def test_langchain_synthesis_has_one_call_budget() -> None:
    adapter = LangChainReviewAdapter()
    context = {"requirements": [{"requirement_id": "REQ-001", "text": "model trace"}], "evidence": []}
    assert adapter.invoke(context)["requirements"][0]["status"] == "missing"
    with pytest.raises(SynthesisBudgetError):
        adapter.invoke(context)


def test_partial_implementation_is_normalized_and_exposed_as_a_change() -> None:
    class Provider:
        def invoke(self, _context: dict) -> dict:
            return {
                "summary": "The requirement is only partly represented.",
                "requirements": [{"requirement_id": "REQ-001", "status": "partially implemented", "impact": "The trace path exists but the cost metadata is not connected.", "risk": "The remaining cost integration is not evidenced."}],
            }

    result = LangChainReviewAdapter(Provider()).invoke(
        {
            "requirements": [{"requirement_id": "REQ-001", "text": "The workflow must preserve trace cost metadata."}],
            "evidence": [],
        }
    )

    assert result["requirements"][0]["status"] == "partial"
    assert result["requirements"][0]["completion_percent"] is None
    assert result["requirements"][0]["comment"]
    assert result["requirements"][0]["implemented_comment"]
    assert result["requirements"][0]["not_implemented_comment"]
    assert result["requirements"][0]["changed_comment"] == ""
    assert result["changes"][0]["type"] == "changed"
    assert "Partial implementation" in result["proposal_markdown"]


def test_provider_requirement_details_are_kept_as_three_separate_comments() -> None:
    class Provider:
        def invoke(self, _context: dict) -> dict:
            return {
                "summary": "test",
                "requirements": [{
                    "requirement_id": "REQ-001",
                    "status": "partial",
                    "completion_percent": 60,
                    "comment": "summary",
                    "implemented_comment": "Trace span creation is present.",
                    "not_implemented_comment": "Cost attributes are still missing.",
                    "changed_comment": "The adapter uses a local span wrapper instead of the proposal SDK.",
                    "impact": "impact",
                    "risk": "risk",
                }],
            }

    decision = LangChainReviewAdapter(Provider()).invoke({"requirements": [], "evidence": []})["requirements"][0]
    assert decision["completion_percent"] == 60
    assert decision["implemented_comment"] == "Trace span creation is present."
    assert decision["not_implemented_comment"] == "Cost attributes are still missing."
    assert decision["changed_comment"].startswith("The adapter uses")


def test_placeholder_provider_comment_is_replaced_by_status_summary() -> None:
    class Provider:
        def invoke(self, _context: dict) -> dict:
            return {
                "summary": "test",
                "requirements": [{
                    "requirement_id": "REQ-001",
                    "status": "partial",
                    "comment": "No provider comment was returned.",
                    "implemented_comment": "The trace span is present.",
                    "not_implemented_comment": "Cost metadata is still missing.",
                }],
            }

    decision = LangChainReviewAdapter(Provider()).invoke({"requirements": [], "evidence": []})["requirements"][0]
    assert decision["comment"] == "The trace span is present. Cost metadata is still missing."


def test_partial_at_100_percent_completion_is_reclassified_as_implemented() -> None:
    """A requirement cannot be "partial" at 100% completion — that combination
    is self-contradictory. If the provider reports it anyway (a
    misclassification, or a borderline case it couldn't fully resolve to
    "implemented"), the adapter must correct the status rather than surface
    a "PARTIAL 100%" badge."""

    class Provider:
        def invoke(self, _context: dict) -> dict:
            return {
                "summary": "test",
                "requirements": [
                    {"requirement_id": "REQ-001", "status": "partial", "completion_percent": 100, "impact": "Fully covered but reported as partial.", "risk": "none"},
                    {"requirement_id": "REQ-002", "status": "partial", "completion_percent": 60, "impact": "Auth is present; refresh-token rotation is not.", "risk": "medium"},
                ],
            }

    result = LangChainReviewAdapter(Provider()).invoke({"requirements": [], "evidence": []})
    by_id = {item["requirement_id"]: item for item in result["requirements"]}

    assert by_id["REQ-001"]["status"] == "implemented"
    assert by_id["REQ-001"]["completion_percent"] == 100
    assert by_id["REQ-002"]["status"] == "partial"
    assert by_id["REQ-002"]["completion_percent"] == 60


def test_completion_percent_is_clamped_to_zero_to_one_hundred() -> None:
    class Provider:
        def invoke(self, _context: dict) -> dict:
            return {
                "summary": "test",
                "requirements": [
                    {"requirement_id": "REQ-001", "status": "missing", "completion_percent": 150, "impact": "x", "risk": "y"},
                    {"requirement_id": "REQ-002", "status": "partial", "completion_percent": -10, "impact": "x", "risk": "y"},
                ],
            }

    result = LangChainReviewAdapter(Provider()).invoke({"requirements": [], "evidence": []})
    by_id = {item["requirement_id"]: item for item in result["requirements"]}
    assert by_id["REQ-001"]["completion_percent"] == 100
    assert by_id["REQ-002"]["completion_percent"] == 0


def test_each_workbench_mode_includes_pros_cons_and_limitations() -> None:
    context = {
        "requirements": [{"requirement_id": "REQ-001", "text": "The workflow must preserve trace metadata."}],
        "evidence": [{
            "requirement_id": "REQ-001",
            "path": "src/workflow.py",
            "start_line": 10,
            "end_line": 12,
            "excerpt": "10: trace = build_trace()\n11: return trace\n12: # metadata pending",
            "rationale": "This range shows the trace construction and return path connected to the requirement.",
        }],
    }

    for mode in ("implementation", "impact"):
        result = _fallback({**context, "mode": mode})
        assessment = result["assessment"]
        assert set(assessment) == {"pros", "cons", "limitations"}
        assert all(isinstance(assessment[key], list) and assessment[key] for key in assessment)
        assert "## Pros" in result["proposal_markdown"]
        assert "## Cons" in result["proposal_markdown"]
        assert "## Limitations" in result["proposal_markdown"]


def test_proposal_is_markdown_and_only_cites_justified_ranges() -> None:
    value = {
        "requirements": [{"requirement_id": "REQ-001", "text": "the model must preserve trace"}],
        "evidence": [
            {
                "requirement_id": "REQ-001",
                "path": "src/model.py",
                "start_line": 12,
                "end_line": 14,
                "excerpt": "12: model = build_model()\n13: trace(model)\n14: return model",
                "rationale": "The range contains the model construction and trace call, so it identifies the implementation boundary for the requirement.",
            },
            {"requirement_id": "REQ-001", "path": "src/unrelated.py", "line": 2, "excerpt": "trace", "reason": "match"},
        ],
    }

    proposal = _fallback(value)["proposal_markdown"]

    assert proposal.startswith("# Evidence-backed implementation proposal")
    assert "`src/model.py:12–14`" in proposal
    assert "`src/unrelated.py" not in proposal
    assert "explicit selection rationale" in proposal


def test_service_accepts_one_to_three_line_evidence_with_rationale() -> None:
    assert ProposalReviewService._evidence(
        {
            "requirement_id": "REQ-001",
            "path": "src/model.py",
            "start_line": 2,
            "end_line": 4,
            "excerpt": "model flow",
            "rationale": "This range shows the model flow connected to the requirement.",
        }
    ) == {
        "requirement_id": "REQ-001",
        "path": "src/model.py",
        "start_line": 2,
        "end_line": 4,
        "excerpt": "model flow",
        "score": 0,
        "rationale": "This range shows the model flow connected to the requirement.",
    }
    assert ProposalReviewService._evidence(
        {
            "requirement_id": "REQ-001",
            "path": "src/model.py",
            "start_line": 2,
            "end_line": 2,
            "excerpt": "return model",
            "rationale": "This line returns the model required by the acceptance criterion.",
        }
    ) == {
        "requirement_id": "REQ-001",
        "path": "src/model.py",
        "start_line": 2,
        "end_line": 2,
        "excerpt": "return model",
        "score": 0,
        "rationale": "This line returns the model required by the acceptance criterion.",
    }
    assert ProposalReviewService._evidence(
        {"requirement_id": "REQ-001", "path": "src/model.py", "line": 2, "reason": "match"}
    ) is None
    with pytest.raises(ReviewRequestError, match="one to three lines"):
        ProposalReviewService._evidence(
            {
                "requirement_id": "REQ-001",
                "path": "src/model.py",
                "start_line": 1,
                "end_line": 4,
                "excerpt": "too wide",
                "rationale": "This range is wider than the deployment evidence contract.",
            }
        )


def test_large_evidence_is_compacted_before_review_context_gate() -> None:
    service = ProposalReviewService(ReviewArtifactStore())
    evidence = [
        {
            "requirement_id": "REQ-001",
            "path": f"src/model_{index}.py",
            "start_line": 1,
            "end_line": 3,
            "excerpt": "model flow " * 100,
            "rationale": "This range contains the model flow connected to the requirement and is useful for review.",
            "score": 1,
        }
        for index in range(200)
    ]

    result = service.start(
        "tenant",
        {
            "review_id": "review-large-evidence",
            "document": {"name": "proposal.md", "media_type": "text/markdown", "sha256": "doc"},
            "repository": {"root_name": "repo", "fingerprint": "repo", "unknowns": []},
            "requirements": [{"requirement_id": "REQ-001", "text": "model trace", "source": "markdown"}],
            "evidence": evidence,
        },
    )

    assert result["status"] == "complete"
    assert result["payload"]["report"]["evidence_candidates"] < len(evidence)
    assert result["payload"]["report"]["evidence_count"] > 0


def test_select_relevant_evidence_prevents_one_requirement_from_starving_the_rest() -> None:
    """Evidence arrives grouped by requirement_id in document order. Before
    round-robin interleaving, one requirement with many keyword matches could
    consume the entire MAX_EVIDENCE_ITEMS budget and leave every later
    requirement with zero evidence — reported as "missing" regardless of what
    the code actually contains."""
    requirements = [{"requirement_id": f"REQ-{index:03d}"} for index in range(1, 6)]
    evidence = [{"requirement_id": "REQ-001", "excerpt": "match", "rationale": "matches REQ-001."} for _ in range(150)]
    for requirement_id in ("REQ-002", "REQ-003", "REQ-004", "REQ-005"):
        evidence += [{"requirement_id": requirement_id, "excerpt": "match", "rationale": f"matches {requirement_id}."} for _ in range(2)]

    bounded_without_fix = ProposalReviewService._bound_evidence(evidence)
    starved = {item["requirement_id"] for item in bounded_without_fix}
    assert starved == {"REQ-001"}, "positional truncation should starve every requirement after the flooded one"

    selected = ProposalReviewService._select_relevant_evidence(requirements, evidence)
    bounded = ProposalReviewService._bound_evidence(selected)
    represented = {item["requirement_id"] for item in bounded}
    assert represented == {"REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"}


def test_service_start_keeps_every_requirement_evidenced_when_one_dominates() -> None:
    service = ProposalReviewService(ReviewArtifactStore())
    requirements = [{"requirement_id": f"REQ-{index:03d}", "text": f"requirement {index}", "source": "markdown"} for index in range(1, 6)]
    evidence = [
        {"requirement_id": "REQ-001", "path": "src/model.py", "start_line": 1, "end_line": 3, "excerpt": "model flow", "rationale": "This range is connected to the requirement and is useful for review."}
        for _ in range(150)
    ]
    for requirement_id in ("REQ-002", "REQ-003", "REQ-004", "REQ-005"):
        evidence.append(
            {"requirement_id": requirement_id, "path": f"src/{requirement_id}.py", "start_line": 1, "end_line": 3, "excerpt": requirement_id, "rationale": f"This range covers {requirement_id} and is useful for review."}
        )

    result = service.start(
        "tenant",
        {
            "review_id": "review-fair-distribution",
            "document": {"name": "proposal.md", "media_type": "text/markdown", "sha256": "doc"},
            "repository": {"root_name": "repo", "fingerprint": "repo", "unknowns": []},
            "requirements": requirements,
            "evidence": evidence[:200],
        },
    )

    stored_requirement_ids = {item.get("requirement_id") for item in result["payload"]["evidence"]}
    for requirement_id in ("REQ-002", "REQ-003", "REQ-004", "REQ-005"):
        assert requirement_id in stored_requirement_ids, f"{requirement_id} was starved of evidence by REQ-001's flood"


def test_jev_filters_context_before_langchain_synthesis() -> None:
    calls: list[dict] = []

    def evaluator(context: dict) -> dict:
        calls.append(context)
        return {"selected_evidence_ids": [context["evidence"][0]["evidence_id"]], "score": 0.8, "rubric": {"context": 1.0}}

    store = ReviewArtifactStore()
    graph = ProposalReviewGraph(store, jev=JEVReviewAdapter(evaluator))
    service = ProposalReviewService(store, graph=graph)
    result = service.start(
        "tenant",
        {
            "review_id": "review-jev-filter",
            "document": {"name": "proposal.md", "media_type": "text/markdown", "sha256": "doc"},
            "repository": {"root_name": "repo", "fingerprint": "repo", "unknowns": []},
            "requirements": [{"requirement_id": "REQ-001", "text": "model trace", "source": "markdown"}],
            "evidence": [
                {"requirement_id": "REQ-001", "path": "src/first.py", "start_line": 1, "end_line": 3, "excerpt": "first", "rationale": "This range shows the first model flow for the requirement."},
                {"requirement_id": "REQ-001", "path": "src/second.py", "start_line": 4, "end_line": 6, "excerpt": "second", "rationale": "This range shows a second model flow for the requirement."},
            ],
        },
    )

    assert calls[0]["mode"] == "context_filter"
    assert result["payload"]["report"]["provider_calls"] == {"langchain": 1, "jev": 1}
    assert result["payload"]["report"]["evidence_count"] == 1
    assert result["payload"]["jev"]["filtered_out"] == 1
    store.close()


def test_review_mode_is_persisted_for_the_two_workbench_branches() -> None:
    store = ReviewArtifactStore()
    service = ProposalReviewService(store)
    result = service.start(
        "tenant",
        {
            "review_id": "review-implementation-mode",
            "mode": "implementation",
            "document": {"name": "proposal.md", "media_type": "text/markdown", "sha256": "doc"},
            "repository": {"root_name": "repo", "fingerprint": "repo", "unknowns": []},
            "requirements": [{"requirement_id": "REQ-001", "text": "model trace", "source": "markdown"}],
            "evidence": [{"requirement_id": "REQ-001", "path": "src/model.py", "start_line": 1, "end_line": 3, "excerpt": "model flow", "rationale": "This range shows the model flow connected to the requirement."}],
        },
    )

    assert result["payload"]["report"]["mode"] == "implementation"
    assert result["payload"]["mode"] == "implementation"
    report_requirement = result["payload"]["report"]["requirements"][0]
    assert report_requirement["text"] == "model trace"
    assert report_requirement["kind_code"] == "REQ"
    assert "functional, quality, or operational capability" in report_requirement["kind_description"]
    store.close()


def test_langchain_provider_adapter_wraps_context_in_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.runnables import RunnableLambda

    # Capture the fully-rendered prompt into a side channel rather than
    # returning it as `summary` — `summary` is truncated to 2_000 chars
    # (a real limit for actual LLM output), which is unrelated to what this
    # test verifies and would flake any time the system prompt grows.
    captured: dict[str, str] = {}

    class FakeChatOpenAI:
        def __init__(self, **_: object) -> None:
            pass

        def with_structured_output(self, _: object) -> RunnableLambda:
            def _capture(prompt: object) -> dict[str, object]:
                captured["text"] = prompt.to_string()  # type: ignore[attr-defined]
                return {"summary": "ok", "requirements": []}

            return RunnableLambda(_capture)

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=FakeChatOpenAI))
    adapter = LangChainReviewAdapter.from_env({"AGENT_PROVIDER_MODE": "langchain", "OPENAI_API_KEY": "test-key"})

    result = adapter.invoke({"document": {}, "repository": {}, "requirements": [], "evidence": []})

    assert result["requirements"] == []
    assert "bounded JSON context" in captured["text"]


def test_langsmith_adapter_uses_env_aliases_and_redacts_client_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

        def create_run(self, **_: object) -> None:
            return None

    monkeypatch.setitem(sys.modules, "langsmith", SimpleNamespace(Client=FakeClient))
    adapter = LangSmithClientAdapter.from_env(
        project="trace-project",
        environment={
            "LANGCHAIN_TRACING_V2": "true",
            "LANGCHAIN_API_KEY": "test-key",
            "LANGCHAIN_ENDPOINT": "https://api.smith.example",
            "LANGSMITH_CONSOLE_URL": "https://smith.example",
        },
    )

    assert adapter is not None
    assert adapter.api_url == "https://api.smith.example"
    assert created["api_url"] == "https://api.smith.example"
    assert created["anonymizer"] is not None
    assert adapter.project == "trace-project"


def test_langgraph_run_passes_langsmith_callback_config() -> None:
    captured: dict[str, object] = {}

    class CallbackTracer:
        def langchain_callbacks(self) -> list[object]:
            return ["langsmith-callback"]

    store = ReviewArtifactStore()
    graph = ProposalReviewGraph(store, tracer=CallbackTracer())

    class CompiledGraph:
        def invoke(self, state: dict, *, config: dict) -> dict:
            captured.update(config)
            return {**state, "stage": "complete", "report": {}}

    graph._graph = CompiledGraph()
    result = graph.run({"review_id": "trace-review", "mode": "impact", "document": {}, "repository": {}})

    assert result["stage"] == "complete"
    assert captured["run_name"] == "proposal.review"
    assert captured["callbacks"] == ["langsmith-callback"]
    assert captured["metadata"]["review_id"] == "trace-review"
    store.close()


def test_review_graph_persists_report_and_human_decision() -> None:
    store = ReviewArtifactStore()
    graph = ProposalReviewGraph(store)
    service = ProposalReviewService(store, graph=graph)
    result = service.start(
        "tenant",
        {
            "review_id": "review-1",
            "document": {"name": "proposal.html", "media_type": "text/html", "sha256": "doc"},
            "repository": {"root_name": "repo", "fingerprint": "repo", "unknowns": []},
            "requirements": [{"requirement_id": "REQ-001", "text": "model must preserve trace", "source": "html", "kind": "acceptance"}],
            "evidence": [{"requirement_id": "REQ-001", "path": "model.py", "line": 3, "excerpt": "model trace", "score": 3, "reason": "match"}],
        },
    )
    assert result["status"] == "complete"
    assert result["payload"]["report"]["provider_calls"] == {"langchain": 1, "jev": 0}
    assert result["payload"]["report"]["no_code_execution"] is True
    decided = service.decide("review-1", "tenant", {"decision": "revise", "reason": "human check", "reviewer": "engineer"})
    assert decided["status"] == "revise"
    assert decided["decisions"][0]["reviewer"] == "engineer"
    store.close()


def test_review_request_preserves_explicit_reference_answer_for_context_recall() -> None:
    sanitized = ProposalReviewService._requirement({
        "requirement_id": "REQ-001",
        "text": "The service must store sessions.",
        "reference_answer": "The service stores user sessions in the repository.",
    })
    assert sanitized["reference_answer"] == "The service stores user sessions in the repository."


def test_review_provider_budgets_reset_for_each_review() -> None:
    store = ReviewArtifactStore()
    graph = ProposalReviewGraph(store)
    service = ProposalReviewService(store, graph=graph)
    context = {
        "document": {"name": "proposal.html", "media_type": "text/html", "sha256": "doc"},
        "repository": {"root_name": "repo", "fingerprint": "repo", "unknowns": []},
        "requirements": [{"requirement_id": "REQ-001", "text": "model must preserve trace", "source": "html", "kind": "acceptance"}],
        "evidence": [{"requirement_id": "REQ-001", "path": "model.py", "line": 3, "excerpt": "model trace", "score": 3, "reason": "match"}],
    }

    first = service.start("tenant", {"review_id": "review-budget-1", **context})
    second = service.start("tenant", {"review_id": "review-budget-2", **context})

    assert first["payload"]["report"]["provider_calls"] == {"langchain": 1, "jev": 0}
    assert second["payload"]["report"]["provider_calls"] == {"langchain": 1, "jev": 0}
    store.close()


def test_review_api_rejects_commands_and_unbounded_context() -> None:
    service = ProposalReviewService(ReviewArtifactStore())
    with pytest.raises(ReviewRequestError, match="commands"):
        service.start("tenant", {"document": {}, "repository": {}, "shell": "rm -rf"})
    with pytest.raises(ReviewRequestError, match="too large"):
        service.start("tenant", {"document": {}, "repository": {}, "requirements": [], "evidence": [], "padding": "x" * 200_000})


def test_review_api_compacts_large_document_and_repository_metadata_before_the_context_gate() -> None:
    service = ProposalReviewService(ReviewArtifactStore())
    result = service.start(
        "tenant",
        {
            "document": {"name": "proposal.html", "media_type": "text/html", "sha256": "doc", "sections": [{"text": "x" * 100_000}]},
            "repository": {"root_name": "repo", "fingerprint": "repo", "unknowns": [], "files": [{"path": f"file-{index}.py", "content": "x" * 1000} for index in range(200)]},
            "requirements": [{"requirement_id": "REQ-001", "text": "model trace", "source": "html"}],
            "evidence": [{"requirement_id": "REQ-001", "path": "model.py", "line": 1, "excerpt": "model trace", "score": 3}],
        },
    )
    assert result["status"] == "complete"
    assert result["payload"]["document"] == {"name": "proposal.html", "media_type": "text/html", "sha256": "doc", "extraction_confidence": None}


def test_jev_is_optional_and_bounded() -> None:
    calls = []
    adapter = JEVReviewAdapter(lambda report: calls.append(report) or {"score": 0.9, "rubric": {"coverage": 1.0}})
    assert adapter.filter_context({"requirements": [], "evidence": []})["score"] == 0.9
    with pytest.raises(RuntimeError, match="budget"):
        adapter.filter_context({"requirements": [], "evidence": []})
    assert len(calls) == 1


def test_control_api_exposes_catalog_review_and_human_decision() -> None:
    runtime = build_runtime(ControlApiConfig(host="127.0.0.1", port=0, database=":memory:"))
    server = create_server(runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    runtime.proposal_review.fetch_document = lambda url: {"document": {"name": "remote.html", "media_type": "text/html", "sha256": "remote", "sections": []}, "requirements": []}  # type: ignore[method-assign]

    def request(path: str, method: str = "GET", body: dict | None = None) -> dict:
        payload = None if body is None else json.dumps(body).encode()
        request_obj = urllib.request.Request(f"{base}{path}", data=payload, method=method, headers={"X-Tenant-ID": "api-tenant", "Content-Type": "application/json"})
        with urllib.request.urlopen(request_obj) as response:
            return json.loads(response.read())

    try:
        assert request("/v1/change-impact/catalog")["provider_budget"]["langchain_max_calls"] == 1
        assert request("/v1/change-impact/documents/from-url", "POST", {"url": "https://example.com/proposal"})["document"]["name"] == "remote.html"
        created = request(
            "/v1/change-impact/reviews",
            "POST",
            {
                "review_id": "api-review-1",
                "document": {"name": "proposal.html", "sha256": "doc"},
                "repository": {"root_name": "repo", "fingerprint": "repo", "unknowns": []},
                "requirements": [{"requirement_id": "REQ-001", "text": "model must preserve trace", "source": "html"}],
                "evidence": [{"requirement_id": "REQ-001", "path": "model.py", "line": 1, "excerpt": "model trace", "score": 3}],
            },
        )
        assert created["status"] == "complete"
        assert request("/v1/change-impact/reviews/api-review-1")["review_id"] == "api-review-1"
        decided = request("/v1/change-impact/reviews/api-review-1/decision", "POST", {"decision": "ready", "reason": "evidence reviewed", "reviewer": "engineer"})
        assert decided["status"] == "ready"
    finally:
        server.shutdown()
        server.server_close()
        runtime.catalog.close()
        runtime.proposal_review.store.close()
        runtime.store.close()


def test_control_runtime_falls_back_to_local_model_without_openai_key() -> None:
    runtime = build_runtime(
        ControlApiConfig(host="127.0.0.1", port=0, database=":memory:"),
        environment={"AGENT_PROVIDER_MODE": "langchain", "OPENAI_API_KEY": ""},
    )
    try:
        assert isinstance(runtime.workflow.model, FakeStructuredModel)
    finally:
        runtime.catalog.close()
        runtime.proposal_review.store.close()
        runtime.store.close()
