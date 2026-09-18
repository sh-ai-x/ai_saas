"""Optional worker-only Fargate Spot launch boundary."""

from __future__ import annotations

from typing import Mapping


class FargateSpotBoundary:
    """Describe an on-demand worker task without exposing an inbound API."""

    def __init__(self, *, cluster_arn: str, task_definition: str, subnet_id: str, security_group_id: str) -> None:
        for value in (cluster_arn, task_definition, subnet_id, security_group_id):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Fargate worker identifiers must be non-empty")
        self.cluster_arn = cluster_arn
        self.task_definition = task_definition
        self.subnet_id = subnet_id
        self.security_group_id = security_group_id

    def task_request(self, run_id: str, tenant_id: str) -> Mapping[str, str]:
        if not run_id or not tenant_id:
            raise ValueError("worker task requires run and tenant identifiers")
        return {
            "cluster": self.cluster_arn,
            "task_definition": self.task_definition,
            "capacity_provider": "FARGATE_SPOT",
            "architecture": "arm64",
            "cpu": "0.25",
            "memory_mb": "512",
            "subnet_id": self.subnet_id,
            "security_group_id": self.security_group_id,
            "assign_public_ip": "true",
            "inbound_rules": "none",
            "run_id": run_id,
            "tenant_id": tenant_id,
        }

    def run_task_request(self, run_id: str, tenant_id: str, trace_id: str) -> Mapping[str, object]:
        """Return the exact ECS ``RunTask`` request shape for one worker run.

        The task definition owns the ARM64/0.25-vCPU/512-MiB limits. This
        request only selects Fargate Spot, enables public-subnet egress, and
        passes opaque durable identifiers; it deliberately has no listener or
        inbound route.
        """

        if not all(isinstance(value, str) and value.strip() for value in (run_id, tenant_id, trace_id)):
            raise ValueError("worker task requires run, tenant, and trace identifiers")
        return {
            "cluster": self.cluster_arn,
            "taskDefinition": self.task_definition,
            "capacityProviderStrategy": [{"capacityProvider": "FARGATE_SPOT", "weight": 1}],
            "count": 1,
            "platformVersion": "1.4.0",
            "networkConfiguration": {
                "awsvpcConfiguration": {
                    "subnets": [self.subnet_id],
                    "securityGroups": [self.security_group_id],
                    "assignPublicIp": "ENABLED",
                }
            },
            "overrides": {
                "containerOverrides": [
                    {
                        "name": "agent-worker",
                        "environment": [
                            {"name": "RUN_ID", "value": run_id},
                            {"name": "TENANT_ID", "value": tenant_id},
                            {"name": "TRACE_ID", "value": trace_id},
                        ],
                    }
                ]
            },
        }
