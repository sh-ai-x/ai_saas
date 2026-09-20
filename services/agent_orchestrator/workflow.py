"""Runnable Proposal-to-Verified-Change vertical slice."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from agent_platform.budgets import BudgetPolicy, TokenBudgetLedger, estimate_tokens
from agent_platform.cache import ContentAddressedContextCache
from agent_platform.contracts import ApprovalToken, EvidenceReference, Plan, ReleaseReport, RunLifecycle, UsageRecord
from agent_platform.redaction import redact
from agent_platform.storage import InvalidApproval, KernelStore
from project_packs.proposal_to_verified_change.pack import PromptInjectionDetected, ProposalToVerifiedChangePack

from .graph import NODE_NAMES
from .langgraph_runtime import LangGraphRuntime
from .model_port import FakeStructuredModel, PromptContextAdapter, StructuredModelPort


@dataclass(frozen=True)
class RunOutcome:
    run: RunLifecycle
    requirements: tuple[Any, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    plan: Plan | None = None
    approval: ApprovalToken | None = None
    report: Mapping[str, Any] | None = None


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
        graph_runtime: LangGraphRuntime | None = None,
        artifact_store: Any | None = None,
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
        self.prompt_adapter = PromptContextAdapter()

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
    ) -> RunOutcome:
        if mode not in {"plan_only", "verify"}:
            raise ValueError("mode must be plan_only or verify")
        run_id = run_id or f"run-{uuid.uuid4().hex}"
        run = self.store.create_run(run_id=run_id, tenant_id=tenant_id, idempotency_key=idempotency_key, mode=mode, payload={"proposal": proposal, "mode": mode})
        run_id = run.run_id
        checkpoint = self.store.checkpoint(run_id, tenant_id)
        if run.state in {"plan_only", "verified", "quota_paused", "budget_exceeded", "failed", "rejected"}:
            return self._outcome(run, checkpoint)
        ledger = TokenBudgetLedger(BudgetPolicy.local_lite(mode), quota_limit=quota_limit)
        if run.state == "queued":
            run = self.store.transition(run_id, tenant_id, "running", payload={"node": "intake"})
        values: dict[str, Any] = {"proposal": proposal, "mode": mode}
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
            return self._verify(run_id, tenant_id, proposal, parsed.requirements, evidence, plan, values, approval, ledger)
        except PromptInjectionDetected as exc:
            return self._finish_rejected(run_id, tenant_id, values, str(exc))
        except (ValueError, FileNotFoundError) as exc:
            return self._finish_failed(run_id, tenant_id, (), (), None, values, str(exc))

    def _verify(self, run_id: str, tenant_id: str, proposal: str, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan, values: dict[str, Any], approval: ApprovalToken | None, ledger: TokenBudgetLedger) -> RunOutcome:
        del proposal, ledger
        checkpoint = self.store.checkpoint(run_id, tenant_id)
        if approval is None:
            token = self.store.issue_approval(run_id=run_id, tenant_id=tenant_id, scopes=("patch", "deliver"), expires_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat())
            values["approval_id"] = token.token_id
            self._checkpoint(run_id, tenant_id, "human_approval", values)
            run = self.store.transition(run_id, tenant_id, "waiting_approval", payload={"node": "human_approval", "approval_id": token.token_id})
            return RunOutcome(run, requirements, evidence, plan, token, self.store.report(run_id, tenant_id))
        try:
            consumed = self.store.consume_approval(approval.token_id, run_id=run_id, tenant_id=tenant_id, scope="patch")
        except InvalidApproval as exc:
            return self._finish_rejected(run_id, tenant_id, values, str(exc), requirements, evidence, plan)
        self._event(run_id, tenant_id, "approval.consumed", {"token_id": consumed.token_id, "scope": "patch"})
        self.store.transition(run_id, tenant_id, "running", payload={"node": "patch", "approval_id": consumed.token_id})
        self._checkpoint(run_id, tenant_id, "patch", values)
        if self.sandbox is None:
            from services.sandbox_worker import DeterministicSandbox

            self.sandbox = DeterministicSandbox()
        simulation = self.sandbox.apply(plan, approval=consumed)
        if not simulation.success:
            retry = self.sandbox.apply(plan, approval=consumed, retry=True)
            if not retry.success:
                return self._finish_failed(run_id, tenant_id, requirements, evidence, plan, values, "sandbox patch failed")
        self._checkpoint(run_id, tenant_id, "test", values)
        test_result = self.sandbox.test(plan)
        if not test_result.success:
            return self._finish_failed(run_id, tenant_id, requirements, evidence, plan, values, "deterministic tests failed")
        self._checkpoint(run_id, tenant_id, "evaluate", values)
        report = self._report(run_id, "verified", requirements, evidence, plan, latency_ms=0, usage=self.store.usage(run_id, tenant_id), approval_bypass=0, secret_leakage=0, prompt_injection=0)
        artifact = self._persist_artifact(run_id, requirements, evidence, plan, report)
        self.store.save_report(report, tenant_id)
        self._checkpoint(run_id, tenant_id, "report", values)
        self._event(run_id, tenant_id, "delivery.prepared", {"approval_token_id": consumed.token_id, "artifact_hash": self._artifact_hash(plan)})
        if artifact:
            self._event(run_id, tenant_id, "artifact.persisted", artifact)
        run = self.store.transition(run_id, tenant_id, "verified", payload={"plan_id": plan.plan_id, "report_persisted": True})
        return RunOutcome(run, requirements, evidence, plan, consumed, self.store.report(run_id, tenant_id))

    def _finish_plan_only(self, run_id: str, tenant_id: str, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan, values: dict[str, Any], reason: str | None) -> RunOutcome:
        report = self._report(run_id, "plan_only", requirements, evidence, plan, latency_ms=0, usage=self.store.usage(run_id, tenant_id), approval_bypass=0, secret_leakage=0, prompt_injection=0, reason=reason)
        artifact = self._persist_artifact(run_id, requirements, evidence, plan, report)
        self.store.save_report(report, tenant_id)
        self._checkpoint(run_id, tenant_id, "report", values)
        if artifact:
            self._event(run_id, tenant_id, "artifact.persisted", artifact)
        run = self.store.transition(run_id, tenant_id, "plan_only", payload={"plan_id": plan.plan_id, "report_persisted": True, "reason": reason or "plan-only requested"})
        return RunOutcome(run, requirements, evidence, plan, None, self.store.report(run_id, tenant_id))

    def _finish_failed(self, run_id: str, tenant_id: str, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan | None, values: dict[str, Any], reason: str) -> RunOutcome:
        if plan is None:
            plan = None
        run = self.store.transition(run_id, tenant_id, "failed", payload={"reason": reason}, error=reason)
        return RunOutcome(run, requirements, evidence, plan, None, self.store.report(run_id, tenant_id))

    def _finish_rejected(self, run_id: str, tenant_id: str, values: dict[str, Any], reason: str, requirements: tuple[Any, ...] = (), evidence: tuple[EvidenceReference, ...] = (), plan: Plan | None = None) -> RunOutcome:
        run = self.store.transition(run_id, tenant_id, "rejected", payload={"reason": reason}, error=reason)
        self._checkpoint(run_id, tenant_id, "report", values)
        return RunOutcome(run, requirements, evidence, plan, None, self.store.report(run_id, tenant_id))

    def _budget_stop(self, run: RunLifecycle, tenant_id: str, status: str, reason: str, values: dict[str, Any], requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...]) -> RunOutcome:
        target = "quota_paused" if status == "quota_paused" else "budget_exceeded"
        current = self.store.transition(run.run_id, tenant_id, target, payload={"reason": reason})
        self._checkpoint(run.run_id, tenant_id, "report", values)
        return RunOutcome(current, requirements, evidence, None, None, None)

    def _report(self, run_id: str, status: str, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan, *, latency_ms: int, usage: tuple[UsageRecord, ...], approval_bypass: int, secret_leakage: int, prompt_injection: int, reason: str | None = None) -> ReleaseReport:
        from services.evaluation import build_release_report

        return build_release_report(run_id=run_id, status=status, requirements=requirements, evidence=evidence, plan=plan, usage=usage, latency_ms=latency_ms, approval_bypass=approval_bypass, secret_leakage=secret_leakage, prompt_injection=prompt_injection, reason=reason)

    def _persist_artifact(self, run_id: str, requirements: tuple[Any, ...], evidence: tuple[EvidenceReference, ...], plan: Plan, report: ReleaseReport) -> Mapping[str, Any] | None:
        if self.artifact_store is None:
            return None
        try:
            artifact = self.artifact_store.write(
                run_id,
                {
                    "requirements": [asdict(item) for item in requirements],
                    "evidence": [asdict(item) for item in evidence],
                    "plan": asdict(plan),
                    "report": asdict(report),
                },
            )
        except OSError as exc:
            raise ValueError("review artifact could not be persisted") from exc
        return {"artifact_id": artifact.artifact_id, "path": artifact.path, "digest": artifact.digest, "bytes_written": artifact.bytes_written}

    def _outcome(self, run: RunLifecycle, checkpoint: Mapping[str, Any] | None) -> RunOutcome:
        if not checkpoint:
            return RunOutcome(run)
        values = checkpoint.get("state", {})
        return RunOutcome(run, plan=None, report=self.store.report(run.run_id, run.tenant_id))

    def _checkpoint(self, run_id: str, tenant_id: str, node: str, values: Mapping[str, Any]) -> None:
        self.store.save_checkpoint(run_id, tenant_id, node, values)
        if self.graph_runtime is not None:
            self.graph_runtime.checkpoint(redact(values), thread_id=run_id, node=node)

    def _event(self, run_id: str, tenant_id: str, event: str, payload: Mapping[str, Any]) -> None:
        self.store.append_event(run_id, tenant_id, event, payload)
        if self.tracer is not None:
            self.tracer.record(event, {"run_id": run_id, **redact(payload)})

    @staticmethod
    def _plan_json(plan: Plan) -> dict[str, Any]:
        return {"plan_id": plan.plan_id, "runtime": plan.runtime, "mode": plan.mode, "supported_runtime": plan.supported_runtime, "valid_references": plan.valid_references}

    @staticmethod
    def _artifact_hash(plan: Plan) -> str:
        return hashlib.sha256(json.dumps(ProposalVerifiedWorkflow._plan_json(plan), sort_keys=True).encode()).hexdigest()
