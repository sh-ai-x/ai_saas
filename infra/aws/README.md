# AWS low-cost worker contract

`fargate-spot-runtask.json` is an auditable RunTask contract, not a
provisioning script. An operator resolves its non-secret identifiers through
the `aws-worker` profile and supplies an ARM64 worker image and task role.

The contract intentionally describes one interruptible Fargate Spot task at
256 CPU units / 512 MiB, in a public subnet with a public IP for outbound
provider access. The worker security group has no inbound rules and the task
has no listener, ALB, NAT gateway, Redis, or always-on ECS service. This is a
low-cost profile without a commercial SLA or multi-AZ availability claim.

Before any launch, verify that the image handles SIGTERM, persists its
checkpoint before model work, and carries only run/tenant/trace identifiers in
the task override. Payment payloads, OAuth codes, prompts, and credentials
must arrive through their owning server-side boundary, never as task
environment values.
