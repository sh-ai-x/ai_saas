#!/usr/bin/env python3
"""Run the no-cloud local vertical slice and report Docker availability.

The smoke test succeeds when the host-local runtime and Compose configuration
work. Docker build/start evidence is included when a daemon is available, but
an unavailable daemon is reported as an environment block rather than hidden
or treated as a reason to buy a paid service.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def request(base_url: str, method: str, path: str, payload: dict[str, object] | None = None) -> tuple[int, Any, str]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=3) as response:
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
            value = raw if "text/event-stream" in content_type else json.loads(raw)
            return response.status, value, content_type
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8")), "application/json"


def docker_checks(env: dict[str, str]) -> list[str]:
    if shutil.which("docker") is None:
        return ["docker=unavailable (CLI not installed)", "docker_build=skipped"]

    info = subprocess.run(
        ["docker", "info"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=False,
    )
    if info.returncode != 0:
        return ["docker=blocked (daemon unavailable)", "docker_build=skipped"]

    compose = subprocess.run(
        ["docker", "compose", "-f", "docker/dev/compose.yaml", "config"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    if compose.returncode != 0:
        raise RuntimeError("docker compose config failed")
    build = subprocess.run(
        ["docker", "build", "--file", "docker/dev/Dockerfile", "--tag", "ai-saas-foundation:local", "."],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=600,
        check=False,
    )
    if build.returncode != 0:
        raise RuntimeError("docker build failed")
    return ["docker=available", "docker_compose_config=pass", "docker_build=pass"]


def main() -> int:
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="ai-saas-smoke-") as state_dir:
        env = os.environ.copy()
        env.update(
            {
                "APP_SECRET_KEY": "local-smoke-secret-not-for-production-1234567890",
                "APP_BASE_URL": f"http://127.0.0.1:{port}",
                "LOCAL_STATE_DB": str(Path(state_dir) / "state.sqlite3"),
                "LOCAL_INITIAL_CREDITS": "20",
            }
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "foundation.server",
                "--env-file",
                "config/profiles/free-portfolio.example.env",
                "--profile",
                "free-portfolio",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base_url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(30):
                if process.poll() is not None:
                    raise RuntimeError("local server exited before health check")
                try:
                    status, health, _ = request(base_url, "GET", "/healthz")
                    if status == 200 and health.get("status") == "ok":
                        break
                except (URLError, OSError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("local server health check timed out")

            status, start, _ = request(base_url, "GET", "/v1/auth/google/start")
            assert status == 200 and start["state"]
            status, _callback, _ = request(
                base_url,
                "POST",
                "/v1/auth/google/callback",
                {"state": start["state"], "code": "local-code"},
            )
            assert status == 200
            status, admin_result, _ = request(
                base_url,
                "POST",
                "/v1/admin/plan",
                {
                    "target_user_id": "demo-member",
                    "plan": "pro",
                    "reason": "local smoke",
                    "correlation_id": "smoke-admin-001",
                },
            )
            assert status == 200 and admin_result["after"]["plan"] == "pro"
            status, run, _ = request(
                base_url,
                "POST",
                "/v1/runs",
                {
                    "contract_version": "v1",
                    "tenant_id": "demo-tenant",
                    "project_id": "demo-project",
                    "idempotency_key": "smoke-run-001",
                    "trace_id": "smoke-trace-001",
                    "input": {"message": "smoke"},
                },
            )
            assert status == 201 and run["state"] == "completed"
            status, events, _ = request(base_url, "GET", f"/v1/runs/{run['run_id']}/events")
            assert status == 200 and "run.completed" in events
            status, credit_result, _ = request(
                base_url,
                "POST",
                "/v1/admin/credits",
                {
                    "target_user_id": "demo-user",
                    "amount": 3,
                    "reason": "local smoke credit grant",
                    "correlation_id": "smoke-credits-001",
                },
            )
            assert status == 200 and credit_result["after"]["credit_balance"] == 22
            status, owned_run, _ = request(base_url, "GET", f"/v1/runs/{run['run_id']}")
            assert status == 200 and owned_run["tenant_id"] == "demo-tenant"
            foreign_request = Request(
                base_url + f"/v1/runs/{run['run_id']}",
                headers={"X-Tenant-Id": "other-tenant"},
                method="GET",
            )
            try:
                with urlopen(foreign_request, timeout=3) as response:
                    raise AssertionError(f"foreign tenant unexpectedly succeeded: {response.status}")
            except HTTPError as exc:
                try:
                    foreign_payload = json.loads(exc.read().decode("utf-8"))
                    assert exc.code == 403 and foreign_payload["error"] == "tenant_access_denied"
                finally:
                    exc.close()

            status, _order, _ = request(
                base_url,
                "POST",
                "/v1/billing/orders",
                {"order_id": "smoke-order-001", "idempotency_key": "smoke-order-key-001", "credit_grant": 5},
            )
            assert status == 201
            status, payment, _ = request(
                base_url,
                "POST",
                "/v1/billing/mock/complete",
                {"order_id": "smoke-order-001"},
            )
            assert status == 200 and payment["applied"] is True
            print("local_health=pass")
            print("google_auth_mock=pass")
            print("admin_and_tenant_boundary=pass")
            print("mock_payment_webhook_and_ledger=pass")
            print("run_checkpoint_and_sse=pass")
            for line in docker_checks(env):
                print(line)
            return 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"local smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
