import {
  approveTossBilling,
  confirmTossPayment,
  issueTossBillingKey,
} from "@/lib/payments/toss-billing";
import {
  getPaymentOrder,
  getPaymentOrderByCustomerKey,
  createPaymentOrder,
  getPricingOffer,
  listDueTossSubscriptions,
  expireEndedSubscriptions,
  recordTossRenewal,
  recordTossRenewalFailure,
  recordTossSubscription,
  updatePaymentOrder,
} from "@/lib/pricing/repository";
import type { PaymentOrder } from "@/lib/pricing/types";

function requireTossOrder(order: PaymentOrder | null, mode: PaymentOrder["mode"]) {
  if (!order || order.provider !== "toss" || order.mode !== mode) {
    throw new Error("Toss payment order was not found");
  }
  if (order.currency !== "KRW") throw new Error("Toss payment order currency must be KRW");
  return order;
}

export async function settleTossOneTimePayment(input: {
  paymentKey: string;
  orderId: string;
  amount: number;
  request?: typeof fetch;
}) {
  const order = requireTossOrder(await getPaymentOrder(input.orderId), "one_time");
  if (order.status === "succeeded") return order;
  if (order.status !== "pending") throw new Error("Toss payment order is not pending");
  if (order.amountMinor !== input.amount) throw new Error("Toss payment amount does not match the pending order");

  const payload = await confirmTossPayment({
    paymentKey: input.paymentKey,
    orderId: order.id,
    amount: order.amountMinor,
    idempotencyKey: order.idempotencyKey,
  }, input.request);
  const updated = await updatePaymentOrder(order.id, {
    status: "succeeded",
    externalPaymentRef: String(payload.paymentKey ?? input.paymentKey),
  });
  if (!updated) throw new Error("Toss payment order could not be settled");
  return updated;
}

export async function settleTossSubscription(input: {
  customerKey: string;
  authKey: string;
  request?: typeof fetch;
}) {
  const order = requireTossOrder(await getPaymentOrderByCustomerKey(input.customerKey), "subscription");
  if (order.status === "succeeded") return order;
  if (order.status !== "pending") throw new Error("Toss subscription order is not pending");

  const currentBillingKey = typeof order.metadata.billingKey === "string" ? order.metadata.billingKey : "";
  const billingKey = currentBillingKey || (await issueTossBillingKey({
    authKey: input.authKey,
    customerKey: input.customerKey,
  }, input.request)).billingKey;
  if (!currentBillingKey) {
    await updatePaymentOrder(order.id, {
      metadata: { ...order.metadata, customerKey: input.customerKey, billingKey },
    });
  }

  const payload = await approveTossBilling({
    billingKey,
    customerKey: input.customerKey,
    orderId: order.id,
    orderName: typeof order.metadata.orderName === "string" ? order.metadata.orderName : "AI SaaS subscription",
    amount: order.amountMinor,
    idempotencyKey: order.idempotencyKey,
  }, input.request);
  const settlementPatch: Pick<PaymentOrder, "status" | "externalPaymentRef" | "metadata"> = {
    status: "succeeded",
    externalPaymentRef: String(payload.paymentKey ?? payload.transactionKey ?? "") || null,
    metadata: { ...order.metadata, customerKey: input.customerKey, billingKey },
  };
  const settledOrder: PaymentOrder = { ...order, ...settlementPatch };
  await recordTossSubscription({ order: settledOrder, customerKey: input.customerKey, billingKey });
  const updated = await updatePaymentOrder(order.id, settlementPatch);
  if (!updated) throw new Error("Toss subscription order could not be settled");
  return updated;
}

export async function renewDueTossSubscriptions(input: { request?: typeof fetch; now?: Date } = {}) {
  await expireEndedSubscriptions(input.now);
  const due = await listDueTossSubscriptions(input.now);
  const results: Array<{ subscriptionId: string; status: "renewed" | "failed" | "skipped"; error?: string }> = [];
  for (const subscription of due) {
    if (subscription.cancelAtPeriodEnd) {
      results.push({ subscriptionId: subscription.id, status: "skipped" });
      continue;
    }
    let order: PaymentOrder | null = null;
    try {
      const offer = await getPricingOffer(subscription.pricingOptionId);
      const billingKey = typeof subscription.metadata.billingKey === "string" ? subscription.metadata.billingKey : "";
      if (!offer || !billingKey || !subscription.externalCustomerRef) throw new Error("subscription billing configuration is incomplete");
      if (!subscription.nextBillingAt) throw new Error("subscription next billing date is missing");
      const orderId = `renewal-${subscription.id}-${subscription.nextBillingAt.getTime()}`;
      order = await createPaymentOrder({
        id: orderId,
        tenantId: subscription.tenantId,
        userId: subscription.userId,
        option: { ...offer.option, provider: "toss" },
        idempotencyKey: `${orderId}-key`,
        metadata: { renewalFor: subscription.id, customerKey: subscription.externalCustomerRef, billingKey, orderName: `${offer.plan.name} renewal`, interval: offer.option.interval },
      });
      if (order.status === "succeeded") {
        await recordTossRenewal({ subscription, paymentOrder: order, paymentRef: order.externalPaymentRef ?? order.id });
        results.push({ subscriptionId: subscription.id, status: "renewed" });
        continue;
      }
      const payload = await approveTossBilling({
        billingKey,
        customerKey: subscription.externalCustomerRef,
        orderId: order.id,
        orderName: `${offer.plan.name} renewal`,
        amount: order.amountMinor,
        idempotencyKey: order.idempotencyKey,
      }, input.request);
      await updatePaymentOrder(order.id, { status: "succeeded", externalPaymentRef: String(payload.paymentKey ?? payload.transactionKey ?? "") || null });
      await recordTossRenewal({ subscription, paymentOrder: order, paymentRef: String(payload.paymentKey ?? payload.transactionKey ?? "") });
      results.push({ subscriptionId: subscription.id, status: "renewed" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Toss renewal failed";
      if (order) await updatePaymentOrder(order.id, { status: "failed" });
      await recordTossRenewalFailure(subscription, message);
      results.push({ subscriptionId: subscription.id, status: "failed", error: message });
    }
  }
  return results;
}
