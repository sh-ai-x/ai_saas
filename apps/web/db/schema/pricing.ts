import {
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

const timestamps = {
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
};

export const pricingPlans = pgTable(
  "pricing_plans",
  {
    id: text("id").primaryKey(),
    tenantId: text("tenant_id").notNull().default("platform"),
    code: text("code").notNull(),
    name: text("name").notNull(),
    description: text("description").notNull().default(""),
    billingMode: text("billing_mode").notNull().default("subscription"),
    active: boolean("active").notNull().default(true),
    isDefault: boolean("is_default").notNull().default(false),
    displayOrder: integer("display_order").notNull().default(0),
    features: jsonb("features").$type<string[]>().notNull().default([]),
    quotas: jsonb("quotas").$type<Record<string, number>>().notNull().default({}),
    ...timestamps,
  },
  (table) => ({
    tenantCode: uniqueIndex("pricing_plans_tenant_code_idx").on(table.tenantId, table.code),
    activeOrder: index("pricing_plans_active_order_idx").on(table.tenantId, table.active, table.displayOrder),
  }),
);

export const pricingCatalogSettings = pgTable("pricing_catalog_settings", {
  id: text("id").primaryKey(),
  billingMode: text("billing_mode").notNull().default("subscription"),
  currency: text("currency").notNull().default("USD"),
  updatedBy: text("updated_by"),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const pricingOptions = pgTable(
  "pricing_options",
  {
    id: text("id").primaryKey(),
    planId: text("plan_id").notNull().references(() => pricingPlans.id, { onDelete: "cascade" }),
    mode: text("mode").notNull(),
    interval: text("interval").notNull(),
    provider: text("provider").notNull(),
    currency: text("currency").notNull().default("USD"),
    amountMinor: integer("amount_minor").notNull(),
    compareAtAmountMinor: integer("compare_at_amount_minor"),
    providerProductRef: text("provider_product_ref"),
    providerPriceRef: text("provider_price_ref"),
    active: boolean("active").notNull().default(true),
    metadata: jsonb("metadata").$type<Record<string, unknown>>().notNull().default({}),
    ...timestamps,
  },
  (table) => ({
    planModeIntervalProvider: uniqueIndex("pricing_options_identity_idx").on(
      table.planId,
      table.mode,
      table.interval,
      table.provider,
    ),
    planActive: index("pricing_options_plan_active_idx").on(table.planId, table.active),
  }),
);

export const paymentProviderSettings = pgTable(
  "payment_provider_settings",
  {
    id: text("id").primaryKey(),
    provider: text("provider").notNull(),
    enabled: boolean("enabled").notNull().default(false),
    sandbox: boolean("sandbox").notNull().default(true),
    publicConfig: jsonb("public_config").$type<Record<string, unknown>>().notNull().default({}),
    secretRef: text("secret_ref"),
    ...timestamps,
  },
  (table) => ({
    providerUnique: uniqueIndex("payment_provider_settings_provider_idx").on(table.provider),
  }),
);

export const paymentOrders = pgTable(
  "payment_orders",
  {
    id: text("id").primaryKey(),
    tenantId: text("tenant_id").notNull(),
    userId: text("user_id"),
    pricingOptionId: text("pricing_option_id").notNull().references(() => pricingOptions.id),
    provider: text("provider").notNull(),
    mode: text("mode").notNull(),
    status: text("status").notNull().default("pending"),
    externalOrderRef: text("external_order_ref"),
    externalPaymentRef: text("external_payment_ref"),
    amountMinor: integer("amount_minor").notNull(),
    currency: text("currency").notNull(),
    idempotencyKey: text("idempotency_key").notNull(),
    metadata: jsonb("metadata").$type<Record<string, unknown>>().notNull().default({}),
    ...timestamps,
  },
  (table) => ({
    idempotencyUnique: uniqueIndex("payment_orders_idempotency_idx").on(table.idempotencyKey),
    externalOrderUnique: uniqueIndex("payment_orders_external_order_idx").on(table.provider, table.externalOrderRef),
    tenantStatus: index("payment_orders_tenant_status_idx").on(table.tenantId, table.status),
  }),
);

export const subscriptions = pgTable(
  "subscriptions",
  {
    id: text("id").primaryKey(),
    tenantId: text("tenant_id").notNull(),
    userId: text("user_id"),
    pricingOptionId: text("pricing_option_id").notNull().references(() => pricingOptions.id),
    provider: text("provider").notNull(),
    externalCustomerRef: text("external_customer_ref"),
    externalSubscriptionRef: text("external_subscription_ref"),
    status: text("status").notNull().default("pending"),
    providerStatus: text("provider_status"),
    currentPeriodStart: timestamp("current_period_start", { withTimezone: true }),
    currentPeriodEnd: timestamp("current_period_end", { withTimezone: true }),
    cancelAtPeriodEnd: boolean("cancel_at_period_end").notNull().default(false),
    cancelRequestedAt: timestamp("cancel_requested_at", { withTimezone: true }),
    canceledAt: timestamp("canceled_at", { withTimezone: true }),
    endedAt: timestamp("ended_at", { withTimezone: true }),
    nextBillingAt: timestamp("next_billing_at", { withTimezone: true }),
    graceUntil: timestamp("grace_until", { withTimezone: true }),
    lastPaymentAt: timestamp("last_payment_at", { withTimezone: true }),
    lastPaymentError: text("last_payment_error"),
    version: integer("version").notNull().default(1),
    metadata: jsonb("metadata").$type<Record<string, unknown>>().notNull().default({}),
    ...timestamps,
  },
  (table) => ({
    externalSubscriptionUnique: uniqueIndex("subscriptions_external_ref_idx").on(table.provider, table.externalSubscriptionRef),
    tenantStatus: index("subscriptions_tenant_status_idx").on(table.tenantId, table.status),
  }),
);

export const subscriptionTransitions = pgTable(
  "subscription_transitions",
  {
    id: text("id").primaryKey(),
    subscriptionId: text("subscription_id").notNull().references(() => subscriptions.id, { onDelete: "cascade" }),
    userId: text("user_id"),
    fromStatus: text("from_status"),
    toStatus: text("to_status").notNull(),
    eventType: text("event_type").notNull(),
    reason: text("reason"),
    idempotencyKey: text("idempotency_key").notNull(),
    occurredAt: timestamp("occurred_at", { withTimezone: true }).notNull(),
    metadata: jsonb("metadata").$type<Record<string, unknown>>().notNull().default({}),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => ({
    idempotencyUnique: uniqueIndex("subscription_transitions_idempotency_idx").on(table.idempotencyKey),
    subscriptionOccurred: index("subscription_transitions_subscription_idx").on(table.subscriptionId, table.occurredAt),
    userOccurred: index("subscription_transitions_user_idx").on(table.userId, table.occurredAt),
  }),
);

export const tokenUsagePeriods = pgTable(
  "token_usage_periods",
  {
    id: text("id").primaryKey(),
    userId: text("user_id").notNull(),
    subscriptionId: text("subscription_id"),
    planId: text("plan_id").notNull(),
    periodStart: timestamp("period_start", { withTimezone: true }).notNull(),
    periodEnd: timestamp("period_end", { withTimezone: true }).notNull(),
    inputLimit: integer("input_limit").notNull().default(0),
    outputLimit: integer("output_limit").notNull().default(0),
    totalLimit: integer("total_limit").notNull().default(0),
    inputUsed: integer("input_used").notNull().default(0),
    outputUsed: integer("output_used").notNull().default(0),
    totalUsed: integer("total_used").notNull().default(0),
    status: text("status").notNull().default("active"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => ({
    userPeriodUnique: uniqueIndex("token_usage_periods_user_period_idx").on(table.userId, table.periodStart),
    subscriptionPeriod: index("token_usage_periods_subscription_idx").on(table.subscriptionId, table.periodStart),
  }),
);

export const tokenUsageEntries = pgTable(
  "token_usage_entries",
  {
    id: text("id").primaryKey(),
    userId: text("user_id").notNull(),
    subscriptionId: text("subscription_id"),
    periodId: text("period_id"),
    runId: text("run_id"),
    requestId: text("request_id"),
    inputTokens: integer("input_tokens").notNull().default(0),
    outputTokens: integer("output_tokens").notNull().default(0),
    totalTokens: integer("total_tokens").notNull().default(0),
    status: text("status").notNull().default("committed"),
    idempotencyKey: text("idempotency_key").notNull(),
    metadata: jsonb("metadata").$type<Record<string, unknown>>().notNull().default({}),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => ({
    idempotencyUnique: uniqueIndex("token_usage_entries_idempotency_idx").on(table.idempotencyKey),
    userCreated: index("token_usage_entries_user_created_idx").on(table.userId, table.createdAt),
    periodCreated: index("token_usage_entries_period_created_idx").on(table.periodId, table.createdAt),
  }),
);

export const billingEvents = pgTable(
  "billing_events",
  {
    id: text("id").primaryKey(),
    provider: text("provider").notNull(),
    externalEventId: text("external_event_id").notNull(),
    rawBodyHash: text("raw_body_hash").notNull(),
    normalizedPayload: jsonb("normalized_payload").$type<Record<string, unknown>>().notNull().default({}),
    verificationStatus: text("verification_status").notNull().default("received"),
    eventType: text("event_type"),
    aggregateId: text("aggregate_id"),
    occurredAt: timestamp("occurred_at", { withTimezone: true }),
    applied: boolean("applied").notNull().default(false),
    failureReason: text("failure_reason"),
    payloadVersion: integer("payload_version").notNull().default(1),
    processedAt: timestamp("processed_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => ({
    providerEventUnique: uniqueIndex("billing_events_provider_event_idx").on(table.provider, table.externalEventId),
  }),
);

export const adminAuditEvents = pgTable(
  "admin_audit_events",
  {
    id: text("id").primaryKey(),
    actorUserId: text("actor_user_id").notNull(),
    action: text("action").notNull(),
    resourceType: text("resource_type").notNull(),
    resourceId: text("resource_id").notNull(),
    reason: text("reason").notNull(),
    beforeJson: jsonb("before_json").$type<Record<string, unknown> | null>(),
    afterJson: jsonb("after_json").$type<Record<string, unknown> | null>(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => ({
    resource: index("admin_audit_events_resource_idx").on(table.resourceType, table.resourceId, table.createdAt),
  }),
);
