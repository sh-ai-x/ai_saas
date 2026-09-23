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
};

type PickerWindow = Window & {
  showDirectoryPicker?: () => Promise<DirectoryHandleLike>;
};

type PendingDirectory = {
  name: string;
  handle?: DirectoryHandleLike;
};

type Props = {
  onSelect: (repository: Repository) => void;
  selected: Repository | null;
};

const REPOSITORY_REQUEST_TIMEOUT_MS = 15_000;

function repositoryErrorMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : String(error);
  if (code === "repository_metadata_unavailable") {
    return "선택한 레포지토리의 Git 메타데이터를 읽지 못했습니다. Docker를 해당 레포지토리 폴더 자체에 LOCAL_REPOSITORY_HOST_ROOT로 지정하고 다시 시작하세요.";
  }
  if (code === "repository_discovery_limit") {
    return "마운트된 폴더가 너무 넓어 레포지토리 검색이 중단됐습니다. 선택한 레포지토리 자체 또는 좁은 상위 폴더만 LOCAL_REPOSITORY_HOST_ROOT로 지정하고 다시 시작하세요.";
  }
  if (code === "repository_discovery_timeout" || code === "foundation_unavailable") {
    return "레포지토리 검색이 오래 걸리고 있습니다. Docker가 실행 중인지 확인하고, LOCAL_REPOSITORY_HOST_ROOT를 좁은 폴더로 지정한 뒤 다시 시도하세요.";
  }
  return code;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REPOSITORY_REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`/api/foundation${path}`, {
      ...init,
      credentials: "same-origin",
      headers: {
        "content-type": "application/json",
        ...(init?.headers ?? {}),
      },
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pickerError, setPickerError] = useState("");
  const [pickerBusy, setPickerBusy] = useState(false);
  const [pendingDirectory, setPendingDirectory] = useState<PendingDirectory | null>(null);
  const directoryInputRef = useRef<HTMLInputElement>(null);

  const fetchRepositories = useCallback(async (name?: string): Promise<Repository[]> => {
    const query = name ? `?name=${encodeURIComponent(name)}` : "";
    const result = await api<{ repositories: Repository[] }>(`/v1/repositories${query}`);
    return result.repositories;
  }, []);

  const load = useCallback(async (name?: string): Promise<Repository[]> => {
    setLoading(true);
    try {
      const result = await fetchRepositories(name);
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
    void load();
  }, [load]);

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
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const relativePath = file.webkitRelativePath || file.name;
    setPendingDirectory({ name: relativePath.split("/")[0] });
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

      let available: Repository[];
      try {
        available = await fetchRepositories(pendingDirectory.name);
        setRepositories(available);
        setError("");
      } catch (err) {
        const message = repositoryErrorMessage(err);
        setError(message);
        setPickerError(message);
        return;
      }
      const matches = available.filter((item) => item.repository.name === pendingDirectory.name);
      if (matches.length === 0) {
        setPickerError(
          `“${pendingDirectory.name}”을(를) 선택했지만 서버에 마운트된 Git 레포지토리로 찾지 못했습니다. ` +
            "Docker를 다시 시작하거나 LOCAL_REPOSITORY_HOST_ROOT를 선택한 레포지토리 자체 또는 좁은 상위 폴더로 설정하세요."
        );
        return;
      }
      if (matches.length > 1) {
        setPickerError("같은 이름의 레포지토리가 여러 개입니다. 목록에서 정확한 경로를 선택하세요.");
        return;
      }

      const repository = matches[0];
      if (repository.authorization.read_analysis) {
        onSelect(repository);
      } else {
        await authorize(repository);
      }
      setPendingDirectory(null);
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
        Finder에서 Git 레포지토리 폴더를 선택하면 읽기 권한을 확인한 뒤 분석 대상으로 등록합니다.
      </p>
      {loading && <p className="selector-status">Mounted repositories are still being discovered…</p>}
      {error && <div className="picker-error" role="alert">{error}</div>}
      {pickerError && <div className="picker-error" role="alert">{pickerError}</div>}

      {!repositories.length ? (
        <div className="repository-empty-state">
          <div className="empty-state-icon" aria-hidden="true">⌂</div>
          <h4>No local repositories configured</h4>
          <p>선택할 로컬 레포지토리가 없습니다. 폴더 선택 버튼으로 Git 레포지토리를 지정하세요.</p>
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
                {pickerBusy ? "Checking access…" : "Allow read access"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
