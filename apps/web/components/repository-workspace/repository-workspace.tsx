"use client";

import { useState } from "react";
import { RepositorySelector } from "./repository-selector";
import { ProposalList } from "./proposal-list";
import { ProposalDetail } from "./proposal-detail";
import { ProposalCreate } from "./proposal-create";

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

type View =
  | { type: "select-repository" }
  | { type: "proposal-list"; repository: Repository }
  | { type: "proposal-detail"; repository: Repository; proposalId: string }
  | { type: "create-proposal"; repository: Repository };

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

export function RepositoryWorkspace() {
  const [view, setView] = useState<View>({ type: "select-repository" });
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null);

  const handleSelectRepository = (repository: Repository) => {
    setSelectedRepository(repository);
    setView({ type: "proposal-list", repository });
  };

  const handleSelectProposal = (proposalId: string) => {
    if (selectedRepository) {
      setView({ type: "proposal-detail", repository: selectedRepository, proposalId });
    }
  };

  const handleCreateNew = () => {
    if (selectedRepository) {
      setView({ type: "create-proposal", repository: selectedRepository });
    }
  };

  const handleBackToList = () => {
    if (selectedRepository) {
      setView({ type: "proposal-list", repository: selectedRepository });
    }
  };

  const handleBackToRepositories = () => {
    setSelectedRepository(null);
    setView({ type: "select-repository" });
  };

  const handleSubmitProposal = async (proposal: string, mode: string) => {
    if (!selectedRepository) return;

    const idempotencyKey = `web-proposal-${Date.now()}`;

    await api(`/v1/repositories/${selectedRepository.repository.repository_id}/proposals`, {
      method: "POST",
      body: JSON.stringify({
        proposal,
        mode,
        idempotency_key: idempotencyKey,
        repository_id: selectedRepository.repository.repository_id,
      }),
    });

    handleBackToList();
  };

  return (
    <div className="repository-workspace">
      {view.type === "select-repository" && (
        <RepositorySelector
          onSelect={handleSelectRepository}
          selected={selectedRepository}
        />
      )}

      {view.type === "proposal-list" && (
        <div className="workspace-with-context">
          <div className="context-bar">
            <div className="repository-context">
              <p className="eyebrow">SELECTED REPOSITORY</p>
              <h4>{view.repository.repository.name}</h4>
              <p className="path mono">{view.repository.repository.canonical_path}</p>
            </div>
            <button className="text-button" onClick={handleBackToRepositories}>
              Change repository
            </button>
          </div>
          <ProposalList
            repositoryId={view.repository.repository.repository_id}
            onSelect={handleSelectProposal}
            onCreateNew={handleCreateNew}
          />
        </div>
      )}

      {view.type === "proposal-detail" && (
        <div className="workspace-with-context">
          <div className="context-bar">
            <div className="repository-context">
              <p className="eyebrow">REPOSITORY</p>
              <h4>{view.repository.repository.name}</h4>
            </div>
            <button className="text-button" onClick={handleBackToRepositories}>
              Change repository
            </button>
          </div>
          <ProposalDetail
            repositoryId={view.repository.repository.repository_id}
            proposalId={view.proposalId}
            onBack={handleBackToList}
          />
        </div>
      )}

      {view.type === "create-proposal" && (
        <div className="workspace-with-context">
          <div className="context-bar">
            <div className="repository-context">
              <p className="eyebrow">REPOSITORY</p>
              <h4>{view.repository.repository.name}</h4>
            </div>
            <button className="text-button" onClick={handleBackToRepositories}>
              Change repository
            </button>
          </div>
          <ProposalCreate
            repositoryId={view.repository.repository.repository_id}
            repositoryName={view.repository.repository.name}
            onSubmit={handleSubmitProposal}
            onCancel={handleBackToList}
          />
        </div>
      )}
    </div>
  );
}
