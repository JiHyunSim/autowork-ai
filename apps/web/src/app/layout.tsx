import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "AutoWork AI — AI가 반복 업무를 대신합니다",
    template: "%s | AutoWork AI",
  },
  description:
    "추가 채용 없이 주 10시간 절약. 미팅 요약·보고서·이메일 초안을 AI가 자동으로 처리합니다. 3일 내 도입 가능.",
  keywords: ["AI 자동화", "업무 자동화", "미팅 요약 AI", "보고서 자동화", "한국 SaaS", "AI 도입"],
  metadataBase: new URL("https://autowork-ai.vercel.app"),
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
