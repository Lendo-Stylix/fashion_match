import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Allow backend-served / remote product images (localhost dev + https).
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "https", hostname: "**" },
    ],
  },
};

export default nextConfig;
