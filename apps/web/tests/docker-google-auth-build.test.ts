import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(webRoot, "../..");

describe("passes the Google auth flag into the Docker client build", () => {
  it("declares the build-time ARG and propagates it into ENV in apps/web/Dockerfile", () => {
    const dockerfile = readFileSync(resolve(webRoot, "Dockerfile"), "utf8");
    // Extract the `FROM deps AS builder` stage so the contract is anchored on
    // the builder stage only — reordering COPY / RUN inside the stage, or
    // renaming the workspace package, must not silently break this test.
    const builderStage = dockerfile.match(
      /FROM deps AS builder\n([\s\S]*?)(?=\nFROM |\Z)/,
    )?.[1] ?? "";

    expect(builderStage).toMatch(/^ARG NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true$/m);
    expect(builderStage).toMatch(
      /^ENV NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=\$NEXT_PUBLIC_GOOGLE_AUTH_ENABLED$/m,
    );
    expect(builderStage).toMatch(
      /^RUN pnpm --filter ai-saas-foundation-web build$/m,
    );
  });

  it("forwards the flag into the web service's build args in docker/prod/compose.yaml", () => {
    const compose = readFileSync(resolve(repoRoot, "docker/prod/compose.yaml"), "utf8");
    // Capture the `web:` service block only (top-level services are indented with
    // two spaces). The block ends at the next service definition or EOF, so the
    // capture stays valid even if `web:` gains sibling keys.
    const webBlock = compose.match(/^  web:\n([\s\S]*?)(?=^  \w|\Z)/m)?.[1] ?? "";

    expect(webBlock).toMatch(
      /^ {6}args:\n {8}NEXT_PUBLIC_GOOGLE_AUTH_ENABLED: \$\{NEXT_PUBLIC_GOOGLE_AUTH_ENABLED:-true\}/m,
    );
  });
});
