"use client";

import { useState } from "react";

import { loadTossSdk } from "@/lib/payments/toss-sdk";
import type { BillingMode, PricingPlan } from "@/lib/pricing/types";

function formatPrice(amountMinor: number, currency: string, interval: string) {
  const value = new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amountMinor / (currency.toUpperCase() === "KRW" ? 1 : 100));
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
      const body = (await response.json()) as {
        checkoutUrl?: string;
        provider?: string;
        mode?: string;
        error?: string;
        checkoutContext?: Record<string, unknown>;
      };
      if (!response.ok) throw new Error(body.error ?? "Checkout could not be created");
      if (body.provider === "toss") {
        const context = body.checkoutContext;
        const clientKey = typeof context?.client_key === "string" ? context.client_key : "";
        const customerKey = typeof context?.customer_key === "string" ? context.customer_key : "";
        if (!context || !clientKey || !customerKey) throw new Error("Toss checkout context is incomplete");
        const TossPayments = await loadTossSdk();
        const payment = TossPayments(clientKey).payment({ customerKey });
        const common = {
          method: "CARD" as const,
          successUrl: String(context.success_url ?? ""),
          failUrl: String(context.fail_url ?? ""),
          customerEmail: String(context.customer_email ?? ""),
          customerName: String(context.customer_name ?? ""),
        };
        if (context.billing_auth === true) {
          await payment.requestBillingAuth(common);
        } else {
          const amount = context.amount as { value?: unknown; currency?: unknown } | undefined;
          await payment.requestPayment({
            ...common,
            amount: { value: Number(amount?.value), currency: String(amount?.currency ?? "KRW") },
            orderId: String(context.order_id ?? body.checkoutUrl ?? ""),
            orderName: String(context.order_name ?? "AI SaaS payment"),
          });
        }
        setMessage("Toss sandbox checkout opened.");
      } else {
        setMessage(`${body.provider} ${body.mode} checkout ready.`);
      }
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
