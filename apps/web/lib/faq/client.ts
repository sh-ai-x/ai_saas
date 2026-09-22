import { catalogResponseSchema, responseSchema, type FaqEntry } from './contracts';
export async function loadFaqCatalog(signal: AbortSignal, fetcher = fetch) {
  const response = await fetcher('/api/faq', { signal, credentials: 'omit' });
  if (!response.ok) throw new Error('FAQ unavailable');
  return catalogResponseSchema.parse(await response.json()).entries;
}
export async function askFaq(question: string, entries: FaqEntry[], signal: AbortSignal, fetcher = fetch) {
  const response = await fetcher('/api/faq', { method: 'POST', credentials: 'omit', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: '1', question }) });
  if (!response.ok) throw new Error('FAQ unavailable');
  const result = responseSchema.parse(await response.json());
  if (result.outcome === 'answer' && !entries.some(x => x.id === result.faqId && x.answer === result.answer)) throw new Error('Catalog changed; reopen FAQ');
  return result;
}
