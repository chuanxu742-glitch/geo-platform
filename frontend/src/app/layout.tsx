import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "GEO Agent 工作室",
  description: "提交业务目标，由 Agent 阅读官网、提出计划与有据改稿；人工审核并明确授权发布，后台持续执行与全文核验。",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
