import type { FaqEntry } from './contracts';
export const normalize = (text: string) => text.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').replace(/\s+/g, ' ').trim();
export function redact(text: string): string {
  return text.normalize('NFKC').replace(/\b(?:token|password|secret|bearer|api[_ -]?key)\b.*$/gim, '[redacted]')
    .replace(/https?:\/\/\S+|[\w.+-]+@[\w.-]+\.[a-z]+/gi, '[redacted]')
    .replace(/\b[\w-]*\d[\w-]*\b/g, '[redacted]').slice(0, 500);
}
export function isSensitive(text: string): boolean {
  return /account|tenant|payment|refund|billing|card|auth|password|secret|token|bearer|api.?key|conversation|history|계정|결제|비밀번호|환불|인증/i.test(text) || redact(text) !== text.normalize('NFKC').slice(0, 500);
}
export function matchFaq(text: string, entries: FaqEntry[]) {
  const query = normalize(text);
  const exact = entries.filter(row => [row.question, ...row.aliases].some(x => normalize(x) === query));
  const words = new Set(query.split(' '));
  const candidates = [...entries].sort((a, b) => {
    const score = (row: FaqEntry) => normalize([row.question, ...row.aliases].join(' ')).split(' ').filter(w => words.has(w)).length;
    return score(b) - score(a) || a.id.localeCompare(b.id);
  }).slice(0, 5);
  return { exact: exact.length === 1 ? exact[0] : undefined, candidates };
}
