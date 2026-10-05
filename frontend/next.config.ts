/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.resolve(__dirname),
  transpilePackages: [
    // Thesys C1 Generative UI SDK: react-ui is ESM and imports the CJS
    // react-core, so both must be transpiled for webpack to resolve them.
    "@thesysai/genui-sdk",
    "@crayonai/react-ui",
    "@crayonai/react-core",
    "@crayonai/stream",
  ],
  webpack: (config, { dev }) => {
    config.resolve.alias["@react-aria/ssr"] = path.resolve(
      __dirname,
      "shims/react-aria-ssr.js",
    );
    if (dev) {
      // Cold compiles of the root layout can exceed webpack's 120s default on
      // this repo (first /app/* compile has been ~90s), which surfaces as
      // ChunkLoadError: Loading chunk app/layout failed (timeout).
      config.output = {
        ...config.output,
        chunkLoadTimeout: 300_000,
      };
    }
    return config;
  },
  async headers() {
    // A script-src CSP needs per-request nonces for Next's inline scripts and
    // the chunk-recovery script in app/layout.tsx; until that exists, lock
    // down the directives that do not affect scripts. frame-ancestors is
    // 'self' (not 'none') because artifact previews frame /api/... content.
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'",
          },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)",
          },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
    ];
  },
  async redirects() {
    return [
      { source: "/session/new", destination: "/app", permanent: true },
      { source: "/session/:id", destination: "/app/s/:id", permanent: true },
      { source: "/app/session/new", destination: "/app", permanent: true },
      { source: "/app/session/:id", destination: "/app/s/:id", permanent: true },
      { source: "/dashboard", destination: "/app/dashboard", permanent: true },
      { source: "/history", destination: "/app/history", permanent: true },
      { source: "/history/:session_id", destination: "/app/history/:session_id", permanent: true },
      { source: "/schedule", destination: "/app/schedule", permanent: true },
      { source: "/library", destination: "/app/library", permanent: true },
      { source: "/templates", destination: "/app/templates", permanent: true },
      { source: "/skills", destination: "/app/skills", permanent: true },
      { source: "/skills/:skill_id", destination: "/app/skills/:skill_id", permanent: true },
      { source: "/connectors", destination: "/app/connectors", permanent: true },
      { source: "/settings", destination: "/app/settings", permanent: true },
      { source: "/settings/:path*", destination: "/app/settings/:path*", permanent: true },
    ];
  },
  images: {
    qualities: [75, 100],
    localPatterns: [
      {
        pathname: "/**",
      },
    ],
    remotePatterns: [
      {
        protocol: "https",
        hostname: "www.gstatic.com",
      },
      {
        protocol: "https",
        hostname: "exa.imgix.net",
      },
    ],
  },
};

export default nextConfig;
