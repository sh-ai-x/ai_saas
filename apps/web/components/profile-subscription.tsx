"use client";

import { useEffect, useState } from "react";

type Subscription = {
  status: string;
  cancelAtPeriodEnd: boolean;
  currentPeriodEnd: string | null;
  nextBillingAt: string | null;
  cancelRequestedAt: string | null;
  lastPaymentError: string | null;
};

type Summary = {
  access: "free" | "paid" | "grace" | "expired";
  plan: { name: string; description: string; quotas: Record<string, number> } | null;
  subscription: Subscription | null;
  usage: {
    inputLimit: number;
    outputLimit: number;
    totalLimit: number;
    inputUsed: number;
    outputUsed: number;
    totalUsed: number;
    totalRemaining: number;
    periodStart: string;
    periodEnd: string;
  };
  transitions: Array<{ eventType: string; toStatus: string; occurredAt: string }>;
};

function date(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function percent(used: number, limit: number) {
  return limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
}

function statusLabel(status: string | undefined) {
  return ({
    active: "Active",
    pending: "Payment pending",
    cancel_scheduled: "Cancellation scheduled",
    past_due: "Payment issue / grace period",
    expired: "Expired",
    canceled: "Canceled",
    free: "Free",
  } as Record<string, string>)[status ?? "free"] ?? status ?? "Free";
}

export function ProfileSubscription({ user }: { user: { name: string; email: string } }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const response = await fetch("/api/profile/subscription", { cache: "no-store" });
    const body = (await response.json()) as Summary & { error?: string };
    if (!response.ok) throw new Error(body.error ?? "Subscription unavailable");
    setSummary(body);
  }

  useEffect(() => {
    void load().catch((requestError: unknown) => setError(requestError instanceof Error ? requestError.message : "Subscription unavailable"));
  }, []);

  async function update(action: "cancel" | "resume") {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/profile/subscription", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action, idempotencyKey: `profile-${action}-${Date.now()}` }),
      });
      const body = (await response.json()) as Summary & { error?: string };
      if (!response.ok) throw new Error(body.error ?? "Subscription update failed");
      setSummary(body);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Subscription update failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="billing-page profile-page">
      <nav className="user-app-nav"><a className="brand" href="/app"><span className="brand-mark">AI</span><span><small>FOUNDATION</small><strong>Profile</strong></span></a><div><a href="/app">Workspace</a><a href="/billing">Plans</a><a href="/admin">Admin</a></div></nav>
      <header className="billing-header"><p className="eyebrow accent">ACCOUNT / SUBSCRIPTION</p><h1>{user.name}'s plan</h1><p>{user.email} · subscription access, renewal timing, and token usage in one place.</p></header>
      {error && <div className="alert">{error}</div>}
      {!summary ? <section className="admin-panel"><p>Loading subscription details…</p></section> : <>
        <section className="profile-summary-grid">
          <article className="admin-panel profile-card"><p className="eyebrow">CURRENT PLAN</p><h2>{summary.plan?.name ?? "Free"}</h2><p>{summary.plan?.description ?? "Use the free workspace until you choose a paid plan."}</p><span className={`tag status-${summary.access}`}>{statusLabel(summary.subscription?.status ?? "free")}</span></article>
          <article className="admin-panel profile-card"><p className="eyebrow">BILLING STATUS</p><h2>{summary.subscription ? statusLabel(summary.subscription.status) : "No active subscription"}</h2><p>Paid through: <strong>{date(summary.subscription?.currentPeriodEnd)}</strong></p><p>Next automatic billing: <strong>{summary.subscription?.cancelAtPeriodEnd ? "Skipped — cancellation scheduled" : date(summary.subscription?.nextBillingAt)}</strong></p>{summary.subscription?.cancelAtPeriodEnd && <p className="admin-message">Cancellation scheduled for {date(summary.subscription.currentPeriodEnd)}. Access remains available through the paid period.</p>}{summary.subscription?.lastPaymentError && <p className="alert">Payment issue: {summary.subscription.lastPaymentError}</p>}</article>
        </section>
        <section className="admin-panel token-usage-card"><div className="panel-heading"><div><p className="eyebrow">TOKEN USAGE</p><h2>{summary.usage.totalUsed.toLocaleString()} / {summary.usage.totalLimit.toLocaleString()} tokens</h2></div><span className="tag">{percent(summary.usage.totalUsed, summary.usage.totalLimit)}% USED</span></div><div className="usage-meter"><span style={{ width: `${percent(summary.usage.totalUsed, summary.usage.totalLimit)}%` }} /></div><div className="usage-breakdown"><span>Input <strong>{summary.usage.inputUsed.toLocaleString()} / {summary.usage.inputLimit.toLocaleString()}</strong></span><span>Output <strong>{summary.usage.outputUsed.toLocaleString()} / {summary.usage.outputLimit.toLocaleString()}</strong></span><span>Remaining <strong>{summary.usage.totalRemaining.toLocaleString()}</strong></span></div><p className="panel-copy">Current period: {date(summary.usage.periodStart)} – {date(summary.usage.periodEnd)}</p></section>
        <section className="profile-actions"><a className="button button-secondary" href="/billing">Change plan</a>{summary.subscription?.cancelAtPeriodEnd ? <button className="button" disabled={busy} onClick={() => void update("resume")}>{busy ? "Updating…" : "Resume automatic renewal"}</button> : summary.subscription ? <button className="button button-danger" disabled={busy} onClick={() => { if (window.confirm("Cancel automatic renewal at the end of the current paid period? Your access remains active until then.")) void update("cancel"); }}>{busy ? "Updating…" : "Cancel at period end"}</button> : null}</section>
        <section className="admin-panel"><div className="panel-heading"><div><p className="eyebrow">SUBSCRIPTION HISTORY</p><h2>Recent lifecycle events</h2></div></div>{summary.transitions.length ? <ul className="event-list">{summary.transitions.map((transition) => <li key={`${transition.eventType}-${transition.occurredAt}`}><span>{transition.eventType}</span><strong>{transition.toStatus}</strong><time>{date(transition.occurredAt)}</time></li>)}</ul> : <p className="panel-copy">No paid subscription events yet.</p>}</section>
      </>}
    </main>
  );
}
