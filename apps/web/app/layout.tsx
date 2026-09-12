import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CommercePilot",
  description: "AI e-commerce manager for your store and marketplaces.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
