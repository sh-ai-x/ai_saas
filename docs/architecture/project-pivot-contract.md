---
doc_id: project-pivot-contract
domain: architecture
purpose: Keep the reusable agent platform separable from any project-specific workflow.
source_of_truth: contract
owner: platform-engineering
last_reviewed: 2026-09-21
change_impact: high
---

# Project Pivot Contract

## Decision

The product is split into a reusable **Agent Platform Kernel** and a replaceable
**Project Pack**. The Proposal-to-Verified-Change workflow is one Project Pack,
not the identity of the platform kernel.

```text
                    Web / Control API
                           |
                    Agent Platform Kernel
     contracts · policy · run state · checkpoint · approval
     metering · audit · sandbox boundary · evaluation ledger
                           |
                    Project Pack boundary
     profile · prompts · requirement extensions · tools · evaluators
     repository adapter · execution adapter · delivery adapter
```

The kernel must compile, run its contract tests, and expose a deterministic
health check when no Project Pack is installed. A Project Pack may be added,
removed, or replaced through a versioned registry and capability manifest.

## Stable kernel contracts

The following objects and behaviors are product-neutral:

- `Run`, `RunEvent`, `Checkpoint`, `Approval`, `PolicyDecision`;
- `Requirement`, `EvidenceRef`, `Plan`, `Patch`, `TestResult`, `EvaluationReport`;
- tenant/project authorization, idempotency, quota/metering, audit, retention;
- LangGraph lifecycle, checkpoint/resume, cancellation, retry, and SSE replay;
- LangChain structured-output boundary and typed tool protocol;
- LangSmith trace/evaluation sink protocol with redaction;
- sandbox request/response protocol and resource policy;
- Local Lite and Production MSA runtime profiles;
- metric formulas, event vocabulary, release report, and failure states.

The kernel never imports a project name, project prompt, domain entity, domain
tool, repository language rule, or project-specific evaluator.

## Replaceable Project Pack

Each pack implements a versioned manifest:

```yaml
pack_id: proposal-to-verified-change
pack_version: 1
kernel_api: 1
capabilities:
  - requirement_parser
  - repository_evidence
  - patch_verification
  - git_ci_delivery
adapters:
  repository: path-symbol
  execution: node-pnpm
  delivery: git-ci
evaluation_dataset: proposal-to-verified-change-v1
```

A pack owns only:

- project-specific requirement and acceptance-criteria extensions;
- prompt templates and model-output schemas extending kernel schemas;
- repository/profile rules and retrieval ranking;
- explicitly registered read/write/network tools;
- execution and delivery adapters;
- gold, adversarial, and regression fixtures;
- UI copy and report sections that are not kernel fields.

Pack capabilities are allowlisted. An absent capability causes a typed
`unsupported` or `plan_only` result; it cannot cause the kernel to guess or
silently grant authority.

## Dependency and import rules

```text
kernel  -> kernel contracts, ports, policy, storage interfaces
pack    -> kernel contracts and ports
adapter -> a port implementation; never kernel internals
web     -> versioned API/SSE contracts; never pack internals
```

The kernel may not import `project-packs/*`. The web and API may resolve a pack
only through the registry. Cross-pack imports are forbidden. A project pack
must not write kernel tables directly; it calls versioned use cases or emits
versioned events.

## Port inventory

| Port | Kernel responsibility | Replaceable implementation |
| --- | --- | --- |
| `ModelPort` | timeout, budget, structured output, redaction | provider/model adapter |
| `RepositoryPort` | authorization, evidence shape, snapshot identity | Git/local upload/provider connector |
| `ProfilePort` | capability detection and confirmation | Node, Python, future runtime pack |
| `ExecutionPort` | bounded command protocol and test evidence | Local Lite subprocess, Production Sandbox |
| `DeliveryPort` | signed request, policy decision, idempotency | Git PR, CI dispatch, future deployment provider |
| `TracePort` | redaction and correlation | LangSmith or another conforming sink |
| `EvaluationPort` | metric execution and report persistence | deterministic evaluator, LangSmith evaluator |
| `StoragePort` | run/checkpoint/event/evaluation persistence | SQLite Local Lite, PostgreSQL Production |
| `IdentityPolicyPort` | tenant, role, tool, and data authorization | product auth/admin integration |

## Pivot procedure

To pivot from Proposal-to-Verified-Change to another project:

1. keep the kernel and its contract/evaluation/security tests;
2. add a new `project-packs/<pack-id>/` implementation;
3. add the pack manifest, prompts, adapters, and versioned datasets;
4. run kernel contract tests plus the new pack conformance suite;
5. enable the pack through configuration/registry, never source-code branching;
6. remove the old pack and its data only after retention/export policy passes.

The kernel should remain deployable during the transition. A project pivot is
therefore a pack replacement and dataset migration, not a rewrite of auth,
metering, run state, safety, or infrastructure boundaries.

## Verification

Every pack must pass:

- schema compatibility and serialization tests;
- authorization and tenant-isolation contract tests;
- tool capability and approval tests;
- deterministic metric/evaluation conformance;
- Local Lite resource checks and Production MSA integration checks;
- prompt-injection, secret-redaction, path, process, and network fixtures;
- remove-pack test proving the kernel still builds and health-checks alone.

