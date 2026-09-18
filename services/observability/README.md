# Observability

Owns redacted correlation and evaluation records. Telemetry must never become
the source of truth for entitlement or durable run state.

`SampledTracer` samples before export and redacts again at export time. Prompt
and input content, payment data, OAuth codes, credentials, authorization
headers, and tokens are represented only by `[REDACTED]`. Export failure is
non-blocking. The free profile uses a bounded in-memory exporter at a 10%
sample rate; this step does not provision a collector or claim a commercial
SLA.
