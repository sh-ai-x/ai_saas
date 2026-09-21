import { catalogSchema, responseSchema } from '../lib/faq/contracts';
import { seedFaqs } from '../lib/faq/seed';
import { answerFaq } from '../lib/faq/service';
import { redact, normalize } from '../lib/faq/matcher';
import { createOpenAiProvider, DEFAULT_OPENAI_TIMEOUT_MS } from '../lib/faq/openai';

const repository = { list: async () => seedFaqs };
const decision = (overrides: Record<string, unknown> = {}) => ({ faqId: 'faq-getting-started', category: 'general', answerable: true, confidence: 1, ...overrides });
const payload = (overrides: Record<string, unknown> = {}) => ({ output: [{ type: 'message', content: [{ type: 'output_text', text: JSON.stringify(decision(overrides)) }] }] });

describe('FAQ policy and OpenAI boundary', () => {
  it('validates seed and rejects duplicate IDs and empty answers', () => {
    expect(catalogSchema.parse(seedFaqs)).toEqual(seedFaqs);
    expect(() => catalogSchema.parse([...seedFaqs, seedFaqs[0]])).toThrow();
    expect(() => catalogSchema.parse([{ ...seedFaqs[0], answer: '' }])).toThrow();
  });
  it('uses a provider timeout compatible with container network latency', () => {
    expect(DEFAULT_OPENAI_TIMEOUT_MS).toBe(5_000);
  });
  it.each(['What is AI SaaS Foundation?', 'service overview', '  service overview?!  '])('matches %s without calling provider', async question => {
    const select = jest.fn();
    const result = await answerFaq(question, repository, { select });
    expect(result).toMatchObject({ outcome: 'answer', answer: seedFaqs[0].answer });
    expect(select).not.toHaveBeenCalled();
    expect(responseSchema.parse(result)).toEqual(result);
  });
  it('redacts private data and normalizes punctuation', () => {
    expect(redact('email a@example.com token abc 123456 https://private.test')).not.toMatch(/example|abc|123456|private/);
    expect(normalize(' Setup GUIDES?! ')).toBe('setup guides');
  });
  it('never calls provider for sensitive questions', async () => {
    const select = jest.fn();
    expect((await answerFaq('my account password is secret', repository, { select })).outcome).toBe('handoff');
    expect(select).not.toHaveBeenCalled();
  });
  it('makes one typed call and returns catalog prose only', async () => {
    const fetcher = jest.fn(async () => Response.json(payload()));
    const provider = createOpenAiProvider({ enabled: true, key: 'test-placeholder', fetcher });
    expect((await answerFaq('help with documentation', repository, provider)).answer).toBe(seedFaqs[0].answer);
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://api.openai.com/v1/responses');
    const body = JSON.parse(init.body as string);
    expect(body.text.format.type).toBe('json_schema');
    expect(body.text.format.strict).toBe(true);
    expect(body.store).toBe(false);
    expect(JSON.stringify(body)).not.toContain(seedFaqs[0].answer);
  });
  it.each(['disabled', 'missing-key', 'low', 'malformed', 'unknown', 'category', 'rate', 'error'])('fails closed: %s', async mode => {
    const overrides = mode === 'low' ? { confidence: 0.2 } : mode === 'unknown' ? { faqId: 'invented' } : mode === 'category' ? { category: 'product' } : mode === 'noul' ? { answerable: false } : {};
    const fetcher = jest.fn(async () => { if (mode === 'error') throw new Error('private'); return Response.json(mode === 'malformed' ? {} : payload(overrides), { status: mode === 'rate' ? 429 : 200 }); });
    const result = await answerFaq('documentation help', repository, createOpenAiProvider({ enabled: mode !== 'disabled', key: mode === 'missing-key' ? undefined : 'test-placeholder', fetcher }));
    expect(result.outcome).not.toBe('answer');
    expect(JSON.stringify(result)).not.toContain('private');
    expect(fetcher.mock.calls.length).toBeLessThanOrEqual(1);
  });
  it('bounds timeout and opens circuit after failure', async () => {
    const fetcher = jest.fn(() => new Promise<Response>(() => {}));
    const provider = createOpenAiProvider({ enabled: true, key: 'test-placeholder', fetcher, timeoutMs: 5 });
    expect((await answerFaq('documentation help', repository, provider)).outcome).toBe('handoff');
    await answerFaq('documentation help', repository, provider);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

import { createFaqHttp } from '../lib/faq/http';
import { askFaq, loadFaqCatalog } from '../lib/faq/client';
import { FAQ_ANSWER_TIMEOUT_MS, FAQ_CATALOG_TIMEOUT_MS, FaqWidget } from '../components/faq-widget';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { faqEntries } from '../db/schema';
import { getTableName } from 'drizzle-orm';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('FAQ HTTP and widget contracts', () => {
  const request = (body: unknown) => new Request('http://localhost/api/faq', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  it('owns a Drizzle table and wires the widget into the layout', () => {
    expect(getTableName(faqEntries)).toBe('faq_entries');
    expect(Object.keys(faqEntries).filter(key => key !== 'enableRLS')).toEqual([
      'id', 'slug', 'locale', 'category', 'question', 'answer', 'aliases',
      'active', 'displayOrder', 'createdAt', 'updatedAt',
    ]);
    expect(readFileSync(resolve(__dirname, '../app/layout.tsx'), 'utf8')).toContain('<FaqWidget />');
    expect(renderToStaticMarkup(createElement(FaqWidget))).toContain('FAQ &amp; Support');
    expect(FAQ_CATALOG_TIMEOUT_MS).toBeGreaterThan(FAQ_ANSWER_TIMEOUT_MS);
    expect(FAQ_CATALOG_TIMEOUT_MS).toBe(60_000);
  });
  it('serves versioned catalog and exact answers with safe logs', async () => {
    const select = jest.fn(); const log = jest.fn();
    const http = createFaqHttp(repository, { select }, Date.now, log);
    expect((await (await http.GET()).json()).entries).toEqual(seedFaqs);
    const result = await http.POST(request({ version: '1', question: 'service overview' }));
    expect(result.status).toBe(200);
    expect((await result.json()).outcome).toBe('answer');
    expect(select).not.toHaveBeenCalled();
    expect(log).toHaveBeenCalledWith({ event: 'faq', outcome: 'answer', status: 200 });
  });
  it.each([{}, { version: '2', question: 'help' }, { version: '1', question: '' }, { version: '1', question: 'a'.repeat(501) }, { version: '1', question: 'help', tenant: 'private' }])('rejects invalid request %j', async body => {
    const select = jest.fn(); const http = createFaqHttp(repository, { select }, Date.now, () => {});
    expect((await http.POST(request(body))).status).toBe(400);
    expect(select).not.toHaveBeenCalled();
  });
  it('rejects invalid JSON, oversized bodies and wrong media type', async () => {
    const http = createFaqHttp(repository, { select: jest.fn() }, Date.now, () => {});
    expect((await http.POST(new Request('http://localhost', { method: 'POST', body: '{', headers: { 'Content-Type': 'application/json' } }))).status).toBe(400);
    expect((await http.POST(request({ question: 'x'.repeat(3000) }))).status).toBe(400);
    expect((await http.POST(new Request('http://localhost', { method: 'POST', body: 'help' }))).status).toBe(415);
  });
  it('rate limits without relying on spoofable client headers and resets', async () => {
    let time = 0;
    const http = createFaqHttp(repository, { select: jest.fn() }, () => time, () => {});
    for (let i = 0; i < 60; i++) await http.GET();
    expect((await http.GET()).status).toBe(429);
    time = 60001;
    expect((await http.GET()).status).toBe(200);
  });
  it('fails closed on catalog failure', async () => {
    const http = createFaqHttp({ list: async () => { throw new Error('database secret'); } }, { select: jest.fn() }, Date.now, () => {});
    expect((await http.GET()).status).toBe(503);
    expect((await (await http.POST(request({ version: '1', question: 'help' }))).json()).outcome).toBe('handoff');
  });
  it('widget uses HTTP only and rejects non-catalog prose', async () => {
    const http = createFaqHttp(repository, { select: jest.fn() }, Date.now, () => {});
    const fetcher = jest.fn(async (_url: string | URL | Request, init?: RequestInit) => init?.method === 'POST' ? http.POST(new Request('http://localhost/api/faq', init)) : http.GET());
    const signal = new AbortController().signal;
    const entries = await loadFaqCatalog(signal, fetcher);
    expect((await askFaq('service overview', entries, signal, fetcher)).answer).toBe(seedFaqs[0].answer);
    expect(fetcher.mock.calls.every(([url]) => url === '/api/faq')).toBe(true);
    const forged = jest.fn(async () => Response.json({ version: '1', outcome: 'answer', faqId: 'faq-getting-started', answer: 'invented answer', support: { label: 'Support guide', href: '/guides' } }));
    await expect(askFaq('help', entries, signal, forged)).rejects.toThrow('Catalog changed');
    await expect(loadFaqCatalog(signal, jest.fn(async () => new Response('', { status: 503 })))).rejects.toThrow();
  });
  it('ambiguous aliases make at most one provider call', async () => {
    const select = jest.fn(async () => null);
    const rows = seedFaqs.map(x => ({ ...x, aliases: ['same'] }));
    expect((await answerFaq('same', { list: async () => rows }, { select })).outcome).toBe('clarify');
    expect(select).toHaveBeenCalledTimes(1);
  });
});

describe('FAQ repository and bounded wire validation', () => {
  it('rejects production without a database even after local reads', async () => {
    const { faqRepository } = await import('../lib/faq/repository');
    const oldUrl = process.env.DATABASE_URL; const oldEnv = process.env.APP_ENV;
    delete process.env.DATABASE_URL;
    try {
      process.env.APP_ENV = 'local';
      expect(await faqRepository.list()).toEqual(seedFaqs);
      process.env.APP_ENV = 'production';
      await expect(faqRepository.list()).rejects.toThrow('database required');
    } finally {
      if (oldUrl === undefined) delete process.env.DATABASE_URL; else process.env.DATABASE_URL = oldUrl;
      if (oldEnv === undefined) delete process.env.APP_ENV; else process.env.APP_ENV = oldEnv;
    }
  });
  it('keeps migration seed equal to local seed', () => {
    const sql = readFileSync(resolve(__dirname, '../drizzle/0004_faq_english.sql'), 'utf8');
    expect(sql).toContain('UPDATE "faq_entries"');
    for (const row of seedFaqs) for (const value of [row.id, row.category, row.question, ...row.aliases, row.answer]) expect(sql).toContain(value);
  });
  it.each(['type', 'distribution', 'oversized', 'noul'])('rejects malformed provider %s', async mode => {
    const overrides = mode === 'distribution' ? { confidence: 2 } : mode === 'noul' ? { answerable: 'invalid' } : {};
    const fetcher = jest.fn(async () => mode === 'oversized' ? new Response('x'.repeat(17000)) : mode === 'type' ? Response.json({ output: [{ type: 'message', content: [{ type: 'text', text: '{}' }] }] }) : Response.json(payload(overrides)));
    expect((await answerFaq('documentation help', repository, createOpenAiProvider({ enabled: true, key: 'test-placeholder', fetcher }))).outcome).toBe('handoff');
  });
});
