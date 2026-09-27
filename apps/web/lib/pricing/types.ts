export type PricingMode = "one_time" | "subscription";
export type BillingMode = PricingMode;
export type PricingInterval = "one_time" | "month" | "year";
export type PricingProvider = "mock" | "toss" | "lemon-squeezy";

export type PricingOption = {
  id: string;
  planId: string;
  mode: PricingMode;
  interval: PricingInterval;
  provider: PricingProvider;
  currency: string;
  amountMinor: number;
  compareAtAmountMinor: number | null;
  providerProductRef: string | null;
  providerPriceRef: string | null;
  active: boolean;
};

export type PricingPlan = {
  id: string;
  tenantId: string;
  code: string;
  name: string;
  description: string;
  billingMode: BillingMode;
  active: boolean;
  isDefault: boolean;
  displayOrder: number;
  features: string[];
  quotas: Record<string, number>;
  options: PricingOption[];
};

export type ProviderSetting = {
  id: string;
  provider: PricingProvider;
  enabled: boolean;
  sandbox: boolean;
  publicConfig: Record<string, unknown>;
  secretRef: string | null;
};

export type PaymentOrder = {
  id: string;
  tenantId: string;
  userId: string | null;
  pricingOptionId: string;
  provider: PricingProvider;
  mode: PricingMode;
  status: "pending" | "succeeded" | "failed" | "cancelled";
  externalOrderRef: string | null;
  externalPaymentRef: string | null;
  amountMinor: number;
  currency: string;
  idempotencyKey: string;
  metadata: Record<string, unknown>;
};

export type SubscriptionStatus = "pending" | "active" | "cancel_scheduled" | "past_due" | "expired" | "canceled";

export type SubscriptionRecord = {
  id: string;
  tenantId: string;
  userId: string | null;
  pricingOptionId: string;
  provider: "toss";
  externalCustomerRef: string;
  externalSubscriptionRef: string;
  status: SubscriptionStatus;
  providerStatus?: string | null;
  currentPeriodStart: Date;
  currentPeriodEnd: Date;
  cancelAtPeriodEnd: boolean;
  cancelRequestedAt?: Date | null;
  canceledAt?: Date | null;
  endedAt?: Date | null;
  nextBillingAt?: Date | null;
  graceUntil?: Date | null;
  lastPaymentAt?: Date | null;
  lastPaymentError?: string | null;
  version?: number;
  metadata: Record<string, unknown>;
};

export type TokenUsageSummary = {
  inputLimit: number;
  outputLimit: number;
  totalLimit: number;
  inputUsed: number;
  outputUsed: number;
  totalUsed: number;
  inputRemaining: number;
  outputRemaining: number;
  totalRemaining: number;
  periodStart: Date;
  periodEnd: Date;
};

export type SubscriptionSummary = {
  subscription: SubscriptionRecord | null;
  plan: PricingPlan | null;
  usage: TokenUsageSummary;
  access: "free" | "paid" | "grace" | "expired";
  transitions: Array<{
    id: string;
    fromStatus: string | null;
    toStatus: string;
    eventType: string;
    occurredAt: Date;
  }>;
};

export type AdminSubscriptionRow = SubscriptionSummary & {
  user: { id: string; name: string; email: string; role: string };
};

export type PricingPolicy = {
  id: string;
  billingMode: BillingMode;
  currency: string;
  updatedBy: string | null;
};

export type PricingPlanInput = {
  tenantId?: string;
  code: string;
  name: string;
  description?: string;
  billingMode: BillingMode;
  active?: boolean;
  isDefault?: boolean;
  displayOrder?: number;
  features?: string[];
  quotas?: Record<string, number>;
  options?: PricingOptionInput[];
};

export type PricingOptionInput = {
    id?: string;
    mode: PricingMode;
    interval: PricingInterval;
    provider: PricingProvider;
    currency: string;
    amountMinor: number;
    compareAtAmountMinor?: number | null;
    providerProductRef?: string | null;
    providerPriceRef?: string | null;
    active?: boolean;
};
