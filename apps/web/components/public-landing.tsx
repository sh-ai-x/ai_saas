import { PricingCatalog } from "@/components/pricing-catalog";
import type { BillingMode, PricingPlan } from "@/lib/pricing/types";

export function PublicLanding({ plans, source, billingMode }: { plans: PricingPlan[]; source: string; billingMode: BillingMode }) {
  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand landing-brand" href="/"><span className="brand-mark">AI</span><span><small>FOUNDATION</small><strong>Substrate</strong></span></a>
        <div className="landing-links"><a href="/guides">Setup guides</a><a href="/app">Open workspace</a><a className="button button-primary" href="/admin">Admin console</a></div>
      </nav>
      <section className="landing-hero">
        <div className="landing-copy"><p className="eyebrow accent">AI PRODUCT FOUNDATION / v1</p><h1>Build the product.<br /><em>Keep the substrate.</em></h1><p>Auth, tenant boundaries, agent runs, sandbox billing, and operational contracts for shipping a serious AI SaaS without repeating the same first six weeks.</p><div className="landing-actions"><a className="button button-primary" href="/app">Try the workspace</a><a className="button button-quiet" href="/guides">Read setup guides</a></div></div>
        <div className="landing-system"><span className="system-label">SYSTEM STATUS</span><div className="system-line"><i /> Neon + Drizzle data boundary</div><div className="system-line"><i /> Google OAuth / provider adapters</div><div className="system-line"><i /> Bounded Agent + SSE replay</div><div className="system-line"><i /> Mock-first, sandbox-ready checkout</div><div className="system-foot">local profile · no paid infra required</div></div>
      </section>
      <PricingCatalog plans={plans} source={source} billingMode={billingMode} />
      <section className="landing-strip"><span>PUBLIC LANDING</span><strong>→</strong><span>USER WORKSPACE</span><strong>→</strong><span>ADMIN POLICY</span><strong>→</strong><span>PROVIDER CHECKOUT</span></section>
      <footer className="landing-footer"><span>AI SaaS Foundation</span><span>Neon · Drizzle · adapter pattern · sandbox first</span></footer>
    </main>
  );
}
