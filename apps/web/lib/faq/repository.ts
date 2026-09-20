import { asc, eq } from 'drizzle-orm';
import { getDb } from '@/db';
import { faqEntries } from '@/db/schema';
import { catalogSchema, type FaqEntry } from './contracts';
import { seedFaqs } from './seed';
export interface FaqRepository { list(): Promise<FaqEntry[]> }
export const faqRepository: FaqRepository = {
  async list() {
    const production = process.env.APP_ENV === 'production' || (process.env.NODE_ENV === 'production' && !['local', 'test'].includes(process.env.APP_ENV ?? ''));
    if (production && !process.env.DATABASE_URL) throw new Error('FAQ database required');
    const db = getDb();
    if (!db) return catalogSchema.parse(seedFaqs);
    const rows = await db.select({ id: faqEntries.id, category: faqEntries.category, question: faqEntries.question, aliases: faqEntries.aliases, answer: faqEntries.answer }).from(faqEntries).where(eq(faqEntries.active, true)).orderBy(asc(faqEntries.id)).limit(51);
    return catalogSchema.parse(rows);
  },
};
