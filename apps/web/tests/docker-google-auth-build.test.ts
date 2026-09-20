import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(webRoot, "../..");

test("passes the Google auth flag into the Docker client build", () => {
  const dockerfile = readFileSync(resolve(webRoot, "Dockerfile"), "utf8");
  const compose = readFileSync(resolve(repoRoot, "docker/prod/compose.yaml"), "utf8");
  const webService = compose.match(/  web:\n([\s\S]*?)\n    depends_on:/)?.[1] ?? "";

  assert.match(
    dockerfile,
    /FROM deps AS builder[\s\S]*ARG NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true[\s\S]*ENV NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=\$NEXT_PUBLIC_GOOGLE_AUTH_ENABLED[\s\S]*RUN pnpm --filter ai-saas-foundation-web build/,
  );
  assert.match(
    webService,
    /build:\n[\s\S]*args:\n\s+NEXT_PUBLIC_GOOGLE_AUTH_ENABLED: \$\{NEXT_PUBLIC_GOOGLE_AUTH_ENABLED:-true\}/,
  );
});
