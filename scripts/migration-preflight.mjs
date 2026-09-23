#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");
const requireFromWeb = createRequire(pathToFileURL(path.join(REPO_ROOT, "apps/web/package.json")));
let postgresClient;

function getPostgresClient() {
  postgresClient ??= requireFromWeb("postgres");
  return postgresClient;
}

function parseArgs(argv) {
  const args = {
    target: "",
    fromFile: "",
    migrationDir: path.join(REPO_ROOT, "apps/web/drizzle"),
    staticOnly: false,
    requireHistory: false,
    requireVector: process.env.REQUIRE_PGVECTOR === "true",
    json: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--") continue;
    if (value === "--target") args.target = argv[++index] ?? "";
    else if (value === "--from-file") args.fromFile = argv[++index] ?? "";
    else if (value === "--migration-dir") args.migrationDir = path.resolve(REPO_ROOT, argv[++index] ?? "");
    else if (value === "--static-only") args.staticOnly = true;
    else if (value === "--require-history") args.requireHistory = true;
    else if (value === "--require-vector") args.requireVector = true;
    else if (value === "--json") args.json = true;
    else throw new Error(`unknown argument: ${value}`);
  }

  if (!new Set(["staging", "production"]).has(args.target)) {
    throw new Error("--target must be staging or production");
  }
  return args;
}

function parseDotenvValue(raw) {
  const value = raw.trim();
  if (value.length >= 2 && ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'")))) {
    return value.slice(1, -1);
  }
  return value;
}

function loadDotenv(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return false;
  const content = fs.readFileSync(filePath, "utf8");
  for (const line of content.split(/\r?\n/u)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/u);
    if (!match || match[1] in process.env) continue;
    process.env[match[1]] = parseDotenvValue(match[2]);
  }
  return true;
}

function loadDefaultEnv(target, fromFile) {
  if (fromFile) {
    const resolved = path.resolve(REPO_ROOT, fromFile);
    if (!loadDotenv(resolved)) throw new Error(`environment file not found: ${fromFile}`);
    return path.relative(REPO_ROOT, resolved);
  }

  const candidates = target === "production"
    ? [".env.production", ".env.prod", ".env"]
    : [".env.stage", ".env.staging", ".env.neon", ".env"];
  const selected = candidates.find((candidate) => loadDotenv(path.join(REPO_ROOT, candidate)));
  return selected ?? null;
}

function redactedError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return message
    .replace(/postgres(?:ql)?:\/\/[^\s"']+/giu, "[redacted database url]")
    .replace(/password=[^&\s]+/giu, "password=[redacted]");
}

function resultCheck(name, ok, detail, severity = "error") {
  return { name, ok, detail, severity };
}

function readMigrationManifest(migrationDir) {
  const journalPath = path.join(migrationDir, "meta", "_journal.json");
  if (!fs.existsSync(journalPath)) throw new Error(`Drizzle journal not found: ${path.relative(REPO_ROOT, journalPath)}`);

  const journal = JSON.parse(fs.readFileSync(journalPath, "utf8"));
  if (!Array.isArray(journal.entries) || journal.entries.length === 0) {
    throw new Error("Drizzle journal has no migration entries");
  }

  const entries = [...journal.entries].sort((left, right) => left.idx - right.idx);
  const seenTags = new Set();
  const migrations = [];
  for (const entry of entries) {
    if (typeof entry.tag !== "string" || !/^[A-Za-z0-9_-]+$/u.test(entry.tag)) {
      throw new Error(`invalid migration tag at index ${entry.idx}`);
    }
    if (seenTags.has(entry.tag)) throw new Error(`duplicate migration tag: ${entry.tag}`);
    seenTags.add(entry.tag);

    const filePath = path.join(migrationDir, `${entry.tag}.sql`);
    if (!fs.existsSync(filePath)) throw new Error(`migration SQL not found: ${entry.tag}.sql`);
    const sql = fs.readFileSync(filePath, "utf8");
    if (!sql.trim()) throw new Error(`migration SQL is empty: ${entry.tag}.sql`);
    migrations.push({
      idx: entry.idx,
      tag: entry.tag,
      createdAt: String(entry.when),
      hash: crypto.createHash("sha256").update(sql).digest("hex"),
      file: path.relative(REPO_ROOT, filePath),
      destructive: findDestructiveStatements(sql),
    });
  }
  return migrations;
}

function findDestructiveStatements(sql) {
  const statements = sql.split(/-->\s*statement-breakpoint/u);
  const findings = [];
  for (const statement of statements) {
    const normalized = statement.replace(/--[^\n]*/gu, " ").trim();
    if (/\bDROP\s+(?:TABLE|COLUMN|SCHEMA|TYPE|DATABASE)\b/iu.test(normalized)) {
      findings.push("DROP statement");
    } else if (/\bTRUNCATE\b/iu.test(normalized)) {
      findings.push("TRUNCATE statement");
    } else if (/\bALTER\s+TABLE\b[\s\S]*\bDROP\s+COLUMN\b/iu.test(normalized)) {
      findings.push("DROP COLUMN statement");
    } else if (/\bDELETE\s+FROM\b/iu.test(normalized) && !/\bWHERE\b/iu.test(normalized)) {
      findings.push("DELETE without WHERE");
    }
  }
  return findings;
}

function readTargetChecks(target, migrations) {
  const checks = [];
  const appEnv = (process.env.APP_ENV ?? "").trim().toLowerCase();
  const neonBranch = (process.env.NEON_BRANCH ?? "").trim().toLowerCase();
  const protectedBranches = new Set(["production", "prod", "main", "master"]);
  const pooled = (process.env.DATABASE_URL ?? "").trim();
  const direct = (process.env.DATABASE_URL_UNPOOLED ?? "").trim();

  checks.push(resultCheck(
    "environment",
    appEnv === target,
    appEnv ? `APP_ENV=${appEnv}` : "APP_ENV is missing",
  ));
  checks.push(resultCheck(
    "neon-branch",
    target === "production"
      ? neonBranch === "production"
      : Boolean(neonBranch) && !protectedBranches.has(neonBranch),
    neonBranch
      ? target === "production"
        ? `NEON_BRANCH=${neonBranch}`
        : `NEON_BRANCH=${neonBranch} (non-production branch)`
      : "NEON_BRANCH is missing",
  ));

  let pooledUrl;
  let directUrl;
  for (const [name, value] of [["DATABASE_URL", pooled], ["DATABASE_URL_UNPOOLED", direct]]) {
    if (!value) {
      checks.push(resultCheck(name, false, `${name} is missing`));
      continue;
    }
    try {
      const parsed = new URL(value);
      const localHost = new Set(["localhost", "127.0.0.1", "::1", "postgres"]);
      const isNeon = parsed.hostname.endsWith(".neon.tech");
      const isLocal = localHost.has(parsed.hostname) || parsed.hostname.startsWith("127.");
      const tls = parsed.searchParams.get("sslmode");
      const secure = tls === "require" || tls === "verify-full";
      const hostOk = !isLocal && (isNeon || process.env.ALLOW_NON_NEON_DATABASE === "true");
      const ok = hostOk && secure && parsed.protocol === "postgresql:";
      checks.push(resultCheck(name, ok, ok ? `${parsed.hostname} with TLS` : "must be a TLS Neon URL"));
      if (name === "DATABASE_URL") pooledUrl = parsed;
      else directUrl = parsed;
    } catch {
      checks.push(resultCheck(name, false, `${name} is not a valid PostgreSQL URL`));
    }
  }

  if (pooledUrl && directUrl) {
    const directLooksPooled = /-pooler\./iu.test(directUrl.hostname);
    checks.push(resultCheck(
      "direct-migration-connection",
      !directLooksPooled,
      directLooksPooled ? "DATABASE_URL_UNPOOLED still points to a pooler host" : "direct host selected for migrations",
    ));
  }

  if (target === "production") {
    checks.push(resultCheck(
      "production-preflight-confirmation",
      process.env.CONFIRM_PRODUCTION_PREFLIGHT === "production",
      process.env.CONFIRM_PRODUCTION_PREFLIGHT === "production"
        ? "explicit production preflight confirmation present"
        : "set CONFIRM_PRODUCTION_PREFLIGHT=production",
    ));
  }

  const destructive = migrations.flatMap((migration) => migration.destructive.map((finding) => ({
    file: migration.file,
    finding,
  })));
  checks.push(resultCheck(
    "destructive-migrations",
    destructive.length === 0 || process.env.ALLOW_DESTRUCTIVE_MIGRATION === target,
    destructive.length === 0
      ? "no destructive SQL detected"
      : `review required: ${destructive.map((item) => `${item.file} (${item.finding})`).join(", ")}`,
  ));

  return { checks, pooledUrl, directUrl, destructive };
}

function failedChecks(checks) {
  return checks.filter((check) => !check.ok && check.severity === "error");
}

export function assessHistory(rows, migrations) {
  const expectedPairs = new Set(migrations.map((migration) => `${migration.hash}:${migration.createdAt}`));
  const appliedPairs = new Set(rows.map((row) => `${row.hash}:${String(row.created_at)}`));
  const pending = migrations.filter((migration) => !appliedPairs.has(`${migration.hash}:${migration.createdAt}`));
  const unexpected = rows.filter((row) => !expectedPairs.has(`${row.hash}:${String(row.created_at)}`));
  const mismatched = rows.flatMap((row, index) => {
    const expected = migrations[index];
    if (expected && row.hash === expected.hash && String(row.created_at) === expected.createdAt) return [];
    return [{
      id: row.id,
      actualHash: row.hash,
      actualCreatedAt: String(row.created_at),
      expectedTag: expected?.tag ?? null,
      expectedHash: expected?.hash ?? null,
      expectedCreatedAt: expected?.createdAt ?? null,
    }];
  });
  return {
    pending,
    unexpected,
    mismatched,
    compatible: mismatched.length === 0,
    current: mismatched.length === 0 && pending.length === 0,
  };
}

async function inspectDatabase(directUrl, migrations, requireHistory, requireVector) {
  const sql = getPostgresClient()(directUrl.toString(), {
    max: 1,
    connect_timeout: 8,
    idle_timeout: 5,
    prepare: false,
  });
  try {
    const [identity] = await sql`
      select current_database() as database,
             current_schema() as schema,
             current_setting('server_version_num') as server_version_num
    `;
    const [historyTable] = await sql`
      select to_regclass('drizzle.__drizzle_migrations') as migration_table
    `;
    const historyExists = Boolean(historyTable?.migration_table);
    const rows = historyExists
      ? await sql`select id, hash, created_at::text as created_at from drizzle.__drizzle_migrations order by id asc`
      : [];
    const [vector] = await sql`
      select exists(select 1 from pg_extension where extname = 'vector') as installed
    `;

    const historyAssessment = assessHistory(rows, migrations);
    const historyCompatible = historyExists ? historyAssessment.compatible : true;
    const historyCurrent = historyCompatible && historyAssessment.current;
    const vectorInstalled = Boolean(vector?.installed);
    const historyStatus = !historyExists
      ? "missing"
      : !historyCompatible
        ? "incompatible"
        : historyCurrent
          ? "current"
          : "pending";

    const checks = [
      resultCheck("database-connection", true, `${identity.database}/${identity.schema}`),
      resultCheck("migration-history", historyCompatible && (!requireHistory || historyCurrent), historyStatus),
      resultCheck("pgvector", !requireVector || vectorInstalled, vectorInstalled ? "installed" : "not installed"),
    ];

    return {
      database: {
        name: identity.database,
        schema: identity.schema,
        serverVersion: identity.server_version_num,
      },
      history: {
        status: historyStatus,
        applied: rows.length,
        expected: migrations.length,
        pending: historyAssessment.pending.map((migration) => migration.tag),
        unexpected: historyAssessment.unexpected.length,
        compatible: historyCompatible,
        mismatched: historyAssessment.mismatched,
      },
      pgvector: vectorInstalled,
      checks,
      ok: failedChecks(checks).length === 0,
    };
  } finally {
    await sql.end({ timeout: 5 });
  }
}

function staticDatabaseState(migrations, requireHistory, requireVector, reason = "static-only") {
  return {
    database: null,
    history: {
      status: requireHistory ? "not checked (static-only)" : "not requested",
      applied: null,
      expected: migrations.length,
      pending: null,
      unexpected: null,
    },
    pgvector: requireVector ? null : false,
    checks: [
      resultCheck("database-connection", true, `skipped (${reason})`, "info"),
      resultCheck("migration-history", !requireHistory, requireHistory ? "cannot verify history in static-only mode" : "not requested", requireHistory ? "warning" : "info"),
      resultCheck("pgvector", true, requireVector ? "deferred to database check" : "not required", "info"),
    ],
    ok: !requireHistory,
  };
}

function printResult(result, asJson) {
  if (asJson) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  console.log(`migration preflight: ${result.ok ? "PASS" : "FAIL"}`);
  console.log(`target=${result.target} branch=${result.branch || "missing"} migrations=${result.migrationFiles}`);
  for (const check of result.checks) {
    console.log(`- ${check.ok ? "PASS" : check.severity === "warning" ? "WARN" : "FAIL"} ${check.name}: ${check.detail}`);
  }
  if (result.history?.pending?.length) console.log(`pending migrations: ${result.history.pending.join(", ")}`);
}

export function loadEnvironment(target, fromFile = "") {
  return loadDefaultEnv(target, fromFile);
}

export async function runPreflight(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const loadedEnvFile = loadEnvironment(args.target, args.fromFile);
  if (process.env.REQUIRE_PGVECTOR === "true") args.requireVector = true;
  const migrations = readMigrationManifest(args.migrationDir);
  const targetChecks = readTargetChecks(args.target, migrations);
  const checks = [...targetChecks.checks];
  let databaseState = staticDatabaseState(migrations, args.requireHistory, args.requireVector, "static-only");

  if (failedChecks(checks).length === 0 && !args.staticOnly) {
    databaseState = await inspectDatabase(targetChecks.directUrl, migrations, args.requireHistory, args.requireVector);
  } else if (failedChecks(checks).length > 0) {
    databaseState = staticDatabaseState(
      migrations,
      args.requireHistory,
      args.requireVector,
      "static preflight failed",
    );
  }

  checks.push(...databaseState.checks);
  const result = {
    ok: failedChecks(checks).length === 0 && databaseState.ok,
    target: args.target,
    branch: process.env.NEON_BRANCH ?? "",
    appEnv: process.env.APP_ENV ?? "",
    envFile: loadedEnvFile,
    migrationFiles: migrations.length,
    migrations: migrations.map(({ file, tag, hash, createdAt, destructive }) => ({ file, tag, hash, createdAt, destructive })),
    checks,
    database: databaseState.database,
    history: databaseState.history,
    pgvector: databaseState.pgvector,
  };
  printResult(result, args.json);
  return result;
}

const entrypoint = process.argv[1] ? pathToFileURL(path.resolve(process.argv[1])).href : "";
if (entrypoint && import.meta.url === entrypoint) {
  try {
    const result = await runPreflight();
    process.exitCode = result.ok ? 0 : 1;
  } catch (error) {
    const result = { ok: false, error: redactedError(error) };
    if (process.argv.includes("--json")) console.log(JSON.stringify(result, null, 2));
    else console.error(`migration preflight: FAIL — ${result.error}`);
    process.exitCode = 1;
  }
}
