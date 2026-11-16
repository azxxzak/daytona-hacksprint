import type { NextConfig } from "next";

const API = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  experimental: {
    // ad uploads go through the /api rewrite; allow up to the backend's 500 MB limit and slow interviews
    proxyClientMaxBodySize: "500mb",
    proxyTimeout: 600_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
