import type { NextConfig } from "next";

const API = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // deploy sandboxes have little memory: types are checked locally/CI (`npm run build`), the deploy build sets SKIP_TYPECHECK=1
  typescript: { ignoreBuildErrors: process.env.SKIP_TYPECHECK === "1" },
  experimental: {
    // the deploy sandbox has ~1 GB RAM: build with one worker there (NEXT_BUILD_CPUS=1); locally use all cores
    ...(process.env.NEXT_BUILD_CPUS ? { cpus: Number(process.env.NEXT_BUILD_CPUS), workerThreads: false } : {}),
    // ad uploads go through the /api rewrite; allow up to the backend's 500 MB limit and slow interviews
    proxyClientMaxBodySize: "500mb",
    proxyTimeout: 600_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
