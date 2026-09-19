"use client";

import { useState } from "react";

import type { BillingMode, PricingPlan } from "@/lib/pricing/types";

function formatPrice(amountMinor: number, currency: string, interval: string) {
  const value = new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amountMinor / 100);
  return interval === "one_time" ? value : `${value} / ${interval}`;
}

export function PricingCatalog({ plans, source, billingMode }: { plans: PricingPlan[]; source: string; billingMode: BillingMode }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  async function checkout(optionId: string) {
    setBusy(optionId);
    setMessage("");
    try {
      const response = await fetch("/api/pricing/checkout", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ optionId }),
      });
      const body = (await response.json()) as { checkoutUrl?: string; provider?: string; mode?: string; error?: string };
      if (!response.ok) throw new Error(body.error ?? "Checkout could not be created");
      setMessage(`${body.provider} ${body.mode} checkout ready.`);
      if (body.checkoutUrl && body.provider !== "mock") window.open(body.checkoutUrl, "_blank", "noopener,noreferrer");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Checkout could not be created");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="pricing-section" aria-labelledby="pricing-heading">
      <div className="section-heading">
        <div><p className="eyebrow accent">CATALOG / ADMIN CONTROLLED</p><h2 id="pricing-heading">Choose a payment shape.</h2></div>
        <p className="muted">Prices are loaded from the active catalog. This catalog accepts <strong>{billingMode === "one_time" ? "one-time payments" : "subscriptions"}</strong> only; switch the policy in Admin before offering the other mode.</p>
      </div>
      <div className="pricing-grid">
        {plans.map((plan) => (
          <article className={`pricing-card ${plan.isDefault ? "is-featured" : ""}`} key={plan.id}>
            {plan.isDefault && <span className="pricing-badge">DEFAULT</span>}
            <p className="eyebrow">{plan.code.toUpperCase()}</p>
            <h3>{plan.name}</h3>
            <p className="pricing-description">{plan.description}</p>
            <ul className="feature-list">{plan.features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
            <div className="pricing-options">
              {plan.options.filter((option) => option.active).map((option) => (
                <button className="pricing-option" key={option.id} onClick={() => void checkout(option.id)} disabled={busy !== null}>
                  <span><strong>{formatPrice(option.amountMinor, option.currency, option.interval)}</strong><small>{option.mode === "one_time" ? "One-time" : option.interval === "year" ? "Annual subscription" : "Monthly subscription"} · {option.provider}</small></span>
                  <span className="arrow">{busy === option.id ? "…" : "→"}</span>
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>
      {message && <p className="checkout-message">{message}</p>}
      <p className="catalog-source">Catalog source: {source === "neon" ? "Neon PostgreSQL" : "explicit local seed fallback"}</p>
    </section>
  );
}
