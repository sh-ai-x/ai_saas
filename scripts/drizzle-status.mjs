#!/usr/bin/env node
// scripts/drizzle-status.mjs — file-only Drizzle status check.
//
// Reads the journal + SQL files in apps/web/drizzle/ and prints:
//   - total migrations (commit count)
//   - last 5 applied (by journal order)
//   - any orphan files (`.sql` outside the journal)
//   - any missing files (journal entry with no `.sql`)
//
// Does NOT contact a database. Runs offline. Exit 0 when the manifest
// is consistent; exit 1 when orphan files or missing files are found.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readMigrationManifest } from "./migration-common.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");

function parseArgs(argv) {
  const args = { migrationDir: "" };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--migration-dir") args.migrationDir = argv[++index] ?? "";
    else throw new Error(`unknown argument: ${value}`);
  }
  return args;
}

function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (err) {
    console.error(`drizzle-status: ${err.message}`);
    process.exit(2);
  }
  const migrationDir = args.migrationDir
    ? path.resolve(args.migrationDir)
    : path.join(REPO_ROOT, "apps", "web", "drizzle");

  let migrations;
  try {
    migrations = readMigrationManifest(migrationDir, REPO_ROOT);
  } catch (err) {
    console.error(`drizzle-status: FAIL — ${err.message}`);
    process.exit(1);
  }

  // Orphan detection: SQL files on disk not in the journal.
  const sqlFiles = fs
    .readdirSync(migrationDir)
    .filter((name) => name.endsWith(".sql"))
    .map((name) => name.replace(/\.sql$/u, ""));
  const journalTags = new Set(migrations.map((migration) => migration.tag));
  const orphans = sqlFiles.filter((tag) => !journalTags.has(tag));

  const recent = migrations.slice(-5).reverse();

  const status = {
    ok: orphans.length === 0,
    totalMigrations: migrations.length,
    firstMigration: migrations[0]?.tag ?? null,
    lastMigration: migrations[migrations.length - 1]?.tag ?? null,
    recentMigrations: recent.map((migration) => ({
      tag: migration.tag,
      hash: migration.hash.slice(0, 12),
      createdAt: migration.createdAt,
    })),
    orphanSqlFiles: orphans,
    migrationDir: path.relative(REPO_ROOT, migrationDir),
  };

  console.log(JSON.stringify(status, null, 2));
  process.exit(status.ok ? 0 : 1);
}

main();
