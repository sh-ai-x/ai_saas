# infra/gcp/foundation — GCE e2-micro deploy for the foundation service

Smoke-test clone of the foundation service on Google Compute Engine.
Replaces the Fly.io deploy (`fly.toml` + `.github/workflows/foundation-fly-deploy.yml`)
for the staging smoke-test workload, preserving the Fly method on the
`archive/flyio-foundation-deploy` branch in case prod ever needs to roll
back.

## Why GCE over Fly for this workload

| | Fly (current) | GCE e2-micro + CF Tunnel |
|---|---|---|
| Monthly cost | $0 with auto-stop, ~$1.94/mo always-on | $0 always-free (within egress cap) |
| Region | nrt (Tokyo, ~5ms to KR) | us-west1 (~150ms to KR) |
| Cold deploy | ~30s | ~3 min (image push + SSH restart) |
| State persistence | Fly volume | Persistent disk (pd-standard, free tier) |
| TLS | Built-in (force_https) | Cloudflare Tunnel (free, off-VM) |
| Egress ceiling | Generous | **1 GB/mo free**, then $0.12/GB |
| Always-on availability | yes (with $) / cold (free) | yes (free) |
| Multi-instance HA | Possible (paid) | No — always-free quota = 1 instance |

The deciding factor: the foundation service is documented as a smoke-test
(see `cd95833 docs(ops): mark foundation deploy as staging smoke-test`),
so always-reachable + $0/mo beats nrt latency + $1.94/mo. Production traffic
stays on whatever else runs the prod deploy.

## One-time setup (operator)

```bash
# 1. gcloud auth + Artifact Registry
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud auth configure-docker us-west1-docker.pkg.dev
gcloud artifacts repositories create foundation \
  --repository-format=docker --location=us-west1

# 2. Provision the VM + data disk + firewall (idempotent)
./infra/gcp/foundation/create-vm.sh <PROJECT_ID>

# 3. Create the Cloudflare Tunnel
#    Cloudflare Zero Trust dashboard → Networks → Tunnels → Create a tunnel
#    Name: foundation. Public hostname: foundation.<your-domain> → service
#    http://localhost:8080. Copy the tunnel token (a base64 JSON blob).
echo -n "$CLOUDFLARE_TUNNEL_TOKEN" | gcloud secrets create foundation-cloudflared-token --data-file=-

# 4. Create the foundation-env Secret Manager entry (copy
#    config/profiles/free-portfolio.example.env and override APP_BASE_URL,
#    DATABASE_URL, APP_SECRET_KEY for the GCE smoke-test).
gcloud secrets create foundation-env --data-file=config/profiles/gcp-smoke.env

# 5. Push the first image
gcloud builds submit --tag us-west1-docker.pkg.dev/<PROJECT_ID>/foundation/app:initial
echo -n "us-west1-docker.pkg.dev/<PROJECT_ID>/foundation/app:initial" \
  | gcloud secrets versions add foundation-image --data-file=-

# 6. Confirm the VM booted and the tunnel resolves
gcloud compute ssh foundation --zone=us-west1-a \
  --command='sudo docker compose -f /opt/ai-saas/docker-compose.yaml ps'
curl -fsS https://foundation.<your-domain>/healthz
```

## Deploy flow

The CI workflow `.github/workflows/foundation-gce-deploy.yml` runs on every
push to `main` that touches foundation, services, or this infra directory.
It:

1. Cloud Build → `us-west1-docker.pkg.dev/PROJECT/foundation/app:$GITHUB_SHA`.
2. `gcloud secrets versions add foundation-image --data-file=-` with the
   new tag.
3. SSHes to the VM, re-fetches `foundation-image` + `foundation-cloudflared-token`,
   and runs `docker compose up -d --remove-orphans`.
4. Smoke-tests `https://foundation.<your-domain>/healthz`.

No static external IP — the always-free e2-micro quota does not cover one
($7.20/mo otherwise). Cloudflare Tunnel terminates TLS for free; the VM has
`--no-address` at create time. Local-only firewall rule (`deny-8080-ingress`)
locks the app port to loopback as defence-in-depth.

## What lives where

| Path | Purpose |
|---|---|
| `infra/gcp/foundation/create-vm.sh` | One-time VM provisioning |
| `infra/gcp/foundation/cloud-init.yaml` | First-boot setup (apt, data disk mount, secret fetch) |
| `infra/gcp/foundation/docker-compose.yaml` | App + cloudflared runtime |
| `infra/gcp/foundation/README.md` | This file |
| `.github/workflows/foundation-gce-deploy.yml` | CI: build + push + restart |
| GCP Secret Manager: `foundation-env` | Full env-file body |
| GCP Secret Manager: `foundation-cloudflared-token` | Tunnel token |
| GCP Secret Manager: `foundation-image` | Current image tag |
| VM: `/mnt/foundation-state` | pd-standard 30GB, mounts to `/var/lib/ai-saas` |
| VM: `/etc/ai-saas/foundation.env` | Boot-fetched env file |
| VM: `/etc/ai-saas/cloudflared.env` | Boot-fetched tunnel token |
| VM: `/opt/ai-saas/docker-compose.yaml` | Pushed by CI on each deploy |

## Migration from Fly

The Fly artifacts remain on main; this branch adds GCE alongside, not
replacing. To switch fully:

1. Disable `.github/workflows/foundation-fly-deploy.yml` (rename to
   `foundation-fly-deploy.yml.disabled` or gate it on a label).
2. Archive the Fly secrets (`FLY_API_TOKEN` + app secrets in Fly's vault).
3. Verify `https://foundation.<your-domain>/healthz` for 24h, then delete
   the Fly app (`fly apps destroy ai-saas-foundation`).

The data in `/var/lib/ai-saas` (SQLite state) does NOT migrate from Fly
volumes — Fly volumes are Fly-managed and not portable. Treat the first
GCE deploy as a clean-state smoke-test; restore from a `fly volumes
snapshot` only if the prod data model requires it.

## Deletion

```bash
gcloud compute instances delete foundation --zone=us-west1-a
gcloud compute disks delete foundation-state --zone=us-west1-a
gcloud compute firewall-rules delete deny-8080-ingress
gcloud secrets delete foundation-env foundation-cloudflared-token foundation-image
gcloud artifacts repositories delete foundation --location=us-west1
# Cloudflare: Zero Trust dashboard → Networks → Tunnels → delete "foundation"
```