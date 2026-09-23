"use client";

import { useState, useEffect, useCallback } from "react";

type Evidence = {
  evidence_id: string;
  requirement_id: string;
  path: string;
  start_line: number;
  end_line: number;
  content_hash: string;
  symbol: string | null;
  authorized: boolean;
  valid: boolean;
  stale: boolean;
  stale_reason: string | null;
  checked_commit: string;
};

type Approval = {
  token_id: string;
  run_id: string;
  proposal_id: string;
  tenant_id: string;
  repository_id: string;
  branch: string;
  commit: string;
  plan_digest: string;
  scopes: string[];
  consumed: boolean;
  status: string;
  created_at: string;
  updated_at: string;
};

type Artifact = {
  artifact_id: string;
  kind: string;
  path: string | null;
  digest: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

type Trace = {
  trace_id: string | null;
  provider: string;
  project: string | null;
  console_url: string | null;
  export_status: string;
  observational: boolean;
  updated_at: string;
};

type Report = {
  run_id: string;
  status: string;
  terminal_state_consistent: boolean;
  verification_status: string;
  changed_files: string[];
  test_results: unknown[];
  artifact_ids: string[];
  trace_id: string | null;
  reason: string | null;
  verification_blocked?: boolean;
};

type ProposalDetail = {
  proposal_id: string;
  tenant_id: string;
  repository_id: string;
  branch: string;
  commit: string;
  repository_dirty: boolean;
  state: string;
  stale_evidence: boolean;
  stale_reason: string | null;
  created_at: string;
  updated_at: string;
  run: {
    run_id: string;
    state: string;
    mode: string;
    error: string | null;
    trace_id: string | null;
    ledger_state?: string;
    verification_blocked?: boolean;
  } | null;
  requirements: Array<{ requirement_id: string; text: string }>;
  evidence: Evidence[];
  plan: {
    plan_id: string;
    steps: Array<{ step_id: string; action: string; target: string; rationale: string }>;
  } | null;
  approval: Approval | null;
  report: Report | null;
  artifacts: Artifact[];
  trace: Trace | null;
};

type Props = {
  repositoryId: string;
  proposalId: string;
  onBack: () => void;
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

export function ProposalDetail({ repositoryId, proposalId, onBack }: Props) {
  const [detail, setDetail] = useState<ProposalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showRawJson, setShowRawJson] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api<{ proposal: ProposalDetail }>(
        `/v1/repositories/${repositoryId}/proposals/${proposalId}`
      );
      setDetail(result.proposal);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load proposal");
    } finally {
      setLoading(false);
    }
  }, [repositoryId, proposalId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <div className="proposal-detail loading">Loading proposal details…</div>;
  if (error) return <div className="proposal-detail error">{error}</div>;
  if (!detail) return <div className="proposal-detail error">Proposal not found</div>;

  const evidenceStale = detail.evidence.filter((e) => e.stale).length;
  const evidenceValid = detail.evidence.filter((e) => e.valid && e.authorized && !e.stale).length;
  const verificationBlocked = detail.run?.verification_blocked || detail.stale_evidence;

  return (
    <div className="proposal-detail">
      <div className="detail-header">
        <button className="text-button" onClick={onBack}>
          ← Back to proposals
        </button>
        <div className="header-actions">
          <button
            className="text-button"
            onClick={() => setShowRawJson(!showRawJson)}
          >
            {showRawJson ? "Hide" : "Show"} raw JSON
          </button>
        </div>
      </div>

      <div className="detail-hero">
        <div>
          <p className="eyebrow">PROPOSAL DETAIL</p>
          <h2 className="mono">{proposalId}</h2>
        </div>
        <div className="hero-meta">
          <div className="meta-row">
            <span className="meta-label">STATE</span>
            <span className={`state-badge ${detail.stale_evidence ? "state-stale" : detail.state === "verified" ? "state-success" : detail.state === "failed" ? "state-error" : "state-info"}`}>
              {detail.stale_evidence ? "STALE" : detail.state.toUpperCase()}
            </span>
          </div>
          <div className="meta-row">
            <span className="meta-label">COMMIT</span>
            <span className="mono">{detail.commit.slice(0, 8)}</span>
            {detail.repository_dirty && <span className="dirty-badge">*</span>}
          </div>
          <div className="meta-row">
            <span className="meta-label">BRANCH</span>
            <span>{detail.branch}</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">CREATED</span>
            <span>{formatDate(detail.created_at)}</span>
          </div>
        </div>
      </div>

      {detail.stale_evidence && detail.stale_reason && (
        <div className="alert alert-warning">
          <strong>⚠ Stale Evidence</strong>
          <p>{detail.stale_reason}</p>
        </div>
      )}

      {verificationBlocked && (
        <div className="alert alert-error">
          <strong>Verification Blocked</strong>
          <p>Evidence is stale or invalid. Re-analysis is required before verification can proceed.</p>
        </div>
      )}

      <div className="detail-sections">
        {detail.run && (
          <section className="detail-section">
            <div className="section-header">
              <div>
                <p className="eyebrow">RUN STATUS</p>
                <h3>Execution state</h3>
              </div>
              {detail.run.trace_id && detail.trace && detail.trace.console_url && (
                <a
                  className="text-button"
                  href={detail.trace.console_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  View LangSmith trace →
                </a>
              )}
            </div>
            <div className="status-timeline">
              <div className="timeline-item">
                <span className="timeline-label">Run ID</span>
                <span className="timeline-value mono">{detail.run.run_id}</span>
              </div>
              <div className="timeline-item">
                <span className="timeline-label">Mode</span>
                <span className="timeline-value">{detail.run.mode}</span>
              </div>
              <div className="timeline-item">
                <span className="timeline-label">State</span>
                <span className="timeline-value">{detail.run.ledger_state || detail.run.state}</span>
              </div>
              {detail.run.error && (
                <div className="timeline-item error">
                  <span className="timeline-label">Error</span>
                  <span className="timeline-value">{detail.run.error}</span>
                </div>
              )}
            </div>
          </section>
        )}

        {detail.requirements.length > 0 && (
          <section className="detail-section">
            <div className="section-header">
              <div>
                <p className="eyebrow">REQUIREMENTS</p>
                <h3>Extracted requirements</h3>
              </div>
              <span className="count-badge">{detail.requirements.length}</span>
            </div>
            <div className="requirements-list">
              {detail.requirements.map((req) => (
                <div key={req.requirement_id} className="requirement-item">
                  <span className="req-id mono">{req.requirement_id}</span>
                  <p>{req.text}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {detail.evidence.length > 0 && (
          <section className="detail-section">
            <div className="section-header">
              <div>
                <p className="eyebrow">EVIDENCE</p>
                <h3>Evidence snapshots</h3>
              </div>
              <div className="evidence-summary">
                <span className="count-badge success">{evidenceValid} valid</span>
                {evidenceStale > 0 && (
                  <span className="count-badge warning">{evidenceStale} stale</span>
                )}
              </div>
            </div>
            <div className="evidence-list">
              {detail.evidence.map((ev) => (
                <div
                  key={ev.evidence_id}
                  className={`evidence-item ${ev.stale ? "is-stale" : ev.valid && ev.authorized ? "is-valid" : "is-invalid"}`}
                >
                  <div className="evidence-header">
                    <span className="path">{ev.path}</span>
                    <span className="lines mono">
                      L{ev.start_line}–L{ev.end_line}
                    </span>
                    {ev.symbol && <span className="symbol mono">{ev.symbol}</span>}
                  </div>
                  <div className="evidence-meta">
                    <span className="hash mono" title={ev.content_hash}>
                      {ev.content_hash.slice(0, 12)}
                    </span>
                    <span className={`status ${ev.stale ? "stale" : ev.valid && ev.authorized ? "valid" : "invalid"}`}>
                      {ev.stale
                        ? `STALE: ${ev.stale_reason}`
                        : ev.valid && ev.authorized
                        ? "VALID"
                        : !ev.authorized
                        ? "UNAUTHORIZED"
                        : "INVALID HASH"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {detail.plan && detail.plan.steps && (
          <section className="detail-section">
            <div className="section-header">
              <div>
                <p className="eyebrow">IMPLEMENTATION PLAN</p>
                <h3>Planned steps</h3>
              </div>
              <span className="count-badge">{detail.plan.steps.length}</span>
            </div>
            <div className="plan-steps">
              {detail.plan.steps.map((step, index) => (
                <div key={step.step_id} className="plan-step">
                  <div className="step-number">{index + 1}</div>
                  <div className="step-content">
                    <div className="step-header">
                      <strong>{step.action}</strong>
                      <span className="target mono">{step.target}</span>
                    </div>
                    <p className="rationale">{step.rationale}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {detail.approval && (
          <section className="detail-section">
            <div className="section-header">
              <div>
                <p className="eyebrow">APPROVAL</p>
                <h3>Authorization record</h3>
              </div>
              <span className={`status-badge ${detail.approval.consumed ? "consumed" : "issued"}`}>
                {detail.approval.status.toUpperCase()}
              </span>
            </div>
            <div className="approval-detail">
              <div className="approval-row">
                <span className="label">Token ID</span>
                <span className="value mono">{detail.approval.token_id}</span>
              </div>
              <div className="approval-row">
                <span className="label">Scopes</span>
                <span className="value">{detail.approval.scopes.join(", ")}</span>
              </div>
              <div className="approval-row">
                <span className="label">Plan digest</span>
                <span className="value mono">{detail.approval.plan_digest.slice(0, 16)}</span>
              </div>
              <div className="approval-row">
                <span className="label">Issued</span>
                <span className="value">{formatDate(detail.approval.created_at)}</span>
              </div>
            </div>
          </section>
        )}

        {detail.report && (
          <section className="detail-section">
            <div className="section-header">
              <div>
                <p className="eyebrow">VERIFICATION REPORT</p>
                <h3>Verification outcome</h3>
              </div>
              <span className={`status-badge ${detail.report.status === "verified" ? "success" : detail.report.status === "stale" ? "stale" : "error"}`}>
                {detail.report.status.toUpperCase()}
              </span>
            </div>
            <div className="report-content">
              <div className="report-row">
                <span className="label">Verification status</span>
                <span className="value">{detail.report.verification_status}</span>
              </div>
              <div className="report-row">
                <span className="label">Terminal state consistent</span>
                <span className="value">{detail.report.terminal_state_consistent ? "Yes" : "No"}</span>
              </div>
              {detail.report.changed_files.length > 0 && (
                <div className="report-row">
                  <span className="label">Changed files</span>
                  <div className="changed-files">
                    {detail.report.changed_files.map((file, i) => (
                      <div key={i} className="file-path mono">{file}</div>
                    ))}
                  </div>
                </div>
              )}
              {detail.report.reason && (
                <div className="report-row">
                  <span className="label">Reason</span>
                  <span className="value">{detail.report.reason}</span>
                </div>
              )}
            </div>
          </section>
        )}

        {detail.artifacts.length > 0 && (
          <section className="detail-section">
            <div className="section-header">
              <div>
                <p className="eyebrow">ARTIFACTS</p>
                <h3>Generated artifacts</h3>
              </div>
              <span className="count-badge">{detail.artifacts.length}</span>
            </div>
            <div className="artifacts-list">
              {detail.artifacts.map((artifact) => (
                <div key={artifact.artifact_id} className="artifact-item">
                  <div className="artifact-header">
                    <span className="kind">{artifact.kind}</span>
                    {artifact.path && <span className="path mono">{artifact.path}</span>}
                  </div>
                  <div className="artifact-meta">
                    <span className="digest mono" title={artifact.digest}>
                      {artifact.digest.slice(0, 16)}
                    </span>
                    <span className="created">{formatDate(artifact.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {showRawJson && (
        <section className="detail-section raw-json">
          <div className="section-header">
            <h3>Raw JSON</h3>
          </div>
          <pre className="json-display">{JSON.stringify(detail, null, 2)}</pre>
        </section>
      )}
    </div>
  );
}
