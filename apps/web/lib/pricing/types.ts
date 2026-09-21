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

export type SubscriptionRecord = {
  id: string;
  tenantId: string;
  userId: string | null;
  pricingOptionId: string;
  provider: "toss";
  externalCustomerRef: string;
  externalSubscriptionRef: string;
  status: "active" | "cancelled" | "past_due";
  currentPeriodStart: Date;
  currentPeriodEnd: Date;
  cancelAtPeriodEnd: boolean;
  metadata: Record<string, unknown>;
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
