"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type JsonRecord = Record<string, unknown>;

const tenantId = "demo-tenant";
const jsonHeaders = { "content-type": "application/json" };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/foundation${path}`, {
    ...init,
    headers: {
      ...jsonHeaders,
      "x-tenant-id": tenantId,
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

export function FoundationConsole() {
  const [health, setHealth] = useState("checking");
  const [session, setSession] = useState<JsonRecord | null>(null);
  const [plan, setPlan] = useState("pro");
  const [creditAmount, setCreditAmount] = useState("5");
  const [message, setMessage] = useState("Summarize the local foundation flow");
  const [runOutput, setRunOutput] = useState("아직 실행된 run이 없습니다.");
  const [runId, setRunId] = useState("");
  const [orderId, setOrderId] = useState("");
  const [balance, setBalance] = useState<JsonRecord | null>(null);
  const [activity, setActivity] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const log = useCallback((entry: string) => {
    setActivity((current) => [`${new Date().toLocaleTimeString()} · ${entry}`, ...current].slice(0, 8));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [healthResult, balanceResult] = await Promise.all([
        api<JsonRecord>("/healthz"),
        api<JsonRecord>("/v1/billing/balance"),
      ]);
      setHealth(String(healthResult.status ?? "ok"));
      setBalance(balanceResult);
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

  async function login() {
    setBusy("login");
    try {
      const start = await api<JsonRecord>("/v1/auth/google/start");
      const nextSession = await api<JsonRecord>("/v1/auth/google/callback", {
        method: "POST",
        body: JSON.stringify({ state: start.state, code: "local-browser-code" }),
      });
      setSession(nextSession);
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
        body: JSON.stringify({
          target_user_id: "demo-member",
          plan,
          reason: "local web console demo",
        }),
      });
      const creditResult = await api<JsonRecord>("/v1/admin/credits", {
        method: "POST",
        body: JSON.stringify({
          target_user_id: "demo-user",
          amount: Number(creditAmount),
          reason: "local web console demo",
        }),
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
      const result = await api<JsonRecord>("/v1/runs", {
        method: "POST",
        body: JSON.stringify({
          contract_version: "v1",
          tenant_id: tenantId,
          project_id: "demo-project",
          idempotency_key: `web-run-${Date.now()}`,
          trace_id: `web-trace-${Date.now()}`,
          input: { message },
        }),
      });
      const nextRunId = String(result.run_id);
      setRunId(nextRunId);
      const events = await fetch(`/api/foundation/v1/runs/${nextRunId}/events`, {
        headers: { "x-tenant-id": tenantId },
        cache: "no-store",
      }).then((response) => response.text());
      setRunOutput(events);
      log(`Run ${nextRunId.slice(0, 12)}… completed and SSE replayed`);
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
      await api<JsonRecord>("/v1/billing/orders", {
        method: "POST",
        body: JSON.stringify({
          order_id: nextOrderId,
          idempotency_key: `${nextOrderId}-key`,
          credit_grant: 10,
          amount_minor: 1000,
        }),
      });
      const payment = await api<JsonRecord>("/v1/billing/mock/complete", {
        method: "POST",
        body: JSON.stringify({ order_id: nextOrderId }),
      });
      setOrderId(nextOrderId);
      log(`Mock payment ${String(payment.status)}; ledger applied=${String(payment.applied)}`);
      await refresh();
      setError("");
    } catch (requestError) {
      setError(formatError(requestError));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">AI</span>
          <div>
            <p className="eyebrow">FOUNDATION CONSOLE</p>
            <h1>Operator workspace</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <span className={`status-pill ${health === "ok" ? "is-ok" : ""}`}>
            <span className="status-dot" /> API {health}
          </span>
          <button className="button button-quiet" onClick={() => void login()} disabled={busy !== null}>
            {session ? "Google session active" : busy === "login" ? "Signing in…" : "Sign in with Google"}
          </button>
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow accent">LOCAL / FREE-PORTFOLIO</p>
          <h2>Ship the AI product layer<br />without rebuilding the substrate.</h2>
          <p className="hero-copy">Auth, tenancy, durable runs, metering, billing, and operator controls are wired to the same contract-first runtime.</p>
        </div>
        <div className="hero-meta">
          <span className="meta-label">TENANT</span>
          <strong>{tenantId}</strong>
          <span className="meta-label">RUNTIME</span>
          <strong>SQLite · stdlib HTTP</strong>
        </div>
      </section>

      {error && <div className="alert">{error}</div>}

      <section className="metrics">
        <article className="metric-card"><span>RUN CREDITS</span><strong>{String(balance?.run_credits_available ?? "—")}</strong><small>shared executable balance</small></article>
        <article className="metric-card"><span>PAYMENT CREDITS</span><strong>{String(balance?.payment_credits ?? "—")}</strong><small>verified mock webhook ledger</small></article>
        <article className="metric-card"><span>ENTITLEMENT</span><strong>{String(balance?.entitlement ?? "free")}</strong><small>{session ? "Google mock session" : "sign in to establish session"}</small></article>
        <article className="metric-card"><span>LAST RUN</span><strong>{runStatus}</strong><small>checkpoint + SSE replay</small></article>
      </section>

      <section className="grid">
        <article className="panel panel-wide">
          <div className="panel-heading"><div><p className="eyebrow">01 / AGENT RUN</p><h3>Run a bounded workflow</h3></div><span className="tag">SSE REPLAY</span></div>
          <form onSubmit={submitRun} className="stack">
            <label htmlFor="message">Prompt</label>
            <textarea id="message" value={message} onChange={(event) => setMessage(event.target.value)} rows={3} />
            <div className="form-row"><button className="button button-primary" disabled={busy !== null}>{busy === "run" ? "Executing…" : "Execute local run"}</button><span className="muted">LocalEchoModel · 1 credit reservation</span></div>
          </form>
          <pre className="event-stream">{runOutput}</pre>
        </article>

        <article className="panel">
          <div className="panel-heading"><div><p className="eyebrow">02 / ADMIN</p><h3>Operate safely</h3></div><span className="tag">AUDITED</span></div>
          <form onSubmit={submitAdmin} className="stack">
            <label htmlFor="plan">Member plan</label>
            <select id="plan" value={plan} onChange={(event) => setPlan(event.target.value)}><option value="free">Free</option><option value="pro">Pro</option><option value="team">Team</option></select>
            <label htmlFor="creditAmount">Credit adjustment</label>
            <input id="creditAmount" type="number" value={creditAmount} onChange={(event) => setCreditAmount(event.target.value)} />
            <button className="button button-secondary" disabled={busy !== null}>{busy === "admin" ? "Applying…" : "Apply admin changes"}</button>
          </form>
        </article>

        <article className="panel">
          <div className="panel-heading"><div><p className="eyebrow">03 / BILLING</p><h3>Test payment adapter</h3></div><span className="tag">MOCK</span></div>
          <p className="panel-copy">Create a pending order, complete the signed mock webhook, and grant credits exactly once.</p>
          <button className="button button-secondary" onClick={() => void submitPayment()} disabled={busy !== null}>{busy === "payment" ? "Processing…" : "Complete mock payment"}</button>
          {orderId && <p className="success-note">Order {orderId} applied to ledger.</p>}
        </article>

        <article className="panel activity-panel">
          <div className="panel-heading"><div><p className="eyebrow">04 / ACTIVITY</p><h3>Operator trail</h3></div><span className="tag">LOCAL</span></div>
          {activity.length ? <ul className="activity-list">{activity.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Actions will appear here after the first interaction.</p>}
        </article>
      </section>

      <footer><span>AI SaaS Foundation · contract v1</span><span>Provider-neutral · no paid infrastructure</span></footer>
    </main>
  );
}
