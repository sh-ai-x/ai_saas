import {
  approveTossBilling,
  confirmTossPayment,
  issueTossBillingKey,
} from "@/lib/payments/toss-billing";
import {
  getPaymentOrder,
  getPaymentOrderByCustomerKey,
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
