'use client';
import { useEffect, useRef, useState } from 'react';
import { askFaq, loadFaqCatalog } from '@/lib/faq/client';
import { SUPPORT, type FaqEntry, type FaqResponse } from '@/lib/faq/contracts';
export const FAQ_CATALOG_TIMEOUT_MS = 60_000;
export const FAQ_ANSWER_TIMEOUT_MS = 15_000;
export function FaqWidget() {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<FaqEntry[]>([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<FaqResponse | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    active.current = controller;
    const timer = setTimeout(() => controller.abort(), FAQ_CATALOG_TIMEOUT_MS);
    setBusy(true); setError('');
    loadFaqCatalog(controller.signal).then(setEntries).catch(() => { if (!controller.signal.aborted) setError('FAQ is unavailable. Please use the support guide.'); }).finally(() => { clearTimeout(timer); if (active.current === controller) { setBusy(false); if (controller.signal.aborted) setError('FAQ timed out. Please try again.'); } });
    return () => { active.current = null; controller.abort(); clearTimeout(timer); };
  }, [open]);
  useEffect(() => () => active.current?.abort(), []);
  async function submit(text: string) {
    if (busy || !text.trim()) return;
    const controller = new AbortController(); active.current = controller;
    const timer = setTimeout(() => controller.abort(), FAQ_ANSWER_TIMEOUT_MS);
    setBusy(true); setError(''); setResult(null);
    try { setResult(await askFaq(text, entries, controller.signal)); }
    catch { setError('FAQ is unavailable. Please try again or use the support guide.'); }
    finally { clearTimeout(timer); setBusy(false); }
  }
  return <aside className="faq-widget" aria-label="FAQ support">
    <button className="button button-primary" aria-expanded={open} aria-controls="faq-panel" onClick={() => { active.current?.abort(); setOpen(!open); }}> {open ? 'Close FAQ' : 'FAQ & Support'} </button>
    {open && <section id="faq-panel" className="faq-panel" aria-label="Ask a question">
      <h3>How can we help?</h3>
      <p className="muted">Ask a general question. Do not include personal or payment details.</p>
      <div className="stack">{entries.map(entry => <button key={entry.id} className="button button-quiet" disabled={busy} onClick={() => void submit(entry.question)}>{entry.question}</button>)}</div>
      <form className="stack" onSubmit={event => { event.preventDefault(); void submit(question); }}>
        <label htmlFor="faq-question">Your question</label>
        <input id="faq-question" value={question} maxLength={500} onChange={event => setQuestion(event.target.value)} disabled={busy} />
        <button className="button button-secondary" disabled={busy || !entries.length || !question.trim()}>Ask FAQ</button>
      </form>
      <div role="status" aria-live="polite">{busy ? 'Finding help…' : result?.outcome === 'answer' ? result.answer : result?.message}</div>
      {error && <p role="alert">{error}</p>}
      <a href={SUPPORT.href}>{SUPPORT.label}</a>
    </section>}
  </aside>;
}
