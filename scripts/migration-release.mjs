#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { loadEnvironment } from "./migration-preflight.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");
const PREFLIGHT = path.join(SCRIPT_DIR, "migration-preflight.mjs");

function parseArgs(argv) {
  const args = { target: "", mode: "", fromFile: "", staticOnly: false };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--") continue;
    if (value === "--target") args.target = argv[++index] ?? "";
    else if (value === "--plan") {
      if (args.mode) throw new Error("choose exactly one of --plan or --apply");
      args.mode = "plan";
    } else if (value === "--apply") {
      if (args.mode) throw new Error("choose exactly one of --plan or --apply");
      args.mode = "apply";
    }
    else if (value === "--from-file") args.fromFile = argv[++index] ?? "";
    else if (value === "--static-only") args.staticOnly = true;
    else throw new Error(`unknown argument: ${value}`);
  }
  if (!new Set(["staging", "production"]).has(args.target)) throw new Error("--target must be staging or production");
  if (!new Set(["plan", "apply"]).has(args.mode)) throw new Error("choose exactly one of --plan or --apply");
  return args;
}

function fail(message) {
  console.error(`migration release: FAIL — ${message}`);
  process.exitCode = 1;
}

function redactOutput(value) {
  return String(value)
    .replace(/postgres(?:ql)?:\/\/[^\s"']+/giu, "[redacted database url]")
    .replace(/password=[^&\s]+/giu, "password=[redacted]");
}

function runPreflight(args, requireHistory = false) {
  const commandArgs = [PREFLIGHT, "--target", args.target, "--json"];
  if (args.fromFile) commandArgs.push("--from-file", args.fromFile);
  if (args.staticOnly) commandArgs.push("--static-only");
  if (requireHistory) commandArgs.push("--require-history");
  if (process.env.REQUIRE_PGVECTOR === "true") commandArgs.push("--require-vector");

  const result = spawnSync(process.execPath, commandArgs, {
    cwd: REPO_ROOT,
    env: process.env,
    encoding: "utf8",
  });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  let document = null;
  try {
    document = JSON.parse(result.stdout || "");
  } catch {
    // The child already reported the actionable error; preserve its exit code.
  }
  return { status: result.status ?? 1, document };
}

function assertApplyConfirmation(target, explicitEnvironment) {
  if (target === "staging" && explicitEnvironment.confirmStaging !== "staging") {
    throw new Error("staging apply requires CONFIRM_STAGING_DB=staging");
  }
  if (target === "production") {
    if (explicitEnvironment.confirmProduction !== "production") {
      throw new Error("production apply requires CONFIRM_PRODUCTION_DB=production");
    }
    if (explicitEnvironment.githubActions !== "true") {
      throw new Error("production apply is allowed only from GitHub Actions");
    }
  }
}

function applyMigration() {
  const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
  const result = spawnSync(pnpm, ["--filter", "ai-saas-foundation-web", "db:migrate"], {
    cwd: REPO_ROOT,
    env: process.env,
    stdio: ["inherit", "pipe", "pipe"],
    encoding: "utf8",
  });
  if (result.stdout) process.stdout.write(redactOutput(result.stdout));
  if (result.stderr) process.stderr.write(redactOutput(result.stderr));
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Drizzle migration exited with code ${result.status}`);
}

async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const explicitEnvironment = {
    confirmStaging: process.env.CONFIRM_STAGING_DB,
    confirmProduction: process.env.CONFIRM_PRODUCTION_DB,
    githubActions: process.env.GITHUB_ACTIONS,
  };
  loadEnvironment(args.target, args.fromFile);
  if (args.mode === "plan") {
    const preflight = runPreflight(args);
    if (preflight.status === 0) {
      const pending = preflight.document?.history?.pending ?? [];
      console.log(`migration release: PLAN — ${args.target}`);
      if (pending.length === 0) {
        console.log("pending migrations: none");
      } else {
        const byTag = new Map((preflight.document?.migrations ?? []).map((migration) => [migration.tag, migration]));
        for (const tag of pending) {
          const migration = byTag.get(tag);
          console.log(`- ${tag}${migration ? ` (${migration.file}, sha256=${migration.hash})` : ""}`);
        }
      }
      console.log(`migration release: PLAN PASS — no database changes made for ${args.target}`);
    }
    return preflight.status;
  }

  assertApplyConfirmation(args.target, explicitEnvironment);
  if (args.staticOnly) throw new Error("--static-only cannot be combined with --apply");

  const preflight = runPreflight(args);
  if (preflight.status !== 0) {
    throw new Error("preflight failed; Drizzle migration was not started");
  }

  console.log(`migration release: applying committed migrations to ${args.target}`);
  applyMigration();

  const verification = runPreflight(args, true);
  if (verification.status !== 0) throw new Error("post-migration history verification failed");
  console.log(`migration release: APPLY PASS — ${args.target} history is current`);
  return 0;
}

const entrypoint = process.argv[1] ? pathToFileURL(path.resolve(process.argv[1])).href : "";
if (entrypoint && import.meta.url === entrypoint) {
  try {
    process.exitCode = await main();
  } catch (error) {
    fail(error instanceof Error ? error.message : String(error));
  }
}
