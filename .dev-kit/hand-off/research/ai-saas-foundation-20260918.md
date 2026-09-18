---
session: ai-saas-foundation-20260918
stage: RESEARCH_GATE
status: pending_approval
source_of_truth: user-proposal-plus-copied-sot
---

# Research Gate — Production-Ready AI SaaS Foundation

## Goal

Create a production-minimal, MSA-oriented full-stack AI SaaS foundation that
can be extended with domain-specific agent products without rebuilding Google
authentication, multi-tenancy, long-running execution, billing, metering,
admin operations, observability, and deployment foundations.

This Ralph run includes Google OAuth login, an authenticated admin page,
Toss Payments and Lemon Squeezy adapter boundaries, and a non-production mock
payment path. It does not treat payment success redirects or mock actions as
entitlement truth.

## Evidence already available

1. The user-provided proposal defines the required product surface: Google or
   OAuth login, organization/RBAC/RLS, async agent execution, token metering,
   credits, provider webhooks, AWS/Vercel deployment, OTel, and a reusable
   scaffold.
2. The copied local SOT contract `auth-google-oauth` requires server-side
   authorization-code validation, exact redirect URIs, subject-ID mapping,
   and fail-closed callback handling.
3. The copied local SOT contracts `admin-operations-audit`,
   `billing-provider-adapter-architecture`, and
   `billing-payment-webhooks-ledger` require privileged server-side admin
   operations, append-only audit events, provider adapters, durable inbox
   dedupe, and transactional ledger effects.
4. The copied provider contracts `billing-provider-toss-payments` and
   `billing-provider-lemon-squeezy` define provider-specific confirmation,
   idempotency, raw-body/signature or query verification, subscription state,
   replay, and reconciliation behavior.

## Proposed implementation boundary

The first deliverable is a deployable foundation, not a domain-specific AI
product. Service boundaries are:

- web-console
- api-gateway
- identity-tenant
- project-service
- run-service
- agent-worker
- metering-billing
- admin-operations
- observability

The initial deployment may use one PostgreSQL cluster with schema ownership,
but services communicate through versioned contracts and durable events. A
mock payment adapter implements the same ports and ledger/audit path as real
providers, and is forbidden in production configuration.

## Proposed dependency order

1. Contracts, service topology, Google OAuth, RBAC, provider ports, and audit
   schema.
2. Durable run lifecycle, queue/checkpoint recovery, pending billing orders,
   provider inbox, admin read/mutation APIs, and mock scenarios.
3. Deterministic tests, evaluator E2E flows, provider replay/concurrency tests,
   RLS isolation, and billing ledger gates.
4. OTel correlation, secret/payment redaction, progress artifacts, and
   session handoff.
5. Production hardening, test/live key separation, mock gating, deployment,
   rollback, and security review.

## Ambiguities for proposal and plan gates

- A1: Neon versus Supabase as the launch database/auth baseline.
- A2: Redis/Celery or SQS as the queue baseline.
- A3: Whether the first release enables Toss, Lemon Squeezy, or both.
- A4: Whether mock payment controls are local-only or also available in a
  staging support console.
- A5: Admin MFA/step-up authentication and least-privilege role model.
- A6: Whether the first release is a single repository with independent
  deployable services or physically split repositories.

## Research Gate recommendation

Approve the research boundary and carry A1–A6 into the Proposal and Plan
gates as explicit decisions. No application code has been written in this
gate.
