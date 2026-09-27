"use client";

import { useEffect, useState } from "react";

type AdminRow = {
  user: { id: string; name: string; email: string; role: string };
  access: string;
  plan: { name: string } | null;
  subscription: { status: string; cancelAtPeriodEnd: boolean; currentPeriodEnd: string | null; nextBillingAt: string | null; lastPaymentError: string | null } | null;
  usage: { totalUsed: number; totalLimit: number; totalRemaining: number };
};

function date(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium" }).format(new Date(value));
}

function statusLabel(status: string | undefined) {
  return ({
    active: "Active",
    pending: "Payment pending",
    cancel_scheduled: "Cancellation scheduled",
    past_due: "Payment issue",
    expired: "Expired",
    canceled: "Canceled",
  } as Record<string, string>)[status ?? ""] ?? status ?? "Free";
}

export function AdminSubscriptionDirectory() {
  const [rows, setRows] = useState<AdminRow[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (status) params.set("status", status);
    void fetch(`/api/admin/subscriptions?${params.toString()}`, { cache: "no-store" }).then(async (response) => {
      const body = (await response.json()) as { subscriptions?: AdminRow[]; error?: string };
      if (!response.ok) throw new Error(body.error ?? "Subscription list unavailable");
      setRows(body.subscriptions ?? []);
    }).catch((requestError: unknown) => setError(requestError instanceof Error ? requestError.message : "Subscription list unavailable"));
  }, [query, status]);

  return <section className="admin-panel admin-subscriptions"><div className="panel-heading"><div><p className="eyebrow">ADMIN / SUBSCRIPTIONS</p><h2>User subscription status</h2></div><span className="tag">READ + AUDIT</span></div><div className="admin-filters"><input aria-label="Search users" placeholder="Search name, email, or user ID" value={query} onChange={(event) => setQuery(event.target.value)} /><select aria-label="Filter status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="cancel_scheduled">Cancel scheduled</option><option value="past_due">Past due</option><option value="expired">Expired</option></select></div>{error ? <p className="alert">{error}</p> : <div className="table-wrap"><table><thead><tr><th>User</th><th>Plan / status</th><th>Period end</th><th>Next billing</th><th>Tokens</th></tr></thead><tbody>{rows.length ? rows.map((row) => <tr key={row.user.id}><td><strong>{row.user.name}</strong><small>{row.user.email}</small></td><td><strong>{row.plan?.name ?? "Free"}</strong><small>{row.subscription?.cancelAtPeriodEnd ? "Cancellation scheduled" : statusLabel(row.subscription?.status ?? row.access)}</small></td><td>{date(row.subscription?.currentPeriodEnd)}</td><td>{row.subscription?.cancelAtPeriodEnd ? "Skipped" : date(row.subscription?.nextBillingAt)}</td><td>{row.usage.totalUsed.toLocaleString()} / {row.usage.totalLimit.toLocaleString()}<small>{row.usage.totalRemaining.toLocaleString()} remaining</small></td></tr>) : <tr><td colSpan={5}>No subscription records match the filters.</td></tr>}</tbody></table></div>}</section>;
}
