"use client";

import { useState, useEffect, useCallback } from "react";

type ProposalSummary = {
  proposal_id: string;
  repository_id: string;
  branch: string;
  commit: string;
  repository_dirty: boolean;
  state: string;
  stale_evidence: boolean;
  stale_reason: string | null;
  created_at: string;
  updated_at: string;
};

type Props = {
  repositoryId: string;
  onSelect: (proposalId: string) => void;
  onCreateNew: () => void;
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

function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleString();
  } catch {
    return isoString;
  }
}

function stateLabel(state: string, stale: boolean): string {
  if (stale) return "STALE";
  switch (state) {
    case "created":
      return "CREATED";
    case "queued":
      return "QUEUED";
    case "running":
      return "ANALYZING";
    case "waiting_approval":
      return "AWAITING APPROVAL";
    case "plan_only":
      return "PLAN READY";
    case "verified":
      return "VERIFIED";
    case "failed":
      return "FAILED";
    case "rejected":
      return "REJECTED";
    default:
      return state.toUpperCase();
  }
}

function stateClass(state: string, stale: boolean): string {
  if (stale) return "state-stale";
  switch (state) {
    case "verified":
      return "state-success";
    case "failed":
    case "rejected":
      return "state-error";
    case "waiting_approval":
      return "state-warning";
    case "plan_only":
      return "state-info";
    default:
      return "state-neutral";
  }
}

export function ProposalList({ repositoryId, onSelect, onCreateNew }: Props) {
  const [proposals, setProposals] = useState<ProposalSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api<{ proposals: ProposalSummary[] }>(
        `/v1/repositories/${repositoryId}/proposals`
      );
      setProposals(result.proposals);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load proposals");
    } finally {
      setLoading(false);
    }
  }, [repositoryId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <div className="proposal-list loading">Loading proposals…</div>;
  if (error) return <div className="proposal-list error">{error}</div>;

  return (
    <div className="proposal-list">
      <div className="list-header">
        <div>
          <p className="eyebrow">PROPOSAL HISTORY</p>
          <h3>Repository proposals</h3>
        </div>
        <button className="button button-primary" onClick={onCreateNew}>
          + New proposal
        </button>
      </div>
      {!proposals.length ? (
        <div className="empty-state">
          <p>No proposals yet for this repository.</p>
          <button className="button button-secondary" onClick={onCreateNew}>
            Create your first proposal
          </button>
        </div>
      ) : (
        <div className="proposal-table">
          <div className="table-header">
            <div className="col-id">Proposal</div>
            <div className="col-commit">Commit</div>
            <div className="col-state">State</div>
            <div className="col-updated">Updated</div>
            <div className="col-actions"></div>
          </div>
          {proposals.map((proposal) => (
            <div key={proposal.proposal_id} className="table-row">
              <div className="col-id mono">{proposal.proposal_id.slice(9, 21)}</div>
              <div className="col-commit">
                <span className="mono">{proposal.commit.slice(0, 8)}</span>
                {proposal.repository_dirty && <span className="dirty-badge">*</span>}
              </div>
              <div className="col-state">
                <span className={`state-badge ${stateClass(proposal.state, proposal.stale_evidence)}`}>
                  {stateLabel(proposal.state, proposal.stale_evidence)}
                </span>
                {proposal.stale_reason && (
                  <span className="stale-hint" title={proposal.stale_reason}>
                    ⚠
                  </span>
                )}
              </div>
              <div className="col-updated">{formatDate(proposal.updated_at)}</div>
              <div className="col-actions">
                <button
                  className="text-button"
                  onClick={() => onSelect(proposal.proposal_id)}
                >
                  View details →
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
