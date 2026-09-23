"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { loadTossSdk } from "@/lib/payments/toss-sdk";
import { RepositoryWorkspace } from "./repository-workspace/repository-workspace";

type JsonRecord = Record<string, unknown>;

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


export function FoundationConsole() {
  const [tenantId, setTenantId] = useState("demo-tenant");
  const [health, setHealth] = useState("checking");
  const [session, setSession] = useState<JsonRecord | null>(null);
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
  const [activeTab, setActiveTab] = useState<"agent" | "proposals">("proposals");
  const refreshInFlight = useRef<Promise<void> | null>(null);

  const log = useCallback((entry: string) => {
    setActivity((current) => [`${new Date().toLocaleTimeString()} · ${entry}`, ...current].slice(0, 8));
  }, []);

  const refresh = useCallback(() => {
    if (refreshInFlight.current) return refreshInFlight.current;
    const request = (async () => {
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
    })();
    const trackedRequest = request.finally(() => {
      if (refreshInFlight.current === trackedRequest) refreshInFlight.current = null;
    });
    refreshInFlight.current = trackedRequest;
    return trackedRequest;
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const runStatus = useMemo(() => (runId ? `run ${runId.slice(0, 12)}…` : "ready"), [runId]);
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
            <div className="tab-switcher">
              <button
                className={`tab-button ${activeTab === "proposals" ? "is-active" : ""}`}
                onClick={() => setActiveTab("proposals")}
              >
                Repository Proposals
              </button>
              <button
                className={`tab-button ${activeTab === "agent" ? "is-active" : ""}`}
                onClick={() => setActiveTab("agent")}
              >
                Agent Run
              </button>
            </div>
            <span className={`status-pill ${health === "ok" ? "is-ok" : ""}`}><span className="status-dot" /> API {health}</span>
            <span className="workspace-scope">USER WORKSPACE</span>
          </div>
        </header>

        <div className="content-wrap">
          <section className="hero">
            <div><p className="eyebrow accent">USER WORKSPACE / INTEGRATION-READY</p><h2>Run your AI product<br />inside the foundation.</h2><p className="hero-copy">Execute bounded workflows, review your usage, and manage your own billing. Organization policy and member administration stay in the separate admin console.</p></div>
            <div className="hero-meta"><span className="meta-label">WORKSPACE</span><strong>{tenantId}</strong><span className="meta-label">DATA / RUNTIME</span><strong>Neon + Drizzle · Foundation API</strong></div>
          </section>

          {error && <div className="alert">{error}</div>}

          {activeTab === "proposals" && (
            <section className="workspace-section">
              <RepositoryWorkspace />
            </section>
          )}

          {activeTab === "agent" && (<>
          <section className="metrics">
            <article className="metric-card"><span>RUN CREDITS</span><strong>{String(balance?.run_credits_available ?? "—")}</strong><small>shared executable balance</small></article>
            <article className="metric-card"><span>PAYMENT</span><strong>{String(payment?.provider ?? "—")}</strong><small>{payment?.sandbox ? "sandbox enabled" : "production mode"}</small></article>
            <article className="metric-card"><span>AGENT</span><strong>{String(agent?.provider ?? "—")}</strong><small>{String(agent?.model ?? "not configured")}</small></article>
            <article className="metric-card"><span>LAST RUN</span><strong>{runStatus}</strong><small>{session ? "session-aware" : "checkpoint + SSE replay"}</small></article>
          </section>

          <section className="grid">
            <article className="panel panel-wide"><div className="panel-heading"><div><p className="eyebrow">01 / AGENT RUN</p><h3>Run a bounded workflow</h3></div><span className="tag">SSE REPLAY</span></div><form onSubmit={submitRun} className="stack"><label htmlFor="message">Prompt</label><textarea id="message" value={message} onChange={(event) => setMessage(event.target.value)} rows={3} /><div className="form-row"><button className="button button-primary" disabled={busy !== null}>{busy === "run" ? "Executing…" : "Execute Agent run"}</button><span className="muted">{String(agent?.provider ?? "local")} · bounded usage</span></div></form><pre className="event-stream">{runOutput}</pre></article>
            <article className="panel"><div className="panel-heading"><div><p className="eyebrow">02 / BILLING</p><h3>{payment?.provider !== "mock" ? "Open sandbox checkout" : "Test payment adapter"}</h3></div><span className="tag">{payment?.sandbox ? "SANDBOX" : "MOCK"}</span></div><p className="panel-copy">{payment?.provider !== "mock" ? "Create a pending order and finish the provider sandbox checkout." : "Create a deterministic test order and grant credits exactly once."}</p><button className="button button-secondary" onClick={() => void submitPayment()} disabled={busy !== null}>{busy === "payment" ? "Creating…" : payment?.provider !== "mock" ? "Create sandbox order" : "Complete mock payment"}</button><a className="text-button" href="/billing">Review billing catalog →</a>{orderId && <p className="success-note">Order {orderId} created.{checkoutUrl && " Checkout opened in a new tab."}</p>}</article>
            <article className="panel activity-panel"><div className="panel-heading"><div><p className="eyebrow">03 / ACTIVITY</p><h3>Recent activity</h3></div><span className="tag">PERSONAL</span></div>{activity.length ? <ul className="activity-list">{activity.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Your runs and billing actions will appear here.</p>}</article>
          </section>
          <footer><span>AI SaaS Foundation · contract v1</span><span>Provider-neutral · sandbox-first</span></footer>
          </>)}
        </div>
      </div>
    </main>
  );
}
