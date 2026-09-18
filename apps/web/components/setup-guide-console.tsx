"use client";

import { useMemo, useState } from "react";

import { setupGuides, SetupGuide } from "../content/setup-guides";

function GuidePanel({ guide }: { guide: SetupGuide }) {
  const [copied, setCopied] = useState(false);

  async function copyMarkdown() {
    try {
      await navigator.clipboard.writeText(guide.markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="guide-panel">
      <div className="guide-heading">
        <p className="eyebrow accent">SETUP GUIDE / {guide.category}</p>
        <h2>{guide.title}</h2>
        <p>{guide.summary}</p>
      </div>
      <div className="markdown-editor" aria-label={`${guide.title} Markdown source`}>
        <div className="markdown-toolbar">
          <span className="markdown-path">{guide.path}</span>
          <span className="markdown-mode">MARKDOWN · READ ONLY</span>
          <button className="markdown-copy" type="button" onClick={copyMarkdown}>
            {copied ? "Copied" : "Copy markdown"}
          </button>
        </div>
        <pre className="markdown-source">
          {guide.markdown.split("\n").map((line, index) => (
            <span className="markdown-line" key={`${index}-${line}`}>
              <span className="line-number">{String(index + 1).padStart(2, "0")}</span>
              <span>{line || " "}</span>
            </span>
          ))}
        </pre>
      </div>
      <div className="guide-steps">
        {guide.steps.map((step) => (
          <article className="guide-step" key={step.title}>
            <h3>{step.title}</h3>
            <p>{step.body}</p>
            {step.code && <pre className="guide-code"><code>{step.code}</code></pre>}
          </article>
        ))}
      </div>
    </section>
  );
}

export function SetupGuideConsole() {
  const [activeGuideId, setActiveGuideId] = useState("getting-started");
  const paymentGuides = useMemo(
    () => setupGuides.filter((guide) => guide.id.startsWith("payment-")),
    [],
  );
  const standaloneGuides = useMemo(
    () => setupGuides.filter((guide) => !guide.id.startsWith("payment-")),
    [],
  );
  const activeGuide = useMemo(
    () => setupGuides.find((guide) => guide.id === activeGuideId) ?? setupGuides[0],
    [activeGuideId],
  );

  return (
    <main className="app-shell">
      <aside className="guide-sidebar" aria-label="Setup guide navigation">
        <a className="sidebar-home" href="/">← Operator console</a>
        <div className="sidebar-brand"><span className="brand-mark">AI</span><div><p className="eyebrow">FOUNDATION</p><strong>Setup guides</strong></div></div>
        <p className="sidebar-caption">Provider setup and verification</p>
        <nav className="guide-nav">
          {standaloneGuides.map((guide) => (
            <button className={`guide-nav-item ${activeGuideId === guide.id ? "is-active" : ""}`} key={guide.id} onClick={() => setActiveGuideId(guide.id)} aria-current={activeGuideId === guide.id ? "page" : undefined}>
              <span>{guide.category}</span><strong>{guide.title}</strong>
            </button>
          ))}
          <div className="guide-nav-group">
            <p className="guide-nav-group-label">PAYMENTS</p>
            {paymentGuides.map((guide) => (
              <button className={`guide-nav-item guide-nav-child ${activeGuideId === guide.id ? "is-active" : ""}`} key={guide.id} onClick={() => setActiveGuideId(guide.id)} aria-current={activeGuideId === guide.id ? "page" : undefined}>
                <span>PAYMENT</span><strong>{guide.title}</strong>
              </button>
            ))}
          </div>
        </nav>
        <div className="sidebar-note"><span className="status-dot" /> Secrets stay server-side<br /><small>Sandbox first · one provider at a time</small></div>
      </aside>

      <section className="console-column">
        <header className="guide-topbar">
          <div><p className="eyebrow accent">DOCUMENTATION / MARKDOWN</p><h1>Integration setup guides</h1></div>
          <a className="button button-quiet" href="/">Open operator console</a>
        </header>
        <div className="content-wrap">
          <GuidePanel guide={activeGuide} />
        </div>
      </section>
    </main>
  );
}
