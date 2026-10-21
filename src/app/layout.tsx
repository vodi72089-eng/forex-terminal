import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Forex Terminal",
  description: "Tauri + Next.js + OpenCode + bot MT5 embarque",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
