import { and, asc, desc, eq, gt, inArray, lte, or, sql } from "drizzle-orm";

import { getDb, schema } from "@/db";
import { seededBillingMode, seededPricingCatalog, seededProviderSettings } from "./seed";
import type {
  BillingMode,
  PricingOption,
  PricingOptionInput,
  PricingPlan,
  PricingPlanInput,
  PricingPolicy,
  PricingProvider,
  PaymentOrder,
  SubscriptionRecord,
  ProviderSetting,
  SubscriptionSummary,
  TokenUsageSummary,
  AdminSubscriptionRow,
  SubscriptionStatus,
} from "./types";

const {
  adminAuditEvents,
  paymentOrders,
  paymentProviderSettings,
  pricingCatalogSettings,
  pricingOptions,
  pricingPlans,
  subscriptions,
  subscriptionTransitions,
  tokenUsagePeriods,
  tokenUsageEntries,
  users,
} = schema;

type LocalPricingState = {
  plans: PricingPlan[];
  providers: ProviderSetting[];
  billingMode: BillingMode;
  orders: PaymentOrder[];
  subscriptions: SubscriptionRecord[];
};

const globalState = globalThis as typeof globalThis & { __aiSaasPricingState?: LocalPricingState };
const localState: LocalPricingState = globalState.__aiSaasPricingState ??= {
  plans: clonePlans(seededPricingCatalog),
  providers: cloneProviders(seededProviderSettings),
  billingMode: seededBillingMode,
  orders: [],
  subscriptions: [],
};

function clonePlans(plans: PricingPlan[]) {
  return structuredClone(plans);
}

function cloneProviders(settings: ProviderSetting[]) {
  return structuredClone(settings);
}

function assertProductionDatabase() {
  if (!process.env.DATABASE_URL && process.env.APP_ENV === "production") {
    throw new Error("DATABASE_URL is required in production; local catalog fallback is disabled");
  }
}

function validateOption(option: PricingOptionInput) {
  if (option.mode === "one_time" && option.interval !== "one_time") {
    throw new Error("one_time options must use interval one_time");
  }
  if (option.mode === "subscription" && !["month", "year"].includes(option.interval)) {
    throw new Error("subscription options must use interval month or year");
  }
  if (!Number.isInteger(option.amountMinor) || option.amountMinor <= 0) {
    throw new Error("amountMinor must be a positive integer");
  }
}

function mapRows(
  plans: Array<typeof pricingPlans.$inferSelect>,
  options: Array<typeof pricingOptions.$inferSelect>,
): PricingPlan[] {
  return plans.map((plan) => ({
    id: plan.id,
    tenantId: plan.tenantId,
    code: plan.code,
    name: plan.name,
    description: plan.description,
    billingMode: plan.billingMode as BillingMode,
    active: plan.active,
    isDefault: plan.isDefault,
    displayOrder: plan.displayOrder,
    features: plan.features,
    quotas: plan.quotas,
    options: options.filter((option) => option.planId === plan.id).map((option) => ({
      id: option.id,
      planId: option.planId,
      mode: option.mode as PricingOption["mode"],
      interval: option.interval as PricingOption["interval"],
      provider: option.provider as PricingProvider,
      currency: option.currency,
      amountMinor: option.amountMinor,
      compareAtAmountMinor: option.compareAtAmountMinor,
      providerProductRef: option.providerProductRef,
      providerPriceRef: option.providerPriceRef,
      active: option.active,
    })),
  }));
}

export async function listPricingCatalog(activeOnly = false): Promise<PricingPlan[]> {
  assertProductionDatabase();
  const db = getDb();
  const billingMode = activeOnly ? (await getBillingPolicy()).billingMode : undefined;
  if (!db) {
    return clonePlans(localState.plans).filter((plan) => !activeOnly || (plan.active && plan.billingMode === billingMode)).map((plan) => ({
      ...plan,
      options: plan.options.filter((option) => !activeOnly || (option.active && option.mode === billingMode)),
    }));
  }

  const planPredicates = [eq(pricingPlans.tenantId, "platform")];
  if (activeOnly) {
    planPredicates.push(eq(pricingPlans.active, true), eq(pricingPlans.billingMode, billingMode ?? seededBillingMode));
  }
  const where = and(...planPredicates);
  const plans = await db.select().from(pricingPlans).where(where).orderBy(asc(pricingPlans.displayOrder));
  if (!plans.length) return [];
  const optionPredicates = [inArray(pricingOptions.planId, plans.map((plan) => plan.id))];
  if (activeOnly) optionPredicates.push(eq(pricingOptions.active, true), eq(pricingOptions.mode, billingMode ?? seededBillingMode));
  const options = await db.select().from(pricingOptions).where(and(...optionPredicates));
  return mapRows(plans, options);
}

export async function getBillingPolicy(): Promise<PricingPolicy> {
  const db = getDb();
  if (!db) return { id: "platform", billingMode: localState.billingMode, currency: "KRW", updatedBy: "local-seed" };
  const [row] = await db.select().from(pricingCatalogSettings).where(eq(pricingCatalogSettings.id, "platform")).limit(1);
  if (!row) return { id: "platform", billingMode: seededBillingMode, currency: "KRW", updatedBy: "migration-seed" };
  return { id: row.id, billingMode: row.billingMode as BillingMode, currency: row.currency, updatedBy: row.updatedBy };
}

export async function setBillingMode(billingMode: BillingMode, actorUserId = "local-admin", reason = "") {
  if (!["one_time", "subscription"].includes(billingMode)) throw new Error("billingMode must be one_time or subscription");
  if (!reason.trim()) throw new Error("reason is required for billing policy changes");
  const before = await getBillingPolicy();
  const db = getDb();
  if (!db) {
    localState.billingMode = billingMode;
    return { ...before, billingMode, updatedBy: actorUserId };
  }
  const values = { id: "platform", billingMode, currency: before.currency, updatedBy: actorUserId, updatedAt: new Date() };
  const [existing] = await db.select({ id: pricingCatalogSettings.id }).from(pricingCatalogSettings).where(eq(pricingCatalogSettings.id, "platform")).limit(1);
  if (existing) await db.update(pricingCatalogSettings).set(values).where(eq(pricingCatalogSettings.id, "platform"));
  else await db.insert(pricingCatalogSettings).values(values);
  await db.insert(adminAuditEvents).values(auditRow(actorUserId, "billing.policy.updated", "platform", before, values, reason));
  return getBillingPolicy();
}

export async function getPricingOption(optionId: string): Promise<PricingOption | null> {
  const catalog = await listPricingCatalog(false);
  for (const plan of catalog) {
    const option = plan.options.find((candidate) => candidate.id === optionId);
    if (option) return option;
  }
  return null;
}

export async function getPricingOffer(optionId: string): Promise<{ plan: PricingPlan; option: PricingOption } | null> {
  const catalog = await listPricingCatalog(false);
  for (const plan of catalog) {
    const option = plan.options.find((candidate) => candidate.id === optionId);
    if (option) return { plan, option };
  }
  return null;
}

function mapPaymentOrder(row: typeof paymentOrders.$inferSelect): PaymentOrder {
  return {
    id: row.id,
    tenantId: row.tenantId,
    userId: row.userId,
    pricingOptionId: row.pricingOptionId,
    provider: row.provider as PricingProvider,
    mode: row.mode as PaymentOrder["mode"],
    status: row.status as PaymentOrder["status"],
    externalOrderRef: row.externalOrderRef,
    externalPaymentRef: row.externalPaymentRef,
    amountMinor: row.amountMinor,
    currency: row.currency,
    idempotencyKey: row.idempotencyKey,
    metadata: row.metadata,
  };
}

function mapSubscription(row: typeof subscriptions.$inferSelect): SubscriptionRecord {
  return {
    id: row.id,
    tenantId: row.tenantId,
    userId: row.userId,
    pricingOptionId: row.pricingOptionId,
    provider: row.provider as "toss",
    externalCustomerRef: row.externalCustomerRef ?? "",
    externalSubscriptionRef: row.externalSubscriptionRef ?? "",
    status: row.status as SubscriptionStatus,
    providerStatus: row.providerStatus,
    currentPeriodStart: row.currentPeriodStart,
    currentPeriodEnd: row.currentPeriodEnd,
    cancelAtPeriodEnd: row.cancelAtPeriodEnd,
    cancelRequestedAt: row.cancelRequestedAt,
    canceledAt: row.canceledAt,
    endedAt: row.endedAt,
    nextBillingAt: row.nextBillingAt,
    graceUntil: row.graceUntil,
    lastPaymentAt: row.lastPaymentAt,
    lastPaymentError: row.lastPaymentError,
    version: row.version,
    metadata: row.metadata,
  };
}

const FREE_USAGE_START = new Date(0);
const FREE_USAGE_END = new Date("9999-12-31T23:59:59.999Z");

function quotaValue(plan: PricingPlan | null, keys: string[], fallback = 0) {
  for (const key of keys) {
    const value = plan?.quotas?.[key];
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) return Math.floor(value);
  }
  return fallback;
}

function emptyUsage(plan: PricingPlan | null, start = FREE_USAGE_START, end = FREE_USAGE_END): TokenUsageSummary {
  const inputLimit = quotaValue(plan, ["monthlyInputTokens", "monthly_input_tokens", "inputTokens"], 0);
  const outputLimit = quotaValue(plan, ["monthlyOutputTokens", "monthly_output_tokens", "outputTokens"], 0);
  const totalLimit = quotaValue(plan, ["monthlyTokens", "monthly_tokens", "totalTokens"], inputLimit + outputLimit);
  return {
    inputLimit,
    outputLimit,
    totalLimit,
    inputUsed: 0,
    outputUsed: 0,
    totalUsed: 0,
    inputRemaining: inputLimit,
    outputRemaining: outputLimit,
    totalRemaining: totalLimit,
    periodStart: start,
    periodEnd: end,
  };
}

function usageFromRow(row: typeof tokenUsagePeriods.$inferSelect, plan: PricingPlan | null): TokenUsageSummary {
  return {
    inputLimit: row.inputLimit,
    outputLimit: row.outputLimit,
    totalLimit: row.totalLimit,
    inputUsed: row.inputUsed,
    outputUsed: row.outputUsed,
    totalUsed: row.totalUsed,
    inputRemaining: Math.max(0, row.inputLimit - row.inputUsed),
    outputRemaining: Math.max(0, row.outputLimit - row.outputUsed),
    totalRemaining: Math.max(0, row.totalLimit - row.totalUsed),
    periodStart: row.periodStart,
    periodEnd: row.periodEnd,
  };
}

function localUsage(subscription: SubscriptionRecord | null, plan: PricingPlan | null): TokenUsageSummary {
  return emptyUsage(plan, subscription?.currentPeriodStart ?? FREE_USAGE_START, subscription?.currentPeriodEnd ?? FREE_USAGE_END);
}

export async function createPaymentOrder(input: {
  id: string;
  tenantId: string;
  userId?: string | null;
  option: PricingOption;
  idempotencyKey: string;
  metadata?: Record<string, unknown>;
}): Promise<PaymentOrder> {
  const row: PaymentOrder = {
    id: input.id,
    tenantId: input.tenantId,
    userId: input.userId ?? null,
    pricingOptionId: input.option.id,
    provider: input.option.provider,
    mode: input.option.mode,
    status: "pending",
    externalOrderRef: input.id,
    externalPaymentRef: null,
    amountMinor: input.option.amountMinor,
    currency: input.option.currency.toUpperCase(),
    idempotencyKey: input.idempotencyKey,
    metadata: input.metadata ?? {},
  };
  const db = getDb();
  if (!db) {
    const existing = localState.orders.find((order) => order.idempotencyKey === row.idempotencyKey);
    if (existing) return structuredClone(existing);
    localState.orders.push(row);
    return structuredClone(row);
  }
  const [existing] = await db.select().from(paymentOrders).where(eq(paymentOrders.idempotencyKey, row.idempotencyKey)).limit(1);
  if (existing) return mapPaymentOrder(existing);
  await db.insert(paymentOrders).values({
    id: row.id,
    tenantId: row.tenantId,
    userId: row.userId,
    pricingOptionId: row.pricingOptionId,
    provider: row.provider,
    mode: row.mode,
    status: row.status,
    externalOrderRef: row.externalOrderRef,
    externalPaymentRef: row.externalPaymentRef,
    amountMinor: row.amountMinor,
    currency: row.currency,
    idempotencyKey: row.idempotencyKey,
    metadata: row.metadata,
  });
  return row;
}

export async function getPaymentOrder(orderId: string): Promise<PaymentOrder | null> {
  const db = getDb();
  if (!db) return structuredClone(localState.orders.find((order) => order.id === orderId) ?? null);
  const [row] = await db.select().from(paymentOrders).where(eq(paymentOrders.id, orderId)).limit(1);
  return row ? mapPaymentOrder(row) : null;
}

export async function getPaymentOrderByCustomerKey(customerKey: string): Promise<PaymentOrder | null> {
  const db = getDb();
  if (!db) return structuredClone(localState.orders.find((order) => order.metadata.customerKey === customerKey) ?? null);
  const [row] = await db.select().from(paymentOrders).where(and(
    eq(paymentOrders.provider, "toss"),
    sql`${paymentOrders.metadata}->>'customerKey' = ${customerKey}`,
  )).orderBy(desc(paymentOrders.createdAt)).limit(1);
  return row ? mapPaymentOrder(row) : null;
}

export async function updatePaymentOrder(
  orderId: string,
  patch: Partial<Pick<PaymentOrder, "status" | "externalPaymentRef" | "metadata">>,
): Promise<PaymentOrder | null> {
  const db = getDb();
  if (!db) {
    const current = localState.orders.find((order) => order.id === orderId);
    if (!current) return null;
    Object.assign(current, patch);
    return structuredClone(current);
  }
  await db.update(paymentOrders).set({ ...patch, updatedAt: new Date() }).where(eq(paymentOrders.id, orderId));
  return getPaymentOrder(orderId);
}

export async function recordTossSubscription(input: {
  order: PaymentOrder;
  customerKey: string;
  billingKey: string;
}): Promise<void> {
  const db = getDb();
  const offer = await getPricingOffer(input.order.pricingOptionId);
  const periodStart = new Date();
  const periodEnd = new Date(periodStart);
  if (input.order.metadata.interval === "year") periodEnd.setUTCFullYear(periodEnd.getUTCFullYear() + 1);
  else periodEnd.setUTCMonth(periodEnd.getUTCMonth() + 1);
  const values: SubscriptionRecord = {
    id: `subscription-${input.order.id}`,
    tenantId: input.order.tenantId,
    userId: input.order.userId,
    pricingOptionId: input.order.pricingOptionId,
    provider: "toss",
    externalCustomerRef: input.customerKey,
    externalSubscriptionRef: input.order.id,
    status: "active",
    providerStatus: "DONE",
    currentPeriodStart: periodStart,
    currentPeriodEnd: periodEnd,
    cancelAtPeriodEnd: false,
    nextBillingAt: periodEnd,
    lastPaymentAt: periodStart,
    version: 1,
    metadata: { billingKey: input.billingKey, interval: input.order.metadata.interval },
  };
  if (!db) {
    const index = localState.subscriptions.findIndex((subscription) => subscription.id === values.id);
    if (index === -1) {
      localState.subscriptions.push(structuredClone(values));
      if (values.userId) globalUsage.set(values.userId, emptyUsage(offer?.plan ?? null, periodStart, periodEnd));
      pushLocalTransition(values.id, null, "active", "subscription.started");
    }
    return;
  }
  const [existing] = await db.select({ id: subscriptions.id }).from(subscriptions).where(eq(subscriptions.id, values.id)).limit(1);
  if (existing) return;
  await db.transaction(async (tx) => {
    await tx.insert(subscriptions).values(values);
    if (values.userId) {
      const usage = emptyUsage(offer?.plan ?? null, periodStart, periodEnd);
      await tx.insert(tokenUsagePeriods).values({
        id: `usage-period-${values.id}-${periodStart.getTime()}`,
        userId: values.userId,
        subscriptionId: values.id,
        planId: offer?.plan.id ?? "unknown",
        periodStart,
        periodEnd,
        inputLimit: usage.inputLimit,
        outputLimit: usage.outputLimit,
        totalLimit: usage.totalLimit,
        inputUsed: 0,
        outputUsed: 0,
        totalUsed: 0,
        status: "active",
      }).onConflictDoNothing();
    }
    await tx.insert(subscriptionTransitions).values({
      id: `transition-${input.order.id}`,
      subscriptionId: values.id,
      userId: values.userId,
      fromStatus: null,
      toStatus: "active",
      eventType: "subscription.started",
      reason: "Toss first recurring charge succeeded",
      idempotencyKey: transitionKey(values.id, "started", input.order.id),
      occurredAt: periodStart,
      metadata: { provider: "toss", paymentOrderId: input.order.id },
    }).onConflictDoNothing({ target: subscriptionTransitions.idempotencyKey });
  });
}

export async function listDueTossSubscriptions(now = new Date()): Promise<SubscriptionRecord[]> {
  const db = getDb();
  if (!db) return localState.subscriptions.filter((subscription) => {
    if (subscription.provider !== "toss" || subscription.cancelAtPeriodEnd || !subscription.nextBillingAt || subscription.nextBillingAt > now) return false;
    return subscription.status === "active" || (subscription.status === "past_due" && Boolean(subscription.graceUntil && subscription.graceUntil > now));
  }).map((subscription) => structuredClone(subscription));
  const rows = await db.select().from(subscriptions).where(and(
    eq(subscriptions.provider, "toss"),
    eq(subscriptions.cancelAtPeriodEnd, false),
    lte(subscriptions.nextBillingAt, now),
    or(
      eq(subscriptions.status, "active"),
      and(eq(subscriptions.status, "past_due"), gt(subscriptions.graceUntil, now)),
    ),
  )).orderBy(asc(subscriptions.nextBillingAt));
  return rows.map(mapSubscription);
}

export async function expireEndedSubscriptions(now = new Date()): Promise<number> {
  const db = getDb();
  if (!db) {
    let count = 0;
    for (const subscription of localState.subscriptions) {
      if ((subscription.status === "cancel_scheduled" && Boolean(subscription.currentPeriodEnd && subscription.currentPeriodEnd <= now))
        || (subscription.status === "past_due" && Boolean(subscription.graceUntil && subscription.graceUntil <= now))) {
        const fromStatus = subscription.status;
        subscription.status = "expired";
        subscription.endedAt = now;
        subscription.canceledAt = now;
        subscription.cancelAtPeriodEnd = false;
        subscription.version = (subscription.version ?? 1) + 1;
        pushLocalTransition(subscription.id, fromStatus, "expired", "subscription.expired");
        count += 1;
      }
    }
    return count;
  }
  const rows = await db.select().from(subscriptions).where(or(
    and(eq(subscriptions.status, "cancel_scheduled"), lte(subscriptions.currentPeriodEnd, now)),
    and(eq(subscriptions.status, "past_due"), lte(subscriptions.graceUntil, now)),
  ));
  for (const row of rows) {
    await db.transaction(async (tx) => {
      const [updated] = await tx.update(subscriptions).set({ status: "expired", endedAt: now, canceledAt: now, cancelAtPeriodEnd: false, version: row.version + 1, updatedAt: now }).where(and(eq(subscriptions.id, row.id), eq(subscriptions.version, row.version))).returning({ id: subscriptions.id });
      if (!updated) return;
      await tx.insert(subscriptionTransitions).values({
        id: `transition-${crypto.randomUUID()}`,
        subscriptionId: row.id,
        userId: row.userId,
        fromStatus: row.status,
        toStatus: "expired",
        eventType: "subscription.expired",
        reason: "Current period ended without renewal",
        idempotencyKey: transitionKey(row.id, "expired", String(row.version)),
        occurredAt: now,
        metadata: {},
      }).onConflictDoNothing({ target: subscriptionTransitions.idempotencyKey });
    });
  }
  return rows.length;
}

export async function recordTossRenewal(input: {
  subscription: SubscriptionRecord;
  paymentOrder: PaymentOrder;
  paymentRef: string;
}): Promise<SubscriptionRecord> {
  const offer = await getPricingOffer(input.subscription.pricingOptionId);
  const periodEnd = input.subscription.currentPeriodEnd;
  if (!periodEnd) throw new Error("subscription renewal period end is missing");
  const start = periodEnd > new Date() ? periodEnd : new Date();
  const end = new Date(start);
  if (offer?.option.interval === "year") end.setUTCFullYear(end.getUTCFullYear() + 1);
  else end.setUTCMonth(end.getUTCMonth() + 1);
  const next: SubscriptionRecord = {
    ...input.subscription,
    status: "active",
    providerStatus: "DONE",
    currentPeriodStart: start,
    currentPeriodEnd: end,
    nextBillingAt: end,
    lastPaymentAt: new Date(),
    lastPaymentError: null,
    graceUntil: null,
    version: (input.subscription.version ?? 1) + 1,
  };
  const db = getDb();
  if (!db) {
    const index = localState.subscriptions.findIndex((subscription) => subscription.id === input.subscription.id);
    if (index < 0) throw new Error("subscription renewal target was not found");
    const current = localState.subscriptions[index];
    if ((current.version ?? 1) !== (input.subscription.version ?? 1)) throw new Error("subscription renewal version conflict");
    localState.subscriptions[index] = structuredClone(next);
    if (next.userId) globalUsage.set(next.userId, emptyUsage(offer?.plan ?? null, start, end));
    pushLocalTransition(next.id, input.subscription.status, "active", "subscription.renewed");
    return structuredClone(next);
  }
  await db.transaction(async (tx) => {
    const [updated] = await tx.update(subscriptions).set({
      status: next.status,
      providerStatus: next.providerStatus,
      currentPeriodStart: next.currentPeriodStart,
      currentPeriodEnd: next.currentPeriodEnd,
      nextBillingAt: next.nextBillingAt,
      lastPaymentAt: next.lastPaymentAt,
      lastPaymentError: null,
      graceUntil: null,
      version: next.version,
      updatedAt: new Date(),
    }).where(and(eq(subscriptions.id, next.id), eq(subscriptions.version, input.subscription.version ?? 1))).returning({ id: subscriptions.id });
    if (!updated) throw new Error("subscription renewal version conflict");
    if (next.userId) {
      const usage = emptyUsage(offer?.plan ?? null, start, end);
      await tx.update(tokenUsagePeriods).set({ status: "closed" }).where(and(
        eq(tokenUsagePeriods.subscriptionId, next.id),
        eq(tokenUsagePeriods.status, "active"),
      ));
      await tx.insert(tokenUsagePeriods).values({
        id: `usage-period-${next.id}-${start.getTime()}`,
        userId: next.userId,
        subscriptionId: next.id,
        planId: offer?.plan.id ?? "unknown",
        periodStart: start,
        periodEnd: end,
        inputLimit: usage.inputLimit,
        outputLimit: usage.outputLimit,
        totalLimit: usage.totalLimit,
        inputUsed: 0,
        outputUsed: 0,
        totalUsed: 0,
        status: "active",
      }).onConflictDoNothing();
    }
    await tx.insert(subscriptionTransitions).values({
      id: `transition-${crypto.randomUUID()}`,
      subscriptionId: next.id,
      userId: next.userId,
      fromStatus: input.subscription.status,
      toStatus: "active",
      eventType: "subscription.renewed",
      reason: "Toss recurring charge succeeded",
      idempotencyKey: transitionKey(next.id, "renewed", input.paymentOrder.id),
      occurredAt: new Date(),
      metadata: { paymentOrderId: input.paymentOrder.id, paymentRef: input.paymentRef },
    }).onConflictDoNothing({ target: subscriptionTransitions.idempotencyKey });
  });
  return next;
}

export async function recordTossRenewalFailure(subscription: SubscriptionRecord, message: string, graceHours = 72): Promise<SubscriptionRecord> {
  const now = new Date();
  const graceUntil = subscription.graceUntil && subscription.graceUntil > now
    ? subscription.graceUntil
    : new Date(now.getTime() + graceHours * 60 * 60 * 1000);
  const retryAt = new Date(Math.min(now.getTime() + 24 * 60 * 60 * 1000, graceUntil.getTime() - 60_000));
  const next = { ...subscription, status: "past_due" as const, providerStatus: "FAILED", graceUntil, nextBillingAt: retryAt, lastPaymentError: message, version: (subscription.version ?? 1) + 1 };
  const db = getDb();
  if (!db) {
    const index = localState.subscriptions.findIndex((candidate) => candidate.id === subscription.id);
    if (index < 0) throw new Error("subscription renewal failure target was not found");
    const current = localState.subscriptions[index];
    if ((current.version ?? 1) !== (subscription.version ?? 1)) throw new Error("subscription renewal failure version conflict");
    localState.subscriptions[index] = structuredClone(next);
    pushLocalTransition(next.id, subscription.status, "past_due", "subscription.renewal_failed");
    return structuredClone(next);
  }
  await db.transaction(async (tx) => {
    const [updated] = await tx.update(subscriptions).set({ status: "past_due", providerStatus: "FAILED", graceUntil, nextBillingAt: retryAt, lastPaymentError: message, version: next.version, updatedAt: now }).where(and(eq(subscriptions.id, subscription.id), eq(subscriptions.version, subscription.version ?? 1))).returning({ id: subscriptions.id });
    if (!updated) throw new Error("subscription renewal failure version conflict");
    await tx.insert(subscriptionTransitions).values({
      id: `transition-${crypto.randomUUID()}`,
      subscriptionId: subscription.id,
      userId: subscription.userId,
      fromStatus: subscription.status,
      toStatus: "past_due",
      eventType: "subscription.renewal_failed",
      reason: message,
      idempotencyKey: transitionKey(subscription.id, "renewal_failed", String(subscription.version ?? 1)),
      occurredAt: new Date(),
      metadata: {},
    }).onConflictDoNothing({ target: subscriptionTransitions.idempotencyKey });
  });
  return next;
}

type LocalTransition = { id: string; fromStatus: string | null; toStatus: string; eventType: string; occurredAt: Date };

function transitionKey(subscriptionId: string, eventType: string, identity: string) {
  return `subscription:${subscriptionId}:${eventType}:${identity}`;
}

const globalTransitions = ((globalThis as typeof globalThis & { __aiSaasSubscriptionTransitions?: Map<string, LocalTransition[]> }).__aiSaasSubscriptionTransitions ??= new Map());
const globalUsage = ((globalThis as typeof globalThis & { __aiSaasTokenUsage?: Map<string, TokenUsageSummary> }).__aiSaasTokenUsage ??= new Map());
const globalUsageKeys = ((globalThis as typeof globalThis & { __aiSaasTokenUsageKeys?: Map<string, Set<string>> }).__aiSaasTokenUsageKeys ??= new Map());

function pushLocalTransition(subscriptionId: string, fromStatus: string | null, toStatus: string, eventType: string) {
  const current = globalTransitions.get(subscriptionId) ?? [];
  current.unshift({ id: `transition-${crypto.randomUUID()}`, fromStatus, toStatus, eventType, occurredAt: new Date() });
  globalTransitions.set(subscriptionId, current.slice(0, 20));
}

function accessFor(subscription: SubscriptionRecord | null): SubscriptionSummary["access"] {
  if (!subscription) return "free";
  if (subscription.status === "past_due") return "grace";
  if (subscription.status === "expired" || subscription.status === "canceled") return "expired";
  if (!subscription.currentPeriodEnd) return "free";
  if (subscription.currentPeriodEnd.getTime() <= Date.now()) return "expired";
  return "paid";
}

export async function getSubscriptionSummary(userId: string): Promise<SubscriptionSummary> {
  const db = getDb();
  if (!db) {
    const subscription = localState.subscriptions
      .filter((candidate) => candidate.userId === userId)
      .sort((a, b) => (b.currentPeriodEnd?.getTime() ?? 0) - (a.currentPeriodEnd?.getTime() ?? 0))[0] ?? null;
    const offer = subscription ? await getPricingOffer(subscription.pricingOptionId) : null;
    return {
      subscription,
      plan: offer?.plan ?? null,
      usage: globalUsage.get(userId) ?? localUsage(subscription, offer?.plan ?? null),
      access: accessFor(subscription),
      transitions: subscription ? (globalTransitions.get(subscription.id) ?? []) : [],
    };
  }

  const [row] = await db.select().from(subscriptions).where(eq(subscriptions.userId, userId)).orderBy(desc(subscriptions.updatedAt)).limit(1);
  const subscription = row ? mapSubscription(row) : null;
  const offer = subscription ? await getPricingOffer(subscription.pricingOptionId) : null;
  let usage = localUsage(subscription, offer?.plan ?? null);
  if (subscription) {
    const [period] = await db.select().from(tokenUsagePeriods)
      .where(eq(tokenUsagePeriods.userId, userId))
      .orderBy(desc(tokenUsagePeriods.periodStart)).limit(1);
    if (period) usage = usageFromRow(period, offer?.plan ?? null);
  }
  const transitions = subscription
    ? (await db.select().from(subscriptionTransitions)
      .where(eq(subscriptionTransitions.subscriptionId, subscription.id))
      .orderBy(desc(subscriptionTransitions.occurredAt)).limit(20)).map((transition) => ({
        id: transition.id,
        fromStatus: transition.fromStatus,
        toStatus: transition.toStatus,
        eventType: transition.eventType,
        occurredAt: transition.occurredAt,
      }))
    : [];
  return {
    subscription,
    plan: offer?.plan ?? null,
    usage,
    access: accessFor(subscription),
    transitions,
  };
}

export async function cancelSubscriptionAtPeriodEnd(userId: string, idempotencyKey: string): Promise<SubscriptionRecord | null> {
  if (!idempotencyKey.trim()) throw new Error("idempotencyKey is required");
  const now = new Date();
  const db = getDb();
  if (!db) {
    const subscription = localState.subscriptions.find((candidate) => candidate.userId === userId && ["active", "past_due", "cancel_scheduled"].includes(candidate.status));
    if (!subscription) return null;
    if (subscription.cancelAtPeriodEnd) return structuredClone(subscription);
    const fromStatus = subscription.status;
    subscription.cancelAtPeriodEnd = true;
    subscription.status = "cancel_scheduled";
    subscription.cancelRequestedAt = now;
    subscription.version = (subscription.version ?? 1) + 1;
    pushLocalTransition(subscription.id, fromStatus, "cancel_scheduled", "subscription.cancel_scheduled");
    return structuredClone(subscription);
  }
  const [current] = await db.select().from(subscriptions).where(eq(subscriptions.userId, userId)).orderBy(desc(subscriptions.updatedAt)).limit(1);
  if (!current) return null;
  if (!["pending", "active", "cancel_scheduled", "past_due"].includes(current.status)) return null;
  if (current.cancelAtPeriodEnd) return mapSubscription(current);
  await db.transaction(async (tx) => {
    const [updated] = await tx.update(subscriptions).set({
      status: "cancel_scheduled",
      cancelAtPeriodEnd: true,
      cancelRequestedAt: now,
      version: current.version + 1,
      updatedAt: now,
    }).where(and(eq(subscriptions.id, current.id), eq(subscriptions.version, current.version))).returning({ id: subscriptions.id });
    if (!updated) throw new Error("subscription cancellation version conflict");
    await tx.insert(subscriptionTransitions).values({
      id: `transition-${crypto.randomUUID()}`,
      subscriptionId: current.id,
      userId,
      fromStatus: current.status,
      toStatus: "cancel_scheduled",
      eventType: "subscription.cancel_scheduled",
      reason: "User requested cancellation at period end",
      idempotencyKey: transitionKey(current.id, "cancel_scheduled", idempotencyKey),
      occurredAt: now,
      metadata: { currentPeriodEnd: current.currentPeriodEnd?.toISOString() ?? null },
    }).onConflictDoNothing({ target: subscriptionTransitions.idempotencyKey });
  });
  const updated = await db.select().from(subscriptions).where(eq(subscriptions.id, current.id)).limit(1);
  return updated[0] ? mapSubscription(updated[0]) : null;
}

export async function resumeSubscription(userId: string, idempotencyKey: string): Promise<SubscriptionRecord | null> {
  if (!idempotencyKey.trim()) throw new Error("idempotencyKey is required");
  const now = new Date();
  const db = getDb();
  if (!db) {
    const subscription = localState.subscriptions.find((candidate) => candidate.userId === userId && candidate.cancelAtPeriodEnd);
    if (!subscription) return null;
    if (!subscription.currentPeriodEnd || subscription.currentPeriodEnd.getTime() <= now.getTime()) throw new Error("subscription period has ended");
    subscription.cancelAtPeriodEnd = false;
    subscription.status = "active";
    subscription.cancelRequestedAt = null;
    subscription.version = (subscription.version ?? 1) + 1;
    pushLocalTransition(subscription.id, "cancel_scheduled", "active", "subscription.cancel_resumed");
    return structuredClone(subscription);
  }
  const [current] = await db.select().from(subscriptions).where(eq(subscriptions.userId, userId)).orderBy(desc(subscriptions.updatedAt)).limit(1);
  if (!current) return null;
  if (!current.cancelAtPeriodEnd) return mapSubscription(current);
  if (!current.currentPeriodEnd || current.currentPeriodEnd.getTime() <= now.getTime()) throw new Error("subscription period has ended");
  await db.transaction(async (tx) => {
    const [updated] = await tx.update(subscriptions).set({
      status: "active",
      cancelAtPeriodEnd: false,
      cancelRequestedAt: null,
      version: current.version + 1,
      updatedAt: now,
    }).where(and(eq(subscriptions.id, current.id), eq(subscriptions.version, current.version))).returning({ id: subscriptions.id });
    if (!updated) throw new Error("subscription resume version conflict");
    await tx.insert(subscriptionTransitions).values({
      id: `transition-${crypto.randomUUID()}`,
      subscriptionId: current.id,
      userId,
      fromStatus: current.status,
      toStatus: "active",
      eventType: "subscription.cancel_resumed",
      reason: "User resumed automatic renewal",
      idempotencyKey: transitionKey(current.id, "cancel_resumed", idempotencyKey),
      occurredAt: now,
      metadata: {},
    }).onConflictDoNothing({ target: subscriptionTransitions.idempotencyKey });
  });
  const updated = await db.select().from(subscriptions).where(eq(subscriptions.id, current.id)).limit(1);
  return updated[0] ? mapSubscription(updated[0]) : null;
}

export async function recordTokenUsage(input: {
  userId: string;
  inputTokens: number;
  outputTokens: number;
  idempotencyKey: string;
  runId?: string;
  requestId?: string;
}): Promise<TokenUsageSummary> {
  if (![input.inputTokens, input.outputTokens].every((value) => Number.isInteger(value) && value >= 0)) throw new Error("token usage must be non-negative integers");
  if (!input.idempotencyKey.trim()) throw new Error("idempotencyKey is required");
  const summary = await getSubscriptionSummary(input.userId);
  const totalTokens = input.inputTokens + input.outputTokens;
  const db = getDb();
  if (!db) {
    const keys = globalUsageKeys.get(input.userId) ?? new Set<string>();
    if (keys.has(input.idempotencyKey)) return structuredClone(globalUsage.get(input.userId) ?? summary.usage);
    keys.add(input.idempotencyKey);
    globalUsageKeys.set(input.userId, keys);
    const current = globalUsage.get(input.userId) ?? structuredClone(summary.usage);
    globalUsage.set(input.userId, current);
    current.inputUsed += input.inputTokens;
    current.outputUsed += input.outputTokens;
    current.totalUsed += totalTokens;
    current.inputRemaining = Math.max(0, current.inputLimit - current.inputUsed);
    current.outputRemaining = Math.max(0, current.outputLimit - current.outputUsed);
    current.totalRemaining = Math.max(0, current.totalLimit - current.totalUsed);
    return structuredClone(current);
  }
  const [period] = await db.select().from(tokenUsagePeriods).where(and(
    eq(tokenUsagePeriods.userId, input.userId),
    eq(tokenUsagePeriods.status, "active"),
  )).orderBy(desc(tokenUsagePeriods.periodStart)).limit(1);
  if (!period) return summary.usage;
  await db.transaction(async (tx) => {
      const [inserted] = await tx.insert(tokenUsageEntries).values({
        id: `usage-${crypto.randomUUID()}`,
        userId: input.userId,
        subscriptionId: period.subscriptionId,
        periodId: period.id,
        runId: input.runId,
        requestId: input.requestId,
        inputTokens: input.inputTokens,
        outputTokens: input.outputTokens,
        totalTokens,
        status: "committed",
        idempotencyKey: input.idempotencyKey,
        metadata: {},
      }).onConflictDoNothing({ target: tokenUsageEntries.idempotencyKey }).returning({ id: tokenUsageEntries.id });
      if (inserted) await tx.update(tokenUsagePeriods).set({
        inputUsed: sql`${tokenUsagePeriods.inputUsed} + ${input.inputTokens}`,
        outputUsed: sql`${tokenUsagePeriods.outputUsed} + ${input.outputTokens}`,
        totalUsed: sql`${tokenUsagePeriods.totalUsed} + ${totalTokens}`,
      }).where(and(eq(tokenUsagePeriods.id, period.id), eq(tokenUsagePeriods.status, "active")));
    });
  const [updated] = await db.select().from(tokenUsagePeriods).where(eq(tokenUsagePeriods.id, period.id)).limit(1);
  return updated ? usageFromRow(updated, summary.plan) : summary.usage;
}

export async function listAdminSubscriptions(filters: { query?: string; status?: string } = {}): Promise<AdminSubscriptionRow[]> {
  const db = getDb();
  if (!db) {
    const knownUsers = new Map([
      ["demo-user", { id: "demo-user", name: "Local Demo", email: "demo@example.test", role: "admin" }],
      ["demo-member", { id: "demo-member", name: "Local Member", email: "member@example.test", role: "member" }],
    ]);
    for (const subscription of localState.subscriptions) {
      if (subscription.userId && !knownUsers.has(subscription.userId)) knownUsers.set(subscription.userId, { id: subscription.userId, name: subscription.userId, email: "local@example.test", role: "user" });
    }
    const rows = [...knownUsers.values()].filter((user) => {
      const subscription = localState.subscriptions.find((candidate) => candidate.userId === user.id);
      if (filters.status && subscription?.status !== filters.status) return false;
      const query = filters.query?.trim().toLowerCase();
      return !query || [user.id, user.name, user.email].some((value) => value.toLowerCase().includes(query));
    });
    return Promise.all(rows.map(async (user) => ({ ...(await getSubscriptionSummary(user.id)), user })));
  }
  const rows = await db.select({ subscription: subscriptions, user: users })
    .from(users)
    .leftJoin(subscriptions, eq(users.id, subscriptions.userId))
    .orderBy(desc(subscriptions.updatedAt));
  const filtered = rows.filter(({ subscription, user }) => {
    if (filters.status && subscription?.status !== filters.status) return false;
    const query = filters.query?.trim().toLowerCase();
    if (!query) return true;
    return [user?.id, user?.name, user?.email, subscription?.externalCustomerRef].some((value) => value?.toLowerCase().includes(query));
  });
  return Promise.all(filtered.map(async ({ subscription, user }) => ({
    ...(await getSubscriptionSummary(user.id)),
    user: { id: user.id, name: user.name, email: user.email, role: user.role },
  })));
}

export async function createPricingPlan(input: PricingPlanInput, actorUserId = "local-admin", reason = "") {
  validatePlanInput(input, reason);
  const policy = await getBillingPolicy();
  assertBillingModeIsEditable(undefined, input, policy);
  const planId = `plan-${crypto.randomUUID()}`;
  const options = (input.options ?? []).map((option) => ({ ...option, id: option.id ?? `option-${crypto.randomUUID()}`, planId }));
  validatePlanOptions(options, input.billingMode);
  const db = getDb();
  if (!db) {
    const plan = toLocalPlan(planId, input, options);
    localState.plans = [...localState.plans, plan].sort((a, b) => a.displayOrder - b.displayOrder);
    return plan;
  }
  await db.transaction(async (tx) => {
    await tx.insert(pricingPlans).values(toPlanRow(planId, input));
    if (options.length) await tx.insert(pricingOptions).values(options.map(toOptionRow));
    await tx.insert(adminAuditEvents).values(auditRow(actorUserId, "pricing.plan.created", planId, null, planToAudit(input), reason));
  });
  return (await listPricingCatalog(false)).find((plan) => plan.id === planId) ?? null;
}

export async function updatePricingPlan(
  planId: string,
  input: PricingPlanInput,
  actorUserId = "local-admin",
  reason = "",
) {
  validatePlanInput(input, reason);
  const policy = await getBillingPolicy();
  const db = getDb();
  if (!db) {
    const current = localState.plans.find((plan) => plan.id === planId);
    if (!current) return null;
    assertBillingModeIsEditable(current, input, policy);
    const next = toLocalPlan(planId, input, (input.options ?? current.options).map((option) => ({
      ...option,
      id: option.id ?? `option-${crypto.randomUUID()}`,
      planId,
    })));
    validatePlanOptions(next.options, input.billingMode);
    localState.plans = localState.plans.map((plan) => (plan.id === planId ? next : plan)).sort((a, b) => a.displayOrder - b.displayOrder);
    return next;
  }

  const current = (await listPricingCatalog(false)).find((plan) => plan.id === planId);
  if (!current) return null;
  assertBillingModeIsEditable(current, input, policy);
  const options = input.options ?? current.options;
  validatePlanOptions(options, input.billingMode);
  const normalizedOptions = options.map((option) => ({
    ...option,
    id: option.id ?? `option-${crypto.randomUUID()}`,
    planId,
  }));
  await db.transaction(async (tx) => {
    await tx.update(pricingPlans).set({ ...toPlanRow(planId, input), updatedAt: new Date() }).where(eq(pricingPlans.id, planId));
    const staleOptionIds = current.options
      .filter((option) => !normalizedOptions.some((candidate) => candidate.id === option.id))
      .map((option) => option.id);
    if (staleOptionIds.length) {
      const referencedOptionIds = new Set<string>();
      for (const optionId of staleOptionIds) {
        const [order] = await tx.select({ id: paymentOrders.id }).from(paymentOrders).where(eq(paymentOrders.pricingOptionId, optionId)).limit(1);
        const [subscription] = await tx.select({ id: subscriptions.id }).from(subscriptions).where(eq(subscriptions.pricingOptionId, optionId)).limit(1);
        if (order || subscription) referencedOptionIds.add(optionId);
      }
      const removableOptionIds = staleOptionIds.filter((optionId) => !referencedOptionIds.has(optionId));
      if (removableOptionIds.length) {
        await tx.delete(pricingOptions).where(inArray(pricingOptions.id, removableOptionIds));
      }
      for (const optionId of referencedOptionIds) {
        await tx.update(pricingOptions).set({ active: false, updatedAt: new Date() }).where(eq(pricingOptions.id, optionId));
      }
    }
    for (const option of normalizedOptions) {
      const row = toOptionRow(option);
      const existing = current.options.find((candidate) => candidate.id === option.id);
      if (existing) {
        await tx.update(pricingOptions).set({ ...row, updatedAt: new Date() }).where(eq(pricingOptions.id, option.id));
      } else {
        await tx.insert(pricingOptions).values(row);
      }
    }
    await tx.insert(adminAuditEvents).values(auditRow(actorUserId, "pricing.plan.updated", planId, planToAudit(current), planToAudit({ ...input, options: normalizedOptions }), reason));
  });
  return (await listPricingCatalog(false)).find((plan) => plan.id === planId) ?? null;
}

export async function listProviderSettings(): Promise<ProviderSetting[]> {
  assertProductionDatabase();
  const db = getDb();
  if (!db) return cloneProviders(localState.providers);
  const rows = await db.select().from(paymentProviderSettings).orderBy(asc(paymentProviderSettings.provider));
  if (!rows.length) return cloneProviders(seededProviderSettings);
  return rows.map((row) => ({
    id: row.id,
    provider: row.provider as PricingProvider,
    enabled: row.enabled,
    sandbox: row.sandbox,
    publicConfig: row.publicConfig,
    secretRef: row.secretRef,
  }));
}

export async function updateProviderSetting(
  provider: PricingProvider,
  input: Pick<ProviderSetting, "enabled" | "sandbox" | "publicConfig" | "secretRef">,
  actorUserId = "local-admin",
  reason = "",
) {
  if (!reason.trim()) throw new Error("reason is required for provider setting changes");
  if (input.enabled && !input.sandbox) {
    const settings = await listProviderSettings();
    const conflicting = settings.find((setting) => setting.enabled && !setting.sandbox && setting.provider !== provider);
    if (conflicting) throw new Error(`only one live provider may be enabled; disable ${conflicting.provider} first`);
  }
  const db = getDb();
  if (!db) {
    localState.providers = localState.providers.map((setting) => input.enabled
      ? { ...setting, enabled: setting.provider === provider, ...(setting.provider === provider ? input : {}) }
      : setting.provider === provider ? { ...setting, ...input } : setting);
    return localState.providers.find((setting) => setting.provider === provider) ?? null;
  }
  const current = (await listProviderSettings()).find((setting) => setting.provider === provider);
  const row = { ...input, updatedAt: new Date() };
  if (current) {
    if (input.enabled) await db.update(paymentProviderSettings).set({ enabled: false, updatedAt: new Date() }).where(eq(paymentProviderSettings.enabled, true));
    await db.update(paymentProviderSettings).set(row).where(eq(paymentProviderSettings.provider, provider));
  } else {
    await db.insert(paymentProviderSettings).values({ id: `provider-${provider}`, provider, ...input });
  }
  await db.insert(adminAuditEvents).values(auditRow(actorUserId, "billing.provider.updated", `provider-${provider}`, current, input, reason));
  return (await listProviderSettings()).find((setting) => setting.provider === provider) ?? null;
}

export async function selectedPaymentProvider(): Promise<PricingProvider> {
  const settings = await listProviderSettings();
  const configured = process.env.PAYMENT_PROVIDER as PricingProvider | undefined;
  if (configured && ["toss", "lemon-squeezy"].includes(configured)) return configured;
  const enabled = settings.find((setting) => setting.enabled);
  if (enabled) return enabled.provider;
  if (configured === "mock") return configured;
  return "mock";
}

export function applySelectedPaymentProvider(plans: PricingPlan[], provider: PricingProvider): PricingPlan[] {
  return plans
    .map((plan) => ({
      ...plan,
      // Public pricing is provider-neutral. Provider-specific rows remain
      // available to admin/API contract tests, but must not become a second
      // product card that can be clicked under a different active provider.
      options: plan.options
        .filter((option) => option.provider === "mock")
        .map((option) => ({ ...option, provider })),
    }))
    .filter((plan) => plan.options.length > 0);
}

function validatePlanInput(input: PricingPlanInput, reason: string) {
  if (!input.code.trim() || !input.name.trim()) throw new Error("plan code and name are required");
  if (!["one_time", "subscription"].includes(input.billingMode)) throw new Error("valid billingMode is required");
  if (!reason.trim()) throw new Error("reason is required for pricing changes");
}

function assertBillingModeIsEditable(current: PricingPlan | undefined, next: PricingPlanInput, policy: PricingPolicy) {
  if (current === undefined) {
    if (next.billingMode !== policy.billingMode) {
      throw new Error(
        `plan billingMode ${next.billingMode} requires the active catalog mode to also be ${next.billingMode}; current policy is ${policy.billingMode}`,
      );
    }
    return;
  }
  if (next.billingMode !== current.billingMode && next.billingMode !== policy.billingMode) {
    throw new Error(
      `plan billingMode change to ${next.billingMode} requires the active catalog mode to also be ${next.billingMode}; current policy is ${policy.billingMode}`,
    );
  }
}

function validatePlanOptions(options: PricingOptionInput[], billingMode: BillingMode) {
  options.forEach((option) => {
    validateOption(option);
    if (option.mode !== billingMode) throw new Error(`pricing option mode must match plan billingMode: ${billingMode}`);
  });
}

function toPlanRow(id: string, input: PricingPlanInput) {
  return {
    id,
    tenantId: input.tenantId ?? "platform",
    code: input.code.trim(),
    name: input.name.trim(),
    description: input.description?.trim() ?? "",
    billingMode: input.billingMode,
    active: input.active ?? true,
    isDefault: input.isDefault ?? false,
    displayOrder: input.displayOrder ?? 0,
    features: input.features ?? [],
    quotas: input.quotas ?? {},
  };
}

function toOptionRow(option: PricingOptionInput & { id: string; planId: string }) {
  return {
    id: option.id,
    planId: option.planId,
    mode: option.mode,
    interval: option.interval,
    provider: option.provider,
    currency: option.currency.toUpperCase(),
    amountMinor: option.amountMinor,
    compareAtAmountMinor: option.compareAtAmountMinor ?? null,
    providerProductRef: option.providerProductRef ?? null,
    providerPriceRef: option.providerPriceRef ?? null,
    active: option.active ?? true,
    metadata: {},
  };
}

function toLocalPlan(id: string, input: PricingPlanInput, options: Array<PricingOptionInput & { id: string; planId: string }>): PricingPlan {
  return {
    ...toPlanRow(id, input),
    options: options.map((option) => ({
      ...option,
      currency: option.currency.toUpperCase(),
      compareAtAmountMinor: option.compareAtAmountMinor ?? null,
      providerProductRef: option.providerProductRef ?? null,
      providerPriceRef: option.providerPriceRef ?? null,
      active: option.active ?? true,
    })),
  };
}

function planToAudit(value: unknown) {
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
}

function auditRow(actorUserId: string, action: string, resourceId: string, beforeJson: unknown, afterJson: unknown, reason: string) {
  return {
    id: `audit-${crypto.randomUUID()}`,
    actorUserId,
    action,
    resourceType: action === "billing.policy.updated" ? "pricing_catalog_settings" : action.startsWith("billing.") ? "payment_provider_settings" : "pricing_plans",
    resourceId,
    reason: reason.trim(),
    beforeJson: beforeJson ? planToAudit(beforeJson) : null,
    afterJson: afterJson ? planToAudit(afterJson) : null,
  };
}
