"use client";

import { useEffect, useState } from "react";

import type { BillingMode, ProviderSetting } from "@/lib/pricing/types";

export function AdminPaymentConsole() {
  const [providers, setProviders] = useState<ProviderSetting[]>([]);
  const [billingMode, setBillingMode] = useState<BillingMode>("subscription");
  const [reason, setReason] = useState("Select local mock provider");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [response, policyResponse] = await Promise.all([
      fetch("/api/admin/payment-providers", { cache: "no-store" }),
      fetch("/api/admin/billing-policy", { cache: "no-store" }),
    ]);
    const body = (await response.json()) as { providers?: ProviderSetting[]; error?: string };
    const policyBody = (await policyResponse.json()) as { billing?: { billingMode: BillingMode }; error?: string };
    if (!response.ok) throw new Error(body.error ?? "Could not load providers");
    if (!policyResponse.ok) throw new Error(policyBody.error ?? "Could not load billing policy");
    setProviders(body.providers ?? []);
    setBillingMode(policyBody.billing?.billingMode ?? "subscription");
  }

  useEffect(() => { void load().catch((error) => setMessage(error instanceof Error ? error.message : "Could not load providers")); }, []);

  async function toggle(provider: ProviderSetting) {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/admin/payment-providers", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ provider: provider.provider, enabled: !provider.enabled, sandbox: true, publicConfig: provider.publicConfig, secretRef: provider.secretRef, reason }) });
      const body = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(body.error ?? "Could not update provider");
      await load();
      setMessage(`${provider.provider} is now ${!provider.enabled ? "enabled" : "disabled"}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update provider");
    } finally {
      setBusy(false);
    }
  }

  async function changeBillingMode(nextMode: BillingMode) {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/admin/billing-policy", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ billingMode: nextMode, reason }) });
      const body = (await response.json()) as { billing?: { billingMode: BillingMode }; error?: string };
      if (!response.ok) throw new Error(body.error ?? "Could not update billing mode");
      setBillingMode(body.billing?.billingMode ?? nextMode);
      setMessage(`Catalog now accepts ${nextMode === "one_time" ? "one-time payments" : "subscriptions"} only.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update billing mode");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-page"><header className="admin-header"><div><p className="eyebrow accent">ADMIN / PAYMENT SETTINGS</p><h1>One payment model at a time.</h1><p className="admin-lede">The catalog offers either one-time payment or subscription. Provider selection is a separate adapter policy; secrets stay in runtime environment variables. <a href="/guides?guide=payment-toss">Read the Toss sandbox setup →</a></p></div><span className="tag">SANDBOX-FIRST</span></header><section className="admin-panel provider-panel"><div className="panel-heading"><div><p className="eyebrow">CATALOG PAYMENT POLICY</p><h2>Choose one billing model</h2></div><span className="tag">DYNAMIC CATALOG</span></div><label>Change reason<input value={reason} onChange={(event) => setReason(event.target.value)} /></label><div className="billing-mode-switch"><button className={billingMode === "subscription" ? "is-selected" : ""} onClick={() => void changeBillingMode("subscription")} disabled={busy}>Subscription<div>Monthly / annual renewal</div></button><button className={billingMode === "one_time" ? "is-selected" : ""} onClick={() => void changeBillingMode("one_time")} disabled={busy}>One-time payment<div>Single charge / no renewal</div></button></div><p className="muted">Current policy: <strong>{billingMode === "one_time" ? "one-time payment only" : "subscription only"}</strong>. Public pricing and checkout reject the other mode.</p><div className="provider-heading"><p className="eyebrow">PROVIDER REGISTRY</p><h2>Checkout adapters</h2></div><div className="provider-list">{providers.map((provider) => <article className={`provider-row ${provider.enabled ? "is-enabled" : ""}`} key={provider.provider}><div><span className="provider-name">{provider.provider}</span><p>{provider.provider === "mock" ? "Deterministic local and test checkout" : provider.provider === "toss" ? "Toss Payments browser SDK + billing auth" : "Lemon Squeezy hosted checkout + signed webhook"}</p><small>{provider.sandbox ? "sandbox" : "live"} · secret ref: {provider.secretRef ?? "none"}</small></div><button className={`button ${provider.enabled ? "button-secondary" : "button-primary"}`} onClick={() => void toggle(provider)} disabled={busy}>{provider.enabled ? "Disable" : "Enable"}</button></article>)}</div>{message && <p className="admin-message">{message}</p>}</section><section className="admin-callout"><p className="eyebrow accent">PROVIDER RULE</p><h2>Redirects do not grant access.</h2><p>A server-created order is followed by a verified provider event. The event inbox and ledger are the entitlement authority, whether the checkout is one-time or recurring.</p></section></div>
  );
}
