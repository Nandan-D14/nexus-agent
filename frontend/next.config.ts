/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
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
  webpack: (config) => {
    config.resolve.alias["@react-aria/ssr"] = path.resolve(
      __dirname,
      "shims/react-aria-ssr.js"
    );
    return config;
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
