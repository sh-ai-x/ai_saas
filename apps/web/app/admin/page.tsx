import { AdminOperationsConsole } from "@/components/admin-operations-console";

export default function AdminPage() {
  return (
    <div className="admin-page">
      <header className="admin-header"><div><p className="eyebrow accent">ADMIN / OVERVIEW</p><h1>Product policy, kept separate.</h1><p className="admin-lede">Manage the catalog and payment adapter configuration here. The public landing page only consumes active pricing data.</p></div><span className="tag">SERVER-GUARDED</span></header>
      <section className="admin-card-grid">
        <a className="admin-card" href="/admin/pricing"><span className="eyebrow">01 / CATALOG</span><strong>Pricing plans</strong><p>Create plan policy, edit purchase modes, and archive options without touching UI code.</p><span className="card-link">Open catalog →</span></a>
        <a className="admin-card" href="/admin/payments"><span className="eyebrow">02 / PAYMENTS</span><strong>Provider settings</strong><p>Choose mock, Toss, or Lemon Squeezy with one-live-provider enforcement and safe public identifiers.</p><span className="card-link">Open settings →</span></a>
      </section>
      <AdminOperationsConsole />
      <section className="admin-callout"><p className="eyebrow accent">DATA BOUNDARY</p><h2>Neon is the source of truth.</h2><p>Drizzle owns the relational pricing schema. Local mode uses an explicit seed fallback only when `DATABASE_URL` is absent and `APP_ENV` is not production. Provider secrets stay in runtime environment or a secret manager.</p></section>
    </div>
  );
}
