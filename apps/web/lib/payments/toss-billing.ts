export type TossBillingRequest = {
  authKey: string;
  customerKey: string;
};

export type TossBillingApprovalRequest = {
  billingKey: string;
  customerKey: string;
  orderId: string;
  orderName: string;
  amount: number;
  idempotencyKey: string;
};

export type TossPaymentConfirmationRequest = {
  paymentKey: string;
  orderId: string;
  amount: number;
  idempotencyKey: string;
};

type TossJson = Record<string, unknown>;

const tossApiBase = () => (process.env.TOSS_API_BASE_URL ?? "https://api.tosspayments.com").replace(/\/$/, "");

export function assertSandboxTossConfiguration() {
  const clientKey = process.env.TOSS_CLIENT_KEY?.trim() ?? "";
  const secretKey = process.env.TOSS_SECRET_KEY?.trim() ?? "";
  if (!clientKey || !secretKey) throw new Error("TOSS_CLIENT_KEY and TOSS_SECRET_KEY are required for Toss sandbox");
  if ((process.env.PAYMENT_SANDBOX ?? "true") === "true" && (!clientKey.startsWith("test_") || !secretKey.startsWith("test_"))) {
    throw new Error("PAYMENT_SANDBOX=true requires matching Toss test keys");
  }
  return { clientKey, secretKey };
}

function authorization(secretKey: string) {
  return `Basic ${Buffer.from(`${secretKey}:`).toString("base64")}`;
}

async function tossRequest(
  path: string,
  method: "POST",
  body: TossJson,
  request: typeof fetch = fetch,
  idempotencyKey?: string,
): Promise<TossJson> {
  const { secretKey } = assertSandboxTossConfiguration();
  const response = await request(`${tossApiBase()}${path}`, {
    method,
    headers: {
      Authorization: authorization(secretKey),
      "Content-Type": "application/json",
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const payload = (await response.json()) as TossJson;
  if (!response.ok) {
    const code = typeof payload.code === "string" ? payload.code : "TOSS_REQUEST_FAILED";
    throw new Error(`${code}: Toss request failed`);
  }
  return payload;
}

export async function issueTossBillingKey(input: TossBillingRequest, request: typeof fetch = fetch) {
  if (!input.authKey.trim() || !input.customerKey.trim()) throw new Error("authKey and customerKey are required");
  const payload = await tossRequest("/v1/billing/authorizations/issue", "POST", input, request);
  const returnedCustomerKey = String(payload.customerKey ?? input.customerKey);
  const billingKey = String(payload.billingKey ?? "");
  if (returnedCustomerKey !== input.customerKey || !billingKey) throw new Error("Toss billing key response is invalid");
  return { billingKey, customerKey: returnedCustomerKey };
}

export async function approveTossBilling(input: TossBillingApprovalRequest, request: typeof fetch = fetch) {
  if (!input.billingKey || !input.customerKey || !input.orderId || !Number.isInteger(input.amount) || input.amount <= 0) {
    throw new Error("billing approval input is incomplete");
  }
  const payload = await tossRequest(`/v1/billing/${encodeURIComponent(input.billingKey)}`, "POST", {
    customerKey: input.customerKey,
    orderId: input.orderId,
    orderName: input.orderName,
    amount: input.amount,
  }, request, input.idempotencyKey);
  if (String(payload.orderId ?? "") !== input.orderId || Number(payload.totalAmount ?? -1) !== input.amount) {
    throw new Error("Toss billing approval does not match the pending order");
  }
  if (String(payload.status ?? "") !== "DONE") throw new Error("Toss billing approval is not complete");
  return payload;
}

export async function confirmTossPayment(input: TossPaymentConfirmationRequest, request: typeof fetch = fetch) {
  if (!input.paymentKey.trim() || !input.orderId.trim() || !Number.isInteger(input.amount) || input.amount <= 0) {
    throw new Error("payment confirmation input is incomplete");
  }
  const payload = await tossRequest("/v1/payments/confirm", "POST", {
    paymentKey: input.paymentKey,
    orderId: input.orderId,
    amount: input.amount,
  }, request, input.idempotencyKey);
  if (String(payload.orderId ?? "") !== input.orderId || Number(payload.totalAmount ?? -1) !== input.amount) {
    throw new Error("Toss confirmation does not match the pending order");
  }
  if (String(payload.status ?? "") !== "DONE") throw new Error("Toss confirmation is not complete");
  return payload;
}
