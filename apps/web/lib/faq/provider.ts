import type { FaqEntry } from './contracts';
export type Selection = { faqId: string; category: string; confidence: number; answerable: number };
export interface FaqProvider { select(text: string, candidates: FaqEntry[]): Promise<Selection | null> }
export const DEFAULT_PROVIDER_TIMEOUT_MS = 5_000;
