export type TossPayment = {
  requestPayment: (options: {
    method: "CARD";
    amount: { value: number; currency: string };
    orderId: string;
    orderName: string;
    successUrl: string;
    failUrl: string;
    customerEmail?: string;
    customerName?: string;
  }) => Promise<void>;
  requestBillingAuth: (options: {
    method: "CARD";
    successUrl: string;
    failUrl: string;
    customerEmail?: string;
    customerName?: string;
  }) => Promise<void>;
};

type TossPaymentsFactory = (clientKey: string) => {
  payment: (options: { customerKey: string }) => TossPayment;
};

declare global {
  interface Window {
    TossPayments?: TossPaymentsFactory;
  }
}

export async function loadTossSdk() {
  if (window.TossPayments) return window.TossPayments;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://js.tosspayments.com/v2/standard";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Toss Payments SDK를 불러오지 못했습니다."));
    document.head.appendChild(script);
  });
  if (!window.TossPayments) throw new Error("Toss Payments SDK가 초기화되지 않았습니다.");
  return window.TossPayments;
}
