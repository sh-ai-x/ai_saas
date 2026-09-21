import { NextRequest, NextResponse } from "next/server";

import { createCatalogCheckout } from "@/lib/payments/catalog-checkout";
import { createPaymentOrder, getBillingPolicy, getPricingOffer, selectedPaymentProvider } from "@/lib/pricing/repository";
import { getSafeSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as { optionId?: string; tenantId?: string; accountId?: string };
    if (!body.optionId) throw new Error("optionId is required");
    const [offer, billing, session] = await Promise.all([getPricingOffer(body.optionId), getBillingPolicy(), getSafeSession(request)]);
    if (!offer || !offer.option.active || !offer.plan.active) return NextResponse.json({ error: "pricing option is not available" }, { status: 404 });
    if (offer.option.mode !== billing.billingMode) return NextResponse.json({ error: `this catalog accepts ${billing.billingMode} payments only` }, { status: 409 });
    const provider = await selectedPaymentProvider();
    if (provider !== offer.option.provider && offer.option.provider !== "mock") {
      return NextResponse.json({ error: `pricing option is configured for ${offer.option.provider}, selected provider is ${provider}` }, { status: 409 });
    }
    const selectedOption = provider === offer.option.provider ? offer.option : { ...offer.option, provider };
    const orderId = `web-order-${crypto.randomUUID()}`;
    const checkout = await createCatalogCheckout({
      option: selectedOption,
      tenantId: body.tenantId ?? request.headers.get("x-tenant-id") ?? "demo-tenant",
      accountId: body.accountId ?? "demo-account",
      userEmail: session?.user.email,
      userName: session?.user.name,
      orderId,
      idempotencyKey: `${orderId}-key`,
    });
    if (checkout.provider === "toss") {
      await createPaymentOrder({
        id: orderId,
        tenantId: body.tenantId ?? request.headers.get("x-tenant-id") ?? "demo-tenant",
        userId: session?.user.id ?? null,
        option: selectedOption,
        idempotencyKey: `${orderId}-key`,
        metadata: {
          customerKey: checkout.checkoutContext.customer_key,
          interval: selectedOption.interval,
          orderName: checkout.checkoutContext.order_name,
        },
      });
    }
    return NextResponse.json(checkout, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "checkout unavailable" }, { status: 400 });
  }
}
