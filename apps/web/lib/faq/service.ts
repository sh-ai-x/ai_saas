import { catalogSchema, fallback, SUPPORT, type FaqResponse } from './contracts';
import { isSensitive, matchFaq, normalize, redact } from './matcher';
import type { FaqProvider } from './provider';
import type { FaqRepository } from './repository';
export async function answerFaq(question: string, repository: FaqRepository, provider: FaqProvider): Promise<FaqResponse> {
  try {
    const entries = catalogSchema.parse(await repository.list());
    const { exact, candidates } = matchFaq(question, entries);
    const answer = (row: typeof entries[number]): FaqResponse => ({ version: '1', outcome: 'answer', faqId: row.id, answer: row.answer, support: SUPPORT });
    if (isSensitive(question)) return fallback();
    if (exact) return answer(exact);
    if (!candidates.length) return fallback();
    const selection = await provider.select(normalize(redact(question)), candidates);
    if (!selection) return fallback('clarify');
    const row = candidates.find(x => x.id === selection.faqId && x.category === selection.category);
    if (!row || !Number.isFinite(selection.confidence) || selection.confidence < 0.85 || selection.confidence > 1 || !Number.isFinite(selection.answerable) || selection.answerable < 0.9 || selection.answerable > 1) return fallback('clarify');
    return answer(row);
  } catch { return fallback(); }
}
