"""Replaceable product packs.

Provides a small registry that resolves the active pack by name so the
HTTP control plane and the orchestrator do not import a concrete pack
directly. A different pack swap becomes a registry update, not an
edit to the consumer.
"""

from __future__ import annotations

from typing import Type

from .proposal_to_verified_change import (
    ParsedProposal,
    PromptInjectionDetected,
    ProposalToVerifiedChangePack,
    RepositoryIndex,
    UnauthorizedPath,
)


_PROJECT_PACK_REGISTRY: dict[str, Type[ProposalToVerifiedChangePack]] = {
    "proposal_to_verified_change": ProposalToVerifiedChangePack,
}


def register_project_pack(name: str, pack_cls: Type[ProposalToVerifiedChangePack]) -> None:
    """Register a concrete pack class under ``name``."""
    if not issubclass(pack_cls, ProposalToVerifiedChangePack):
        raise TypeError("registered class must subclass ProposalToVerifiedChangePack")
    _PROJECT_PACK_REGISTRY[name] = pack_cls


def resolve_project_pack(name: str = "proposal_to_verified_change") -> Type[ProposalToVerifiedChangePack]:
    """Return the pack class registered under ``name``."""
    if name not in _PROJECT_PACK_REGISTRY:
        raise KeyError(f"unknown project pack: {name}")
    return _PROJECT_PACK_REGISTRY[name]


__all__ = [
    "ParsedProposal",
    "PromptInjectionDetected",
    "ProposalToVerifiedChangePack",
    "RepositoryIndex",
    "UnauthorizedPath",
    "register_project_pack",
    "resolve_project_pack",
]
