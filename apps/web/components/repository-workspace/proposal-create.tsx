"use client";

import { FormEvent, useState } from "react";

type Props = {
  repositoryId: string;
  repositoryName: string;
  onSubmit: (proposal: string, mode: string) => Promise<void>;
  onCancel: () => void;
};

export function ProposalCreate({ repositoryId, repositoryName, onSubmit, onCancel }: Props) {
  const [proposal, setProposal] = useState("");
  const [mode, setMode] = useState<"plan_only" | "verify">("plan_only");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!proposal.trim()) {
      setError("Proposal cannot be empty");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(proposal, mode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create proposal");
      setSubmitting(false);
    }
  };

  return (
    <div className="proposal-create">
      <div className="create-header">
        <button className="text-button" onClick={onCancel} disabled={submitting}>
          ← Cancel
        </button>
      </div>

      <div className="create-hero">
        <p className="eyebrow">NEW PROPOSAL</p>
        <h2>Create proposal for {repositoryName}</h2>
        <p className="hero-copy">
          Describe the change you want to analyze. The system will extract requirements,
          gather evidence, generate a plan, and optionally verify the implementation.
        </p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <form onSubmit={handleSubmit} className="create-form">
        <div className="form-group">
          <label htmlFor="proposal">
            Proposal description
            <span className="required">*</span>
          </label>
          <textarea
            id="proposal"
            value={proposal}
            onChange={(e) => setProposal(e.target.value)}
            rows={8}
            placeholder="Describe the change you want to make to this repository. Example: Add input validation to the user registration form to prevent SQL injection attacks."
            disabled={submitting}
            required
          />
          <small className="form-hint">
            Be specific about what you want to change and why. The analysis will use this
            to identify requirements and evidence.
          </small>
        </div>

        <div className="form-group">
          <label>Execution mode</label>
          <div className="radio-group">
            <label className="radio-option">
              <input
                type="radio"
                name="mode"
                value="plan_only"
                checked={mode === "plan_only"}
                onChange={(e) => setMode(e.target.value as "plan_only")}
                disabled={submitting}
              />
              <div>
                <strong>Plan only</strong>
                <small>Analyze requirements and create an implementation plan</small>
              </div>
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="mode"
                value="verify"
                checked={mode === "verify"}
                onChange={(e) => setMode(e.target.value as "verify")}
                disabled={submitting}
              />
              <div>
                <strong>Plan and verify</strong>
                <small>Create plan, implement changes in isolation, and verify</small>
              </div>
            </label>
          </div>
        </div>

        <div className="form-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={onCancel}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="button button-primary"
            disabled={submitting || !proposal.trim()}
          >
            {submitting ? "Creating proposal…" : "Create proposal"}
          </button>
        </div>
      </form>
    </div>
  );
}
