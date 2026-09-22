import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { SessionControl } from "@/components/auth/session-control";
import { getSafeSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const session = await getSafeSession();
  if (!session || !["admin", "super_admin"].includes(session.user.role)) redirect("/login?next=/admin");
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
        </nav>
        <div className="sidebar-note"><span className="status-dot" /> Server role guard<br /><small>{session.user.role} access · {session.user.email}</small><SessionControl /></div>
      </aside>
      <section className="admin-content">{children}</section>
    </main>
  );
}
