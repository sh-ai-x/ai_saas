import { and, asc, eq, inArray } from "drizzle-orm";

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
} from "./types";

const { adminAuditEvents, paymentOrders, paymentProviderSettings, pricingCatalogSettings, pricingOptions, pricingPlans, subscriptions } = schema;

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
  if (!db) return { id: "platform", billingMode: localState.billingMode, currency: "USD", updatedBy: "local-seed" };
  const [row] = await db.select().from(pricingCatalogSettings).where(eq(pricingCatalogSettings.id, "platform")).limit(1);
  if (!row) return { id: "platform", billingMode: seededBillingMode, currency: "USD", updatedBy: "migration-seed" };
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
  const rows = await db.select().from(paymentOrders).where(eq(paymentOrders.provider, "toss"));
  const row = rows.find((candidate) => (candidate.metadata as Record<string, unknown>).customerKey === customerKey);
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
  const periodEnd = new Date();
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
    currentPeriodStart: new Date(),
    currentPeriodEnd: periodEnd,
    cancelAtPeriodEnd: false,
    metadata: { billingKey: input.billingKey },
  };
  if (!db) {
    const index = localState.subscriptions.findIndex((subscription) => subscription.id === values.id);
    if (index === -1) localState.subscriptions.push(structuredClone(values));
    else localState.subscriptions[index] = structuredClone(values);
    return;
  }
  const [existing] = await db.select({ id: subscriptions.id }).from(subscriptions).where(eq(subscriptions.id, values.id)).limit(1);
  if (existing) await db.update(subscriptions).set({ ...values, updatedAt: new Date() }).where(eq(subscriptions.id, values.id));
  else await db.insert(subscriptions).values(values);
}

export async function createPricingPlan(input: PricingPlanInput, actorUserId = "local-admin", reason = "") {
  validatePlanInput(input, reason);
  const policy = await getBillingPolicy();
  if (input.billingMode !== policy.billingMode) throw new Error(`plan billingMode must match active catalog mode: ${policy.billingMode}`);
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
    assertBillingModeTransitionAllowed(current, input, policy);
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
  assertBillingModeTransitionAllowed(current, input, policy);
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
  const enabled = settings.find((setting) => setting.enabled);
  if (enabled) return enabled.provider;
  const configured = process.env.PAYMENT_PROVIDER as PricingProvider | undefined;
  if (configured && ["mock", "toss", "lemon-squeezy"].includes(configured)) return configured;
  return "mock";
}

function validatePlanInput(input: PricingPlanInput, reason: string) {
  if (!input.code.trim() || !input.name.trim()) throw new Error("plan code and name are required");
  if (!["one_time", "subscription"].includes(input.billingMode)) throw new Error("valid billingMode is required");
  if (!reason.trim()) throw new Error("reason is required for pricing changes");
}

function assertBillingModeTransitionAllowed(current: PricingPlan, next: PricingPlanInput, policy: BillingPolicy) {
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
