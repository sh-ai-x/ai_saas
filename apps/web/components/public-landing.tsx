import { PricingCatalog } from "@/components/pricing-catalog";
import type { BillingMode, PricingPlan } from "@/lib/pricing/types";

export function PublicLanding({ plans, source, billingMode, sessionControl }: { plans: PricingPlan[]; source: string; billingMode: BillingMode; sessionControl?: React.ReactNode }) {
  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand landing-brand" href="/"><span className="brand-mark">AI</span><span><small>FOUNDATION</small><strong>Substrate</strong></span></a>
        <div className="landing-links"><a href="/guides">Setup guides</a><a href="/app">Open workspace</a>{sessionControl ?? <a className="button button-primary" href="/login">Sign in</a>}</div>
      </nav>
      <section className="landing-hero">
        <div className="landing-copy"><p className="eyebrow accent">AI ENGINEERING WORKBENCH / v1</p><h1>Review the change.<br /><em>Trust the evidence.</em></h1><p>Compare an AI engineering proposal with a local Git repository and get bounded REQ/AC status, code impact, and traceable evidence before implementation.</p><div className="landing-actions"><a className="button button-primary" href="/app">Open the workbench</a><a className="button button-quiet" href="/guides">Read setup guides</a></div></div>
        <div className="landing-system"><span className="system-label">WORKBENCH STATUS</span><div className="system-line"><i /> Local Git repository analysis</div><div className="system-line"><i /> REQ / AC evidence mapping</div><div className="system-line"><i /> LangGraph review checkpoints</div><div className="system-line"><i /> LangChain + JEV bounded synthesis</div><div className="system-foot">read-only · no paid infrastructure required</div></div>
      </section>
      <PricingCatalog plans={plans} source={source} billingMode={billingMode} />
      <section className="landing-strip"><span>PUBLIC LANDING</span><strong>→</strong><span>USER WORKSPACE</span><strong>→</strong><span>ADMIN POLICY</span><strong>→</strong><span>PROVIDER CHECKOUT</span></section>
      <footer className="landing-footer"><span>AI SaaS Foundation</span><span>Neon · Drizzle · adapter pattern · sandbox first</span></footer>
    </main>
  );
}
