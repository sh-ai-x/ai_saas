import { NextRequest } from "next/server";
import React from "react";

import HomePage, { dynamic as landingDynamic } from "@/app/page";
import { GET as getAdminPricing } from "@/app/api/admin/pricing/route";
import { PATCH as patchAdminPricing } from "@/app/api/admin/pricing/[id]/route";
import { GET as getPublicPricing } from "@/app/api/pricing/route";
import { getDb, schema } from "@/db";
import { listPricingCatalog } from "@/lib/pricing/repository";
import { localDemoSession, localSessionCookie } from "@/lib/auth/local-session";
import type { PricingPlan, PricingPlanInput } from "@/lib/pricing/types";
import { eq } from "drizzle-orm";

process.env.APP_ENV = "test";
process.env.FOUNDATION_API_URL = "http://127.0.0.1:9";
(globalThis as typeof globalThis & { React?: typeof React }).React = React;

const integrationEnabled = process.env.PRICING_DB_INTEGRATION === "1";
const testDatabaseUrl = process.env.PRICING_TEST_DATABASE_URL;
let openedDb: ReturnType<typeof getDb> = null;
const integrationEnabledTest = integrationEnabled ? it : it.skip;
const configuredIntegrationTest = integrationEnabled && testDatabaseUrl ? it : it.skip;

function request(url: string, init?: ConstructorParameters<typeof NextRequest>[1]) {
  return new NextRequest(`http://127.0.0.1:3012${url}`, {
    ...init,
    headers: {
      cookie: `${localSessionCookie}=${localDemoSession.session.id}`,
      ...(init?.headers ?? {}),
    },
  });
}

function jsonRequest(body: unknown, init?: ConstructorParameters<typeof NextRequest>[1]) {
  return request("/", {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    body: JSON.stringify(body),
  });
}

async function responseBody(response: Response) {
  return response.json() as Promise<Record<string, any>>;
}

function comparablePlan(plan: PricingPlan) {
  return {
    id: plan.id,
    tenantId: plan.tenantId,
    code: plan.code,
    name: plan.name,
    description: plan.description,
    billingMode: plan.billingMode,
    active: plan.active,
    isDefault: plan.isDefault,
    displayOrder: plan.displayOrder,
    features: plan.features,
    quotas: plan.quotas,
    options: plan.options.map((option) => ({
      id: option.id,
      planId: option.planId,
      mode: option.mode,
      interval: option.interval,
      provider: option.provider,
      currency: option.currency,
      amountMinor: option.amountMinor,
      compareAtAmountMinor: option.compareAtAmountMinor,
      providerProductRef: option.providerProductRef,
      providerPriceRef: option.providerPriceRef,
      active: option.active,
    })),
  };
}

describe("admin pricing to landing consistency contract", () => {
  afterAll(async () => {
    const client = (openedDb as unknown as { $client?: { end: () => Promise<void> } } | null)?.$client;
    await client?.end();
    delete process.env.PRICING_DB_INTEGRATION;
    delete process.env.PRICING_TEST_DATABASE_URL;
  });

  it("marks the landing route dynamic so a build-time seed cannot mask database edits", () => {
    expect(landingDynamic).toBe("force-dynamic");
  });

  integrationEnabledTest("requires an explicit isolated database when integration mode is enabled", () => {
    expect(testDatabaseUrl).toBeTruthy();
    expect(testDatabaseUrl).not.toBe(process.env.DATABASE_URL);
  });

  configuredIntegrationTest("keeps database, admin, public, and landing catalogs identical after an update", async () => {
    process.env.DATABASE_URL = testDatabaseUrl;
    openedDb = getDb();
    expect(openedDb).toBeTruthy();
    if (!openedDb) throw new Error("database integration requires a configured PostgreSQL connection");

    const original = (await listPricingCatalog(false)).find((plan) => plan.id === "plan-pro");
    expect(original).toBeTruthy();
    if (!original) throw new Error("migration seed must contain plan-pro");
    expect(original.options.length).toBe(2);

    const updatedInput: PricingPlanInput = {
      tenantId: original.tenantId,
      code: original.code,
      name: "Pro consistency test",
      description: original.description,
      billingMode: original.billingMode,
      active: original.active,
      isDefault: original.isDefault,
      displayOrder: original.displayOrder,
      features: original.features,
      quotas: original.quotas,
      options: [{
        id: original.options[0].id,
        mode: original.options[0].mode,
        interval: original.options[0].interval,
        provider: original.options[0].provider,
        currency: original.options[0].currency,
        amountMinor: 3111,
        compareAtAmountMinor: original.options[0].compareAtAmountMinor,
        providerProductRef: original.options[0].providerProductRef,
        providerPriceRef: original.options[0].providerPriceRef,
        active: true,
      }],
    };

    try {
      const updated = await patchAdminPricing(
        jsonRequest({ plan: updatedInput, reason: "pricing consistency integration test" }, { method: "PATCH" }),
        { params: Promise.resolve({ id: original.id }) },
      );
      expect(updated.status).toBe(200);

      const [dbPlan, dbOptions] = await Promise.all([
        openedDb.select().from(schema.pricingPlans).where(eq(schema.pricingPlans.id, original.id)),
        openedDb.select().from(schema.pricingOptions).where(eq(schema.pricingOptions.planId, original.id)),
      ]);
      expect(dbPlan[0]?.name).toBe(updatedInput.name);
      expect(dbOptions.map((option) => option.id)).toEqual([original.options[0].id]);
      expect(dbOptions[0]?.amountMinor).toBe(3111);

      const admin = await getAdminPricing(request("/api/admin/pricing"));
      expect(admin.status).toBe(200);
      const adminBody = await responseBody(admin);
      const adminPlan = adminBody.plans.find((plan: PricingPlan) => plan.id === original.id);
      expect(dbPlan[0]).toBeTruthy();
      if (!dbPlan[0]) throw new Error("updated database plan is missing");

      const publicResponse = await getPublicPricing();
      expect(publicResponse.status).toBe(200);
      const publicBody = await responseBody(publicResponse);
      const publicPlan = publicBody.plans.find((plan: PricingPlan) => plan.id === original.id);
      expect(adminPlan).toBeTruthy();
      if (!adminPlan) throw new Error("updated admin plan is missing");
      expect(publicPlan).toBeTruthy();
      if (!publicPlan) throw new Error("updated public plan is missing");

      const landing = await HomePage();
      const landingProps = (landing as { props: { plans: PricingPlan[]; billingMode: string } }).props;
      const landingPlan = landingProps.plans.find((plan) => plan.id === original.id);
      expect(landingPlan).toBeTruthy();
      if (!landingPlan) throw new Error("updated landing plan is missing");

      expect({
        id: dbPlan[0].id,
        tenantId: dbPlan[0].tenantId,
        code: dbPlan[0].code,
        name: dbPlan[0].name,
        description: dbPlan[0].description,
        billingMode: dbPlan[0].billingMode,
        active: dbPlan[0].active,
        isDefault: dbPlan[0].isDefault,
        displayOrder: dbPlan[0].displayOrder,
        features: dbPlan[0].features,
        quotas: dbPlan[0].quotas,
        options: dbOptions.map((option) => ({
          id: option.id,
          planId: option.planId,
          mode: option.mode,
          interval: option.interval,
          provider: option.provider,
          currency: option.currency,
          amountMinor: option.amountMinor,
          compareAtAmountMinor: option.compareAtAmountMinor,
          providerProductRef: option.providerProductRef,
          providerPriceRef: option.providerPriceRef,
          active: option.active,
        })),
      }).toEqual(comparablePlan(adminPlan));
      expect(comparablePlan(adminPlan)).toEqual(comparablePlan(publicPlan));
      expect(comparablePlan(publicPlan)).toEqual(comparablePlan(landingPlan));
      expect(publicPlan.options.length).toBe(1);
      expect(publicPlan.options[0].amountMinor).toBe(3111);
      expect(landingProps.billingMode).toBe(publicBody.billing.billingMode);
    } finally {
      await patchAdminPricing(
        jsonRequest({
          plan: {
            tenantId: original.tenantId,
            code: original.code,
            name: original.name,
            description: original.description,
            billingMode: original.billingMode,
            active: original.active,
            isDefault: original.isDefault,
            displayOrder: original.displayOrder,
            features: original.features,
            quotas: original.quotas,
            options: original.options,
          },
          reason: "restore pricing consistency integration fixture",
        }, { method: "PATCH" }),
        { params: Promise.resolve({ id: original.id }) },
      );
    }
  });

  configuredIntegrationTest("deactivates a referenced option instead of breaking payment history", async () => {
    process.env.DATABASE_URL = testDatabaseUrl;
    openedDb = getDb();
    expect(openedDb).toBeTruthy();
    if (!openedDb) throw new Error("database integration requires a configured PostgreSQL connection");
    const db = openedDb;
    const original = (await listPricingCatalog(false)).find((plan) => plan.id === "plan-pro");
    expect(original).toBeTruthy();
    if (!original) throw new Error("migration seed must contain plan-pro");
    const referencedOption = original.options[1];
    expect(referencedOption).toBeTruthy();
    if (!referencedOption) throw new Error("fixture must contain a yearly option");
    const orderId = "pricing-sync-referenced-order";

    await db.insert(schema.paymentOrders).values({
      id: orderId,
      tenantId: "platform",
      userId: null,
      pricingOptionId: referencedOption.id,
      provider: referencedOption.provider,
      mode: referencedOption.mode,
      status: "pending",
      externalOrderRef: null,
      externalPaymentRef: null,
      amountMinor: referencedOption.amountMinor,
      currency: referencedOption.currency,
      idempotencyKey: "pricing-sync-referenced-order-key",
      metadata: {},
    });

    try {
      const updated = await patchAdminPricing(
        jsonRequest({
          plan: {
            tenantId: original.tenantId,
            code: original.code,
            name: original.name,
            description: original.description,
            billingMode: original.billingMode,
            active: original.active,
            isDefault: original.isDefault,
            displayOrder: original.displayOrder,
            features: original.features,
            quotas: original.quotas,
            options: [original.options[0]],
          },
          reason: "preserve referenced pricing option history",
        }, { method: "PATCH" }),
        { params: Promise.resolve({ id: original.id }) },
      );
      expect(updated.status).toBe(200);
      const rows = await db.select({ id: schema.pricingOptions.id, active: schema.pricingOptions.active })
        .from(schema.pricingOptions)
        .where(eq(schema.pricingOptions.id, referencedOption.id));
      expect(rows).toEqual([{ id: referencedOption.id, active: false }]);
    } finally {
      await patchAdminPricing(
        jsonRequest({
          plan: {
            tenantId: original.tenantId,
            code: original.code,
            name: original.name,
            description: original.description,
            billingMode: original.billingMode,
            active: original.active,
            isDefault: original.isDefault,
            displayOrder: original.displayOrder,
            features: original.features,
            quotas: original.quotas,
            options: original.options,
          },
          reason: "restore referenced pricing option fixture",
        }, { method: "PATCH" }),
        { params: Promise.resolve({ id: original.id }) },
      );
      await db.delete(schema.paymentOrders).where(eq(schema.paymentOrders.id, orderId));
    }
  });
});
