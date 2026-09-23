#!/usr/bin/env node

import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { loadDotenv, readMigrationManifest, PROTECTED_BRANCHES } from "./migration-common.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");
const requireFromWeb = createRequire(pathToFileURL(path.join(REPO_ROOT, "apps/web/package.json")));
const postgres = requireFromWeb("postgres");

const REPAIR_KEY = "stage2-canonical-v1";
const LEGACY_HISTORY = [
  [1, "19d877e52b3a5780ba6e4146c5fa08510b5b0c53e9c3a09c506f3cbebf7bb1e3", "1789779671842"],
  [2, "a4511550b760a7b552a6407563d01a4480b21db42fb1afc4d1f7dde39108931b", "1789780992501"],
  [3, "c05dca8eb9e077cd4fce512e7801e90c76568636c4db86946822185d591808ed", "1789784587150"],
  [4, "c2ec2bdfd4a8cffd0810cfd6724f773e8f0e2d3c6051b556fbd0956c6fe1f57d", "1789895455546"],
  [5, "b412411652ff5c21daddebeaf718a84b152cbde3e120e315aab7e6aea47b6cc8", "1789908105531"],
  [6, "8f051805da143cc1fe5072e3a1992e5c7e59bc6c753a856e0fd3884d87a71d1a", "1789915678999"],
  [7, "ca15976228b72e97c66f7e326b076479605e079e46f056cf099f6c30eabdb27f", "1789987873381"],
];
const REQUIRED_FAQ_IDS = [
  "faq-getting-started",
  "faq-google-login",
  "faq-local-development",
  "faq-agent-run",
  "faq-pricing-billing",
  "faq-support",
];
const REQUIRED_FAQ_SLUGS = [
  "getting-started",
  "google-login",
  "local-development",
  "agent-run",
  "pricing-billing",
  "support",
];
const LEGACY_FAQ_IDS = ["guides", "workspace", "support"];

function parseArgs(argv) {
  const args = {
    target: "",
    fromFile: "",
    migrationDir: path.join(REPO_ROOT, "apps/web/drizzle"),
    apply: false,
    cleanupLegacy: false,
    json: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--") continue;
    if (value === "--target") args.target = argv[++index] ?? "";
    else if (value === "--from-file") args.fromFile = argv[++index] ?? "";
    else if (value === "--migration-dir") args.migrationDir = path.resolve(REPO_ROOT, argv[++index] ?? "");
    else if (value === "--apply") args.apply = true;
    else if (value === "--cleanup-legacy") args.cleanupLegacy = true;
    else if (value === "--json") args.json = true;
    else throw new Error(`unknown argument: ${value}`);
  }
  if (args.target !== "staging") throw new Error("history repair is limited to --target staging");
  return args;
}

function rowTuple(row) {
  return [Number(row.id), row.hash, String(row.created_at)];
}

function sameRows(actual, expected) {
  return JSON.stringify(actual.map(rowTuple)) === JSON.stringify(expected);
}

function checkEnvironment({ apply, cleanupLegacy }) {
  const branch = (process.env.NEON_BRANCH ?? "").trim().toLowerCase();
  if ((process.env.APP_ENV ?? "").trim().toLowerCase() !== "staging") throw new Error("APP_ENV must be staging");
  if (!branch || PROTECTED_BRANCHES.has(branch)) throw new Error("NEON_BRANCH must be a non-production branch");
  if (apply && process.env.CONFIRM_STAGING_DB !== "staging") throw new Error("set CONFIRM_STAGING_DB=staging");
  if (apply && cleanupLegacy && process.env.CONFIRM_LEGACY_CLEANUP !== "stage2") throw new Error("set CONFIRM_LEGACY_CLEANUP=stage2");
  if (apply && !cleanupLegacy && process.env.CONFIRM_HISTORY_REPAIR !== "stage2") throw new Error("set CONFIRM_HISTORY_REPAIR=stage2");
  if (!process.env.DATABASE_URL_UNPOOLED) throw new Error("DATABASE_URL_UNPOOLED is required");
  return branch;
}

async function collectState(sql, migrations) {
  const history = await sql`select id, hash, created_at::text as created_at from drizzle.__drizzle_migrations order by id`;
  const [faqTable] = await sql`select to_regclass('public.faq_entries') as table_name`;
  const [pricingTable] = await sql`select to_regclass('public.pricing_options') as table_name`;
  const [catalogTable] = await sql`select to_regclass('public.pricing_catalog_settings') as table_name`;
  const faqRows = faqTable?.table_name
    ? await sql`select id, locale from public.faq_entries where id in ${sql(REQUIRED_FAQ_IDS)} order by id`
    : [];
  const faqConflicts = faqTable?.table_name
    ? await sql`select id, slug, locale from public.faq_entries where locale = 'en' and slug in ${sql(REQUIRED_FAQ_SLUGS)} and id not in ${sql(REQUIRED_FAQ_IDS)} order by id`
    : [];
  const legacyFaqRows = faqTable?.table_name
    ? await sql`select * from public.faq_entries where id in ${sql(LEGACY_FAQ_IDS)} order by id`
    : [];
  const [repairBackup] = await sql`select to_regclass('drizzle.__drizzle_migrations_repair_backup') as table_name`;
  const currencies = pricingTable?.table_name
    ? await sql`select currency, count(*)::int as count from public.pricing_options group by currency order by currency`
    : [];
  const catalogCurrencies = catalogTable?.table_name
    ? await sql`select currency, count(*)::int as count from public.pricing_catalog_settings group by currency order by currency`
    : [];
  return {
    history,
    expected: migrations.map((migration, index) => [index + 1, migration.hash, migration.createdAt]),
    faqTable: Boolean(faqTable?.table_name),
    pricingTable: Boolean(pricingTable?.table_name),
    catalogTable: Boolean(catalogTable?.table_name),
    faqRows,
    faqConflicts,
    legacyFaqRows,
    repairBackup: Boolean(repairBackup?.table_name),
    currencies,
    catalogCurrencies,
  };
}

function validateLegacyCleanup(state) {
  const checks = [];
  checks.push(["canonical-history", sameRows(state.history, state.expected), "migration history is current"]);
  checks.push(["repair-backup", state.repairBackup, "repair backup table exists"]);
  checks.push(["legacy-faq-rows", true, `${state.legacyFaqRows.length} legacy FAQ rows found`]);
  checks.push(["legacy-faq-scope", state.legacyFaqRows.every((row) => LEGACY_FAQ_IDS.includes(row.id)), "cleanup is limited to known legacy FAQ ids"]);
  return checks;
}

function validateCandidate(state) {
  const checks = [];
  checks.push(["legacy-history-signature", sameRows(state.history, LEGACY_HISTORY), `${state.history.length} history rows`]);
  checks.push(["faq-table", state.faqTable, "public.faq_entries exists"]);
  checks.push(["pricing-table", state.pricingTable, "public.pricing_options exists"]);
  checks.push(["catalog-table", state.catalogTable, "public.pricing_catalog_settings exists"]);
  checks.push(["faq-baseline", state.faqRows.length === REQUIRED_FAQ_IDS.length, `${state.faqRows.length}/${REQUIRED_FAQ_IDS.length} canonical FAQ rows exist`]);
  checks.push(["faq-conflicts", state.faqConflicts.every((row) => row.id && row.slug), `${state.faqConflicts.length} legacy FAQ slug conflicts will be preserved`]);
  checks.push(["pricing-baseline", state.currencies.reduce((sum, row) => sum + row.count, 0) === 5, "five pricing options exist"]);
  checks.push(["catalog-baseline", state.catalogCurrencies.reduce((sum, row) => sum + row.count, 0) === 1, "platform catalog setting exists"]);
  return checks;
}

function print(result, asJson) {
  if (asJson) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  console.log(`migration history repair: ${result.ok ? "PASS" : "FAIL"}`);
  console.log(`target=${result.target} branch=${result.branch} mode=${result.mode}`);
  for (const check of result.checks) console.log(`- ${check.ok ? "PASS" : "FAIL"} ${check.name}: ${check.detail}`);
  if (result.ok && result.mode === "plan") console.log("no database changes made");
}

async function applyRepair(sql, state, migrations) {
  const toss = migrations.find((migration) => migration.tag === "0003_toss_catalog_krw");
  const english = migrations.find((migration) => migration.tag === "0005_faq_english");
  if (!toss || !english) throw new Error("canonical 0003/0005 migrations are required");

  await sql.begin(async (tx) => {
    await tx`set local lock_timeout = '5s'`;
    await tx`lock table drizzle.__drizzle_migrations in access exclusive mode`;
    await tx`
      create table if not exists drizzle.__drizzle_migrations_repair_backup (
        repair_key text primary key,
        target text not null,
        neon_branch text not null,
        repaired_at timestamptz not null default now(),
        original_rows jsonb not null,
        original_faq_rows jsonb not null default '[]'::jsonb
      )
    `;
    await tx`
      alter table drizzle.__drizzle_migrations_repair_backup
      add column if not exists original_faq_rows jsonb not null default '[]'::jsonb
    `;
    await tx`
      insert into drizzle.__drizzle_migrations_repair_backup (repair_key, target, neon_branch, original_rows, original_faq_rows)
      values (${REPAIR_KEY}, 'staging', ${process.env.NEON_BRANCH}, ${tx.json(state.history)}, ${tx.json(state.faqConflicts)})
      on conflict (repair_key) do nothing
    `;

    for (const row of state.faqConflicts) {
      const legacySlug = `legacy-${row.id}`;
      const [occupied] = await tx`select exists(select 1 from public.faq_entries where locale = 'en' and slug = ${legacySlug} and id <> ${row.id}) as occupied`;
      if (occupied.occupied) throw new Error(`cannot preserve FAQ slug conflict for ${row.id}: ${legacySlug} is already used`);
      await tx`update public.faq_entries set slug = ${legacySlug}, updated_at = now() where id = ${row.id}`;
    }

    for (const statement of [toss.sql, english.sql].flatMap((content) => content.split(/-->\s*statement-breakpoint/u))) {
      if (statement.trim()) await tx.unsafe(statement);
    }

    for (const [id, hash, createdAt] of state.expected) {
      await tx`update drizzle.__drizzle_migrations set hash = ${hash}, created_at = ${createdAt} where id = ${id}`;
    }
    await tx`delete from drizzle.__drizzle_migrations where id > ${state.expected.length}`;

    const finalRows = await tx`select id, hash, created_at::text as created_at from drizzle.__drizzle_migrations order by id`;
    if (!sameRows(finalRows, state.expected)) throw new Error("post-repair history does not match canonical journal");
    const [pricing] = await tx`select count(*)::int as count from public.pricing_options where currency = 'KRW'`;
    const [catalog] = await tx`select count(*)::int as count from public.pricing_catalog_settings where currency = 'KRW'`;
    const [faq] = await tx`select count(*)::int as count from public.faq_entries where id in ${tx(REQUIRED_FAQ_IDS)} and locale = 'en'`;
    if (pricing.count !== 5 || catalog.count !== 1 || faq.count !== REQUIRED_FAQ_IDS.length) {
      throw new Error("post-repair data verification failed");
    }
  });
}

async function cleanupLegacyFaq(sql, state) {
  await sql.begin(async (tx) => {
    await tx`set local lock_timeout = '5s'`;
    await tx`lock table public.faq_entries in access exclusive mode`;
    await tx`
      alter table drizzle.__drizzle_migrations_repair_backup
      add column if not exists legacy_faq_rows jsonb not null default '[]'::jsonb
    `;
    await tx`
      update drizzle.__drizzle_migrations_repair_backup
      set legacy_faq_rows = ${tx.json(state.legacyFaqRows)}
      where repair_key = ${REPAIR_KEY}
    `;
    await tx`delete from public.faq_entries where id in ${tx(LEGACY_FAQ_IDS)}`;
    const remaining = await tx`select count(*)::int as count from public.faq_entries where id in ${tx(LEGACY_FAQ_IDS)}`;
    if (remaining[0].count !== 0) throw new Error("legacy FAQ cleanup verification failed");
  });
}

async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const envFile = args.fromFile ? path.resolve(args.fromFile) : path.join(REPO_ROOT, ".env.stage");
  if (!loadDotenv(envFile)) throw new Error(`environment file not found: ${envFile}`);
  const branch = checkEnvironment(args);
  const migrations = readMigrationManifest(args.migrationDir, REPO_ROOT);
  const sql = postgres(process.env.DATABASE_URL_UNPOOLED, { max: 1, connect_timeout: 8, prepare: false });
  try {
    const state = await collectState(sql, migrations);
    if (args.cleanupLegacy) {
      const checks = validateLegacyCleanup(state).map(([name, ok, detail]) => ({ name, ok, detail }));
      const result = { ok: checks.every((check) => check.ok), target: "staging", branch, mode: args.apply ? "apply" : "plan", checks };
      if (!result.ok || !args.apply) {
        print(result, args.json);
        return result.ok ? 0 : 1;
      }
      await cleanupLegacyFaq(sql, state);
      result.checks.push({ name: "legacy-faq-cleanup", ok: true, detail: "known legacy FAQ rows removed and archived" });
      print(result, args.json);
      return 0;
    }
    if (sameRows(state.history, state.expected)) {
      const result = {
        ok: true,
        target: "staging",
        branch,
        mode: args.apply ? "apply" : "plan",
        checks: [{ name: "canonical-history", ok: true, detail: `${migrations.length} rows already current; no repair needed` }],
      };
      print(result, args.json);
      return 0;
    }
    const checks = validateCandidate(state).map(([name, ok, detail]) => ({ name, ok, detail }));
    const result = { ok: checks.every((check) => check.ok), target: "staging", branch, mode: args.apply ? "apply" : "plan", checks };
    if (!result.ok || !args.apply) {
      print(result, args.json);
      return result.ok ? 0 : 1;
    }
    await applyRepair(sql, state, migrations);
    result.checks.push({ name: "canonical-history", ok: true, detail: `${migrations.length} rows restored` });
    result.checks.push({ name: "data-verification", ok: true, detail: "KRW catalog and English FAQ verified" });
    print(result, args.json);
    return 0;
  } finally {
    await sql.end({ timeout: 5 });
  }
}

try {
  process.exitCode = await main();
} catch (error) {
  console.error(`migration history repair: FAIL — ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}
