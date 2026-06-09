/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: [
    "@heroui/react",
    "react-aria-components",
    "react-aria",
    "@react-aria/utils"
  ],
  webpack: (config) => {
    config.resolve.alias["@react-aria/ssr"] = path.resolve(
      __dirname,
      "shims/react-aria-ssr.js"
    );
    return config;
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "www.gstatic.com",
      },
    ],
  },
};

export default nextConfig;
