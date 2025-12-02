import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Docker standalone output
  output: "standalone",

  async rewrites() {
    // Use internal Container Apps URL in production, localhost for development
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8400";

    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
