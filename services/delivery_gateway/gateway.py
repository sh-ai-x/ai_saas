"""Request signing and validation without merge, deploy, shell, or network effects."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

from agent_platform.contracts import DeliveryRequest


@dataclass(frozen=True)
class SignedDeliveryRequest:
    request: DeliveryRequest
    body_digest: str


class DeliveryGateway:
    def __init__(self, *, signing_key: bytes) -> None:
        if not signing_key:
            raise ValueError("delivery signing key must be supplied explicitly")
        self._key = signing_key

    def sign(self, *, request_id: str, run_id: str, tenant_id: str, artifact_hash: str, approval_token_id: str) -> SignedDeliveryRequest:
        body = {"request_id": request_id, "run_id": run_id, "tenant_id": tenant_id, "artifact_hash": artifact_hash, "action": "deliver_patch", "approval_token_id": approval_token_id}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        signature = hmac.new(self._key, digest.encode(), hashlib.sha256).hexdigest()
        return SignedDeliveryRequest(DeliveryRequest(request_id, run_id, tenant_id, artifact_hash, "deliver_patch", approval_token_id, signature), digest)

    def validate(self, signed: SignedDeliveryRequest) -> bool:
        request = signed.request
        body = {"request_id": request.request_id, "run_id": request.run_id, "tenant_id": request.tenant_id, "artifact_hash": request.artifact_hash, "action": request.action, "approval_token_id": request.approval_token_id}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        expected = hmac.new(self._key, digest.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, signed.body_digest) and hmac.compare_digest(expected, request.signature)

    def deliver(self, signed: SignedDeliveryRequest) -> str:
        if not self.validate(signed):
            raise PermissionError("invalid signed delivery request")
        return "accepted-for-manual-delivery"

