import { boolean, jsonb, pgTable, text } from 'drizzle-orm/pg-core';
export const faqEntries = pgTable('faq_entries', {
  id: text('id').primaryKey(), category: text('category').notNull(),
  question: text('question').notNull(), aliases: jsonb('aliases').$type<string[]>().notNull().default([]),
  answer: text('answer').notNull(), active: boolean('active').notNull().default(true),
});
