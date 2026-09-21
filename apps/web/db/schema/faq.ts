import {
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
} from 'drizzle-orm/pg-core';

export const faqEntries = pgTable(
  'faq_entries',
  {
    id: text('id').primaryKey(),
    slug: text('slug').notNull(),
    locale: text('locale').notNull().default('ko'),
    category: text('category').notNull(),
    question: text('question').notNull(),
    answer: text('answer').notNull(),
    aliases: jsonb('aliases').$type<string[]>().notNull().default([]),
    active: boolean('active').notNull().default(true),
    displayOrder: integer('display_order').notNull().default(0),
    createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow().notNull(),
  },
  table => ({
    localeSlugUnique: uniqueIndex('faq_entries_locale_slug_idx').on(table.locale, table.slug),
    activeOrder: index('faq_entries_active_order_idx').on(table.locale, table.active, table.displayOrder),
    categoryActive: index('faq_entries_category_active_idx').on(table.locale, table.category, table.active),
  }),
);
