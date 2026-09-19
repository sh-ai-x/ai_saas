"use client";

import { FormEvent, useState } from "react";

type JsonRecord = Record<string, unknown>;

async function adminFoundationApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/foundation${path}`, {
    ...init,
    credentials: "same-origin",
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  const raw = await response.text();
  const body = raw ? (JSON.parse(raw) as JsonRecord) : {};
  if (!response.ok) throw new Error(String(body.message ?? body.error ?? `Request failed: ${response.status}`));
  return body as T;
}

export function AdminOperationsConsole() {
  const [plan, setPlan] = useState("pro");
  const [creditAmount, setCreditAmount] = useState("5");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const planResult = await adminFoundationApi<JsonRecord>("/v1/admin/plan", {
        method: "POST",
        body: JSON.stringify({ target_user_id: "demo-member", plan, reason: "admin console policy update" }),
      });
      const creditResult = await adminFoundationApi<JsonRecord>("/v1/admin/credits", {
        method: "POST",
        body: JSON.stringify({ target_user_id: "demo-user", amount: Number(creditAmount), reason: "admin console credit adjustment" }),
      });
      const afterPlan = planResult.after as JsonRecord | undefined;
      const afterCredits = creditResult.after as JsonRecord | undefined;
      setMessage(`Updated member plan to ${String(afterPlan?.plan ?? plan)} and credits to ${String(afterCredits?.credit_balance ?? "—")}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Admin operation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-panel admin-operations-panel">
      <div className="panel-heading">
        <div><p className="eyebrow">ADMIN / MEMBER OPERATIONS</p><h2>Manage organization usage</h2></div>
        <span className="tag">ADMIN ONLY</span>
      </div>
      <p className="panel-copy">These controls are intentionally unavailable in `/app`. The server checks the authenticated admin role before the foundation API receives the request.</p>
      <form onSubmit={submit} className="stack">
        <label htmlFor="admin-plan">Member plan<select id="admin-plan" value={plan} onChange={(event) => setPlan(event.target.value)}><option value="free">Free</option><option value="pro">Pro</option><option value="team">Team</option></select></label>
        <label htmlFor="admin-credit-amount">Credit adjustment<input id="admin-credit-amount" type="number" value={creditAmount} onChange={(event) => setCreditAmount(event.target.value)} /></label>
        <button className="button button-secondary" disabled={busy}>{busy ? "Applying…" : "Apply admin changes"}</button>
      </form>
      {message && <p className="admin-message">{message}</p>}
    </section>
  );
}
