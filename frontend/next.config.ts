import type { NextConfig } from "next";

// Production (Vercel): set API_ORIGIN to the backend's origin. Files never pass through this rewrite: they go
// browser -> signed storage URL directly (see POST /api/uploads), so the 4.5 MB Vercel body limit does not apply.
const API = (process.env.API_ORIGIN ?? "http://localhost:8000").replace(/\/$/, "");

// Media, portraits and uploads go straight between the browser and Supabase Storage (signed URLs).
const STORAGE = "https://*.supabase.co";
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",           // Next.js inline bootstrap; no eval in production
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${STORAGE}`,
  `media-src 'self' blob: ${STORAGE}`,
  `connect-src 'self' ${STORAGE}`,
  "font-src 'self' data:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    const common = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "same-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ];
    // the dev server needs eval for fast refresh, so the CSP is production-only
    const csp = process.env.NODE_ENV === "production" ? [{ key: "Content-Security-Policy", value: CSP }] : [];
    return [{ source: "/:path*", headers: [...common, ...csp] }];
  },
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
