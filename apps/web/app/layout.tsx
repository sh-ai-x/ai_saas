import type { Metadata } from "next";
import "./globals.css";
import { FaqWidget } from "@/components/faq-widget";

export const metadata: Metadata = {
  title: "AI SaaS Foundation Console",
  description: "Local contract-first AI SaaS foundation console",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}<FaqWidget /></body>
    </html>
  );
}
