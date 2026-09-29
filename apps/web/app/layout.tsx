import type { Metadata } from "next";
import "./globals.css";
import { FaqWidget } from "@/components/faq-widget";
import { ThemeToggle } from "@/components/theme-toggle";

export const metadata: Metadata = {
  title: "Live Docs Console",
  description: "Live Docs console",
};

// Inline before paint so [data-theme="dark"] rules apply on first frame.
const themeBootstrap = `(function(){try{var t=localStorage.getItem('ai-saas-theme');if(t==='dark'||(t==null&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.dataset.theme='dark';}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      {/* Browser extensions may add attributes such as cz-shortcut-listen. */}
      <body suppressHydrationWarning>{children}<FaqWidget /><ThemeToggle /></body>
    </html>
  );
}
