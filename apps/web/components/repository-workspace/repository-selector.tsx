"use client";

import { useState, useEffect, useCallback, useRef } from "react";

type Repository = {
  repository: {
    repository_id: string;
    canonical_path: string;
    name: string;
    branch: string;
    head_commit: string;
    dirty: boolean;
    capabilities: string[];
  };
  authorization: {
    read_analysis: boolean;
    write_patch: boolean;
  };
};

type DirectoryHandleLike = {
  name: string;
  requestPermission?: (options: { mode: "read" }) => Promise<"granted" | "denied" | "prompt">;
  values?: () => AsyncIterable<DirectoryEntryLike>;
};

type DirectoryEntryLike =
  | { kind: "file"; name: string; getFile: () => Promise<File> }
  | { kind: "directory"; name: string; values: () => AsyncIterable<DirectoryEntryLike> };

type ImportedFile = { path: string; file: File };

type PickerWindow = Window & {
  showDirectoryPicker?: () => Promise<DirectoryHandleLike>;
};

type PendingDirectory = {
  name: string;
  handle?: DirectoryHandleLike;
  files?: ImportedFile[];
};

type Props = {
  onSelect: (repository: Repository) => void;
  selected: Repository | null;
};

const REPOSITORY_REQUEST_TIMEOUT_MS = 15_000;

function repositoryErrorMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : String(error);
  if (code === "repository_metadata_unavailable") {
    return "선택한 레포지토리의 Git 메타데이터를 읽지 못했습니다. 폴더 읽기 권한을 다시 허용하고 재가져오기를 시도하세요.";
  }
  if (code === "repository_discovery_limit") {
    return "기존 서버 마운트의 레포지토리 검색 범위가 너무 넓습니다. 폴더 선택 후 가져오기를 사용하면 이 목록 검색을 기다리지 않아도 됩니다.";
  }
  if (code === "repository_discovery_timeout" || code === "foundation_unavailable") {
    return "기존 레포지토리 목록 검색이 오래 걸리고 있습니다. Docker가 실행 중인지 확인하고 폴더 선택으로 계속 진행하세요.";
  }
  if (code === "repository_import_size_limit") {
    return "선택한 폴더가 너무 큽니다. node_modules, 빌드 산출물, 대용량 파일을 제외한 뒤 다시 선택하세요. (최대 25MB)";
  }
  if (code.startsWith("repository_import_")) {
    return "선택한 폴더를 서버 작업 공간으로 가져오지 못했습니다. Git 레포지토리인지 확인하고 다시 시도하세요.";
  }
  return code;
}

const IGNORED_DIRECTORY_NAMES = new Set([".git", "node_modules", ".next", "dist", "build", "coverage", "__pycache__"]);

function shouldImportFile(path: string): boolean {
  const parts = path.split("/");
  return !parts.some((part) => IGNORED_DIRECTORY_NAMES.has(part) || part.startsWith(".env"));
}

async function collectDirectoryFiles(handle: DirectoryHandleLike, prefix = ""): Promise<ImportedFile[]> {
  if (!handle.values) return [];
  const files: ImportedFile[] = [];
  for await (const entry of handle.values()) {
    const path = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (!shouldImportFile(path)) continue;
    if (entry.kind === "file") {
      files.push({ path, file: await entry.getFile() });
    } else {
      files.push(...(await collectDirectoryFiles(entry, path)));
    }
  }
  return files;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REPOSITORY_REQUEST_TIMEOUT_MS);
  try {
    const headers = new Headers(init?.headers);
    if (!(init?.body instanceof FormData) && !headers.has("content-type")) {
      headers.set("content-type", "application/json");
    }
    const response = await fetch(`/api/foundation${path}`, {
      ...init,
      credentials: "same-origin",
      headers,
      cache: "no-store",
      signal: controller.signal,
    });
    const raw = await response.text();
    let body: { error?: string; message?: string } = {};
    try {
      body = raw ? JSON.parse(raw) : {};
    } catch {
      body = { message: raw || "The repository service returned an invalid response." };
    }
    if (!response.ok) {
      throw new Error(String(body.error ?? body.message ?? `Request failed: ${response.status}`));
    }
    return body as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("repository_discovery_timeout");
    }
    throw err;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function RepositorySelector({ onSelect, selected }: Props) {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pickerError, setPickerError] = useState("");
  const [pickerBusy, setPickerBusy] = useState(false);
  const [pendingDirectory, setPendingDirectory] = useState<PendingDirectory | null>(null);
  const directoryInputRef = useRef<HTMLInputElement>(null);

  const fetchRepositories = useCallback(async (): Promise<Repository[]> => {
    const result = await api<{ repositories: Repository[] }>("/v1/repositories");
    return result.repositories;
  }, []);

  const load = useCallback(async (): Promise<Repository[]> => {
    setLoading(true);
    try {
      const result = await fetchRepositories();
      setRepositories(result);
      setError("");
      return result;
    } catch (err) {
      setError(repositoryErrorMessage(err));
      return [];
    } finally {
      setLoading(false);
    }
  }, [fetchRepositories]);

  useEffect(() => {
    directoryInputRef.current?.setAttribute("webkitdirectory", "");
    directoryInputRef.current?.setAttribute("directory", "");
  }, []);

  const authorize = async (repo: Repository): Promise<boolean> => {
    try {
      const result = await api<{ scope: { scope_id: string }; authorization: Repository["authorization"] }>(
        "/v1/repositories/authorize",
        {
          method: "POST",
          body: JSON.stringify({
            repository_id: repo.repository.repository_id,
            permission: "read_analysis",
          }),
        }
      );
      const updated = {
        ...repo,
        authorization: result.authorization,
      };
      setRepositories((current) =>
        current.map((item) =>
          item.repository.repository_id === repo.repository.repository_id ? updated : item
        )
      );
      onSelect(updated);
      return true;
    } catch (err) {
      setPickerError(repositoryErrorMessage(err));
      return false;
    }
  };

  const openDirectoryPicker = async () => {
    setPickerError("");
    setPickerBusy(true);
    try {
      const picker = (window as PickerWindow).showDirectoryPicker;
      if (picker) {
        const handle = await picker();
        setPendingDirectory({ name: handle.name, handle });
      } else {
        directoryInputRef.current?.click();
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setPickerError(err instanceof Error ? err.message : "Could not open the directory picker");
      }
    } finally {
      setPickerBusy(false);
    }
  };

  const handleFallbackDirectory = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.target.files ?? []);
    const firstPath = selectedFiles[0]?.webkitRelativePath || "";
    const name = firstPath.split("/")[0];
    const files = selectedFiles.flatMap<ImportedFile>((file) => {
      const relativePath = file.webkitRelativePath || file.name;
      const parts = relativePath.split("/");
      const path = parts.length > 1 ? parts.slice(1).join("/") : parts[0];
      return shouldImportFile(path) ? [{ path, file }] : [];
    });
    event.target.value = "";
    if (name && files.length) setPendingDirectory({ name, files });
  };

  const importDirectory = async (directory: PendingDirectory): Promise<Repository> => {
    const files = directory.files ?? (directory.handle ? await collectDirectoryFiles(directory.handle) : []);
    if (!files.length) throw new Error("repository_import_empty");
    const formData = new FormData();
    formData.append("repository_name", directory.name);
    formData.append("manifest", JSON.stringify(files.map(({ path }) => ({ path }))));
    files.forEach(({ path, file }) => formData.append("files", file, path));
    const result = await api<{ repository: Repository["repository"]; authorization: Repository["authorization"] }>(
      "/v1/repositories/import",
      { method: "POST", body: formData },
    );
    return { repository: result.repository, authorization: result.authorization };
  };

  const confirmDirectory = async () => {
    if (!pendingDirectory) return;
    setPickerBusy(true);
    setPickerError("");
    try {
      if (pendingDirectory.handle?.requestPermission) {
        const permission = await pendingDirectory.handle.requestPermission({ mode: "read" });
        if (permission !== "granted") {
          setPickerError("읽기 권한이 허용되지 않아 레포지토리를 선택할 수 없습니다.");
          return;
        }
      }

      try {
        const repository = await importDirectory(pendingDirectory);
        setRepositories([repository]);
        setError("");
        const authorized = repository.authorization.read_analysis || await authorize(repository);
        if (authorized) setPendingDirectory(null);
      } catch (err) {
        const message = repositoryErrorMessage(err);
        setError(message);
        setPickerError(message);
        return;
      }
    } finally {
      setPickerBusy(false);
    }
  };

  return (
    <div className="repository-selector">
      <input
        ref={directoryInputRef}
        className="directory-input-hidden"
        type="file"
        multiple
        onChange={handleFallbackDirectory}
        aria-hidden="true"
      />
      <div className="selector-header">
        <div>
          <p className="eyebrow">LOCAL SOURCE</p>
          <h3>Choose a repository directory</h3>
        </div>
        <div className="selector-actions">
          <button className="button button-primary" onClick={() => void openDirectoryPicker()} disabled={pickerBusy}>
            {pickerBusy ? "Opening…" : "Choose folder"}
          </button>
          <button className="text-button" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>
      <p className="selector-help">
        Finder에서 Git 레포지토리 폴더를 선택하면 읽기 권한을 확인한 뒤 서버 작업 공간에 안전한 사본으로 가져옵니다. 원본 폴더는 수정하지 않습니다.
      </p>
      {loading && <p className="selector-status">기존 서버 레포 목록을 불러오는 중입니다. 폴더 선택은 바로 진행할 수 있습니다.</p>}
      {error && <div className="picker-error" role="alert">{error}</div>}
      {pickerError && <div className="picker-error" role="alert">{pickerError}</div>}

      {!repositories.length ? (
        <div className="repository-empty-state">
          <div className="empty-state-icon" aria-hidden="true">⌂</div>
          <h4>No repository imported yet</h4>
          <p>폴더를 선택하고 읽기 권한을 허용하면 서버 작업 공간에 안전한 사본으로 가져옵니다.</p>
          <button className="button button-secondary" onClick={() => void openDirectoryPicker()} disabled={pickerBusy}>
            Select local repository
          </button>
        </div>
      ) : (
        <div className="repository-list">
          {repositories.map((repo) => {
            const isSelected = selected?.repository.repository_id === repo.repository.repository_id;
            const isAuthorized = repo.authorization.read_analysis;
            const isDirty = repo.repository.dirty;
            return (
              <div
                key={repo.repository.repository_id}
                className={`repository-card ${isSelected ? "is-selected" : ""}`}
              >
                <div className="repository-header">
                  <div>
                    <h4>{repo.repository.name}</h4>
                    <p className="path">{repo.repository.canonical_path}</p>
                  </div>
                  <div className="repository-badges">
                    {isDirty && <span className="badge badge-warning">DIRTY</span>}
                    {isAuthorized ? (
                      <span className="badge badge-success">AUTHORIZED</span>
                    ) : (
                      <span className="badge badge-neutral">READ REQUIRED</span>
                    )}
                  </div>
                </div>
                <div className="repository-meta">
                  <div className="meta-row">
                    <span className="meta-label">BRANCH</span>
                    <span className="meta-value">{repo.repository.branch}</span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-label">COMMIT</span>
                    <span className="meta-value mono">{repo.repository.head_commit.slice(0, 8)}</span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-label">CAPABILITIES</span>
                    <span className="meta-value">{repo.repository.capabilities.join(", ")}</span>
                  </div>
                </div>
                <div className="repository-actions">
                  {!isAuthorized && (
                    <button className="button button-secondary" onClick={() => void authorize(repo)}>
                      Grant read access
                    </button>
                  )}
                  {isAuthorized && !isSelected && (
                    <button className="button button-primary" onClick={() => onSelect(repo)}>
                      Select repository
                    </button>
                  )}
                  {isSelected && <span className="selected-indicator">✓ Selected</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {pendingDirectory && (
        <div className="directory-permission-backdrop" role="presentation">
          <section className="directory-permission-dialog" role="dialog" aria-modal="true" aria-labelledby="directory-permission-title">
            <p className="eyebrow">READ ACCESS</p>
            <h4 id="directory-permission-title">Allow repository analysis?</h4>
            <p>
              <strong>{pendingDirectory.name}</strong> 폴더를 분석 대상으로 선택했습니다. Git 메타데이터와 제안서 근거를 읽을 수 있도록 권한을 허용하시겠습니까?
            </p>
            <div className="directory-permission-actions">
              <button className="text-button" onClick={() => setPendingDirectory(null)} disabled={pickerBusy}>Cancel</button>
              <button className="button button-primary" onClick={() => void confirmDirectory()} disabled={pickerBusy}>
                {pickerBusy ? "Importing repository…" : "Allow read access"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
