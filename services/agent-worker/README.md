# agent-worker

Owns bounded model execution and checkpoint recovery. `BoundedWorker` persists
an in-flight model-call key before invoking a model, then commits usage with a
stable key after a checkpoint. A Fargate Spot interruption can therefore retry
the same call and cannot double-spend credits.

`BoundedInngestWorkflow` validates the `run.requested` envelope before handing
it to the worker. Limits are explicit for wall-clock time, steps, and model
calls; there is no unbounded model loop and the browser never calls the worker.

`FargateSpotBoundary` is an optional launch description only: ARM64, 0.25
vCPU, 512 MiB, public-subnet outbound access, and no inbound worker rules.
Its `run_task_request()` method emits the exact ECS RunTask request shape and
passes only run, tenant, and trace identifiers. The declarative contract is in
`infra/aws/fargate-spot-runtask.json`; it is not a provisioning command.

Worker model-call spans use sampled, redacted telemetry when a tracer is
provided. Raw prompts, payment payloads, OAuth codes, and credentials are not
span attributes.
