import type { BillingMode, PricingPlan, ProviderSetting } from "./types";

export const seededBillingMode: BillingMode = "subscription";

export const seededPricingCatalog: PricingPlan[] = [
  {
    id: "plan-starter",
    tenantId: "platform",
    code: "starter",
    name: "Starter",
    description: "A small, production-shaped workspace for trying the foundation.",
    billingMode: "subscription",
    active: true,
    isDefault: true,
    displayOrder: 10,
    features: ["1 workspace", "100 proposal reviews", "Mock or sandbox checkout"],
    quotas: { monthlyRuns: 100, members: 1 },
    options: [
      { id: "option-starter-monthly", planId: "plan-starter", mode: "subscription", interval: "month", provider: "mock", currency: "KRW", amountMinor: 900, compareAtAmountMinor: null, providerProductRef: null, providerPriceRef: null, active: true },
      { id: "option-starter-yearly", planId: "plan-starter", mode: "subscription", interval: "year", provider: "mock", currency: "KRW", amountMinor: 9000, compareAtAmountMinor: 10800, providerProductRef: null, providerPriceRef: null, active: true },
    ],
  },
  {
    id: "plan-pro",
    tenantId: "platform",
    code: "pro",
    name: "Pro",
    description: "A portfolio-ready plan with higher bounded usage and team handoff.",
    billingMode: "subscription",
    active: true,
    isDefault: false,
    displayOrder: 20,
    features: ["5 workspaces", "1,000 proposal reviews", "Usage and audit history"],
    quotas: { monthlyRuns: 1000, members: 5 },
    options: [
      { id: "option-pro-monthly", planId: "plan-pro", mode: "subscription", interval: "month", provider: "mock", currency: "KRW", amountMinor: 2900, compareAtAmountMinor: 3900, providerProductRef: null, providerPriceRef: null, active: true },
      { id: "option-pro-yearly", planId: "plan-pro", mode: "subscription", interval: "year", provider: "mock", currency: "KRW", amountMinor: 29000, compareAtAmountMinor: 34800, providerProductRef: null, providerPriceRef: null, active: true },
    ],
  },
  {
    id: "plan-lifetime",
    tenantId: "platform",
    code: "lifetime",
    name: "Lifetime",
    description: "A separate one-time product. It is not mixed with subscription plans.",
    billingMode: "one_time",
    active: true,
    isDefault: false,
    displayOrder: 30,
    features: ["One payment", "No recurring renewal", "Bounded portfolio license"],
    quotas: { monthlyRuns: 1000, members: 1 },
    options: [
      { id: "option-lifetime-onetime", planId: "plan-lifetime", mode: "one_time", interval: "one_time", provider: "mock", currency: "KRW", amountMinor: 7900, compareAtAmountMinor: null, providerProductRef: null, providerPriceRef: null, active: true },
    ],
  },
];

export const seededProviderSettings: ProviderSetting[] = [
  { id: "provider-mock", provider: "mock", enabled: true, sandbox: true, publicConfig: {}, secretRef: null },
  { id: "provider-toss", provider: "toss", enabled: false, sandbox: true, publicConfig: {}, secretRef: "TOSS_SECRET_KEY" },
  { id: "provider-lemon-squeezy", provider: "lemon-squeezy", enabled: false, sandbox: true, publicConfig: {}, secretRef: "LEMONSQUEEZY_API_KEY" },
];
