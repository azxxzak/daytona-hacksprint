# AdLens frontend

Next.js (App Router) + TypeScript + Tailwind. `/api/*` is proxied to the backend via `next.config.ts` rewrites (`API_ORIGIN`, default `http://localhost:8000` for local dev), so the httpOnly session cookie stays same-origin. Large files are uploaded straight to signed storage URLs (`POST /api/uploads`), never through the proxy.

    npm install
    npm run dev      # http://localhost:3000
    npm run build && npm start

API contract: `../docs/API.md`. All UI strings live in `src/lib/i18n.ts` (JA default, EN switch).

## Deploy on Vercel

1. Import the repo as a new Vercel project and set **Root Directory** to `frontend/` (framework preset: Next.js, defaults for build and output).
2. Environment variables (Production and Preview):
   - `API_ORIGIN` — origin of the backend, for example `https://adlens-api.vercel.app` (no trailing slash, no `/api`). Rewrites send `/api/*` there.
   - Optional, only on memory-constrained builders: `SKIP_TYPECHECK=1` (type checking is done by `npm run build` locally/CI) and `NEXT_BUILD_CPUS=1`.
3. Deploy. No other config is needed: there are no server secrets in this app.

Notes: the session cookie is set by the backend through the rewrite, so the app and `/api` must be served from the same Vercel domain. Server-sent events (`/talks/{id}/ask`) are streamed through the rewrite; if a proxy layer buffers them, replies still arrive when each round finishes.
