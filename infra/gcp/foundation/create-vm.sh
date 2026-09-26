#!/usr/bin/env bash
# infra/gcp/foundation/create-vm.sh — one-time setup for the GCE foundation VM.
#
# Idempotent: re-running after the VM exists is a no-op for the instance
# create, and `gcloud compute disks create` fails cleanly if the disk
# already exists. The first run is the only time the operator needs to
# provision infra; subsequent deploys are just `gcloud builds submit` +
# `gcloud compute scp` from .github/workflows/foundation-gce-deploy.yml.
#
# Prerequisites (operator runs these once before this script):
#   gcloud auth login
#   gcloud auth configure-docker us-west1-docker.pkg.dev
#   gcloud artifacts repositories create foundation \
#     --repository-format=docker --location=us-west1
#
# Then:
#   ./infra/gcp/foundation/create-vm.sh <project-id>
#
# Cost: $0/mo within the e2-micro always-free quota + the 30GB pd-standard
# free tier. Cloudflare Tunnel terminates TLS for free; no static external
# IP is allocated (the always-free quota does NOT cover one — see README).

set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "usage: $0 <project-id>" >&2
  exit 1
fi
ZONE="us-west1-a"
INSTANCE="foundation"

echo "[1/5] service account for secret access"
SA="${PROJECT_ID}@appspot.gserviceaccount.com"
# The default Compute SA already has secretmanager.secretAccessor at the
# project level when Secret Manager is first enabled; this is a safety
# pass in case the operator disabled it.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor" --quiet >/dev/null

echo "[2/5] data disk (30GB pd-standard, free tier)"
if ! gcloud compute disks describe foundation-state --zone="$ZONE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute disks create foundation-state \
    --zone="$ZONE" --project="$PROJECT_ID" \
    --size=30GB --type=pd-standard
fi

echo "[3/5] firewall: deny 8080 ingress (loopback only; tunnel carries traffic)"
if ! gcloud compute firewall-rules describe deny-8080-ingress --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute firewall-rules create deny-8080-ingress \
    --project="$PROJECT_ID" --direction=INGRESS --action=DENY \
    --rules=tcp:8080 --source-ranges=0.0.0.0/0 --priority=65000 \
    --description="App port is loopback-only; Cloudflare Tunnel carries public traffic"
fi

echo "[4/5] VM (e2-micro, Debian 12, COS-equivalent boot disk size)"
if ! gcloud compute instances describe "$INSTANCE" --zone="$ZONE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute instances create "$INSTANCE" \
    --project="$PROJECT_ID" --zone="$ZONE" \
    --machine-type=e2-micro \
    --image-family=debian-12 --image-project=debian-cloud \
    --boot-disk-size=10GB --boot-disk-type=pd-standard \
    --disk=name=foundation-state,device-name=foundation-state,mode=rw,auto-delete=no \
    --metadata-from-file=cloud-init=infra/gcp/foundation/cloud-init.yaml \
    --no-address \
    --tags=foundation \
    --labels=purpose=foundation-smoke-test
fi

echo "[5/5] initial image push (placeholder; CI will overwrite on first deploy)"
gcloud auth configure-docker us-west1-docker.pkg.dev --quiet
# CI is responsible for the real push; this is a no-op placeholder so the
# secret foundation-image resolves to something on first boot.

echo
echo "VM ready: https://console.cloud.google.com/compute/instancesDetail/zones/${ZONE}/instances/${INSTANCE}"
echo "Next steps (operator):"
echo "  1. Create the Cloudflare Tunnel in the Cloudflare Zero Trust dashboard"
echo "     (tunnel name: foundation, public hostname: foundation.<your-domain>)"
echo "  2. Copy the tunnel token, then:"
echo "       gcloud secrets create foundation-cloudflared-token --data-file=-"
echo "  3. Create the env-file secret (see README for the full content template)"
echo "       gcloud secrets create foundation-env --data-file=config/profiles/gcp-smoke.env"
echo "  4. Push the first image:"
echo "       gcloud builds submit --tag us-west1-docker.pkg.dev/${PROJECT_ID}/foundation/app:initial"
echo "       gcloud secrets versions add foundation-image --data-file=- <<<"
echo "       \"us-west1-docker.pkg.dev/${PROJECT_ID}/foundation/app:initial\""
echo "  5. SSH in to confirm boot, then run the deploy workflow."