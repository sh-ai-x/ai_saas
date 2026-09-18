---
doc_id: operations-aws-docker-deployment
domain: operations
purpose: Define Docker packaging and AWS ECS/Fargate production operations.
read_when:
  - changing Dockerfiles, images, ECS services, networking, scaling, or deployment
  - responding to an AWS runtime, health, capacity, or rollback incident
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - ../architecture/system-map.md
  - ../security/safety-boundaries.md
  - ../verification/release-and-incident.md
source_of_truth: contract
owner: platform-engineering
last_reviewed: 2026-09-17
change_impact: high
---

# AWS and Docker Deployment

## Deployment baseline

Package the Python/FastAPI agent service and any supporting worker as Docker
images. Run production services on AWS ECS/Fargate with ECR, ALB, CloudWatch,
IAM, secrets injection, and private network boundaries. The Next.js frontend
may have a separate deployment boundary, but the agent runtime must not depend
on frontend process lifetime.

AWS documents ECS best practices for networking, task definitions, security,
capacity, autoscaling, health checks, and operating at scale. **(source:
https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html)**

## Image contract

- Use reproducible dependency installation and a lockfile.
- Use a multi-stage build where it reduces runtime surface.
- Do not copy local secrets into an image.
- Run as a non-root user where compatible with the runtime.
- Scan images and preserve provenance/SBOM evidence.
- Expose a health endpoint that checks process readiness without performing
  expensive model or database calls.
- Handle SIGTERM, drain requests, stop new work, and persist run state before
  shutdown.

FastAPI's deployment guidance uses Linux containers as a repeatable packaging
boundary for production services. **(source:
https://fastapi.tiangolo.com/deployment/docker/)**

## ECS contract

- Use `awsvpc` networking and task security groups.
- Keep secrets in a managed secret store; inject only required values.
- Run tasks across available zones where the service's availability target
  requires it.
- Set explicit desired/min/max task counts and autoscaling metrics.
- Use ALB health checks and deployment rollback on failed health.
- Send structured logs and metrics to CloudWatch with run correlation IDs.
- Define queue/worker scaling separately from request-serving API scaling.
- Keep model, payment, and data provider failure modes visible in alarms.

## Cost and capacity

AWS capacity guidance emphasizes the balance between overcapacity cost and
undercapacity latency/error risk. **(source:
https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-availability-best-practice.html)**

Capacity decisions require measured traffic, CPU/memory utilization, queue
depth, p95/p99 latency, error rate, and budget. No fixed task size is treated
as universal.

## Verification evidence

- Image build, scan, provenance, and non-root checks.
- Container startup, health, graceful shutdown, and restart tests.
- ECS deployment, rollback, autoscaling, and AZ failure exercises.
- Load tests for API, queue, database pool, and streaming disconnects.
- CloudWatch dashboards and alarms are linked from the runbook.

## Sources

- [AWS ECS best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html)
- [AWS ECS network security](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-network.html)
- [AWS ECS capacity and availability](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-availability-best-practice.html)
- [Docker build best practices](https://docs.docker.com/build/building/best-practices/)
- [FastAPI in containers](https://fastapi.tiangolo.com/deployment/docker/)
- Baseline: `../mysaas/my-saas/docker/dev/compose.yaml:1-64`,
  `docker/prod/Dockerfile:1-59`.
