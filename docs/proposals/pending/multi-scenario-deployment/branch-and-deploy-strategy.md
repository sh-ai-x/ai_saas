# Branch + Deployment Strategy

> Companion to [`docs/proposals/pending/multi-scenario-deployment/aws-hybrid-architecture.yaml`](./aws-hybrid-architecture.yaml). Covers the git topology and the mapping from branch → environment. The Lang* (LangChain/LangGraph/LangSmith) and Ollama/local-LLM work is deferred; this document scopes only branch + deploy for the scenarios shipped today.

---

## 1. Branch taxonomy

GitHub Flow with type-prefixed branches and short-lived lives.

| Prefix | Lifetime | Source | Merges into | Auto-deploys to |
|---|---|---|---|---|
| `main` | permanent | — | — | **Production** (Vercel + Fly.io foundation) |
| `feat/<slug>` | days | `main` | `main` via PR | **PR preview** (Vercel + Fly preview slot) |
| `fix/<slug>` | hours–days | `main` | `main` via PR | **PR preview** + auto hotfix path |
| `docs/<slug>` | hours | `main` | `main` via PR | none (docs PR — Vercel ignores non-app paths) |
| `chore/<slug>` | hours | `main` | `main` via PR | **PR preview** (may include infra) |
| `refactor/<slug>` | days | `main` | `main` via PR | **PR preview** |
| `plan/<slug>` | days–weeks | `main` | none (closed, not merged) | none — drives `/dev-kit:plan` artifacts |
| `design/<slug>` | days | `main` | none (closed) | none — drives design docs |
| `release/<version>` | hours | `main` | `main` (fast-forward only) | **Stage** + **Production canary** |
| `hotfix/<slug>` | hours | `main` (cherry-pick allowed) | `main` AND any active `release/*` | **Production fast-path** |

The worktree-guard hook enforces: new implementation work cuts a worktree off `main`, never edits `main` directly. The dev-kit `worktree-guard.sh` PreToolUse hook blocks Edit/Write on the main checkout.

---

## 2. Branch protection rules

`main` is **protected** in GitHub:

| Setting | Value |
|---|---|
| Require pull request reviews | ✅ 1 approval (configurable per repo) |
| Require status checks | ✅ `/dev-kit:maintenance`, `/dev-kit:review (3-dim)`, `foundation-ci` |
| Require linear history | ✅ (squash merge preferred) |
| Require up-to-date branches | ✅ |
| Include administrators | ✅ |
| Allow force push | ❌ |
| Allow deletion | ❌ |

`release/*` is **semi-protected**: same status checks, but force-merge (no squash) allowed for cherry-picks.

---

## 3. PR lifecycle

```
feat/<slug>
   │
   ├── (1) Open PR  ──────▶  Vercel PR preview + Fly preview slot
   │                            │
   │                            ├── /dev-kit:maintenance  (code-sanity + docs)
   │                            ├── /dev-kit:review (3-dim)
   │                            ├── foundation-ci         (web type/tests)
   │                            └── agent-ci             (uv pytest)
   │
   ├── (2) Iterate  ──────▶  each push re-runs all checks + redeploys preview
   │
   ├── (3) Reviews  ──────▶  human + LLM judge verdicts both required
   │
   ├── (4) Squash-merge to main
   │           │
   │           ▼
   │      main is updated
   │           │
   │           ├── Vercel auto-deploys to production (https://<domain>)
   │           ├── Fly foundation auto-deploys (bluegreen)
   │           └── Tag v<X.Y.Z> created by /dev-kit:ship if review verdict = Approve
   │
   └── (5) Branch auto-deleted by GitHub after merge
```

Rule of thumb: **one PR = one merged commit on main = one production deploy**. Long-lived branches that drift from main are not allowed (status check fails until rebase).

---

## 4. Branch → environment mapping

| Branch | Vercel | Fly foundation | Fly inference (if any) | Neon branch | LangSmith project |
|---|---|---|---|---|---|
| `main` | **prod** domain | `ai-saas-foundation` (blue-green) | `ai-saas-inference` | prod | `ai-saas-foundation-prod` |
| `release/<v>` | staging release | stage `ai-saas-foundation` | stage inference | stage branch | `ai-saas-foundation-stage` |
| `feat/<slug>` (PR) | preview URL | preview slot (`stage: slot+1`) | (reuses main) | preview branch (Neon branching API) | `ai-saas-foundation-pr-<n>` |
| `hotfix/<slug>` | direct prod deploy | prod | preview slot | prod (no branch) | `ai-saas-foundation-hotfix-<n>` |

**No automatic deploys from `docs/*`, `plan/*`, `design/*`** — Vercel's `vercel.json` ignores changes outside `apps/web/**`, and the worktree-guard hook blocks infra changes on those branches anyway.

---

## 5. Vercel deployment config

`vercel.json` (repo root) drives web deploys.

```json
{
  "git": {
    "deploymentEnabled": {
      "main": true,
      "feat/*": true,
      "fix/*": true,
      "release/*": true,
      "docs/*": false,
      "chore/*": false,
      "plan/*": false,
      "design/*": false
    }
  },
  "github": {
    "silent": false,
    "autoAlias": true
  },
  "buildCommand": "pnpm --filter ai-saas-foundation-web build",
  "outputDirectory": "apps/web/.next",
  "framework": "nextjs",
  "regions": ["icn1"],
  "build": {
    "env": {
      "NEXT_PUBLIC_APP_ENV": "@deployment-env"
    }
  }
}
```

Behavior:
- Every push to `feat/*` / `fix/*` creates a preview URL (`ai-saas-foundation-git-<branch>-<user>.vercel.app`).
- Push to `release/*` deploys to a named staging alias (`stage.<domain>`).
- Merge to `main` deploys to the production alias (`<domain>`).
- PR comment posts the preview URL + a "View deployment" badge.

---

## 6. Fly.io foundation deploy

The foundation API runs on Fly.io (Docker). Deployment is driven by `fly.toml` + GitHub Actions, not by branch auto-detection.

`.github/workflows/fly-deploy.yml`:

```yaml
name: deploy-fly-foundation
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      app:
        description: 'Fly app name'
        required: true
        default: 'ai-saas-foundation-stage'

concurrency:
  group: fly-${{ github.event.inputs.app || 'prod' }}
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - name: Deploy
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
        run: |
          app=${{ github.event.inputs.app || 'ai-saas-foundation' }}
          flyctl deploy --app "$app" \
            --dockerfile docker/prod/foundation.Dockerfile \
            --strategy bluegreen \
            --wait-timeout 300
```

Behavior:
- Merge to `main` → Fly deploys `ai-saas-foundation` (prod) via bluegreen.
- Manual `workflow_dispatch` with `app=ai-saas-foundation-stage` → deploys to stage.
- `release/*` push does NOT auto-deploy Fly (Fly is on main only); staging Fly deploy is manual via `workflow_dispatch`.

---

## 7. PR preview slot allocation

Vercel previews are free and ephemeral. Fly previews cost real money, so we use slot math and auto-cleanup:

- Each PR gets a Fly app `ai-saas-foundation-pr-<n>` (n = PR number).
- Created by a bot on PR open; deleted on PR close (bot listens to `pull_request` closed event).
- DB: each preview app points at a Neon preview branch (Neon branching API), auto-deleted with the app.

This avoids the "40 parallel worktrees collide on port 3100" problem at the production deploy path — previews are isolated apps, not slot-shared ones.

---

## 8. Hotfix + rollback

**Hotfix path** (production is broken, can't wait for normal PR flow):

```bash
# 1. Cut from main (production commit)
git fetch origin main
git worktree add -b hotfix/<slug> .worktrees/hotfix-<slug> origin/main

# 2. Fix + commit + open PR titled "hotfix: <one-line>"
#    PR auto-deploys Vercel preview + Fly preview slot for smoke

# 3. After 1 review approval + green CI, "Merge branch": / OR
#    admin can bypass with /dev-kit:ship --force

# 4. Vercel auto-deploys prod on merge
#    Fly deploys prod via bluegreen on merge

# 5. Post-mortem PR opens within 24h
```

**Rollback paths**:

| What broke | Rollback |
|---|---|
| Vercel (web) | `vercel rollback` to previous deployment; or `git revert <merge-sha>` + push to main |
| Fly foundation | `fly releases rollback --app ai-saas-foundation` |
| Neon schema | `neon branches restore <previous-branch>` (Neon keeps 7-day history) |
| LangSmith dataset | restore from git history of `benchmarks/cases/*.yaml` |
| Secrets | rotate via `fly secrets set` or Vercel env update (no code deploy needed) |

The Fly bluegreen strategy means **rollback is always to the previous release**, never to "no release". Vercel keeps every deployment for 90 days; rollback is instant.

---

## 9. Branch cleanup

```bash
# Local
git fetch --prune
git branch -d origin/feat/<merged-slug>

# Remote — automated via GitHub "Delete head branches" (Settings → General)
```

The dev-kit janitor (`/dev-kit:worktree-prune`) audits `.worktrees/*` weekly and lists worktrees whose branches are merged or closed.

---

## 10. Summary table

| Action | Where |
|---|---|
| New feature | Branch `feat/<slug>` off `main`, open PR |
| Bug fix | Branch `fix/<slug>` off `main`, open PR |
| Docs only | Branch `docs/<slug>` off `main`, open PR (no deploy) |
| Infra change (Terraform / Fly.toml / vercel.json) | Branch `chore/<slug>` or `feat/<slug>` off `main`, open PR (deploys preview) |
| Release prep | Branch `release/v<X.Y.Z>` off `main`, cherry-pick fixes, fast-forward merge to main |
| Hotfix | Branch `hotfix/<slug>` off `main`, fast-track review, merge to main |
| Plan / design artifact | Branch `plan/<slug>` or `design/<slug>` off `main`, do not merge, close when superseded |
| Deploy prod (web) | Vercel auto on merge to `main` |
| Deploy prod (foundation) | Fly bluegreen on merge to `main` via `fly-deploy.yml` |
| Deploy stage | Manual `workflow_dispatch` of `fly-deploy.yml` with `app=ai-saas-foundation-stage` |
| Rollback (web) | `vercel rollback` |
| Rollback (foundation) | `fly releases rollback` |
| Schema rollback | `neon branches restore <prev>` |

---

## 11. Migration to AWS (when Phase 3 lands)

This strategy extends unchanged. The branch → environment map gets a third column (AWS infra):

| Branch | Vercel | Fly foundation | AWS ECS service |
|---|---|---|---|
| `main` | prod | — | `ai-saas-foundation-prod` (terraform apply) |
| `release/*` | stage | — | `ai-saas-foundation-stage` |
| `feat/*` | preview | preview slot | preview ECS service (one task, auto-destroyed on PR close) |
| `hotfix/*` | prod | — | prod ECS service (same as main) |

Terraform changes ship via `feat/<slug>` PRs; `terraform plan` output is posted as a PR comment. Drift detection runs nightly (`terraform plan -detailed-exitcode` against the deployed state).

---

## 12. What this document does NOT cover

- **LangChain / LangGraph / LangSmith integration** — deferred. When that lands, the LangSmith project column in §4 fills in automatically from `LANGCHAIN_PROJECT` env.
- **Ollama / local LLM serving** — deferred per your call. When/if it lands, it goes in the `feat/*` PR preview path; no main-branch deployment.
- **Cost ceilings per branch** — handled by `aws-hybrid-architecture.yaml` §6 (cost), not here.
- **On-call rotation** — handled by `docs/runbooks/aws-prod.md` (Phase 3), not here.

This document is the **deployment contract**. Add to it only when branch or deploy topology changes; promote it from "pending" to "applied" when a CI workflow validates it end-to-end.