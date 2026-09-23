"""Runnable Proposal-to-Verified-Change vertical slice."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from agent_platform.budgets import BudgetPolicy, TokenBudgetLedger, estimate_tokens
from agent_platform.cache import ContentAddressedContextCache
from agent_platform.contracts import ApprovalToken, EvidenceReference, Plan, PlanStep, ReleaseReport, Requirement, RunLifecycle, UsageRecord
from agent_platform.redaction import redact
from agent_platform.storage import InvalidApproval, KernelStore, TenantScopeError
from project_packs.proposal_to_verified_change import RepositoryIndex
from project_packs.proposal_to_verified_change.pack import PromptInjectionDetected, ProposalToVerifiedChangePack

from .graph import NODE_NAMES
from .model_port import FakeStructuredModel, PromptContextAdapter, StructuredModelPort


@dataclass(frozen=True)
class RunOutcome:
    run: RunLifecycle
    requirements: tuple[Any, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    plan: Plan | None = None
    approval: ApprovalToken | None = None
    report: Mapping[str, Any] | None = None
    proposal: Mapping[str, Any] | None = None


class ProposalVerifiedWorkflow:
    def __init__(
        self,
        store: KernelStore,
        pack: ProposalToVerifiedChangePack,
        *,
        model: StructuredModelPort | None = None,
        cache: ContentAddressedContextCache | None = None,
        sandbox: Any | None = None,
        delivery: Any | None = None,
        tracer: Any | None = None,
        graph_runtime: Any | None = None,
        artifact_store: Any | None = None,
        patcher: Callable[[Any, Plan], None] | None = None,
    ) -> None:
        self.store = store
        self.pack = pack
        self.model = model or FakeStructuredModel()
        self.cache = cache or ContentAddressedContextCache()
        self.sandbox = sandbox
        self.delivery = delivery
        self.tracer = tracer
        self.graph_runtime = graph_runtime
        self.artifact_store = artifact_store
        self.patcher = patcher
        self.prompt_adapter = PromptContextAdapter()

    def for_repository(self, root: str) -> "ProposalVerifiedWorkflow":
        """Create a bounded pack for one authorized checkout while sharing state."""

        from pathlib import Path

        path = Path(root).resolve(strict=True)
        allowlisted = tuple(
            sorted(
                child.name
                for child in path.iterdir()
                if not child.name.startswith(".") and (child.is_dir() or child.is_file())
            )
        )
        pack = ProposalToVerifiedChangePack(RepositoryIndex(path, allowlisted_paths=allowlisted))
        return ProposalVerifiedWorkflow(
            self.store,
            pack,
            model=self.model,
            cache=self.cache,
            sandbox=self.sandbox,
            delivery=self.delivery,
            tracer=self.tracer,
            graph_runtime=self.graph_runtime,
            artifact_store=self.artifact_store,
            patcher=self.patcher,
        )

    def refresh_proposal(self, proposal_id: str, tenant_id: str, repository_snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
        """Re-hash persisted evidence against the current authorized checkout."""

        view = self.store.proposal_view(proposal_id, tenant_id, current_repository=repository_snapshot)
        current = self.pack.revalidate_evidence(tuple(self._evidence_from_json(item) for item in view.get("evidence", ())))
        self.store.revalidate_proposal(
            proposal_id,
            tenant_id,
            repository_snapshot,
            evidence=(
                {
                    "evidence_id": old.get("evidence_id"),
                    "path": new.path,
                    "content_hash": new.content_hash,
                    "authorized": new.authorized,
                    "valid": new.valid,
                }
                for old, new in zip(view.get("evidence", ()), current)
            ),
        )
        return self.store.proposal_view(proposal_id, tenant_id)

    def run(
        self,
        *,
        tenant_id: str,
        proposal: str,
        mode: str = "plan_only",
        idempotency_key: str,
        approval: ApprovalToken | None = None,
        run_id: str | None = None,
        quota_limit: int | None = None,
        repository_id: str | None = None,
        repository_snapshot: Mapping[str, Any] | None = None,
        proposal_id: str | None = None,
    ) -> RunOutcome:
        trace_run_id = run_id or f"run-{uuid.uuid4().hex}"
        trace_id = self._start_trace("proposal.workflow", {"run_id": trace_run_id, "tenant_id": tenant_id, "mode": mode})
        try:
            outcome = self._run(
                tenant_id=tenant_id,
                proposal=proposal,
                mode=mode,
                idempotency_key=idempotency_key,
                approval=approval,
                run_id=trace_run_id,
                quota_limit=quota_limit,
                repository_id=repository_id,
                repository_snapshot=repository_snapshot,
                proposal_id=proposal_id,
                trace_id=trace_id,
            )
        except Exception as exc:
            self._finish_trace(trace_id, error=f"{type(exc).__name__}: {exc}")
            raise
        terminal = {"run_id": outcome.run.run_id, "state": outcome.run.state, "error": outcome.run.error, "report": outcome.report}
        self._finish_trace(trace_id, outputs=terminal, error=outcome.run.error)
        return outcome

    def _run(
        self,
        *,
        tenant_id: str,
        proposal: str,
        mode: str = "plan_only",
        idempotency_key: str,
        approval: ApprovalToken | None = None,
        run_id: str | None = None,
        quota_limit: int | None = None,
        repository_id: str | None = None,
        repository_snapshot: Mapping[str, Any] | None = None,
        proposal_id: str | None = None,
        trace_id: str | None = None,
    ) -> RunOutcome:
        if mode not in {"plan_only", "verify"}:
            raise ValueError("mode must be plan_only or verify")
        run_id = run_id or f"run-{uuid.uuid4().hex}"
        request_payload: dict[str, Any] = {"proposal": proposal, "mode": mode}
        if repository_id:
            request_payload["repository_id"] = repository_id
        if repository_snapshot is not None:
            request_payload["repository_snapshot"] = dict(repository_snapshot)
        if repository_id and proposal_id is None and repository_snapshot is not None:
            proposal_record = self.store.create_proposal(
                tenant_id=tenant_id,
                repository=repository_snapshot,
                proposal=proposal,
                mode=mode,
                idempotency_key=idempotency_key,
            )
            proposal_id = str(proposal_record["proposal_id"])
        run = self.store.create_run(
            run_id=run_id,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            mode=mode,
            payload=request_payload,
            proposal_id=proposal_id,
            repository_snapshot=repository_snapshot,
            trace_id=trace_id,
        )
        run_id = run.run_id
        if proposal_id:
            tracer_client = getattr(self.tracer, "_client", None)
            project = getattr(tracer_client, "project", None) or getattr(getattr(self.tracer, "_client", None), "project_name", None)
            self.store.save_trace(
                run_id=run_id,
                tenant_id=tenant_id,
                trace_id=trace_id,
                provider="langsmith" if trace_id else "local",
                project=project,
                console_url=getattr(self.tracer, "console_url", None),
                export_status="observational",
            )
        if proposal_id and repository_snapshot is not None:
            self.refresh_proposal(proposal_id, tenant_id, repository_snapshot)
            run = self.store.get_run(run_id, tenant_id)
        checkpoint = self.store.checkpoint(run_id, tenant_id)
        if run.state in {"plan_only", "verified", "quota_paused", "budget_exceeded", "failed", "rejected"}:
            return self._outcome(run, checkpoint, proposal_id)
        ledger = TokenBudgetLedger(BudgetPolicy.local_lite(mode), quota_limit=quota_limit)
        if run.state == "queued":
            run = self.store.transition(run_id, tenant_id, "running", payload={"node": "intake", **({"repository_id": repository_id} if repository_id else {})})
        values: dict[str, Any] = {"proposal": proposal, "mode": mode}
        if repository_id:
            values["repository_id"] = repository_id
        if proposal_id:
            values["proposal_id"] = proposal_id
        if repository_snapshot:
            values["repository_snapshot"] = dict(repository_snapshot)
            values["branch"] = repository_snapshot.get("branch")
            values["commit"] = repository_snapshot.get("commit", repository_snapshot.get("head_commit"))
        if checkpoint:
            values.update(checkpoint["state"])
        try:
            if not checkpoint:
                self._checkpoint(run_id, tenant_id, "intake", values)
                self._event(run_id, tenant_id, "graph.node", {"node": "intake"})
                self._checkpoint(run_id, tenant_id, "profile_validate", values)
                self._event(run_id, tenant_id, "graph.node", {"node": "profile_validate", "provider": self.model.provider_id})
                parsed = self.pack.parse_proposal(proposal)
                values["requirements"] = [item.__dict__ for item in parsed.requirements]
                values["runtime"] = parsed.runtime
                self._checkpoint(run_id, tenant_id, "inventory", values)
                self._event(run_id, tenant_id, "graph.node", {"node": "inventory"})
                evidence = self.pack.evidence(proposal)
                values["evidence"] = [item.__dict__ for item in evidence]
                self._checkpoint(run_id, tenant_id, "retrieve", values)
                context = {"requirement_ids": [item.requirement_id for item in parsed.requirements], "evidence": [item.__dict__ for item in evidence]}
                cache_lookup = self.cache.get_or_put(context)
                values["cache_key"] = cache_lookup.key
                self._event(run_id, tenant_id, "context.cache", {"key": cache_lookup.key, "hit": cache_lookup.hit, "retrieval_expansion": len(evidence)})
                self._checkpoint(run_id, tenant_id, "analyze", values)
                prompt, safe_context = self.prompt_adapter.build(proposal, cache_lookup.value)
                estimated_input = estimate_tokens(prompt)
                if estimated_input > ledger.policy.per_call_input_limit:
                    decision = ledger.reserve(phase=1, input_tokens=estimated_input, output_tokens=0)
                    usage = UsageRecord(run_id, f"{run_id}:analyze", "analyze", estimated_input, 0, estimated_input, True, cache_lookup.hit, len(evidence), decision.status)
                    self.store.record_usage(usage, tenant_id)
                    return self._budget_stop(run, tenant_id, decision.status, decision.reason, values, parsed.requirements, evidence)
                result = self.model.generate(prompt, context=safe_context, schema="proposal-analysis-v1", idempotency_key=f"{run_id}:analyze")
                decision = ledger.reserve(phase=1, input_tokens=result.input_tokens, output_tokens=result.output_tokens)
                usage = UsageRecord(run_id, f"{run_id}:analyze", "analyze", result.input_tokens, result.output_tokens, result.total_tokens, result.estimated, cache_lookup.hit, len(evidence), decision.status)
                self.store.record_usage(usage, tenant_id)
                self._event(run_id, tenant_id, "model.usage", usage.__dict__)
                if not decision.allowed:
                    return self._budget_stop(run, tenant_id, decision.status, decision.reason, values, parsed.requirements, evidence)
                self._checkpoint(run_id, tenant_id, "plan", values)
                plan = self.pack.build_plan(proposal, mode)
                values["plan"] = self._plan_json(plan)
                self._event(run_id, tenant_id, "plan.created", {"plan_id": plan.plan_id, "valid_references": plan.valid_references, "runtime": plan.runtime})
            else:
                parsed = self.pack.parse_proposal(proposal)
                evidence = self.pack.evidence(proposal)
                plan = self.pack.build_plan(proposal, mode)
                values.update({"requirements": [item.__dict__ for item in parsed.requirements], "evidence": [item.__dict__ for item in evidence], "plan": self._plan_json(plan)})
            if not plan.supported_runtime:
                return self._finish_plan_only(run_id, tenant_id, parsed.requirements, evidence, plan, values, "unknown runtime")
            if not plan.valid_references:
                if mode == "verify":
                    return self._finish_failed(run_id, tenant_id, parsed.requirements, evidence, plan, values, "invalid evidence reference")
                return self._finish_plan_only(run_id, tenant_id, parsed.requirements, evidence, plan, values, "invalid evidence reference")
            if mode == "plan_only" or plan.mode == "plan_only":
                return self._finish_plan_only(run_id, tenant_id, parsed.requirements, evidence, plan, values, None)
            return self._verify(run_id, tenant_id, proposal, parsed.requirements, evidence, plan, values, approval, ledger, proposal_id, repository_snapshot)
        except PromptInjectionDetected as exc:
            return self._finish_rejected(run_id, tenant_id, values, str(exc))
        except TenantScopeError as exc:
            return self._finish_rejected(run_id, tenant_id, values, str(exc))
        except (ValueError, FileNotFoundError) as exc:
            return self._finish_failed(run_id, tenant_id, (), (), None, values, str(exc))

    def _verify(
        self,
        run_id: str,
        tenant_id: str,
        proposal: str,
        requirements: tuple[Any, ...],
        evidence: tuple[EvidenceReference, ...],
        plan: Plan,
        values: dict[str, Any],
        approval: ApprovalToken | None,
        ledger: TokenBudgetLedger,
        proposal_id: str | None,
        repository_snapshot: Mapping[str, Any] | None,
    ) -> RunOutcome:
        del proposal, ledger
        checkpoint = self.store.checkpoint(run_id, tenant_id)
        if proposal_id and repository_snapshot is not None:
            if self.store.revalidate_proposal(proposal_id, tenant_id, repository_snapshot):
                return self._finish_failed(run_id, tenant_id, requirements, evidence, plan, values, "evidence is stale; re-analysis is required", proposal_id)
        if approval is None:
            existing_approval = self.store.approval_for_run(run_id, tenant_id)
            if existing_approval is not None and self.store.get_run(run_id, tenant_id).state == "waiting_approval":
                return self._outcome_payload(self.store.get_run(run_id, tenant_id), requirements, evidence, plan, existing_approval, proposal_id)
            if proposal_id and repository_snapshot is not None:
                self.store.save_proposal_outputs(
                    proposal_id=proposal_id,
                    run_id=run_id,
                    tenant_id=tenant_id,
                    requirements=(asdict(item) for item in requirements),
                    evidence=(asdict(item) for item in evidence),
                    plan=asdict(plan),
                    report=self.store.report(run_id, tenant_id),
                    repository_snapshot=repository_snapshot,
                )
            token = self.store.issue_approval(
                run_id=run_id,
                tenant_id=tenant_id,
                scopes=("patch", "deliver"),
                expires_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
                plan_digest=self._plan_digest(plan),
            )
            values["approval_id"] = token.token_id
            self._checkpoint(run_id, tenant_id, "human_approval", values)
            transition_payload = {"node": "human_approval", "approval_id": token.token_id}
            if values.get("repository_id"):
                transition_payload["repository_id"] = values["repository_id"]
            run = self.store.transition(run_id, tenant_id, "waiting_approval", payload=transition_payload)
            if proposal_id and repository_snapshot is not None:
                self.store.save_proposal_outputs(
                    proposal_id=proposal_id,
                    run_id=run_id,
                    tenant_id=tenant_id,
                    requirements=(asdict(item) for item in requirements),
                    evidence=(asdict(item) for item in evidence),
                    plan=asdict(plan),
                    report=self.store.report(run_id, tenant_id),
                    repository_snapshot=repository_snapshot,
                )
            return self._outcome_payload(run, requirements, evidence, plan, token, proposal_id)
        try:
            consumed = self.store.consume_approval(
                approval.token_id,
                run_id=run_id,
                tenant_id=tenant_id,
                scope="patch",
                current_repository=repository_snapshot,
                plan_digest=hashlib.sha256(json.dumps(asdict(plan), sort_keys=True, default=str).encode()).hexdigest(),
            )
        except InvalidApproval as exc:
            return self._finish_rejected(run_id, tenant_id, values, str(exc), requirements, evidence, plan)
        self._event(run_id, tenant_id, "approval.consumed", {"token_id": consumed.token_id, "scope": "patch"})
        self.store.transition(run_id, tenant_id, "running", payload={"node": "patch", "approval_id": consumed.token_id})
        self._checkpoint(run_id, tenant_id, "patch", values)
        sandbox = self.sandbox
        if sandbox is None:
            from services.sandbox_worker import IsolatedRepositorySandbox, SandboxPolicy

            allowed = tuple(sorted({item.path.split("/", 1)[0] for item in evidence if item.authorized and item.path}))
            policy = SandboxPolicy(allowlisted_paths=allowed or SandboxPolicy().allowlisted_paths)
            if repository_snapshot is not None:
                sandbox = IsolatedRepositorySandbox(self.pack.index.root, repository_snapshot, policy, patcher=self.patcher)
            else:
                from services.sandbox_worker import DeterministicSandbox

                sandbox = DeterministicSandbox(policy)
        source_root = getattr(self.pack.index, "root", None)
        try:
            simulation = sandbox.apply(plan, approval=consumed, source_root=source_root, approved_snapshot=repository_snapshot)
        except TypeError:
            # Keep injected legacy workers source-compatible; repository-bound
            # runs still use the built-in isolated worker above.
            simulation = sandbox.apply(plan, approval=consumed)
        if not simulation.success:
            try:
                retry = sandbox.apply(plan, approval=consumed, retry=True, source_root=source_root, approved_snapshot=repository_snapshot)
            except TypeError:
                retry = sandbox.apply(plan, approval=consumed, retry=True)
            if not retry.success:
                close = getattr(sandbox, "close", None)
                if callable(close):
                    close()
                return self._finish_failed(run_id, tenant_id, requirements, evidence, plan, values, f"sandbox patch failed: {retry.detail}", proposal_id)
            simulation = retry
        self._checkpoint(run_id, tenant_id, "test", values)
        test_result = sandbox.test(plan)
        if not test_result.success:
            close = getattr(sandbox, "close", None)
            if callable(close):
                close()
            return self._finish_failed(run_id, tenant_id, requirements, evidence, plan, values, f"verification failed: {test_result.detail}", proposal_id)
        self._checkpoint(run_id, tenant_id, "evaluate", values)
        diff_artifact = simulation.diff_artifact or {"schema_version": "1.0", "kind": "repository_diff", "base_commit": simulation.base_commit, "changed_files": list(simulation.changed_files), "files": [], "source_unchanged": repository_snapshot is not None}
        changed_files = tuple(simulation.changed_files)
        test_results = tuple(test_result.command_results)
        artifact_ids: list[str] = []
        diff_path: str | None = None
        test_path: str | None = None
        try:
            package = {
                "schema_version": "1.0",
                "kind": "verification_package",
                "run_id": run_id,
                "status": "verified",
                "base_commit": simulation.base_commit,
                "changed_files": list(changed_files),
                "diff": diff_artifact,
                "tests": list(test_results),
                "verification": {"status": "verified", "source_unchanged": bool(diff_artifact.get("source_unchanged", False))},
            }
            if self.artifact_store is not None:
                diff_file = self.artifact_store.write(
                    f"{run_id}-diff",
                    {"schema_version": "1.0", "kind": "repository_diff", "diff": diff_artifact, "changed_files": list(changed_files)},
                )
                test_file = self.artifact_store.write(
                    f"{run_id}-tests",
                    {"schema_version": "1.0", "kind": "test_results", "base_commit": simulation.base_commit, "results": list(test_results)},
                )
                diff_path = diff_file.path
                test_path = test_file.path
                self._event(run_id, tenant_id, "artifact.persisted", {"artifact_id": diff_file.artifact_id, "path": diff_file.path, "digest": diff_file.digest})
                self._event(run_id, tenant_id, "artifact.persisted", {"artifact_id": test_file.artifact_id, "path": test_file.path, "digest": test_file.digest})
                artifact = self.artifact_store.write(f"{run_id}-verification", package)
                artifact_ids.append(artifact.artifact_id)
                self._event(run_id, tenant_id, "artifact.persisted", {"artifact_id": artifact.artifact_id, "path": artifact.path, "digest": artifact.digest})
                self.store.record_artifact(artifact_id=artifact.artifact_id, run_id=run_id, tenant_id=tenant_id, kind="verification", path=artifact.path, digest=artifact.digest, metadata={"schema_version": "1.0", "changed_files": list(changed_files), "bytes_written": artifact.bytes_written})
            diff_digest = hashlib.sha256(json.dumps(diff_artifact, sort_keys=True, default=str).encode()).hexdigest()
            test_digest = hashlib.sha256(json.dumps(list(test_results), sort_keys=True, default=str).encode()).hexdigest()
            artifact_ids.extend((f"{run_id}-diff", f"{run_id}-tests"))
            self.store.record_artifact(artifact_id=f"{run_id}-diff", run_id=run_id, tenant_id=tenant_id, kind="diff", digest=diff_digest, metadata={"schema_version": "1.0", "changed_files": list(changed_files), "diff": diff_artifact, "source_unchanged": bool(diff_artifact.get("source_unchanged", False))})
            self.store.record_artifact(artifact_id=f"{run_id}-tests", run_id=run_id, tenant_id=tenant_id, kind="test", digest=test_digest, metadata={"schema_version": "1.0", "results": list(test_results), "status": "passed"})
        except (OSError, ValueError, TypeError) as exc:
            close = getattr(sandbox, "close", None)
            if callable(close):
                close()
            return self._finish_failed(run_id, tenant_id, requirements, evidence, plan, values, f"verification package creation failed: {exc}", proposal_id)
        report = self._report(run_id, "verified", requirements, evidence, plan, latency_ms=0, usage=self.store.usage(run_id, tenant_id), approval_bypass=0, secret_leakage=0, prompt_injection=0, verification_status="verified", changed_files=changed_files, test_results=test_results, artifact_ids=artifact_ids, trace_id=self.store.get_run(run_id, tenant_id).trace_id)
        self.store.save_report(report, tenant_id)
        self._checkpoint(run_id, tenant_id, "report", values)
        self.store.record_artifact(
            artifact_id=f"{run_id}-diff",
            run_id=run_id,
            tenant_id=tenant_id,
            kind="diff",
            digest=hashlib.sha256(json.dumps(diff_artifact, sort_keys=True, default=str).encode()).hexdigest(),
            path=diff_path,
            metadata={"status": "prepared", "schema_version": "1.0", "changed_files": list(changed_files), "source_unchanged": bool(diff_artifact.get("source_unchanged", False)), "detail": simulation.detail},
        )
        self.store.record_artifact(
            artifact_id=f"{run_id}-tests",
            run_id=run_id,
            tenant_id=tenant_id,
            kind="test",
            digest=hashlib.sha256(json.dumps(list(test_results), sort_keys=True, default=str).encode()).hexdigest(),
            path=test_path,
            metadata={"status": "passed", "schema_version": "1.0", "results": list(test_results), "detail": test_result.detail},
        )
        self._event(run_id, tenant_id, "delivery.prepared", {"approval_token_id": consumed.token_id, "artifact_hash": self._artifact_hash(plan)})
        run = self.store.transition(run_id, tenant_id, "verified", payload={"plan_id": plan.plan_id, "report_persisted": True})
        if proposal_id and repository_snapshot is not None:
            self.store.save_proposal_outputs(
                proposal_id=proposal_id,
                run_id=run_id,
                tenant_id=tenant_id,
                requirements=(asdict(item) for item in requirements),
                evidence=(asdict(item) for item in evidence),
                plan=asdict(plan),
                report=self.store.report(run_id, tenant_id),
                repository_snapshot=repository_snapshot,
            )
        close = getattr(sandbox, "close", None)
        if callable(close):
            close()
        return self._outcome_payload(run, requirements, evidence, plan, consumed, proposal_id)

    def _finish_plan_only(self, run_id: str, tenant_id: str, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan, values: dict[str, Any], reason: str | None) -> RunOutcome:
        report = self._report(run_id, "plan_only", requirements, evidence, plan, latency_ms=0, usage=self.store.usage(run_id, tenant_id), approval_bypass=0, secret_leakage=0, prompt_injection=0, reason=reason)
        self.store.save_report(report, tenant_id)
        self._checkpoint(run_id, tenant_id, "report", values)
        if self.artifact_store is not None:
            artifact = self.artifact_store.write(run_id, {"run_id": run_id, "status": "plan_only", "plan": self._plan_json(plan), "report": report.__dict__})
            self._event(run_id, tenant_id, "artifact.persisted", {"artifact_id": artifact.artifact_id, "path": artifact.path, "digest": artifact.digest})
            self.store.record_artifact(artifact_id=artifact.artifact_id, run_id=run_id, tenant_id=tenant_id, kind="review", path=artifact.path, digest=artifact.digest, metadata={"bytes_written": artifact.bytes_written})
        run = self.store.transition(run_id, tenant_id, "plan_only", payload={"plan_id": plan.plan_id, "report_persisted": True, "reason": reason or "plan-only requested"})
        proposal_id = str(values["proposal_id"]) if values.get("proposal_id") else None
        snapshot = values.get("repository_snapshot")
        if proposal_id and isinstance(snapshot, Mapping):
            self.store.save_proposal_outputs(
                proposal_id=proposal_id,
                run_id=run_id,
                tenant_id=tenant_id,
                requirements=(asdict(item) for item in requirements),
                evidence=(asdict(item) for item in evidence),
                plan=asdict(plan),
                report=self.store.report(run_id, tenant_id),
                repository_snapshot=snapshot,
            )
        return self._outcome_payload(run, requirements, evidence, plan, None, proposal_id)

    def _finish_failed(self, run_id: str, tenant_id: str, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan | None, values: dict[str, Any], reason: str, proposal_id: str | None = None) -> RunOutcome:
        if plan is None:
            plan = None
        if plan is not None:
            report = self._report(run_id, "failed", requirements, evidence, plan, latency_ms=0, usage=self.store.usage(run_id, tenant_id), approval_bypass=0, secret_leakage=0, prompt_injection=0, verification_status="failed", trace_id=self.store.get_run(run_id, tenant_id).trace_id, reason=reason)
            self.store.save_report(report, tenant_id)
        run = self.store.transition(run_id, tenant_id, "failed", payload={"reason": reason}, error=reason)
        if plan is not None:
            self._checkpoint(run_id, tenant_id, "report", values)
            current_proposal_id = proposal_id or (str(values["proposal_id"]) if values.get("proposal_id") else None)
            snapshot = values.get("repository_snapshot")
            if current_proposal_id and isinstance(snapshot, Mapping):
                self.store.save_proposal_outputs(proposal_id=current_proposal_id, run_id=run_id, tenant_id=tenant_id, requirements=(asdict(item) for item in requirements), evidence=(asdict(item) for item in evidence), plan=asdict(plan), report=self.store.report(run_id, tenant_id), repository_snapshot=snapshot)
        return self._outcome_payload(run, requirements, evidence, plan, None, proposal_id or (str(values["proposal_id"]) if values.get("proposal_id") else None))

    def _finish_rejected(self, run_id: str, tenant_id: str, values: dict[str, Any], reason: str, requirements: tuple[Any, ...] = (), evidence: tuple[EvidenceReference, ...] = (), plan: Plan | None = None) -> RunOutcome:
        if plan is not None:
            report = self._report(run_id, "rejected", requirements, evidence, plan, latency_ms=0, usage=self.store.usage(run_id, tenant_id), approval_bypass=1, secret_leakage=0, prompt_injection=0, verification_status="rejected", trace_id=self.store.get_run(run_id, tenant_id).trace_id, reason=reason)
            self.store.save_report(report, tenant_id)
        run = self.store.transition(run_id, tenant_id, "rejected", payload={"reason": reason}, error=reason)
        self._checkpoint(run_id, tenant_id, "report", values)
        if plan is not None:
            current_proposal_id = str(values["proposal_id"]) if values.get("proposal_id") else None
            snapshot = values.get("repository_snapshot")
            if current_proposal_id and isinstance(snapshot, Mapping):
                self.store.save_proposal_outputs(proposal_id=current_proposal_id, run_id=run_id, tenant_id=tenant_id, requirements=(asdict(item) for item in requirements), evidence=(asdict(item) for item in evidence), plan=asdict(plan), report=self.store.report(run_id, tenant_id), repository_snapshot=snapshot)
        return self._outcome_payload(run, requirements, evidence, plan, None, str(values["proposal_id"]) if values.get("proposal_id") else None)

    def _budget_stop(self, run: RunLifecycle, tenant_id: str, status: str, reason: str, values: dict[str, Any], requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...]) -> RunOutcome:
        target = "quota_paused" if status == "quota_paused" else "budget_exceeded"
        current = self.store.transition(run.run_id, tenant_id, target, payload={"reason": reason}, error=reason)
        self._checkpoint(run.run_id, tenant_id, "report", values)
        return self._outcome_payload(current, requirements, evidence, None, None, str(values["proposal_id"]) if values.get("proposal_id") else None)

    def _report(self, run_id: str, status: str, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan, *, latency_ms: int, usage: tuple[UsageRecord, ...], approval_bypass: int, secret_leakage: int, prompt_injection: int, reason: str | None = None, verification_status: str | None = None, changed_files: tuple[str, ...] = (), test_results: tuple[Mapping[str, Any], ...] = (), artifact_ids: tuple[str, ...] = (), trace_id: str | None = None) -> ReleaseReport:
        from services.evaluation import build_release_report

        return build_release_report(run_id=run_id, status=status, requirements=requirements, evidence=evidence, plan=plan, usage=usage, latency_ms=latency_ms, approval_bypass=approval_bypass, secret_leakage=secret_leakage, prompt_injection=prompt_injection, reason=reason, verification_status=verification_status, changed_files=changed_files, test_results=test_results, artifact_ids=artifact_ids, trace_id=trace_id)

    def _outcome(self, run: RunLifecycle, checkpoint: Mapping[str, Any] | None, proposal_id: str | None = None) -> RunOutcome:
        if not checkpoint:
            return RunOutcome(run, proposal=self._safe_proposal_view(proposal_id, run.tenant_id))
        values = checkpoint.get("state", {})
        requirements = tuple(self._requirement_from_json(item) for item in values.get("requirements", ()))
        evidence = tuple(self._evidence_from_json(item) for item in values.get("evidence", ()))
        plan = self._plan_from_json(values.get("plan"))
        proposal = self._safe_proposal_view(proposal_id, run.tenant_id)
        report = proposal.get("report") if proposal else self.store.report(run.run_id, run.tenant_id)
        return RunOutcome(run, requirements, evidence, plan, None, report, proposal)

    def _outcome_payload(self, run: RunLifecycle, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan | None, approval: ApprovalToken | None, proposal_id: str | None) -> RunOutcome:
        proposal = self._safe_proposal_view(proposal_id, run.tenant_id)
        report = proposal.get("report") if proposal else self.store.report(run.run_id, run.tenant_id)
        return RunOutcome(run, requirements, evidence, plan, approval, report, proposal)

    def _safe_proposal_view(self, proposal_id: str | None, tenant_id: str) -> Mapping[str, Any] | None:
        if not proposal_id:
            return None
        try:
            return self.store.proposal_view(proposal_id, tenant_id)
        except TenantScopeError:
            return None

    def _checkpoint(self, run_id: str, tenant_id: str, node: str, values: Mapping[str, Any]) -> None:
        self.store.save_checkpoint(run_id, tenant_id, node, values)
        if self.graph_runtime is not None:
            self.graph_runtime.checkpoint(redact(values), thread_id=run_id, node=node)

    def _start_trace(self, name: str, attributes: Mapping[str, Any]) -> str | None:
        if self.tracer is None:
            return None
        callback = getattr(self.tracer, "start_run", None)
        if not callable(callback):
            return None
        try:
            return callback(name, attributes)
        except Exception:
            return None

    def _finish_trace(self, trace_id: str | None, *, outputs: Mapping[str, Any] | None = None, error: str | None = None) -> None:
        if self.tracer is None or not trace_id:
            return
        callback = getattr(self.tracer, "finish_run", None)
        if not callable(callback):
            return
        try:
            callback(trace_id, outputs=outputs, error=error)
        except Exception:
            return

    def _event(self, run_id: str, tenant_id: str, event: str, payload: Mapping[str, Any]) -> None:
        self.store.append_event(run_id, tenant_id, event, payload)
        if self.tracer is not None:
            self.tracer.record(event, {"run_id": run_id, **redact(payload)})

    @staticmethod
    def _plan_json(plan: Plan) -> dict[str, Any]:
        return asdict(plan)

    @staticmethod
    def _requirement_from_json(value: Mapping[str, Any]) -> Requirement:
        return Requirement(str(value["requirement_id"]), str(value["title"]), str(value["description"]), tuple(value.get("acceptance", ())), str(value.get("source_text", "")), bool(value.get("supported", True)))

    @classmethod
    def _evidence_from_json(cls, value: Mapping[str, Any]) -> EvidenceReference:
        return EvidenceReference(str(value["requirement_id"]), str(value["path"]), int(value["start_line"]), int(value["end_line"]), str(value["content_hash"]), value.get("symbol"), bool(value.get("authorized", True)), bool(value.get("valid", True)))

    @classmethod
    def _plan_from_json(cls, value: Mapping[str, Any] | None) -> Plan | None:
        if not value:
            return None
        requirements = tuple(cls._requirement_from_json(item) for item in value.get("requirements", ()))
        steps = tuple(
            PlanStep(
                str(item["step_id"]),
                str(item["title"]),
                str(item["action"]),
                tuple(cls._evidence_from_json(ref) for ref in item.get("evidence", ())),
                str(item.get("impact", "high")),
                tuple(item.get("commands", ())),
            )
            for item in value.get("steps", ())
        )
        return Plan(str(value["plan_id"]), requirements, steps, str(value.get("runtime", "python")), str(value.get("mode", "plan_only")), bool(value.get("supported_runtime", True)), value.get("unsupported_reason"), bool(value.get("valid_references", True)))

    @staticmethod
    def _artifact_hash(plan: Plan) -> str:
        return hashlib.sha256(json.dumps(ProposalVerifiedWorkflow._plan_json(plan), sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _plan_digest(plan: Plan) -> str:
        return hashlib.sha256(json.dumps(asdict(plan), sort_keys=True, default=str).encode()).hexdigest()
