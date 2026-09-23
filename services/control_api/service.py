from __future__ import annotations

from agent_platform.contracts import ApprovalToken
from services.agent_orchestrator.workflow import ProposalVerifiedWorkflow, RunOutcome


class LocalControlService:
    def __init__(self, workflow: ProposalVerifiedWorkflow) -> None:
        self.workflow = workflow

    def submit(self, *, tenant_id: str, proposal: str, mode: str, idempotency_key: str) -> RunOutcome:
        return self.workflow.run(tenant_id=tenant_id, proposal=proposal, mode=mode, idempotency_key=idempotency_key)

    def resume(self, *, tenant_id: str, proposal: str, mode: str, idempotency_key: str, approval: ApprovalToken) -> RunOutcome:
        return self.workflow.run(tenant_id=tenant_id, proposal=proposal, mode=mode, idempotency_key=idempotency_key, approval=approval)
