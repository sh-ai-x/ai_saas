import { FoundationConsole } from "@/components/foundation-console";

export default function UserAppPage() {
  return (
    <main className="user-app-page">
      <nav className="user-app-nav"><a className="brand" href="/"><span className="brand-mark">AI</span><span><small>FOUNDATION</small><strong>User workspace</strong></span></a><div><a href="/billing">Billing</a><a href="/guides">Setup guides</a><a href="/admin">Admin</a></div></nav>
      <FoundationConsole />
    </main>
  );
}
