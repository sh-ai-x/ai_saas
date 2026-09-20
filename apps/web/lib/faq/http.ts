import { boundedJson } from './bounded-json';
import { catalogResponseSchema, catalogSchema, fallback, requestSchema, responseSchema, SUPPORT } from './contracts';
import type { FaqProvider } from './provider';
import type { FaqRepository } from './repository';
import { answerFaq } from './service';

/** A bounded per-process budget; no user identifiers or proxy headers are retained. */
export function createFaqHttp(repository: FaqRepository, provider: FaqProvider, now = Date.now, log: (event: { event: 'faq'; outcome: string; status: number }) => void = event => console.info(JSON.stringify(event))) {
  let start = now();
  let requests = 0;
  function allowed() { if (now() - start >= 60000) { start = now(); requests = 0; } return ++requests <= 60; }
  function send(body: unknown, status = 200) {
    const parsed = responseSchema.parse(body);
    log({ event: 'faq', outcome: parsed.outcome, status });
    return Response.json(parsed, { status, headers: { 'Cache-Control': 'no-store', ...(status === 429 ? { 'Retry-After': '60' } : {}) } });
  }
  return {
    async GET() {
      if (!allowed()) return send(fallback(), 429);
      try { return Response.json(catalogResponseSchema.parse({ version: '1', entries: catalogSchema.parse(await repository.list()), support: SUPPORT }), { headers: { 'Cache-Control': 'no-store' } }); }
      catch { return send(fallback(), 503); }
    },
    async POST(request: Request) {
      if (!allowed()) return send(fallback(), 429);
      if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') return send(fallback(), 415);
      if (Number(request.headers.get('content-length')) > 2048) return send(fallback(), 413);
      const controller = new AbortController();
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        const input = await Promise.race([boundedJson(request.body, 2048, controller.signal), new Promise<never>((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(new Error('Request timeout')); }, 3000); })]);
        const parsed = requestSchema.safeParse(input);
        if (!parsed.success) return send(fallback('clarify'), 400);
        return send(await answerFaq(parsed.data.question, repository, provider));
      } catch { return send(fallback('clarify'), 400); }
      finally { clearTimeout(timer); }
    },
  };
}
