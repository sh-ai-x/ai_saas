"use client";

import { useEffect, useState } from "react";

import type { BillingMode, PricingPlan, PricingPlanInput, PricingProvider } from "@/lib/pricing/types";

const emptyPlan: PricingPlanInput = {
  code: "new-plan",
  name: "New plan",
  description: "",
  billingMode: "subscription",
  active: true,
  isDefault: false,
  displayOrder: 30,
  features: ["Add a feature"],
  quotas: { monthlyRuns: 100 },
  options: [{ mode: "subscription", interval: "month", provider: "mock", currency: "USD", amountMinor: 1900, active: true }],
};

async function adminApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) }, cache: "no-store" });
  const body = (await response.json()) as T & { error?: string };
  if (!response.ok) throw new Error(body.error ?? `Request failed: ${response.status}`);
  return body;
}

export function AdminPricingConsole() {
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [catalogMode, setCatalogMode] = useState<BillingMode>("subscription");
  const [draft, setDraft] = useState<PricingPlanInput>(emptyPlan);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [reason, setReason] = useState("Initial catalog policy");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [result, policy] = await Promise.all([
        adminApi<{ plans: PricingPlan[] }>("/api/admin/pricing"),
        adminApi<{ billing: { billingMode: BillingMode } }>("/api/admin/billing-policy"),
      ]);
      setPlans(result.plans);
      setCatalogMode(policy.billing.billingMode);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load catalog");
    }
  }

  useEffect(() => { void load(); }, []);

  function edit(plan: PricingPlan) {
    setEditingId(plan.id);
    setDraft({ ...plan, options: plan.options.map((option) => ({ ...option })) });
    setReason(`Update ${plan.code} pricing policy`);
    setMessage("");
  }

  function reset() {
    setEditingId(null);
    setDraft({ ...emptyPlan, billingMode: catalogMode, options: [{ ...emptyPlan.options![0], mode: catalogMode, interval: catalogMode === "one_time" ? "one_time" : "month" }] });
    setReason("Initial catalog policy");
  }

  function updateOption(index: number, key: string, value: string | number | boolean) {
    setDraft((current) => ({ ...current, options: (current.options ?? []).map((option, optionIndex) => optionIndex === index ? { ...option, [key]: value } : option) }));
  }

  function updateProvider(index: number, provider: string) {
    const normalizedProvider = (provider === "mock" || provider === "toss" || provider === "lemon-squeezy") ? provider as PricingProvider : "mock";
    setDraft((current) => ({
      ...current,
      options: (current.options ?? []).map((option, optionIndex) => optionIndex === index
        ? { ...option, provider: normalizedProvider, ...(normalizedProvider === "toss" ? { currency: "KRW" } : {}) }
        : option),
    }));
  }

  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const path = editingId ? `/api/admin/pricing/${editingId}` : "/api/admin/pricing";
      await adminApi(path, { method: editingId ? "PATCH" : "POST", body: JSON.stringify({ reason, plan: draft }) });
      await load();
      reset();
      setMessage("Catalog saved. Public pricing will read the active record.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save catalog");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-header"><div><p className="eyebrow accent">ADMIN / PRICING CATALOG</p><h1>Plans and purchase modes.</h1><p className="admin-lede">A plan is policy. Each one-time, monthly, or yearly price is a separate option and can point to a provider product reference.</p></div><span className="tag">DRIZZLE / NEON</span></header>
      <div className="admin-work-grid">
        <section className="admin-panel"><div className="panel-heading"><div><p className="eyebrow">CATALOG RECORDS</p><h2>Active and archived plans</h2></div><button className="button button-quiet" onClick={reset}>New plan</button></div><div className="admin-plan-list">{plans.map((plan) => <button className={`admin-plan-row ${editingId === plan.id ? "is-selected" : ""}`} key={plan.id} onClick={() => edit(plan)}><span><strong>{plan.name}</strong><small>{plan.code} · {plan.options.length} options</small></span><span className={plan.active ? "status-active" : "status-muted"}>{plan.active ? "ACTIVE" : "ARCHIVED"}</span></button>)}</div></section>
        <section className="admin-panel"><div className="panel-heading"><div><p className="eyebrow">POLICY EDITOR</p><h2>{editingId ? "Edit plan" : "Create plan"}</h2></div><span className="tag">AUDIT REQUIRED</span></div><div className="stack"><label>Code<input value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value })} /></label><label>Name<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label>Description<textarea rows={2} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label><div className="form-grid"><label>Catalog billing mode<select value={draft.billingMode} disabled><option value="subscription">Subscription only</option><option value="one_time">One-time only</option></select></label><label>Active<select value={String(draft.active)} onChange={(event) => setDraft({ ...draft, active: event.target.value === "true" })}><option value="true">Active</option><option value="false">Archived</option></select></label></div><p className="muted">Current catalog mode: <strong>{catalogMode === "one_time" ? "one-time payment" : "subscription"}</strong>. Price edits stage for the next policy flip; cross-mode changes that do not match the active policy are rejected with an audit reason.</p><label>Change reason<input value={reason} onChange={(event) => setReason(event.target.value)} /></label><div className="option-editor"><div className="option-editor-heading"><span className="eyebrow">PURCHASE OPTIONS</span><button type="button" className="text-button" onClick={() => setDraft({ ...draft, options: [...(draft.options ?? []), { mode: draft.billingMode, interval: draft.billingMode === "one_time" ? "one_time" : "year", provider: "mock", currency: "USD", amountMinor: 4900, active: true }] })}>+ Add option</button></div>{(draft.options ?? []).map((option, index) => <div className="option-row" key={option.id ?? index}><span className="option-mode">{option.mode === "one_time" ? "ONE-TIME" : "SUBSCRIPTION"}</span><select value={option.interval} onChange={(event) => updateOption(index, "interval", event.target.value)}><option value="month">Monthly</option><option value="year">Yearly</option><option value="one_time">One-time</option></select><select value={option.provider} onChange={(event) => updateProvider(index, event.target.value)}><option value="mock">Mock</option><option value="toss">Toss</option><option value="lemon-squeezy">Lemon</option></select><input value={option.currency} onChange={(event) => updateOption(index, "currency", event.target.value.toUpperCase())} aria-label="Currency" maxLength={3} /><input type="number" value={option.amountMinor} onChange={(event) => updateOption(index, "amountMinor", Number(event.target.value))} aria-label="Amount in minor currency units" /></div>)}</div><button className="button button-primary" onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : editingId ? "Save policy" : "Create plan"}</button>{message && <p className="admin-message">{message}</p>}</div></section>
      </div>
    </div>
  );
}
