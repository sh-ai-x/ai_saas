"use client";

import { useEffect, useState } from "react";

import { ChangeImpactWorkbench } from "./change-impact/change-impact-workbench";

type JsonRecord = Record<string, unknown>;

const jsonHeaders = { "content-type": "application/json" };

async function api<T>(path: string): Promise<T> {
  const response = await fetch(`/api/foundation${path}`, {
    credentials: "same-origin",
    headers: { ...jsonHeaders, "x-tenant-id": "demo-tenant" },
    cache: "no-store",
  });
  const raw = await response.text();
  const body = raw ? (JSON.parse(raw) as JsonRecord) : {};
  if (!response.ok) throw new Error(String(body.message ?? body.error ?? `Request failed: ${response.status}`));
  return body as T;
}

export function FoundationConsole() {
  const [health, setHealth] = useState("checking");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void api<JsonRecord>("/healthz")
      .then((result) => {
        if (active) setHealth(String(result.status ?? "ok"));
      })
      .catch((requestError) => {
        if (active) {
          setHealth("offline");
          setError(requestError instanceof Error ? requestError.message : "Could not connect to the Foundation API.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="console-page">
      <div className="console-column">
        <header className="topbar">
          <div className="brand"><span className="brand-mark">AI</span><div><p className="eyebrow">FOUNDATION CONSOLE</p><h1>Proposal Review workspace</h1></div></div>
          <div className="topbar-actions">
            <span className={`status-pill ${health === "ok" ? "is-ok" : ""}`}><span className="status-dot" /> API {health}</span>
            <span className="workspace-scope">USER WORKSPACE</span>
          </div>
        </header>

        <div className="content-wrap">
          <section className="hero">
            <div><p className="eyebrow accent">AI ENGINEER / CHANGE IMPACT</p><h2>Review the proposal.<br />Understand the code.</h2><p className="hero-copy">Compare a proposal with a local Git repository to review REQ and AC implementation status, partial implementation, code impact, and evidence.</p></div>
            <div className="hero-meta"><span className="meta-label">WORKFLOW</span><strong>Proposal Review</strong><span className="meta-label">RUNTIME</span><strong>LangGraph · LangChain · JEV</strong></div>
          </section>

          {error && <div className="alert">{error}</div>}

          <section className="workspace-section">
            <ChangeImpactWorkbench />
          </section>

          <footer><span>AI Change Impact Workbench</span><span>Read-only proposal and code review</span></footer>
        </div>
      </div>
    </main>
  );
}
