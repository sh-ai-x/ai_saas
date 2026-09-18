"""Tiny local HTTP surface proving the foundation can start without paid services."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .config import ConfigError, merged_environment, validate_profile


class FoundationHandler(BaseHTTPRequestHandler):
    server_version = "ai-saas-foundation/0.1"

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        config = self.server.foundation_config  # type: ignore[attr-defined]
        if path == "/healthz":
            self._json(
                200,
                {
                    "status": "ok",
                    "contract_version": config.contract_version,
                    "deployment_profile": config.deployment_profile,
                },
            )
            return
        if path == "/v1/contracts":
            self._json(
                200,
                {
                    "contract_version": "v1",
                    "families": ["rest", "sse", "events", "providers"],
                    "provider_policy": "domain consumes normalized events only",
                },
            )
            return
        if path.startswith("/v1/runs/") and path.endswith("/events"):
            run_id = path.removeprefix("/v1/runs/").removesuffix("/events").strip("/")
            if not run_id:
                self._json(400, {"error": "run_id is required"})
                return
            body = (
                "id: 1\n"
                "event: run.state_changed\n"
                f"data: {{\"contract_version\":\"v1\",\"run_id\":{json.dumps(run_id)},\"state\":\"queued\"}}\n\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {"error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        # Keep local logs deterministic and free of request payloads.
        print(f"foundation: {format % args}")


def _main() -> int:
    parser = argparse.ArgumentParser(description="Start the local foundation HTTP surface")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--profile", choices=("free-portfolio", "aws-worker"), default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        config = validate_profile(merged_environment(args.env_file), args.profile)
    except ConfigError as exc:
        print(str(exc))
        return 2

    server = ThreadingHTTPServer((args.host, args.port), FoundationHandler)
    server.foundation_config = config  # type: ignore[attr-defined]
    print(f"foundation listening on http://{args.host}:{args.port} ({config.deployment_profile})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("foundation stopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
