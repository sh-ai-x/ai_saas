# Production-Ready AI SaaS Foundation — Cost-Tiered MSA

## 1. Frame

- **Goal:** Ship a reusable AI SaaS foundation that starts from the `mysaas` vertical slice and provides Google auth, tenant/admin boundaries, provider-neutral billing, metering, durable agent runs, and a low-cost deployment path.
- **Target user:** A fullstack AI engineer building a portfolio or early enterprise AI product with a near-zero fixed infrastructure budget.
- **Situation:** The current baseline has a working Next.js/Better Auth/Drizzle/Neon/Inngest shape, but its auth, admin, credit, payment, worker, and deployment contracts are not yet hardened into a reusable foundation.

## 2. Validate

### Evidence

1. **Existing implementation signal:** `../mysaas/my-saas` already contains Next.js 16.3, Better Auth, Drizzle, Neon-compatible PostgreSQL, Inngest, admin routes, credit transactions, and provider checkout paths.
2. **Approved product signal:** The approved foundation proposal requires Google OAuth, multi-tenancy, admin operations, metering, Toss/Lemon Squeezy/mock payments, agent execution, observability, and reproducible deployment.
3. **Cost/architecture signal:** Official Vercel, Inngest, Cloudflare, and AWS documentation supports free-tier hosting for demos, bounded managed workflows, and usage-based Fargate Spot workers; the plan therefore separates free portfolio mode from optional low-cost worker mode.

### Quantified value

- `LTV_per_user`: 1,000 value units per adopted template
- `reachable_users_year1`: 10 portfolio users or derivative projects
- `total_cost`: 2,000 value units of implementation and low-volume infrastructure
- `value_score = (1,000 × 10) / 2,000 = 5.0`

### Ambiguity

- `ambiguity_score: 3/10`
- Locked decisions: `mysaas` is the initial baseline; Neon + Drizzle + Better Auth + Vercel/Cloudflare Free are the initial web/data options; Inngest is the default workflow path; Fargate Spot is an optional worker-only path; Toss and Lemon Squeezy use Ports-and-Adapters.

## 3. Non-goals

1. **Domain-specific agent workflows:** The foundation exposes run/tool/checkpoint contracts only. If requested, add a domain module after the foundation acceptance gates pass.
2. **Always-on paid infrastructure:** No paid Vercel/Cloudflare plan, ALB, NAT Gateway, Redis cluster, multi-AZ worker fleet, or per-service database is provisioned by this plan. If requested, create a separate scale ADR and budget gate.
3. **Live payment processing in local development:** Local and test environments use the mock adapter and provider sandboxes. If a real charge is requested locally, reject the scope and require a sandbox environment.
4. **Automatic physical extraction of every logical service:** The first build may use a modular monolith; only the worker boundary is eligible for the low-cost Fargate Spot profile.

## 4. Phase plan

Phase directory: `phases/ai-saas-foundation/`

| Step | Name | Dependency | Outcome |
|---:|---|---|---|
| 0 | baseline-contracts | none | Repository skeleton, contract packages, environment/profile rules, and runnable checks |
| 1 | identity-tenant-admin | 0 | Google session, tenant/RBAC boundary, admin operations, and audit contract |
| 2 | billing-adapters-ledger | 0, 1 | Ports-and-Adapters billing, Toss/Lemon/mock contracts, webhook inbox, and atomic ledger |
| 3 | run-worker-streaming | 0, 1, 2 | Run state machine, metering reservation, Inngest baseline, optional worker boundary, and SSE replay |
| 4 | low-cost-deployment-observability | 0–3 | Free profile, optional Fargate Spot worker profile, OTel/redaction, CI, and evaluator evidence |

The authoritative step state is `phases/ai-saas-foundation/index.json`.

## 5. Acceptance criteria

- **REQ-1:** A clean checkout can start the local foundation with Docker and validate its contract/configuration profile without paid cloud resources.
- **REQ-2:** Google login/session, tenant scope, admin authorization, reason-required mutation, before/after audit, and cross-tenant denial are covered by tests or executable contract checks.
- **REQ-3:** Toss, Lemon Squeezy, and mock payment adapters implement shared capability ports; raw provider events are verified, deduplicated, normalized, and applied to an atomic ledger exactly once.
- **REQ-4:** A run reserves credits before model work, persists state/checkpoint events, supports SSE replay/reconnect, and handles worker interruption through idempotent retry.
- **REQ-5:** The free profile has explicit quota pause behavior; the optional AWS profile uses Fargate Spot only for checkpointed worker tasks without ALB/NAT or inbound worker access; CI and evidence artifacts are reproducible.

## 6. Handoff to build

The plan is ready for `/dev-kit:build` in dependency order. Build must preserve
the copied SOT under `docs/sot/` as tracked project documentation, avoid
secrets, and keep every step within its declared ownership and acceptance
contract. After build, run `/dev-kit:babysit-pr` with the Ralph unattended flags
and finish at the human merge boundary.

## 7. Real integration extension — Ralph plan

The local vertical slice remains the default no-credential mode, but the
foundation now also defines a real integration path. Credentials are injected
only at runtime; no provider secret or authorization code is committed. A
provider is enabled only after its configuration validator passes.

| Step | Name | Dependency | Outcome |
|---:|---|---|---|
| 7 | integration-contracts-and-validators | 6 | Versioned auth/payment/agent API contracts, fail-closed environment validation, and deterministic provider fixtures |
| 8 | google-oauth-provider | 7 | Server-side Google authorization URL, code exchange, token/userinfo verification, session cookie, and callback route |
| 9 | sandbox-payment-provider | 7 | Toss or Lemon Squeezy sandbox checkout/confirmation/webhook routes, one-provider selection, and exactly-once ledger effects |
| 10 | agent-provider-runtime | 7 | Provider-neutral model port with OpenAI, Anthropic, and Gemini HTTP adapters, bounded usage, redaction, and run integration |
| 11 | setup-guide-console | 8–10 | Dedicated `/guides` Markdown editor, hierarchical left sidebar with separate Toss/Lemon Squeezy pages, environment examples, and a link back to the console |
| 12 | integration-e2e-verification | 8–11 | Contract, config, adapter, API, browser, and sandbox fixture verification with step output evidence |
| 13 | neon-production-database | 7, 12 | Linked Neon production branch, committed policy, ignored connection env flow, read-only connectivity evidence, and web setup guide |
| 14 | sandbox-checkout-handoff | 9, 11 | Provider-correct Toss browser SDK handoff, Lemon Squeezy store/variant checkout, safe redirect routes, and adapter fixture coverage |

### Real integration constraints

- Google OAuth uses the authorization-code web-server flow. The browser sees
  only the authorization URL and session result; client secrets, access tokens,
  ID tokens, and codes stay server-side.
- `PAYMENT_PROVIDER` selects exactly one provider. `APP_ENV=local|staging`
  forces sandbox/test mode; production requires an explicit live deployment
  approval. Toss and Lemon Squeezy remain adapter-compatible but are never
  enabled simultaneously.
- `AGENT_PROVIDER=local` is the deterministic default. `openai`, `anthropic`,
  and `gemini` require a runtime-injected API key and bounded model settings.
  Provider errors fail the run without retry storms or silent paid fallback.
- Every externally reachable callback/webhook has a versioned API contract,
  raw-body verification, idempotency, and a replayable test fixture.
- The web GUIDE is a presentation layer over these contracts. It does not
  store secrets, call providers directly, or bypass the existing console API.

### New acceptance criteria

- **REQ-6:** Invalid/missing integration settings fail before the server binds;
  no mixed live providers, production mock payments, or unbounded agent model
  calls are accepted.
- **REQ-7:** A configured Google client can complete authorization-code exchange
  and create a server-owned session; invalid state, issuer, audience, expiry,
  or unverified email is rejected.
- **REQ-8:** A configured Toss or Lemon Squeezy sandbox can create a pending
  order, confirm/reconcile it, verify a webhook, and apply credit exactly once.
- **REQ-9:** A configured Agent provider can execute a bounded run through the
  same metering/checkpoint/SSE path; provider credentials never enter output or
  telemetry.
- **REQ-10:** The browser contains a dedicated `/guides` route with
  category-based setup guides for local, Google, separate Toss and Lemon
  Squeezy payments, Agent, verification, and operations; the sidebar links the
  guides back to the `/` console without breaking the local profile.
- **REQ-11:** The cloud database setup uses the linked Neon PostgreSQL
  production branch with no committed credentials; `neon.ts`, policy plan/
  deploy, read-only connectivity, ignored env injection, and a web-visible
  Markdown setup guide are reproducible.
- **REQ-12:** A real sandbox checkout receives only browser-safe handoff data:
  Toss uses the client SDK with server-owned amount/order/redirect values, and
  Lemon Squeezy uses configured store/variant JSON:API relationships with
  signed-webhook-authoritative entitlement. Provider-specific fixtures reject
  missing or mismatched checkout identity before any ledger effect.

## 8. Admin-controlled product and pricing extension — `mysaas` reference

The next build slice follows the useful boundaries already present in
`../mysaas/my-saas`: a dedicated admin area, plans managed through CRUD routes,
provider-specific product references, and a public pricing surface. The
foundation normalizes those ideas into relational tables rather than keeping
all prices in a single JSON user record or hardcoded landing-page components.

### Data-first decisions

- Neon PostgreSQL is the cloud source of truth; Drizzle ORM owns the schema and
  migrations in `apps/web/db` and `apps/web/drizzle`.
- The active catalog selects exactly one billing mode: `one_time` or
  `subscription`. Subscription plans may expose monthly and yearly options;
  one-time products expose only a one-time option. A $290 annual subscription
  and a $79 one-time product therefore belong to separate product policies and
  are never presented as two payment choices for the same active catalog.
- Toss and Lemon Squeezy are adapters behind the same checkout contract. Only
  one live provider is selected per environment; `mock` remains the local
  default.
- Provider credentials never enter PostgreSQL. Admin settings store only
  safe public identifiers and a secret reference such as an environment-key
  name.
- Public landing, authenticated user app, and admin console are separate route
  surfaces. Admin mutations require a server-side admin guard and emit audit
  context.

### Phase extension

| Step | Name | Dependency | Outcome |
|---:|---|---|---|
| 15 | pricing-data-model | 13, 14 | Drizzle/Neon schema, migration, seed catalog, repository contract, and pricing SOT |
| 16 | public-app-admin-surfaces | 15 | Separate landing, user app, admin layout, pricing CRUD UI, and DB-backed public catalog |
| 17 | payment-mode-adapters | 15, 16 | One-time/subscription checkout selection and admin provider settings using shared adapters |
| 18 | pricing-verification | 15–17 | Schema, API, browser, and local fallback verification with step output evidence |

### New requirements

- **REQ-13:** The database has normalized `pricing_catalog_settings`,
  `pricing_plans`, `pricing_options`,
  `payment_provider_settings`, `payment_orders`, `subscriptions`,
  `billing_events`, and `admin_audit_events` tables with tenant-safe keys,
  provider identity constraints, and no committed secret values.
- **REQ-14:** Public pricing is read from the active catalog; the landing page
  does not expose admin controls, while `/app` and `/admin` have distinct
  navigation and layouts.
- **REQ-15:** Admins can create, edit, activate, order, and archive plans and
  pricing options; changes validate one-time/monthly/yearly semantics and are
  auditable with actor, reason, and before/after data.
- **REQ-16:** Checkout accepts a pricing-option identity, not a client-supplied
  amount. The server resolves amount, currency, mode, interval, and provider,
  verifies the option matches the active catalog billing mode, then returns
  only browser-safe handoff data.
- **REQ-17:** Local development works without `DATABASE_URL` through a clearly
  marked in-memory seed fallback; configured Neon mode uses Drizzle queries and
  a committed migration. The fallback is never silently used in production.
- **REQ-18:** The schema-first implementation is verified by typecheck,
  migration/config checks, API contract tests, and a browser smoke path for
  landing → app → admin → pricing mode selection.
