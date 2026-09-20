import { z } from 'zod';

export const SUPPORT = { label: 'Support guide', href: '/guides' } as const;
export const entrySchema = z.object({
  id: z.string().regex(/^[a-z][a-z0-9-]{0,39}$/),
  category: z.enum(['guides', 'product', 'support']),
  question: z.string().min(1).max(200), aliases: z.array(z.string().min(1).max(200)).max(10),
  answer: z.string().min(1).max(2000),
}).strict();
export const catalogSchema = z.array(entrySchema).max(50).refine(rows => new Set(rows.map(x => x.id)).size === rows.length);
export type FaqEntry = z.infer<typeof entrySchema>;
export const requestSchema = z.object({ version: z.literal('1'), question: z.string().trim().min(1).max(500) }).strict();
const common = { version: z.literal('1'), support: z.object({ label: z.literal(SUPPORT.label), href: z.literal(SUPPORT.href) }) };
export const responseSchema = z.discriminatedUnion('outcome', [
  z.object({ ...common, outcome: z.literal('answer'), faqId: entrySchema.shape.id, answer: entrySchema.shape.answer }).strict(),
  z.object({ ...common, outcome: z.enum(['clarify', 'handoff']), answer: z.null(), message: z.string().min(1).max(200) }).strict(),
]);
export type FaqResponse = z.infer<typeof responseSchema>;
export const catalogResponseSchema = z.object({ ...common, entries: catalogSchema }).strict();
export function fallback(outcome: 'clarify' | 'handoff' = 'handoff'): FaqResponse {
  return { version: '1', outcome, answer: null, message: outcome === 'clarify' ? 'Please choose a preset question or rephrase without personal details.' : 'Please use the support guide for further help.', support: SUPPORT };
}
