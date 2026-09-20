import { asc, eq } from 'drizzle-orm';
import { getDb } from '@/db';
import { faqEntries } from '@/db/schema';
import { catalogSchema, type FaqEntry } from './contracts';
import { seedFaqs } from './seed';
export interface FaqRepository { list(): Promise<FaqEntry[]> }
const CATALOG_CACHE_TTL_MS = 30_000;
let cachedCatalog: { entries: FaqEntry[]; expiresAt: number } | undefined;
export const faqRepository: FaqRepository = {
  async list() {
    const production = process.env.APP_ENV === 'production' || (process.env.NODE_ENV === 'production' && !['local', 'test'].includes(process.env.APP_ENV ?? ''));
    if (production && !process.env.DATABASE_URL) throw new Error('FAQ database required');
    if (cachedCatalog && cachedCatalog.expiresAt > Date.now()) return cachedCatalog.entries;
    const db = getDb();
    const entries = !db
      ? catalogSchema.parse(seedFaqs)
      : catalogSchema.parse(await db.select({ id: faqEntries.id, category: faqEntries.category, question: faqEntries.question, aliases: faqEntries.aliases, answer: faqEntries.answer }).from(faqEntries).where(eq(faqEntries.active, true)).orderBy(asc(faqEntries.id)).limit(51));
    cachedCatalog = { entries, expiresAt: Date.now() + CATALOG_CACHE_TTL_MS };
    return entries;
  },
};
