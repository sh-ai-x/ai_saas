"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

type JsonRecord = Record<string, any>;
type LocalFile = { file: File; path: string; root: string };
type AnalysisMode = "implementation" | "impact";
type RepositoryStatus = "idle" | "picking" | "loading" | "ready" | "analyzing" | "error";

const CODE_EXTENSIONS = new Set([".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt", ".sql", ".md", ".json", ".yaml", ".yml", ".html", ".css"]);
const MAX_ANALYSIS_FILES = 600;
const MAX_ANALYSIS_BYTES = 8 * 1024 * 1024;
const MAX_EVIDENCE_RANGE_LINES = 3;
const SECRET_RE = /(^|\/)(\.env(?:\.|$)|.*\.(pem|key|p12|pfx|crt|cer)$|credentials?|secrets?)(\/|$)/i;
const BUILD_RE = /(^|\/)(\.git|\.worktrees|worktrees|node_modules|\.next|dist|build|coverage|target|\.venv|venv|__pycache__|\.cache|\.turbo)(\/|$)/;
const AI_SIGNAL_TERMS = ["prompt", "model", "retriev", "graph", "provider", "trace", "safety", "cost"];

function implementationStatus(value: unknown): "implemented" | "partial" | "missing" | "unknown" | "contradicted" {
  const status = String(value ?? "unknown").toLowerCase().replace(/[ -]/g, "_");
  if (["implemented", "complete", "completed", "covered", "satisfied", "ready"].includes(status)) return "implemented";
  if (["partial", "partial_implement", "partial_implemented", "partially_implemented", "partial_implementation", "partially_covered", "in_progress", "revise"].includes(status)) return "partial";
  if (["missing", "not_implemented", "not_found"].includes(status)) return "missing";
  if (["contradicted", "conflict", "failed"].includes(status)) return "contradicted";
  return "unknown";
}

function statusLabel(value: unknown) {
  const status = implementationStatus(value);
  return {
    implemented: "IMPLEMENTED",
    partial: "PARTIAL IMPLEMENTATION",
    missing: "MISSING",
    contradicted: "CONTRADICTED",
    unknown: "UNKNOWN",
  }[status];
}

async function digest(text: string) {
  if (globalThis.crypto?.subtle) {
    const bytes = new TextEncoder().encode(text);
    const hash = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(hash)).map((value) => value.toString(16).padStart(2, "0")).join("");
  }
  return text.length.toString(16);
}

function ignored(path: string, patterns: string[]) {
  if (SECRET_RE.test(path) || BUILD_RE.test(path)) return "policy";
  const base = path.split("/").pop() ?? path;
  for (const raw of patterns) {
    const pattern = raw.trim();
    if (!pattern || pattern.startsWith("#") || pattern.startsWith("!")) continue;
    const normalized = pattern.replace(/^\//, "").replace(/\/$/, "");
    if (normalized === base || path === normalized || path.startsWith(`${normalized}/`)) return "gitignore";
    if (normalized.includes("*")) {
      const patternRegex = normalized.split("*").map((part) => part.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*");
      if (new RegExp(`^${patternRegex}$`).test(path)) return "gitignore";
    }
  }
  return null;
}

function language(path: string) {
  const suffix = path.slice(path.lastIndexOf(".")).toLowerCase();
  return suffix === ".py" ? "python" : [".ts", ".tsx"].includes(suffix) ? "typescript" : [".js", ".jsx", ".mjs"].includes(suffix) ? "javascript" : suffix.slice(1) || "text";
}

function repositoryEntry(file: File): LocalFile {
  const rawPath = file.webkitRelativePath || file.name;
  const parts = rawPath.split("/");
  return { file, root: parts.length > 1 ? parts[0] : "local-repository", path: parts.length > 1 ? parts.slice(1).join("/") : rawPath };
}

function headingsAndRequirements(text: string, source: string) {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const result: JsonRecord[] = [];
  for (const line of lines) {
    const cleaned = line.replace(/^#{1,6}\s+/, "").replace(/^[-*\d.)]+\s+/, "").trim();
    if (cleaned.length < 12) continue;
    if (/must|required|should|shall|acceptance|requirement|latency|cost|safety|trace|checkpoint/i.test(cleaned)) {
      const kind = /must|required|shall|acceptance/i.test(cleaned) ? "acceptance" : "requirement";
      const kindCode = kind === "acceptance" ? "AC" : "REQ";
      const kindDescription = kind === "acceptance" ? "Acceptance Criteria: a concrete and verifiable condition for deciding completion" : "Requirement: a functional, quality, or operational capability the system must provide or preserve";
      const sameKindCount = result.filter((item) => item.kind === kind).length + 1;
      result.push({ requirement_id: `${kindCode}-${String(sameKindCount).padStart(3, "0")}`, text: cleaned.slice(0, 500), source, kind, kind_code: kindCode, kind_label: kind === "acceptance" ? "Acceptance Criteria" : "Requirement", kind_description: kindDescription });
    }
  }
  return result.slice(0, 40);
}

async function parseTextProposal(value: string, name = "proposal.txt", mediaType: "text/markdown" | "text/plain" = "text/plain") {
  const text = value.trim().slice(0, 120_000);
  if (!text) throw new Error("Enter proposal text.");
  const source = mediaType === "text/markdown" ? "markdown" : "text";
  return {
    name,
    media_type: mediaType,
    sha256: await digest(text),
    extraction_confidence: 1,
    sections: [{ title: name, text, source }],
    requirements: headingsAndRequirements(text, source),
  };
}

async function parseProposal(file: File) {
  const isHtml = /\.html?$/i.test(file.name);
  const isMarkdown = /\.(md|markdown)$/i.test(file.name);
  const isText = /\.(txt|text)$/i.test(file.name);
  if (isMarkdown || isText) {
    return parseTextProposal(await file.text(), file.name, isMarkdown ? "text/markdown" : "text/plain");
  }
  let text = "";
  let confidence = 1;
  if (isHtml) {
    const html = await file.text();
    const document = new DOMParser().parseFromString(html, "text/html");
    text = document.body?.innerText ?? html.replace(/<[^>]+>/g, " ");
  } else {
    const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
    const pdf = await pdfjs.getDocument({ data: await file.arrayBuffer(), disableWorker: true } as any).promise;
    const pages: string[] = [];
    for (let pageNumber = 1; pageNumber <= Math.min(pdf.numPages, 60); pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const content = await page.getTextContent();
      const pageText = content.items.map((item: any) => String(item.str ?? "")).join(" ").trim();
      if (pageText) pages.push(`Page ${pageNumber}\n${pageText}`);
    }
    text = pages.join("\n\n");
    confidence = text ? 0.95 : 0;
  }
  if (!text.trim()) throw new Error("No text could be extracted from the proposal.");
  const sections = isHtml ? [{ title: file.name, text: text.slice(0, 12_000), source: "html" }] : text.split(/\n\n(?=Page \d+)/).map((page) => ({ title: page.split("\n", 1)[0] ?? "PDF page", text: page.slice(0, 12_000), source: `pdf:${page.split("\n", 1)[0] ?? "page"}` }));
  return { name: file.name, media_type: isHtml ? "text/html" : "application/pdf", sha256: await digest(text), extraction_confidence: confidence, sections, requirements: headingsAndRequirements(text, isHtml ? "html" : "pdf:p1") };
}

function evidenceForRequirement(path: string, lines: string[], requirement: JsonRecord) {
  const requirementTokens = [...new Set(String(requirement.text ?? "").toLowerCase().match(/[a-z][a-z0-9_-]{2,}/g) ?? [])].slice(0, 24);
  if (!requirementTokens.length) return [];
  const hits = lines.flatMap((line, index) => {
    const lower = line.toLowerCase();
    const matchedTokens = requirementTokens.filter((token) => lower.includes(token));
    const matchedSignals = AI_SIGNAL_TERMS.filter((term) => lower.includes(term));
    const score = matchedTokens.length * 3 + matchedSignals.length;
    return score ? [{ index, matchedTokens, matchedSignals, score }] : [];
  });
  const ranges: Array<{ start: number; end: number; hits: typeof hits }> = [];
  for (const hit of hits) {
    const previous = ranges[ranges.length - 1];
    if (previous && hit.index <= previous.end + 1 && previous.end - previous.start < MAX_EVIDENCE_RANGE_LINES - 1) {
      previous.end = Math.min(Math.max(previous.end, hit.index + 1), previous.start + MAX_EVIDENCE_RANGE_LINES - 1, lines.length - 1);
      previous.hits.push(hit);
      continue;
    }
    const start = hit.index === lines.length - 1 ? Math.max(0, hit.index - (MAX_EVIDENCE_RANGE_LINES - 1)) : hit.index;
    const end = Math.min(lines.length - 1, start + MAX_EVIDENCE_RANGE_LINES - 1);
    ranges.push({ start, end, hits: [hit] });
  }
  return ranges.filter((range) => range.end > range.start).slice(0, 4).map((range) => {
    const matched = [...new Set(range.hits.flatMap((hit) => [...hit.matchedTokens, ...hit.matchedSignals]))].slice(0, 5);
    const startLine = range.start + 1;
    const endLine = range.end + 1;
    return {
      path,
      start_line: startLine,
      end_line: endLine,
      excerpt: lines.slice(range.start, range.end + 1).map((line, offset) => `${startLine + offset}: ${line.trim()}`).join("\n").slice(0, 720),
      score: Math.max(...range.hits.map((hit) => hit.score)),
      rationale: `The range \"${path}:${startLine}–${endLine}\" was selected because ${matched.join(", ")} signals connected to \"${String(requirement.text).slice(0, 120)}\" appear together in the implementation flow. It shows an adjacent code flow rather than a single line.`,
    };
  });
}

async function buildRepository(files: LocalFile[], requirements: JsonRecord[]) {
  const ignoreFile = files.find(({ path }) => path.endsWith(".gitignore"));
  const patterns = ignoreFile ? (await ignoreFile.file.text()).split(/\r?\n/) : [];
  const excluded: Record<string, number> = {};
  const selected: JsonRecord[] = [];
  let analyzedBytes = 0;
  const orderedFiles = [...files].sort((left, right) => left.path.localeCompare(right.path));
  for (const { file, path } of orderedFiles) {
    const reason = ignored(path, patterns);
    if (reason) {
      excluded[reason] = (excluded[reason] ?? 0) + 1;
      continue;
    }
    const suffix = path.slice(path.lastIndexOf(".")).toLowerCase();
    if (!CODE_EXTENSIONS.has(suffix) || file.size > 256 * 1024) {
      excluded[file.size > 256 * 1024 ? "file_size" : "binary_or_unsupported"] = (excluded[file.size > 256 * 1024 ? "file_size" : "binary_or_unsupported"] ?? 0) + 1;
      continue;
    }
    if (selected.length >= MAX_ANALYSIS_FILES || analyzedBytes + file.size > MAX_ANALYSIS_BYTES) {
      excluded["analysis_budget"] = (excluded["analysis_budget"] ?? 0) + 1;
      continue;
    }
    const content = await file.text();
    const lines = content.split(/\r?\n/);
    const evidenceByRequirement = Object.fromEntries(requirements.map((requirement) => [String(requirement.requirement_id), evidenceForRequirement(path, lines, requirement)]));
    selected.push({ path, size: file.size, sha256: await digest(content), language: language(path), symbols: [...content.matchAll(/(?:function|class|def|interface|type|const)\s+([A-Za-z_$][\w$]*)/g)].slice(0, 12).map((match) => match[1]), evidenceByRequirement });
    analyzedBytes += file.size;
  }
  selected.sort((a, b) => String(a.path).localeCompare(String(b.path)));
  const fingerprint = await digest(selected.map((item) => `${item.path}:${item.sha256}`).join("\n"));
  const evidence = requirements.flatMap((requirement) => selected.flatMap((file) => ((file.evidenceByRequirement as Record<string, JsonRecord[]>)[String(requirement.requirement_id)] ?? []).slice(0, 5).map((item) => ({ ...item, requirement_id: requirement.requirement_id })))).slice(0, 200);
  return { root_name: files[0]?.root ?? "local-repository", branch: null, head: null, fingerprint, files: selected.map(({ evidenceByRequirement: _evidence, ...file }) => file), unknowns: [], excluded, evidence };
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/foundation${path}`, { ...init, credentials: "same-origin", headers: { "content-type": "application/json", "x-tenant-id": "demo-tenant", ...(init?.headers ?? {}) }, cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(String(body.message ?? body.error ?? `Request failed (${response.status})`));
  return body as T;
}

// The browser folder picker never exposes an OS absolute path (a platform
// privacy boundary, not something app code can work around), and no repo
// name may be pre-configured server-side: the analyzed repository changes
// on every pick. editorFileRoot only ever matches by coincidence — the one
// repository the server happened to be started against.
function rootMatchesEditorFileRoot(editorFileRoot: string, name: string) {
  return Boolean(editorFileRoot) && editorFileRoot.replace(/\/+$/, "").split("/").pop() === name;
}

export function ChangeImpactWorkbench() {
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("implementation");
  const [editorFileRoot, setEditorFileRoot] = useState("");
  const [knownRepositories, setKnownRepositories] = useState<Record<string, string>>({});
  const [selectedRequirementId, setSelectedRequirementId] = useState("");
  const [proposal, setProposal] = useState<File | null>(null);
  const [proposalUrl, setProposalUrl] = useState("");
  const [proposalText, setProposalText] = useState("");
  const [proposalDocument, setProposalDocument] = useState<JsonRecord | null>(null);
  const [loadedProposalUrl, setLoadedProposalUrl] = useState("");
  const [repoFiles, setRepoFiles] = useState<LocalFile[]>([]);
  const [repoContext, setRepoContext] = useState<JsonRecord | null>(null);
  const [repositoryStatus, setRepositoryStatus] = useState<RepositoryStatus>("idle");
  const [repositoryMessage, setRepositoryMessage] = useState("Select a folder to see repository progress.");
  const [review, setReview] = useState<JsonRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [status, setStatus] = useState("local-only / provider-off");
  const [observability, setObservability] = useState<JsonRecord>({ enabled: false, provider: "none" });
  const [budget] = useState("LangChain 1 call · optional JEV 1 call");
  const proposalInputRef = useRef<HTMLInputElement>(null);
  const directoryInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void api<JsonRecord>("/v1/change-impact/catalog").then((catalog) => {
      setEditorFileRoot(String(catalog.editor_file_root ?? ""));
      setObservability((catalog.observability as JsonRecord | undefined) ?? { enabled: false, provider: "none" });
    }).catch(() => {
      setEditorFileRoot("");
    });
  }, []);

  function selectAnalysisMode(mode: AnalysisMode) {
    setAnalysisMode(mode);
    setReview(null);
    setSelectedRequirementId("");
    setCopied(false);
    setError("");
    setStatus(mode === "implementation" ? "implementation coverage selected" : "code impact selected");
  }

  const selectedCount = useMemo(() => repoFiles.filter(({ path }) => path !== ".gitignore").length, [repoFiles]);

  async function onProposal(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setProposal(file);
    setProposalUrl("");
    setProposalText("");
    setProposalDocument(null);
    setLoadedProposalUrl("");
    setReview(null);
    setError("");
  }

  async function fetchProposalUrl(rawUrl: string) {
    const url = rawUrl.trim();
    if (!url) throw new Error("Enter a document URL.");
    const result = await api<JsonRecord>("/v1/change-impact/documents/from-url", { method: "POST", body: JSON.stringify({ url }) });
    const document = { ...(result.document as JsonRecord), requirements: result.requirements, source: "remote-url" };
    setProposal(null);
    setProposalText("");
    setProposalDocument(document);
    setLoadedProposalUrl(url);
    setError("");
    return document;
  }

  function onProposalText(value: string) {
    setProposalText(value);
    setProposal(null);
    setProposalUrl("");
    setProposalDocument(null);
    setLoadedProposalUrl("");
    setReview(null);
    setError("");
  }

  async function chooseLocalProposalFile() {
    const picker = (window as Window & { showOpenFilePicker?: (options?: { multiple?: boolean; types?: Array<{ description: string; accept: Record<string, string[]> }> }) => Promise<Array<{ getFile: () => Promise<File> }>> }).showOpenFilePicker;
    if (!picker) {
      proposalInputRef.current?.click();
      return;
    }
    const [handle] = await picker({
      multiple: false,
      types: [{ description: "Proposal document", accept: { "text/html": [".html", ".htm"], "text/markdown": [".md", ".markdown"], "text/plain": [".txt", ".text"], "application/pdf": [".pdf"] } }],
    });
    const file = await handle.getFile();
    setProposal(file);
    setProposalUrl("");
    setProposalDocument(null);
    setLoadedProposalUrl("");
    setReview(null);
    setError("");
  }

  async function onProposalUrl() {
    setBusy(true);
    try {
      const url = proposalUrl.trim();
      if (url.toLowerCase().startsWith("file:")) {
        try {
          await fetchProposalUrl(url);
          return;
        } catch {
          // Docker can read only mounted paths. For an external local path,
          // use the same button gesture to request browser file permission.
          await chooseLocalProposalFile();
          return;
        }
      }
      await fetchProposalUrl(url);
    } catch (requestError) {
      const errorName = requestError && typeof requestError === "object" && "name" in requestError ? String(requestError.name) : "";
      if (errorName === "AbortError") {
        setError("");
        return;
      }
      setProposalDocument(null);
      setLoadedProposalUrl("");
      setError(requestError instanceof Error ? requestError.message : "Could not load the document URL.");
    } finally {
      setBusy(false);
    }
  }

  async function prepareRepositoryEntries(entries: LocalFile[]) {
    if (!entries.length) throw new Error("No files were found in the selected Git repository.");
    const ignoreFile = entries.find(({ path }) => path === ".gitignore");
    const patterns = ignoreFile ? (await ignoreFile.file.text()).split(/\r?\n/) : [];
    const retained: LocalFile[] = [];
    let retainedBytes = 0;
    const root = entries[0]?.root ?? "local-repository";
    const candidateEntries = entries.filter(({ path }) => path === ".gitignore" || !BUILD_RE.test(path));
    for (const entry of candidateEntries.sort((left, right) => left.path.localeCompare(right.path))) {
      if (entry.path === ".gitignore") {
        retained.push(entry);
        continue;
      }
      const suffix = entry.path.slice(entry.path.lastIndexOf(".")).toLowerCase();
      if (ignored(entry.path, patterns) || !CODE_EXTENSIONS.has(suffix) || entry.file.size > 256 * 1024) continue;
      if (retained.filter(({ path }) => path !== ".gitignore").length >= MAX_ANALYSIS_FILES || retainedBytes + entry.file.size > MAX_ANALYSIS_BYTES) continue;
      retained.push(entry);
      retainedBytes += entry.file.size;
    }
    const codeFiles = retained.filter(({ path }) => path !== ".gitignore");
    if (!codeFiles.length) throw new Error("No analyzable code files were found. Select the repository root rather than its parent folder.");
    setRepoFiles(retained);
    setRepositoryStatus("ready");
    setStatus(`${root} · ${codeFiles.length} code files ready · worktrees excluded`);
    // Some Chromium builds carry a non-standard absolute `.path` on File
    // objects from a directory picker. When it's there, use it directly —
    // instant, exact, no server round trip. Detected at runtime per pick;
    // most browsers (Safari, Firefox, sandboxed Chromium) leave it
    // undefined, and we fall through to the server lookup below. Reported
    // visibly either way — no DevTools needed to see which path fired.
    const nativePathEntry = entries.find((entry) => typeof (entry.file as File & { path?: string }).path === "string" && (entry.file as File & { path?: string }).path);
    const nativePath = nativePathEntry ? (nativePathEntry.file as File & { path?: string }).path! : "";
    if (nativePath && nativePathEntry && nativePath.length > nativePathEntry.path.length && nativePath.endsWith(nativePathEntry.path)) {
      const absoluteRoot = nativePath.slice(0, nativePath.length - nativePathEntry.path.length).replace(/\/+$/, "");
      setKnownRepositories((current) => ({ ...current, [root]: absoluteRoot }));
      setRepositoryMessage(`Prepared ${codeFiles.length} code files from ${root}. VS Code path (from browser): ${absoluteRoot}`);
    } else {
      setRepositoryMessage(`Prepared ${codeFiles.length} code files from ${root}. Browser did not expose an absolute path; checking the server for a mounted match…`);
      void resolveEditorRoot(root, codeFiles.length);
    }
  }

  // Fired by the existing "Choose Git repository directory" button — the
  // moment a repo is picked, look up its real host path by exact folder
  // name. No prompt, no typing, no pre-declared repo list: any repository
  // under LOCAL_REPOSITORY_HOST_ROOT resolves the instant it's picked, and
  // nothing you haven't picked is ever enumerated (name-scoped, not a full
  // catalog listing — that's what made the eager version slow).
  async function resolveEditorRoot(root: string, codeFileCount: number) {
    if (rootMatchesEditorFileRoot(editorFileRoot, root) || knownRepositories[root]) return;
    try {
      const body = await api<JsonRecord>(`/v1/repositories?name=${encodeURIComponent(root)}`);
      // host_path (not canonical_path — that's container-internal) is the
      // path translated back to this machine's real filesystem.
      const paths = [
        ...new Set(
          ((body.repositories as JsonRecord[] | undefined) ?? [])
            .map((entry) => String(entry.host_path ?? ""))
            .filter(Boolean),
        ),
      ];
      if (paths.length === 1) {
        setKnownRepositories((current) => ({ ...current, [root]: paths[0] }));
        setRepositoryMessage(`Prepared ${codeFileCount} code files from ${root}. VS Code path (from server): ${paths[0]}`);
        return;
      }
      // More than one repository shares this folder name. A general,
      // non-repo-specific tie-break: prefer the one closest to the mounted
      // workspace root -- a repo nested inside another project is almost
      // always a dependency clone, not the one meant by name alone. Only
      // when depth itself ties does this stay genuinely ambiguous.
      if (paths.length > 1) {
        const depth = (path: string) => path.split("/").filter(Boolean).length;
        const sorted = [...paths].sort((left, right) => depth(left) - depth(right));
        if (depth(sorted[0]) < depth(sorted[1])) {
          setKnownRepositories((current) => ({ ...current, [root]: sorted[0] }));
          setRepositoryMessage(`Prepared ${codeFileCount} code files from ${root}. VS Code path (closest to workspace root among ${paths.length} matches): ${sorted[0]}`);
          return;
        }
        setRepositoryMessage(`Prepared ${codeFileCount} code files from ${root}. "Open in VS Code" is unavailable: ${paths.length} repositories on this machine are named "${root}" at the same depth — ${paths.join(" · ")}`);
        return;
      }
      setRepositoryMessage(`Prepared ${codeFileCount} code files from ${root}. "Open in VS Code" is unavailable: no server-mounted repository named "${root}" was found.`);
    } catch {
      setRepositoryMessage(`Prepared ${codeFileCount} code files from ${root}. "Open in VS Code" is unavailable: the repository catalog is not configured on the server.`);
    }
  }

  async function onRepository(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    setRepositoryStatus("loading");
    setRepositoryMessage("Reading the selected folder…");
    await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
    const pickedFiles = Array.from(input.files ?? []);
    input.value = "";
    setBusy(true);
    setRepoContext(null);
    setReview(null);
    setError("");
    setStatus("reading repository directory…");
    try {
      await prepareRepositoryEntries(pickedFiles.map(repositoryEntry));
    } catch (requestError) {
      setRepoFiles([]);
      setRepositoryStatus("error");
      setRepositoryMessage(requestError instanceof Error ? requestError.message : "Could not prepare the Git repository.");
      setError(requestError instanceof Error ? requestError.message : "Could not prepare the Git repository.");
    } finally {
      setBusy(false);
    }
  }

  async function chooseRepository() {
    setRepositoryStatus("picking");
    setRepositoryMessage("Choose the Git repository root in the folder picker.");
    setError("");
    const picker = (window as Window & { showDirectoryPicker?: (options?: { mode: "read" }) => Promise<any> }).showDirectoryPicker;
    if (!picker) {
      directoryInputRef.current?.click();
      return;
    }
    setBusy(true);
    try {
      const directory = await picker({ mode: "read" });
      setRepositoryStatus("loading");
      setRepositoryMessage(`Reading files in ${directory.name}… (worktrees are skipped)`);
      const entries: LocalFile[] = [];
      let scanned = 0;
      const walk = async (handle: any, prefix = ""): Promise<void> => {
        for await (const [name, child] of handle.entries()) {
          const relativePath = prefix ? `${prefix}/${name}` : name;
          if (BUILD_RE.test(relativePath)) continue;
          if (child.kind === "directory") {
            await walk(child, relativePath);
          } else {
            entries.push({ file: await child.getFile(), path: relativePath, root: directory.name });
            scanned += 1;
            if (scanned % 100 === 0) {
              setRepositoryMessage(`Reading ${scanned} files from ${directory.name}…`);
              await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
            }
          }
        }
      };
      await walk(directory);
      await prepareRepositoryEntries(entries);
    } catch (requestError: any) {
      if (requestError?.name === "AbortError") {
        setRepositoryStatus("idle");
        setRepositoryMessage("Folder selection was cancelled. Use the button to choose a folder again.");
      } else {
        setRepositoryStatus("error");
        setRepositoryMessage(requestError instanceof Error ? requestError.message : "Could not read the Git repository directory.");
        setError(requestError instanceof Error ? requestError.message : "Could not read the Git repository directory.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function startReview() {
    if ((!proposal && !proposalDocument && !proposalUrl.trim() && !proposalText.trim()) || !repoFiles.length) {
      setError("Prepare a proposal file, URL, or text input and a Git repository directory.");
      return;
    }
    setBusy(true);
    setCopied(false);
    setError("");
    try {
      let document = proposalDocument;
      if (proposalUrl.trim() && loadedProposalUrl !== proposalUrl.trim()) {
        document = await fetchProposalUrl(proposalUrl);
      } else if (!document && proposal) {
        document = await parseProposal(proposal);
      } else if (!document && proposalText.trim()) {
        document = await parseTextProposal(proposalText);
      }
      if (!document) throw new Error("Could not prepare the proposal.");
      setRepositoryStatus("analyzing");
      setRepositoryMessage("Building repository structure and requirement evidence…");
      const repository = await buildRepository(repoFiles, document.requirements);
      setRepoContext(repository);
      const { sections: _sections, requirements: _documentRequirements, ...documentSummary } = document;
      const { files: _files, evidence: _repositoryEvidence, ...repositorySummary } = repository;
      const result = await api<JsonRecord>("/v1/change-impact/reviews", { method: "POST", body: JSON.stringify({ mode: analysisMode, document: documentSummary, repository: repositorySummary, requirements: document.requirements, evidence: repository.evidence }) });
      const resultPayload = result.payload as JsonRecord | undefined;
      const resultReport = resultPayload?.report as JsonRecord | undefined;
      setReview(result);
      const firstRequirementId = String(((resultReport?.requirements as JsonRecord[] | undefined)?.[0]?.requirement_id) ?? "");
      setSelectedRequirementId(firstRequirementId);
      setRepositoryStatus("ready");
      setRepositoryMessage("Repository analysis and proposal review are complete.");
      setStatus("review complete · raw files not stored");
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Could not start the review.";
      if (repoFiles.length) {
        setRepositoryStatus("ready");
        setRepositoryMessage(`${selectedCount} code files are ready. You can retry the review or choose another repository.`);
      } else {
        setRepositoryStatus("error");
        setRepositoryMessage(message);
      }
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function copyProposal(markdown: string) {
    if (!markdown) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(markdown);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = markdown;
        textarea.setAttribute("readonly", "true");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        if (!document.execCommand("copy")) throw new Error("copy failed");
        textarea.remove();
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Could not copy Markdown to the clipboard.");
    }
  }

  const payload = review?.payload as JsonRecord | undefined;
  const report = payload?.report as JsonRecord | undefined;
  const requirements = (report?.requirements as JsonRecord[] | undefined) ?? [];
  const evidence = (payload?.evidence as JsonRecord[] | undefined) ?? [];
  const assessment = (report?.assessment as JsonRecord | undefined) ?? {};
  const proposalMarkdown = String(report?.proposal_markdown ?? "");
  const proposalChanges = (report?.changes as JsonRecord[] | undefined) ?? [];
  const visibleEvidence = evidence.filter((item) => Number(item.start_line) >= 1 && Number(item.end_line) > Number(item.start_line) && /[.!?。！？]\s*$/.test(String(item.rationale ?? ""))).slice(0, 12);
  const implementationCounts = requirements.reduce((counts, item) => {
    const status = implementationStatus(item.status);
    counts[status] += 1;
    return counts;
  }, { implemented: 0, partial: 0, missing: 0, unknown: 0, contradicted: 0 });
  const implementationProgress = requirements.length ? Math.round(((implementationCounts.implemented + implementationCounts.partial * 0.5) / requirements.length) * 100) : 0;
  const isImplementationMode = analysisMode === "implementation";
  const activeRequirementId = selectedRequirementId || String(requirements[0]?.requirement_id ?? "");
  const activeRequirement = requirements.find((item) => String(item.requirement_id) === activeRequirementId);
  const activeEvidence = visibleEvidence.filter((item) => String(item.requirement_id) === activeRequirementId);
  const activeRequirementKind = String(activeRequirement?.kind_code ?? (String(activeRequirement?.requirement_id).startsWith("AC-") ? "AC" : "REQ"));
  const activeRequirementLabel = activeRequirementKind === "AC" ? "Acceptance Criteria" : "Requirement";
  const activeRequirementDescription = String(activeRequirement?.kind_description ?? (activeRequirementKind === "AC" ? "A concrete and verifiable condition for deciding completion" : "A functional, quality, or operational capability the system must provide or preserve"));
  // editorFileRoot is a single server-configured path (LOCAL_REPOSITORY_HOST_ROOT),
  // correct only for the one repository that server was started against. A
  // different repository analyzed through the browser folder picker has no
  // server-known host path, so only trust editorFileRoot when its last path
  // segment matches the analyzed repo's folder name; otherwise require a
  // per-repo override the user enters once and we persist in localStorage.
  const activeRepoRootName = String(repoContext?.root_name ?? "");
  const resolvedEditorRoot = rootMatchesEditorFileRoot(editorFileRoot, activeRepoRootName) ? editorFileRoot : knownRepositories[activeRepoRootName] ?? "";
  const editorHref = (item: JsonRecord) => {
    if (!resolvedEditorRoot) return "";
    const root = resolvedEditorRoot.replace(/\/+$/, "");
    const encodedPath = String(item.path).split("/").map((part) => encodeURIComponent(part)).join("/");
    return `vscode://file${root.startsWith("/") ? root : `/${root}`}/${encodedPath}:${String(item.start_line)}:1`;
  };
  const renderEvidencePanel = (eyebrow: string, title: string) => (
    <div className="impact-panel impact-evidence-panel">
      <div className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h3>{title}</h3></div><span className="tag">{activeRequirementId || "SELECT ITEM"}</span></div>
      {activeRequirement ? <div className="selected-requirement-context"><p><span className="requirement-kind-badge">{activeRequirementKind}</span> {activeRequirementLabel}</p><strong>{String(activeRequirement.text ?? activeRequirement.impact ?? "No requirement description")}</strong><small>{activeRequirementDescription}</small></div> : <p className="impact-empty">Select a REQ or AC to view its evidence.</p>}
      <div className="impact-evidence">{activeEvidence.length ? activeEvidence.map((item, index) => { const href = editorHref(item); return <div key={`${String(item.path)}-${String(item.start_line)}-${String(item.end_line)}-${index}`}><div className="impact-evidence-meta"><code>{String(item.path)}:{String(item.start_line)}–{String(item.end_line)}</code>{href && <a className="source-link" href={href} title="Open this file in VS Code">Open in VS Code ↗</a>}</div><p className="impact-rationale">{String(item.rationale)}</p><pre>{String(item.excerpt)}</pre></div>; }) : <p className="impact-empty">There is no justified 2–3 line evidence for this {activeRequirementKind || "REQ"}. Without evidence, the requirement is not considered implemented.</p>}</div>
    </div>
  );
  const renderAssessment = () => {
    const sections = [
      { key: "pros", label: "PROS", title: "What works well", className: "assessment-pros", empty: "No positive signal was returned." },
      { key: "cons", label: "CONS", title: "What needs attention", className: "assessment-cons", empty: "No material drawback was returned." },
      { key: "limitations", label: "LIMITATIONS", title: "What this cannot prove", className: "assessment-limitations", empty: "No limitation was returned." },
    ];
    return <div className="impact-assessment">{sections.map((section) => {
      const items = Array.isArray(assessment[section.key]) ? (assessment[section.key] as unknown[]).map((item: unknown) => String(item).trim()).filter(Boolean) : [];
      return <article className={`assessment-card ${section.className}`} key={section.key}><p className="eyebrow">{section.label}</p><h4>{section.title}</h4><ul>{(items.length ? items : [section.empty]).map((item) => <li key={item}>{item}</li>)}</ul></article>;
    })}</div>;
  };
  const renderProposalChanges = () => {
    const groups = [
      { type: "changed", label: "Changed items", english: "CHANGED", empty: "No evidence-backed changes were identified." },
      { type: "deleted", label: "Deleted items", english: "DELETED", empty: "No deletions are required." },
      { type: "added", label: "Added items", english: "ADDED", empty: "No additions are required." },
    ];
    const renderChangeBody = (group: { type: string }, item: JsonRecord) => group.type === "added"
      ? <div className="change-single change-after"><small>Added content</small><p>{String(item.after ?? "None")}</p></div>
      : <div className="change-flow"><div className="change-side change-before"><small>Before</small><p>{String(item.before ?? "None")}</p></div><span className="change-arrow" aria-hidden="true">→</span><div className="change-side change-after"><small>{group.type === "deleted" ? "Deleted content" : "After"}</small><p>{String(item.after ?? "None")}</p></div></div>;
    return <div className="impact-panel impact-change-summary"><div className="panel-heading"><div><p className="eyebrow">PROPOSAL DELTA</p><h3>Change summary</h3></div><span className="tag">BEFORE → AFTER</span></div><p className="panel-copy">This summary lists evidence-backed changes for the new implementation proposal. The Markdown copy below remains unchanged.</p><div className="change-groups">{groups.map((group) => { const items = proposalChanges.filter((item) => String(item.type ?? "changed") === group.type); return <section className={`change-group change-${group.type}`} key={group.type}><div className="change-group-heading"><strong>{group.english}</strong><span>{group.label}</span><b>{items.length}</b></div>{items.length ? items.map((item, index) => <article className="proposal-change-item" key={`${group.type}-${index}`}><span className="change-number">{index + 1}</span>{renderChangeBody(group, item)}{String(item.reason ?? "").trim() && <small className="change-reason">Reason: {String(item.reason)}</small>}</article>) : <p className="change-empty">{group.empty}</p>}</section>; })}</div></div>;
  };
  const modeTitle = isImplementationMode ? "Proposal → Implementation" : "Proposal → Code impact";
  const modeDescription = isImplementationMode
    ? "Review how much of each proposal requirement is represented in the current code, with evidence."
    : "Review which code boundaries and risks would be affected by the proposal change.";

  return (
    <div className="impact-workbench">
      <div className="impact-heading">
        <div>
          <p className="eyebrow accent">AI ENGINEER / LOW-TOKEN REVIEW</p>
          <h2>{modeTitle}</h2>
          <p className="impact-lede">Read an HTML, PDF, Markdown, or text proposal and a local Git repository to review implementation status or code impact with evidence.</p>
        </div>
        <div className="impact-budget"><span>MODEL BUDGET</span><strong>{budget}</strong><small>{status}</small><small className={`observability-status ${observability.enabled ? "is-enabled" : ""}`}>{observability.enabled ? <>LANGSMITH TRACE · {String(observability.project ?? "project")} · <a href={String(observability.console_url ?? "https://smith.langchain.com")} target="_blank" rel="noreferrer">Open LangSmith ↗</a></> : "LANGSMITH TRACE · disabled"}</small></div>
      </div>
      <div className="impact-mode-switcher" role="tablist" aria-label="Proposal analysis mode">
        <button type="button" role="tab" aria-selected={isImplementationMode} className={`impact-mode-tab ${isImplementationMode ? "is-active" : ""}`} onClick={() => selectAnalysisMode("implementation")}>
          <strong>Proposal → Implementation</strong><span>Implementation status by requirement</span>
        </button>
        <button type="button" role="tab" aria-selected={!isImplementationMode} className={`impact-mode-tab ${!isImplementationMode ? "is-active" : ""}`} onClick={() => selectAnalysisMode("impact")}>
          <strong>Proposal → Code impact</strong><span>Change boundaries and impact evidence</span>
        </button>
      </div>
      {error && <div className="alert">{error}</div>}
      <div className="impact-setup">
        <section className="impact-card">
          <div className="panel-heading"><div><p className="eyebrow">01 / PROPOSAL</p><h3>Prepare a proposal</h3></div><span className="tag">BOUNDED PARSE</span></div>
          <p className="panel-copy">Read an HTML, PDF, Markdown, or text file, an HTTP URL, a repository-external file:// document, or direct text input. Local documents are not uploaded or stored.</p>
          <label className="file-picker"><input ref={proposalInputRef} type="file" accept=".html,.htm,.md,.markdown,.txt,.text,.pdf" onChange={onProposal} />{proposal ? proposal.name : "Choose an HTML, Markdown, text, or PDF file"}</label>
          <div className="proposal-url-row"><input type="url" value={proposalUrl} placeholder="https://.../proposal.md or file:///Users/.../proposal.html" onChange={(event) => { setProposalUrl(event.target.value); setProposalDocument(null); setLoadedProposalUrl(""); setProposal(null); setProposalText(""); }} /><button type="button" className="button button-quiet" onClick={() => void onProposalUrl()} disabled={busy || !proposalUrl.trim()}>{loadedProposalUrl ? "URL loaded" : "Load document URL"}</button></div>
          <small className="panel-hint">file:// paths inside the shared workspace are read by the server; paths outside it use browser file permission after the button click.</small>
          <textarea className="proposal-text-input" value={proposalText} placeholder="Enter proposal text or Markdown directly." onChange={(event) => onProposalText(event.target.value)} />
          {proposalDocument && <small className="impact-selected">URL ready · source not stored</small>}{proposal && <small className="impact-selected">File selected · source not uploaded</small>}{proposalText.trim() && <small className="impact-selected">Direct input · 120KB maximum</small>}
        </section>
        <section className="impact-card">
          <div className="panel-heading"><div><p className="eyebrow">02 / REPOSITORY</p><h3>Choose a Git repository</h3></div><span className="tag">READ ONLY</span></div>
          <p className="panel-copy">The browser reads the repository through the folder picker and analyzes only .py .ts .tsx .js .jsx .mjs .go .rs .java .kt .sql .md .json .yaml .yml .html .css files up to 256KB each. Excluded: .git, worktrees, node_modules, .next, dist, build, coverage, target, .venv/venv, __pycache__, .cache, .turbo; .env files, *.pem/*.key/*.p12/*.pfx/*.crt/*.cer, and any credential/secret path segment; anything the repo's own .gitignore matches; and files beyond a 600-file / 8MB analysis budget.</p>
          <button type="button" className="file-picker file-picker-button" onClick={() => void chooseRepository()} disabled={busy}>{selectedCount ? `${selectedCount} files selected · choose again` : "Choose Git repository directory"}</button>
          <input ref={directoryInputRef} className="repository-fallback-input" type="file" {...({ webkitdirectory: "" } as any)} multiple onChange={onRepository} />
          <div className={`repository-progress repository-progress-${repositoryStatus}`} role="status" aria-live="polite">{["loading", "analyzing"].includes(repositoryStatus) && <span className="loading-spinner" aria-hidden="true" />}<span>{repositoryMessage}</span></div>
          {repoContext && <small className="impact-selected">{String(Object.values(repoContext.excluded ?? {}).reduce((sum: number, value: any) => sum + Number(value), 0))} files excluded · fingerprint {String(repoContext.fingerprint).slice(0, 10)}…</small>}
        </section>
      </div>
      <section className="impact-action">
        <div><p className="eyebrow">03 / {isImplementationMode ? "IMPLEMENTATION" : "CODE IMPACT"}</p><h3>{isImplementationMode ? "Check proposal implementation" : "Review proposal code impact"}</h3><p className="panel-copy">{modeDescription} Document parsing, Git, AST, and search use 0 model tokens; only selected evidence is sent to LangChain/JEV. No code, build, or test commands are executed.</p></div>
        <button className="button button-primary" onClick={() => void startReview()} disabled={busy}>{busy ? "Analyzing…" : isImplementationMode ? "Check implementation" : "Review code impact"}</button>
      </section>
      {review && <section className="impact-results">
        <div className="impact-result-header"><div><p className="eyebrow">04 / RESULT</p><h3>{isImplementationMode ? "Implementation status against proposal" : "Evidence-backed code impact review"}</h3></div><span className={`impact-verdict verdict-${String(report?.recommendation ?? "unknown")}`}>{String(report?.recommendation ?? "unknown").toUpperCase()}</span></div>
        {renderAssessment()}
        {isImplementationMode ? <>
          <div className="impact-metrics">
            <article><span>IMPLEMENTED</span><strong>{implementationCounts.implemented}</strong><small>/ {requirements.length} requirements</small></article>
            <article><span>EVIDENCE-SUPPORTED</span><strong>{implementationProgress}%</strong><small>partial counts as 50%</small></article>
            <article><span>PARTIAL IMPLEMENTATION</span><strong>{implementationCounts.partial}</strong><small>some conditions remain</small></article>
            <article><span>MISSING / UNKNOWN</span><strong>{implementationCounts.missing + implementationCounts.unknown + implementationCounts.contradicted}</strong><small>not proven by code</small></article>
          </div>
          <div className="impact-panel implementation-summary"><div className="panel-heading"><div><p className="eyebrow">IMPLEMENTATION BASIS</p><h3>What this score means</h3></div><span className="tag">EVIDENCE ONLY</span></div><p className="panel-copy">{String(report?.summary ?? "Requirements were classified from bounded evidence found in the current code.")} Tests, builds, and deployments are not executed; a requirement without evidence is not considered implemented.</p></div>
          <div className="impact-result-grid">
            <div className="impact-panel"><div className="panel-heading"><div><p className="eyebrow">REQUIREMENTS / AC</p><h3>Implementation status</h3></div><span className="tag">CLICK FOR EVIDENCE</span></div><div className="requirement-legend"><span><strong>REQ</strong> Functional, quality, or operational requirement</span><span><strong>AC</strong> Verifiable completion condition</span></div><div className="impact-requirements">{requirements.map((item) => { const normalizedStatus = implementationStatus(item.status); const itemId = String(item.requirement_id); const itemKind = String(item.kind_code ?? (itemId.startsWith("AC-") ? "AC" : "REQ")); const itemKindLabel = itemKind === "AC" ? "Acceptance Criteria" : "Requirement"; const itemEvidenceCount = visibleEvidence.filter((evidenceItem) => String(evidenceItem.requirement_id) === itemId).length; return <button type="button" className={`impact-requirement ${activeRequirementId === itemId ? "is-selected" : ""}`} aria-expanded={activeRequirementId === itemId} key={itemId} onClick={() => setSelectedRequirementId(itemId)}><div><p className="requirement-kind"><span className="requirement-kind-badge">{itemKind}</span>{itemKindLabel}</p><strong>{itemId}</strong><p>{String(item.text ?? item.impact ?? "No requirement detail")}</p><small className="requirement-impact">{String(item.kind_description ?? (itemKind === "AC" ? "A concrete and verifiable condition for deciding completion" : "A functional, quality, or operational capability the system must provide or preserve"))} · {itemEvidenceCount} evidence item(s)</small></div><span className={`state-badge state-${normalizedStatus}`}>{statusLabel(normalizedStatus)}</span></button>; })}</div></div>
            {renderEvidencePanel("EVIDENCE / SELECTED ITEM", "Evidence for implementation status")}
          </div>
        </> : <>
          <div className="impact-metrics"><article><span>EVIDENCE</span><strong>{String(report?.evidence_count ?? 0)}</strong><small>/ {String(report?.requirement_count ?? 0)} requirements</small></article><article><span>COVERAGE</span><strong>{String(report?.evidence_coverage ?? 0)}</strong><small>deterministic top-k</small></article><article><span>CALLS</span><strong>{String((report?.provider_calls as JsonRecord | undefined)?.langchain ?? 0)} + {String((report?.provider_calls as JsonRecord | undefined)?.jev ?? 0)}</strong><small>LangChain + JEV</small></article><article><span>EXECUTION</span><strong>NONE</strong><small>read-only analysis</small></article></div>
          {renderProposalChanges()}
          <div className="impact-panel impact-proposal"><div className="panel-heading"><div><p className="eyebrow">PROPOSAL / MARKDOWN</p><h3>New implementation proposal</h3></div><button type="button" className="button button-secondary" onClick={() => void copyProposal(proposalMarkdown)} disabled={!proposalMarkdown}>{copied ? "Copied" : "Copy Markdown"}</button></div><pre className="impact-proposal-source">{proposalMarkdown || "No Markdown proposal was generated."}</pre></div>
          <div className="impact-result-grid"><div className="impact-panel"><div className="panel-heading"><div><p className="eyebrow">REQUIREMENTS / AC</p><h3>Status by requirement</h3></div><span className="tag">CLICK FOR EVIDENCE</span></div><div className="requirement-legend"><span><strong>REQ</strong> Functional, quality, or operational requirement</span><span><strong>AC</strong> Verifiable completion condition</span></div><div className="impact-requirements">{requirements.map((item) => { const normalizedStatus = implementationStatus(item.status); const itemId = String(item.requirement_id); const itemKind = String(item.kind_code ?? (itemId.startsWith("AC-") ? "AC" : "REQ")); const itemKindLabel = itemKind === "AC" ? "Acceptance Criteria" : "Requirement"; const itemEvidenceCount = visibleEvidence.filter((evidenceItem) => String(evidenceItem.requirement_id) === itemId).length; return <button type="button" className={`impact-requirement ${activeRequirementId === itemId ? "is-selected" : ""}`} aria-expanded={activeRequirementId === itemId} key={itemId} onClick={() => setSelectedRequirementId(itemId)}><div><p className="requirement-kind"><span className="requirement-kind-badge">{itemKind}</span>{itemKindLabel}</p><strong>{itemId}</strong><p>{String(item.text ?? item.impact ?? "No impact summary")}</p><small className="requirement-impact">{String(item.kind_description ?? (itemKind === "AC" ? "A concrete and verifiable condition for deciding completion" : "A functional, quality, or operational capability the system must provide or preserve"))} · {itemEvidenceCount} evidence item(s)</small></div><span className={`state-badge state-${normalizedStatus}`}>{statusLabel(normalizedStatus)}</span></button>; })}</div></div>{renderEvidencePanel("EVIDENCE / SELECTED ITEM", "Selected REQ/AC code impact evidence")}</div>
        </>}
      </section>}
    </div>
  );
}
