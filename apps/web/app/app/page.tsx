import { FoundationConsole } from "@/components/foundation-console";
import { SessionControl } from "@/components/auth/session-control";

export default function UserAppPage() {
  return (
    <main className="user-app-page">
      <nav className="user-app-nav"><a className="brand" href="/"><span className="brand-mark">AI</span><span><small>FOUNDATION</small><strong>User workspace</strong></span></a><div><a href="/billing">Billing</a><a href="/guides">Setup guides</a><a href="/admin">Admin</a><SessionControl /></div></nav>
      <FoundationConsole />
    </main>
  );
}
