import type { ReactNode } from "react";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <main className="admin-shell">
      <aside className="admin-sidebar">
        <a className="sidebar-home" href="/">← Public landing</a>
        <div className="sidebar-brand"><span className="brand-mark">AI</span><div><p className="eyebrow">FOUNDATION</p><strong>Admin console</strong></div></div>
        <p className="sidebar-caption">Policy, catalog, and payment operations</p>
        <nav className="admin-nav" aria-label="Admin navigation">
          <a href="/admin">Overview<span>ADMIN HOME</span></a>
          <a href="/admin/pricing">Pricing catalog<span>PLANS + OPTIONS</span></a>
          <a href="/admin/payments">Payment settings<span>ADAPTERS</span></a>
          <a href="/billing">User billing<span>DYNAMIC CATALOG</span></a>
          <a href="/guides">Setup guides<span>DOCUMENTATION</span></a>
        </nav>
        <div className="sidebar-note"><span className="status-dot" /> Local admin guard<br /><small>Production requires ADMIN_API_TOKEN</small></div>
      </aside>
      <section className="admin-content">{children}</section>
    </main>
  );
}
