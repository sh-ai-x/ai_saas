#!/usr/bin/env node
// scripts/drizzle-doctor.mjs — comprehensive Drizzle diagnostic.
//
// Combines the file-level check (drizzle-status.mjs) with a database
// query when DATABASE_URL_UNPOOLED is set:
//   - manifest consistency (orphan / missing files)
//   - destructive statements (DROP TABLE, DROP COLUMN, …) per pending migration
//   - direct-vs-pooled connection check (DATABASE_URL_UNPOOLED must not be pooler)
//   - applied-vs-pending history (when DB is reachable)
//
// Exit 0 = clean; exit 1 = at least one finding. JSON output is the
// canonical contract; the human-readable summary at the bottom is for
// the terminal. Wired through `pnpm db:doctor[:stage|:prod]`.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadDotenv, readMigrationManifest } from "./migration-common.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");
const PREFLIGHT = path.join(SCRIPT_DIR, "migration-preflight.mjs");

function parseArgs(argv) {
  const args = { target: "", fromFile: "", migrationDir: "" };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--from-file") args.fromFile = argv[++index] ?? "";
    else if (value === "--migration-dir") args.migrationDir = argv[++index] ?? "";
    else if (!args.target) args.target = value;
    else throw new Error(`unknown argument: ${value}`);
  }
  return args;
}

const DESTRUCTIVE_PATTERN = /\b(drop\s+table|drop\s+schema|drop\s+column|drop\s+index|truncate\s+table|alter\s+table[^;]*drop\s+column)\b/giu;

function findDestructive(sql) {
  const findings = [];
  for (const match of sql.matchAll(DESTRUCTIVE_PATTERN)) {
    findings.push(match[0].trim());
  }
  return findings;
}

function readManifestOrFail(findings, migrationDir) {
  try {
    const migrations = readMigrationManifest(migrationDir, REPO_ROOT);
    return { migrations, error: null };
  } catch (err) {
    findings.push({
      check: "manifest",
      status: "FAIL",
      detail: err.message,
    });
    return { migrations: [], error: err };
  }
}

function isPoolerHost(url) {
  if (!url) return false;
  // Neon pooler hosts end in `-pooler.<region>.aws.neon.tech`.
  return /pooler\.[^/]+/iu.test(url);
}

function checkConnectionEnv(findings, target, fromFile) {
  const envPath = fromFile || path.join(REPO_ROOT, target === "production" ? ".env.production" : ".env.staging");
  const loaded = loadDotenv(envPath);
  if (!loaded) {
    findings.push({
      check: "env-file",
      status: "WARN",
      detail: `${path.basename(envPath)} not found; DB connectivity check skipped`,
    });
    return;
  }

  const pooled = process.env.DATABASE_URL ?? "";
  const direct = process.env.DATABASE_URL_UNPOOLED ?? "";
  if (!direct) {
    findings.push({
      check: "direct-url",
      status: "FAIL",
      detail: "DATABASE_URL_UNPOOLED is not set; migrations require the direct (unpooled) URL",
    });
  } else if (isPoolerHost(direct)) {
    findings.push({
      check: "direct-url",
      status: "FAIL",
      detail: "DATABASE_URL_UNPOOLED still points to a pooler host; Drizzle must use the direct endpoint",
    });
  } else {
    findings.push({
      check: "direct-url",
      status: "PASS",
      detail: "direct host selected for migrations",
    });
  }
  if (pooled && !isPoolerHost(pooled)) {
    findings.push({
      check: "pooled-url",
      status: "WARN",
      detail: "DATABASE_URL is not the pooler; runtime traffic may bypass PgBouncer",
    });
  }
}

function runPreflight(findings, target, fromFile) {
  const args = [PREFLIGHT, "--target", target, "--json"];
  if (fromFile) args.push("--from-file", fromFile);
  const result = spawnSync(process.execPath, args, {
    cwd: REPO_ROOT,
    env: process.env,
    encoding: "utf8",
  });
  // Capture preflight stdout/stderr; do NOT echo. The doctor emits its
  // own JSON summary line so callers get a single parseable document.
  let document = null;
  try {
    document = JSON.parse(result.stdout || "");
  } catch {
    findings.push({
      check: "preflight",
      status: "WARN",
      detail: `preflight did not return JSON (exit=${result.status}); connectivity may be unavailable`,
    });
    return;
  }
  if (!document) return;
  for (const check of document.checks ?? []) {
    findings.push({
      check: check.name,
      status: check.ok ? "PASS" : check.severity === "warning" ? "WARN" : "FAIL",
      detail: check.detail ?? check.status ?? "",
    });
  }
  if (Array.isArray(document.history?.pending) && document.history.pending.length > 0) {
    findings.push({
      check: "pending-migrations",
      status: "WARN",
      detail: `${document.history.pending.length} pending migration(s): ${document.history.pending.join(", ")}`,
    });
  }
}

function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (err) {
    console.error(`drizzle-doctor: ${err.message}`);
    process.exit(2);
  }
  const target = args.target;
  if (!target) {
    console.error("drizzle-doctor: target required (staging | production)");
    console.error("Usage: node scripts/drizzle-doctor.mjs <staging|production>");
    process.exit(2);
  }
  if (target !== "staging" && target !== "production") {
    console.error(`drizzle-doctor: target must be staging or production (got "${target}")`);
    process.exit(2);
  }
  const migrationDir = args.migrationDir
    ? path.resolve(args.migrationDir)
    : path.join(REPO_ROOT, "apps", "web", "drizzle");

  const findings = [];
  const { migrations } = readManifestOrFail(findings, migrationDir);

  for (const migration of migrations) {
    const destructive = findDestructive(migration.sql);
    if (destructive.length > 0) {
      findings.push({
        check: `destructive-migration:${migration.tag}`,
        status: "WARN",
        detail: `${migration.tag} contains destructive statements: ${destructive.join(", ")}`,
      });
    }
  }

  // SQL files on disk but missing from journal — orphan.
  const journalTags = new Set(migrations.map((m) => m.tag));
  const sqlFiles = fs
    .readdirSync(migrationDir)
    .filter((name) => name.endsWith(".sql"))
    .map((name) => name.replace(/\.sql$/u, ""));
  const orphans = sqlFiles.filter((tag) => !journalTags.has(tag));
  if (orphans.length > 0) {
    findings.push({
      check: "orphan-sql",
      status: "FAIL",
      detail: `SQL files not in journal: ${orphans.join(", ")}`,
    });
  }

  checkConnectionEnv(findings, target, args.fromFile);
  runPreflight(findings, target, args.fromFile);

  const fail = findings.some((f) => f.status === "FAIL");
  const warn = findings.some((f) => f.status === "WARN");
  const summary = { target, ok: !fail, findings };

  console.log(JSON.stringify(summary, null, 2));
  process.stderr.write(
    `drizzle-doctor: ${summary.ok ? "PASS" : "FAIL"}${warn && summary.ok ? " (with warnings)" : ""}\n`,
  );
  process.exit(summary.ok ? 0 : 1);
}

main();
