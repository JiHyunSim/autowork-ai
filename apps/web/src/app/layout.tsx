import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AutoWork AI — AI 업무 자동화",
  description: "반복적인 사무 업무를 AI로 자동화. 미팅 요약, 보고서 생성, 이메일 작성을 AI가 대신합니다.",
  keywords: ["AI 자동화", "업무 자동화", "미팅 요약", "보고서 자동화", "SaaS"],
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
