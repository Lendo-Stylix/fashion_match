import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    // Allow backend-served / remote product images (localhost dev + https).
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "https", hostname: "**" },
    ],
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  // Allow preview domain for cross-origin dev requests
  allowedDevOrigins: ["*.space-z.ai"],
};

export default nextConfig;
