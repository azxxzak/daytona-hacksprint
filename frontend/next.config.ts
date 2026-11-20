import type { NextConfig } from "next";

// Production (Vercel): set API_ORIGIN to the backend's origin. Files never pass through this rewrite: they go
// browser -> signed storage URL directly (see POST /api/uploads), so the 4.5 MB Vercel body limit does not apply.
const API = (process.env.API_ORIGIN ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // deploy sandboxes have little memory: types are checked locally/CI (`npm run build`), the deploy build sets SKIP_TYPECHECK=1
  typescript: { ignoreBuildErrors: process.env.SKIP_TYPECHECK === "1" },
  experimental: {
    // the deploy sandbox has ~1 GB RAM: build with one worker there (NEXT_BUILD_CPUS=1); locally use all cores
    ...(process.env.NEXT_BUILD_CPUS ? { cpus: Number(process.env.NEXT_BUILD_CPUS), workerThreads: false } : {}),
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
