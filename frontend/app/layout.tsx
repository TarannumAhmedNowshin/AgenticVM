import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AVMS — Agentic Visual Merchandising Studio",
  description:
    "Upload a retail display photo and receive brand-aware, agent-crafted merchandising recommendations.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
