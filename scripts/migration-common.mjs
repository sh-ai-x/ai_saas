import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const PROTECTED_BRANCHES = new Set(["production", "prod", "main", "master"]);

export function parseDotenvValue(raw) {
  const value = raw.trim();
  if (value.length >= 2 && ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'")))) {
    return value.slice(1, -1);
  }
  return value;
}

export function loadDotenv(filePath, allowedKeys = null) {
  if (!filePath || !fs.existsSync(filePath)) return false;
  const content = fs.readFileSync(filePath, "utf8");
  for (const line of content.split(/\r?\n/u)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/u);
    if (!match || (allowedKeys && !allowedKeys.has(match[1])) || match[1] in process.env) continue;
    process.env[match[1]] = parseDotenvValue(match[2]);
  }
  return true;
}

export function readMigrationManifest(migrationDir, repoRoot = process.cwd()) {
  const journalPath = path.join(migrationDir, "meta", "_journal.json");
  if (!fs.existsSync(journalPath)) throw new Error(`Drizzle journal not found: ${path.relative(repoRoot, journalPath)}`);

  const journal = JSON.parse(fs.readFileSync(journalPath, "utf8"));
  if (!Array.isArray(journal.entries) || journal.entries.length === 0) {
    throw new Error("Drizzle journal has no migration entries");
  }

  const entries = [...journal.entries].sort((left, right) => left.idx - right.idx);
  const seenTags = new Set();
  return entries.map((entry) => {
    if (typeof entry.tag !== "string" || !/^[A-Za-z0-9_-]+$/u.test(entry.tag)) {
      throw new Error(`invalid migration tag at index ${entry.idx}`);
    }
    if (seenTags.has(entry.tag)) throw new Error(`duplicate migration tag: ${entry.tag}`);
    seenTags.add(entry.tag);

    const filePath = path.join(migrationDir, `${entry.tag}.sql`);
    if (!fs.existsSync(filePath)) throw new Error(`migration SQL not found: ${entry.tag}.sql`);
    const sql = fs.readFileSync(filePath, "utf8").replace(/\r\n?/gu, "\n");
    if (!sql.trim()) throw new Error(`migration SQL is empty: ${entry.tag}.sql`);
    return {
      idx: entry.idx,
      tag: entry.tag,
      createdAt: String(entry.when),
      hash: crypto.createHash("sha256").update(sql).digest("hex"),
      file: path.relative(repoRoot, filePath),
      sql,
    };
  });
}
