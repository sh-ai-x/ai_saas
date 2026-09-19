"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type JsonRecord = Record<string, unknown>;

type TossPayment = {
  requestPayment: (options: {
    method: "CARD";
    amount: { value: number; currency: string };
    orderId: string;
    orderName: string;
    successUrl: string;
    failUrl: string;
  }) => Promise<void>;
};

declare global {
  interface Window {
    TossPayments?: (clientKey: string) => {
      payment: (options: { customerKey: string }) => TossPayment;
    };
  }
}

const jsonHeaders = { "content-type": "application/json" };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/foundation${path}`, {
      ...init,
      credentials: "same-origin",
      headers: {
        ...jsonHeaders,
        ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  const raw = await response.text();
  const body = raw ? (JSON.parse(raw) as JsonRecord) : {};
  if (!response.ok) {
    throw new Error(String(body.message ?? body.error ?? `Request failed: ${response.status}`));
  }
  return body as T;
}

function formatError(error: unknown) {
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
}

async function loadTossSdk() {
  if (window.TossPayments) return window.TossPayments;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://js.tosspayments.com/v2/standard";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Toss Payments SDK를 불러오지 못했습니다."));
    document.head.appendChild(script);
  });
  if (!window.TossPayments) throw new Error("Toss Payments SDK가 초기화되지 않았습니다.");
  return window.TossPayments;
}

export function FoundationConsole() {
  const [tenantId, setTenantId] = useState("demo-tenant");
  const [health, setHealth] = useState("checking");
  const [session, setSession] = useState<JsonRecord | null>(null);
  const [plan, setPlan] = useState("pro");
  const [creditAmount, setCreditAmount] = useState("5");
  const [message, setMessage] = useState("Summarize the local foundation flow");
  const [runOutput, setRunOutput] = useState("아직 실행된 run이 없습니다.");
  const [runId, setRunId] = useState("");
  const [orderId, setOrderId] = useState("");
  const [checkoutUrl, setCheckoutUrl] = useState("");
  const [balance, setBalance] = useState<JsonRecord | null>(null);
  const [agent, setAgent] = useState<JsonRecord | null>(null);
  const [payment, setPayment] = useState<JsonRecord | null>(null);
  const [activity, setActivity] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const log = useCallback((entry: string) => {
    setActivity((current) => [`${new Date().toLocaleTimeString()} · ${entry}`, ...current].slice(0, 8));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [healthResult, balanceResult, agentResult, paymentResult] = await Promise.all([
        api<JsonRecord>("/healthz"),
        api<JsonRecord>("/v1/billing/balance"),
        api<JsonRecord>("/v1/agent/providers"),
        api<JsonRecord>("/v1/billing/providers"),
      ]);
      setHealth(String(healthResult.status ?? "ok"));
      setBalance(balanceResult);
      setAgent(agentResult);
      setPayment(paymentResult);
      try {
        const nextSession = await api<JsonRecord>("/v1/auth/session");
        setSession(nextSession);
        if (typeof nextSession.tenant_id === "string") setTenantId(nextSession.tenant_id);
      } catch {
        setSession(null);
      }
      setError("");
    } catch (requestError) {
      setHealth("offline");
      setError(formatError(requestError));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const runStatus = useMemo(() => (runId ? `run ${runId.slice(0, 12)}…` : "ready"), [runId]);
  const isRealPayment = payment?.provider !== "mock";
  const sessionProvider = String(session?.provider ?? "");

  async function login() {
    setBusy("login");
    try {
      const start = await api<JsonRecord>("/v1/auth/google/start");
      if (start.mode === "authorization-code" && typeof start.authorization_url === "string") {
        window.location.assign(start.authorization_url);
        return;
      }
      const nextSession = await api<JsonRecord>("/v1/auth/google/callback", {
        method: "POST",
        body: JSON.stringify({ state: start.state, code: "local-browser-code" }),
      });
      setSession(nextSession);
      if (typeof nextSession.tenant_id === "string") setTenantId(nextSession.tenant_id);
      log("Google mock session established");
      setError("");
    } catch (requestError) {
      setError(formatError(requestError));
    } finally {
      setBusy(null);
    }
  }

  async function submitAdmin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("admin");
    try {
      const planResult = await api<JsonRecord>("/v1/admin/plan", {
        method: "POST",
        body: JSON.stringify({ target_user_id: "demo-member", plan, reason: "local web console demo" }),
      });
      const creditResult = await api<JsonRecord>("/v1/admin/credits", {
        method: "POST",
        body: JSON.stringify({ target_user_id: "demo-user", amount: Number(creditAmount), reason: "local web console demo" }),
      });
      log(`Admin updated plan=${String((planResult.after as JsonRecord).plan)} and credits=${String((creditResult.after as JsonRecord).credit_balance)}`);
      await refresh();
      setError("");
    } catch (requestError) {
      setError(formatError(requestError));
    } finally {
      setBusy(null);
    }
  }

  async function submitRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("run");
    try {
      const result = await api<JsonRecord>("/v1/agent/execute", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          project_id: "demo-project",
          idempotency_key: `web-agent-${Date.now()}`,
          trace_id: `web-trace-${Date.now()}`,
          input: { message },
        }),
      });
      const nextRunId = String(result.run_id);
      setRunId(nextRunId);
      const events = await fetch(`/api/foundation/v1/runs/${nextRunId}/events`, {
        credentials: "same-origin",
        cache: "no-store",
      }).then((response) => response.text());
      setRunOutput(events);
      log(`Agent ${String(agent?.provider ?? "local")} run completed and SSE replayed`);
      await refresh();
      setError("");
    } catch (requestError) {
      setError(formatError(requestError));
    } finally {
      setBusy(null);
    }
  }

  async function submitPayment() {
    setBusy("payment");
    try {
      const nextOrderId = `web-order-${Date.now()}`;
      const checkout = await api<JsonRecord>("/v1/billing/orders", {
        method: "POST",
        body: JSON.stringify({ order_id: nextOrderId, idempotency_key: `${nextOrderId}-key`, credit_grant: 10, amount_minor: 1000 }),
      });
      setOrderId(nextOrderId);
      setCheckoutUrl(String(checkout.checkout_url ?? ""));
      if (payment?.provider === "mock") {
        const result = await api<JsonRecord>("/v1/billing/mock/complete", {
          method: "POST",
          body: JSON.stringify({ order_id: nextOrderId }),
        });
        log(`Mock payment ${String(result.status)}; ledger applied=${String(result.applied)}`);
      } else if (payment?.provider === "toss") {
        const context = checkout.checkout_context as JsonRecord | undefined;
        const clientKey = String(context?.client_key ?? "");
        const amount = context?.amount as JsonRecord | undefined;
        if (!context || !clientKey || !amount) throw new Error("Toss 브라우저 결제 컨텍스트가 없습니다.");
        const TossPayments = await loadTossSdk();
        const tossPayment = TossPayments(clientKey).payment({
          customerKey: `customer-${tenantId}`,
        });
        await tossPayment.requestPayment({
          method: "CARD",
          amount: { value: Number(amount.value), currency: String(amount.currency) },
          orderId: String(context.order_id),
          orderName: String(context.order_name ?? "AI SaaS credits"),
          successUrl: String(context.success_url),
          failUrl: String(context.fail_url),
        });
        log("Toss sandbox checkout opened through the browser SDK");
      } else {
        log(`${String(payment?.provider)} sandbox order created; complete provider checkout/webhook next`);
        if (checkout.checkout_url) window.open(String(checkout.checkout_url), "_blank", "noopener,noreferrer");
      }
      await refresh();
      setError("");
    } catch (requestError) {
      setError(formatError(requestError));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="console-page">
      <div className="console-column">
        <header className="topbar">
          <div className="brand"><span className="brand-mark">AI</span><div><p className="eyebrow">FOUNDATION CONSOLE</p><h1>Operator workspace</h1></div></div>
          <div className="topbar-actions">
            <span className={`status-pill ${health === "ok" ? "is-ok" : ""}`}><span className="status-dot" /> API {health}</span>
            <a className="button button-quiet" href="/guides">Setup guides</a>
            <button className="button button-quiet" onClick={() => void login()} disabled={busy !== null}>
              {sessionProvider === "google" ? "Google session active" : busy === "login" ? "Connecting…" : "Sign in with Google"}
            </button>
          </div>
        </header>

        <div className="content-wrap">
          <section className="hero">
            <div><p className="eyebrow accent">LOCAL / INTEGRATION-READY</p><h2>Ship the AI product layer<br />without rebuilding the substrate.</h2><p className="hero-copy">Real OAuth, sandbox billing, bounded Agent providers, tenant controls, and SSE runs share one contract-first runtime.</p></div>
            <div className="hero-meta"><span className="meta-label">TENANT</span><strong>{tenantId}</strong><span className="meta-label">RUNTIME</span><strong>SQLite · stdlib HTTP</strong></div>
          </section>

          {error && <div className="alert">{error}</div>}
          <section className="metrics">
            <article className="metric-card"><span>RUN CREDITS</span><strong>{String(balance?.run_credits_available ?? "—")}</strong><small>shared executable balance</small></article>
            <article className="metric-card"><span>PAYMENT</span><strong>{String(payment?.provider ?? "—")}</strong><small>{payment?.sandbox ? "sandbox enabled" : "production mode"}</small></article>
            <article className="metric-card"><span>AGENT</span><strong>{String(agent?.provider ?? "—")}</strong><small>{String(agent?.model ?? "not configured")}</small></article>
            <article className="metric-card"><span>LAST RUN</span><strong>{runStatus}</strong><small>{session ? "session-aware" : "checkpoint + SSE replay"}</small></article>
          </section>

          <section className="grid">
            <article className="panel panel-wide"><div className="panel-heading"><div><p className="eyebrow">01 / AGENT RUN</p><h3>Run a bounded workflow</h3></div><span className="tag">SSE REPLAY</span></div><form onSubmit={submitRun} className="stack"><label htmlFor="message">Prompt</label><textarea id="message" value={message} onChange={(event) => setMessage(event.target.value)} rows={3} /><div className="form-row"><button className="button button-primary" disabled={busy !== null}>{busy === "run" ? "Executing…" : "Execute Agent run"}</button><span className="muted">{String(agent?.provider ?? "local")} · bounded usage</span></div></form><pre className="event-stream">{runOutput}</pre></article>
            <article className="panel"><div className="panel-heading"><div><p className="eyebrow">02 / ADMIN</p><h3>Operate safely</h3></div><span className="tag">AUDITED</span></div><form onSubmit={submitAdmin} className="stack"><label htmlFor="plan">Member plan</label><select id="plan" value={plan} onChange={(event) => setPlan(event.target.value)}><option value="free">Free</option><option value="pro">Pro</option><option value="team">Team</option></select><label htmlFor="creditAmount">Credit adjustment</label><input id="creditAmount" type="number" value={creditAmount} onChange={(event) => setCreditAmount(event.target.value)} /><button className="button button-secondary" disabled={busy !== null}>{busy === "admin" ? "Applying…" : "Apply admin changes"}</button></form></article>
            <article className="panel"><div className="panel-heading"><div><p className="eyebrow">03 / BILLING</p><h3>{isRealPayment ? "Open sandbox checkout" : "Test payment adapter"}</h3></div><span className="tag">{payment?.sandbox ? "SANDBOX" : "MOCK"}</span></div><p className="panel-copy">{isRealPayment ? "Create a pending order, finish the provider sandbox checkout, then deliver the signed webhook." : "Create a pending order, complete the signed mock webhook, and grant credits exactly once."}</p><button className="button button-secondary" onClick={() => void submitPayment()} disabled={busy !== null}>{busy === "payment" ? "Creating…" : isRealPayment ? "Create sandbox order" : "Complete mock payment"}</button>{orderId && <p className="success-note">Order {orderId} created.{checkoutUrl && " Checkout opened in a new tab."}</p>}</article>
            <article className="panel activity-panel"><div className="panel-heading"><div><p className="eyebrow">04 / ACTIVITY</p><h3>Operator trail</h3></div><span className="tag">LOCAL</span></div>{activity.length ? <ul className="activity-list">{activity.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Actions will appear here after the first interaction.</p>}</article>
          </section>
          <footer><span>AI SaaS Foundation · contract v1</span><span>Provider-neutral · sandbox-first</span></footer>
        </div>
      </div>
    </main>
  );
}
