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
  return result.status ?? 1;
}

function assertApplyConfirmation(target) {
  if (target === "staging" && process.env.CONFIRM_STAGING_DB !== "staging") {
    throw new Error("staging apply requires CONFIRM_STAGING_DB=staging");
  }
  if (target === "production") {
    if (process.env.CONFIRM_PRODUCTION_DB !== "production") {
      throw new Error("production apply requires CONFIRM_PRODUCTION_DB=production");
    }
    if (process.env.GITHUB_ACTIONS !== "true") {
      throw new Error("production apply is allowed only from GitHub Actions");
    }
  }
}

function applyMigration() {
  const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
  const result = spawnSync(pnpm, ["--filter", "ai-saas-foundation-web", "db:migrate"], {
    cwd: REPO_ROOT,
    env: process.env,
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Drizzle migration exited with code ${result.status}`);
}

async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  loadEnvironment(args.target, args.fromFile);
  if (args.mode === "plan") {
    const status = runPreflight(args);
    if (status === 0) console.log(`migration release: PLAN PASS — no database changes made for ${args.target}`);
    return status;
  }

  assertApplyConfirmation(args.target);
  if (args.staticOnly) throw new Error("--static-only cannot be combined with --apply");

  const preflightStatus = runPreflight(args);
  if (preflightStatus !== 0) {
    throw new Error("preflight failed; Drizzle migration was not started");
  }

  console.log(`migration release: applying committed migrations to ${args.target}`);
  applyMigration();

  const verificationStatus = runPreflight(args, true);
  if (verificationStatus !== 0) throw new Error("post-migration history verification failed");
  console.log(`migration release: APPLY PASS — ${args.target} history is current`);
  return 0;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    process.exitCode = await main();
  } catch (error) {
    fail(error instanceof Error ? error.message : String(error));
  }
}

