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
