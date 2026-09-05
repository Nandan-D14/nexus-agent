/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import { Geist, Geist_Mono, Caveat, Instrument_Serif } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import "@/styles/globals.css";
// Thesys C1 Generative UI styles (required by C1Component)
import "@crayonai/react-ui/styles/index.css";

import { Providers } from "./providers";

/** Runs from the HTML document so a failed `app/layout.js` chunk can still recover. */
const CHUNK_LOAD_RECOVERY = `(function () {
  var key = "cc-chunk-reload-at";
  function isChunkError(err) {
    var name = err && err.name ? String(err.name) : "";
    var msg = err && err.message ? String(err.message) : String(err || "");
    return name === "ChunkLoadError" || /Loading chunk |Loading CSS chunk /.test(msg);
  }
  function reloadOnce() {
    try {
      var prev = Number(sessionStorage.getItem(key) || "0");
      if (Date.now() - prev < 15000) return;
      sessionStorage.setItem(key, String(Date.now()));
    } catch (e) {}
    location.reload();
  }
  window.addEventListener("unhandledrejection", function (event) {
    if (isChunkError(event.reason)) {
      event.preventDefault();
      reloadOnce();
    }
  });
  window.addEventListener("error", function (event) {
    if (isChunkError(event.error)) reloadOnce();
  });
})();`;

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
  metadataBase: new URL("https://cocomputer.ai"),
  manifest: "/manifest.json",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/icon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
    shortcut: "/favicon.ico",
  },
  openGraph: {
    title: "CoComputer — AI Desktop Agent",
    description: "Voice-controlled AI agent with full Linux desktop access",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "CoComputer" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "CoComputer — AI Desktop Agent",
    description: "Voice-controlled AI agent with full Linux desktop access",
    images: ["/og-image.png"],
  },
  appleWebApp: { capable: true, title: "CoComputer", statusBarStyle: "default" },
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
        <Script id="chunk-load-recovery" strategy="beforeInteractive">
          {CHUNK_LOAD_RECOVERY}
        </Script>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
