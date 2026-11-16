# AdLens frontend

Next.js (App Router) + TypeScript + Tailwind. `/api/*` is proxied to the FastAPI backend (`API_ORIGIN`, default `http://localhost:8000`) via `next.config.ts` rewrites, so the httpOnly session cookie stays same-origin.

    npm install
    npm run dev      # http://localhost:3000
    npm run build && npm start

API contract: `../docs/API.md`. All UI strings live in `src/lib/i18n.ts` (EN + JA).
