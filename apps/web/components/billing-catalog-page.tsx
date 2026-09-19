"use client";

import { useEffect, useState } from "react";

import { PricingCatalog } from "@/components/pricing-catalog";
import type { BillingMode, PricingPlan } from "@/lib/pricing/types";

export function BillingCatalogPage() {
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [billingMode, setBillingMode] = useState<BillingMode>("subscription");
  const [source, setSource] = useState("local-seed");
  const [error, setError] = useState("");

  useEffect(() => {
    void fetch("/api/pricing", { cache: "no-store" }).then(async (response) => {
      const body = (await response.json()) as { plans?: PricingPlan[]; billing?: { billingMode: BillingMode }; source?: string; error?: string };
      if (!response.ok) throw new Error(body.error ?? "Pricing unavailable");
      setPlans(body.plans ?? []);
      setBillingMode(body.billing?.billingMode ?? "subscription");
      setSource(body.source ?? "local-seed");
    }).catch((requestError: unknown) => setError(requestError instanceof Error ? requestError.message : "Pricing unavailable"));
  }, []);

  return <main className="billing-page"><nav className="user-app-nav"><a className="brand" href="/app"><span className="brand-mark">AI</span><span><small>FOUNDATION</small><strong>Billing</strong></span></a><div><a href="/app">Workspace</a><a href="/admin">Admin</a></div></nav><header className="billing-header"><p className="eyebrow accent">USER APP / BILLING</p><h1>{billingMode === "one_time" ? "One payment. No renewal." : "Choose your subscription."}</h1><p>Displayed from the active admin catalog. When the admin switches payment model, this page and checkout contract update together.</p></header>{error ? <div className="alert">{error}</div> : <PricingCatalog plans={plans} source={source} billingMode={billingMode} />}</main>;
}
