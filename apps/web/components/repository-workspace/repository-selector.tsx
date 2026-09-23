"use client";

import { useState, useEffect, useCallback } from "react";

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

type Props = {
  onSelect: (repository: Repository) => void;
  selected: Repository | null;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/foundation${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  const raw = await response.text();
  const body = raw ? JSON.parse(raw) : {};
  if (!response.ok) {
    throw new Error(String(body.error ?? body.message ?? `Request failed: ${response.status}`));
  }
  return body as T;
}

export function RepositorySelector({ onSelect, selected }: Props) {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api<{ repositories: Repository[] }>("/v1/repositories");
      setRepositories(result.repositories);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load repositories");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const authorize = async (repo: Repository) => {
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authorization failed");
    }
  };

  if (loading) return <div className="repository-selector loading">Loading repositories…</div>;
  if (error) return <div className="repository-selector error">{error}</div>;
  if (!repositories.length) return <div className="repository-selector empty">No local repositories configured.</div>;

  return (
    <div className="repository-selector">
      <div className="selector-header">
        <h3>Local Repositories</h3>
        <button className="text-button" onClick={() => void load()}>
          Refresh
        </button>
      </div>
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
                  <button
                    className="button button-secondary"
                    onClick={() => void authorize(repo)}
                  >
                    Grant read access
                  </button>
                )}
                {isAuthorized && !isSelected && (
                  <button
                    className="button button-primary"
                    onClick={() => onSelect(repo)}
                  >
                    Select repository
                  </button>
                )}
                {isSelected && (
                  <span className="selected-indicator">✓ Selected</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
