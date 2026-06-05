import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Virtual Try-On",
  description: "Одежда из онлайн-магазина на 3D-модели тела",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
