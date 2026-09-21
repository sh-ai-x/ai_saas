import { FoundationConsole } from "@/components/foundation-console";
import { SessionControl } from "@/components/auth/session-control";
import { getSafeSession } from "@/lib/auth/session";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function UserAppPage() {
  const session = await getSafeSession();
  if (!session) redirect("/login?next=/app");
  const isAdmin = ["admin", "super_admin"].includes(session.user.role);
  return (
    <main className="user-app-page">
      <nav className="user-app-nav"><a className="brand" href="/"><span className="brand-mark">AI</span><span><small>FOUNDATION</small><strong>User workspace</strong></span></a><div><span className="role-badge">{session.user.role.toUpperCase()}</span>{isAdmin ? <a href="/admin">Admin console</a> : null}<SessionControl /></div></nav>
      <FoundationConsole />
    </main>
  );
}
