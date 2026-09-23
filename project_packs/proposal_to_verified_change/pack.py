"""Proposal parsing and evidence/plan generation for one replaceable product."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Sequence

from agent_platform.contracts import EvidenceReference, Plan, PlanStep, Requirement
from agent_platform.ports import ProjectPackPort

from .index import RepositoryIndex, UnauthorizedPath


class PromptInjectionDetected(ValueError):
    pass


@dataclass(frozen=True)
class ParsedProposal:
    requirements: tuple[Requirement, ...]
    runtime: str
    references: tuple[tuple[str, int, int | None, str | None], ...]
    incomplete: bool


class ProposalToVerifiedChangePack(ProjectPackPort):
    """Pure product logic; it never opens the kernel database."""

    SUPPORTED_RUNTIMES = frozenset({"python", "python3", "javascript", "typescript", "node", "react", "nextjs"})
    _injection = re.compile(r"(?i)(ignore\s+(?:all\s+)?previous instructions|reveal\s+(?:the\s+)?system prompt|exfiltrat|send\s+secrets|disable\s+safety)")
    _reference = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.(?:py|js|ts|tsx|json|md|yaml|yml))(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?(?:\s+symbol[:=](?P<symbol>[A-Za-z_][A-Za-z0-9_]*))?")

    def __init__(self, index: RepositoryIndex) -> None:
        self.index = index.build()

    def parse_proposal(self, proposal: str) -> ParsedProposal:
        if not isinstance(proposal, str) or not proposal.strip():
            raise ValueError("proposal must be non-empty")
        if self._injection.search(proposal):
            raise PromptInjectionDetected("proposal contains an unsafe instruction")
        runtime_match = re.search(r"(?im)^\s*(?:runtime|language)\s*[:=]\s*([A-Za-z0-9_.-]+)", proposal)
        runtime = runtime_match.group(1).lower() if runtime_match else "python"
        requirements: list[Requirement] = []
        current: Requirement | None = None
        for line in proposal.splitlines():
            match = re.match(r"^\s*(REQ-\d+)\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
            if match:
                current = Requirement(match.group(1).upper(), match.group(2), match.group(2), source_text=line)
                requirements.append(current)
        if not requirements:
            first = next((line.strip() for line in proposal.splitlines() if line.strip()), "proposal")
            requirements.append(Requirement("REQ-1", first[:120], proposal[:1000], source_text=first))
        refs = tuple((m.group("path"), int(m.group("start") or 1), int(m.group("end") or m.group("start") or 1), m.group("symbol")) for m in self._reference.finditer(proposal))
        return ParsedProposal(tuple(requirements), runtime, refs, incomplete=(not bool(refs) or "incomplete" in proposal.lower()))

    def parse(self, proposal: str) -> tuple[Requirement, ...]:
        return self.parse_proposal(proposal).requirements

    def evidence(self, proposal: str) -> tuple[EvidenceReference, ...]:
        self.index.refresh()
        parsed = self.parse_proposal(proposal)
        refs = parsed.references
        if not refs and self.index.files():
            first = self.index.files()[0]
            refs = ((first.path, 1, min(3, len(first.lines)), None),)
        evidence: list[EvidenceReference] = []
        for requirement in parsed.requirements:
            for path, start, end, symbol in refs:
                try:
                    start_line, end_line, content_hash = self.index.evidence(path, start, end, symbol)
                    evidence.append(EvidenceReference(requirement.requirement_id, path, start_line, end_line, content_hash, symbol, True, True))
                except (UnauthorizedPath, FileNotFoundError, ValueError):
                    invalid_hash = hashlib.sha256(path.encode()).hexdigest()
                    evidence.append(EvidenceReference(requirement.requirement_id, path, max(1, start), max(1, end), invalid_hash, symbol, False, False))
        return tuple(evidence)

    def revalidate_evidence(self, evidence: Sequence[EvidenceReference]) -> tuple[EvidenceReference, ...]:
        """Recompute each bounded reference against the current checkout."""

        self.index.refresh()
        result: list[EvidenceReference] = []
        for item in evidence:
            try:
                start, end, current_hash = self.index.current_evidence(item.path, item.start_line, item.end_line, item.symbol)
                result.append(EvidenceReference(item.requirement_id, item.path, start, end, current_hash, item.symbol, item.authorized, item.authorized and current_hash == item.content_hash))
            except (UnauthorizedPath, FileNotFoundError, ValueError):
                result.append(EvidenceReference(item.requirement_id, item.path, item.start_line, item.end_line, item.content_hash, item.symbol, False, False))
        return tuple(result)

    def plan(self, requirements: Sequence[Requirement], evidence: Sequence[EvidenceReference], mode: str) -> Plan:
        if mode not in {"plan_only", "verify"}:
            raise ValueError("mode must be plan_only or verify")
        runtime = "python"
        valid_references = bool(evidence) and all(item.authorized and item.valid for item in evidence)
        steps = tuple(
            PlanStep(
                step_id=f"step-{index}",
                title=requirement.title,
                action=f"implement {requirement.requirement_id}: {requirement.description}",
                evidence=tuple(item for item in evidence if item.requirement_id == requirement.requirement_id),
                impact="high",
                commands=(),
            )
            for index, requirement in enumerate(requirements, 1)
        )
        plan_id = "plan-" + hashlib.sha256(("|".join(requirement.requirement_id for requirement in requirements) + str(evidence)).encode()).hexdigest()[:16]
        return Plan(plan_id, tuple(requirements), steps, runtime, mode, True, None, valid_references)

    def build_plan(self, proposal: str, mode: str) -> Plan:
        parsed = self.parse_proposal(proposal)
        evidence = self.evidence(proposal)
        supported = parsed.runtime in self.SUPPORTED_RUNTIMES
        requested_mode = mode if supported else "plan_only"
        base = self.plan(parsed.requirements, evidence, requested_mode)
        return Plan(base.plan_id, base.requirements, base.steps, parsed.runtime, requested_mode, supported, None if supported else f"unsupported runtime: {parsed.runtime}", base.valid_references)
