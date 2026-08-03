/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import { Geist, Geist_Mono, Caveat, Instrument_Serif } from "next/font/google";
import "./globals.css";
import "@/styles/globals.css";
// Thesys C1 Generative UI styles (required by C1Component)
import "@crayonai/react-ui/styles/index.css";

import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const cursive = Caveat({
  variable: "--font-cursive",
  subsets: ["latin"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
});

export const metadata: Metadata = {
  title: "CoComputer — AI Desktop Agent",
  description: "Voice-controlled AI agent with full Linux desktop access",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${cursive.variable} ${instrumentSerif.variable} antialiased min-h-screen`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
