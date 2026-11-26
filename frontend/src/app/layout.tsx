import type { Metadata, Viewport } from "next";

import { Providers } from "@/components/knoww/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Knoww: Know what matters", template: "%s · Knoww" },
  description: "Knoww tells you what meaningfully changed in your watchlist since you last checked, and why it matters.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfbf9" },
    { media: "(prefers-color-scheme: dark)", color: "#121418" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
