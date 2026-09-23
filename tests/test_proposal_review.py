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
    assert result["changes"][0]["type"] == "changed"
    assert "Partial implementation" in result["proposal_markdown"]


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


def test_service_drops_single_line_or_unreasoned_evidence() -> None:
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
    assert ProposalReviewService._evidence({"requirement_id": "REQ-001", "path": "src/model.py", "line": 2, "reason": "match"}) is None


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

    class FakeChatOpenAI:
        def __init__(self, **_: object) -> None:
            pass

        def with_structured_output(self, _: object) -> RunnableLambda:
            return RunnableLambda(lambda prompt: {"summary": prompt.to_string(), "requirements": []})

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=FakeChatOpenAI))
    adapter = LangChainReviewAdapter.from_env({"AGENT_PROVIDER_MODE": "langchain", "OPENAI_API_KEY": "test-key"})

    result = adapter.invoke({"document": {}, "repository": {}, "requirements": [], "evidence": []})

    assert result["requirements"] == []
    assert "bounded JSON context" in result["summary"]


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
    assert adapter.evaluate({"requirements": []})["score"] == 0.9
    with pytest.raises(RuntimeError, match="budget"):
        adapter.evaluate({"requirements": []})
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
