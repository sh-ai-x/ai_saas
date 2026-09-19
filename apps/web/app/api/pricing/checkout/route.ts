import { NextRequest, NextResponse } from "next/server";

import { createCatalogCheckout } from "@/lib/payments/catalog-checkout";
import { getBillingPolicy, getPricingOption, selectedPaymentProvider } from "@/lib/pricing/repository";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as { optionId?: string; tenantId?: string; accountId?: string };
    if (!body.optionId) throw new Error("optionId is required");
    const [option, billing] = await Promise.all([getPricingOption(body.optionId), getBillingPolicy()]);
    if (!option || !option.active) return NextResponse.json({ error: "pricing option is not available" }, { status: 404 });
    if (option.mode !== billing.billingMode) return NextResponse.json({ error: `this catalog accepts ${billing.billingMode} payments only` }, { status: 409 });
    const provider = await selectedPaymentProvider();
    if (provider !== option.provider && option.provider !== "mock") {
      return NextResponse.json({ error: `pricing option is configured for ${option.provider}, selected provider is ${provider}` }, { status: 409 });
    }
    const selectedOption = provider === option.provider ? option : { ...option, provider };
    const orderId = `web-order-${crypto.randomUUID()}`;
    const checkout = await createCatalogCheckout({
      option: selectedOption,
      tenantId: body.tenantId ?? request.headers.get("x-tenant-id") ?? "demo-tenant",
      accountId: body.accountId ?? "demo-account",
      orderId,
      idempotencyKey: `${orderId}-key`,
    });
    return NextResponse.json(checkout, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "checkout unavailable" }, { status: 400 });
  }
}
