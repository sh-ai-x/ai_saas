# Documentation map

Use this page to find the current documentation. User-facing setup and product
guides are kept separate from engineering contracts and dev-kit execution
history.

## Start here

- [Project README](../README.md) — install, local start, Docker, verification,
  and integration entry points.
- [Setup guide index](setup-guides/README.md) — operator-facing integration and
  local runtime guides.
- [AI Change Impact Workbench](setup-guides/09-ai-change-impact-workbench.md) —
  proposal-to-code review, bounded evidence, and LangSmith observability.

## Engineering contracts

- [SOT index](sot/00-index.md) — route to architecture, security, agent, billing,
  integration, and verification contracts.
- [Service catalog](service-catalog.md) — ownership and runtime boundaries.
- [Codebase map](CODEBASE-MAP.md) — generated repository map instructions.
- [ADR: worktree ports and database isolation](adr/0002-worktree-port-and-database-isolation.md)
  — local Docker isolation rules.

## Operations and troubleshooting

- [Neon database](neon-database.md) — database linking and connection checks.
- [Google OAuth troubleshooting](troubleshooting/google-oauth-local.md) — local
  redirect and environment diagnostics.

## Maintenance boundary

The former proposal archive contains no user-facing proposal pages. Superseded
proposal HTML/YAML artifacts were removed; the active FAQ provider design record
is retained only because the corresponding phase execution records reference it.
Current Workbench product decisions live in `PRD.md`, the setup guides, SOT
contracts, and ADRs. Files under `phases/` are dev-kit execution records and are
retained for implementation traceability, not presented as user-facing setup
documentation.
