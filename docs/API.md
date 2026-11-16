# AdLens API contract (v1)

Backend: FastAPI at `http://localhost:8000`. The Next.js app proxies `/api/*` to it (same origin, so the session cookie just works).
All JSON. All endpoints except `POST /api/auth/login` and `GET /api/health` require a signed-in session, otherwise `401 {"detail": "..."}`.

## Types

```ts
type Persona = {
  id: string;            // "P001"
  name: string; age: number; gender: "Female" | "Male";
  region: string; occupation: string; income: string;
  interests: string;     // comma separated
  media: string;         // comma separated
  values: string;        // comma separated traits
  color: string;         // "#e6194b" — the persona's identity colour (ring around face, chart lines)
  avatar_url: string;    // "/api/avatars/<key>.jpg" — generated on first request (can take ~10 s), then cached
};

type Gaze = {            // one viewer at one keyframe
  id: string; t: number;             // persona id, seconds
  x: number; y: number;              // 0..1, where they look (top-left origin)
  looking_at: string;                // short English label
  interest: 1 | 2 | 3 | 4 | 5;
  thought: string;                   // Japanese inner voice
  thought_en: string;                // English version ("" on older tests)
};

type Status = "queued" | "running" | "done" | "failed";
type Step = "queued" | "sandbox" | "analysis" | "viewers" | "saving" | "done";

type TestSummary = {
  id: string; name: string; created_at: string;   // ISO 8601
  status: Status; viewers: number;
  media_kind: "video" | "image";
  thumb_url: string | null;                       // "/api/tests/<id>/thumb.jpg"
  engaged: number | null; avg_interest: number | null;
};

type Test = TestSummary & {
  context: string;
  progress: { step: Step; message: string; percent: number };   // percent 0..100
  error: string | null;
  where: "daytona" | "local" | null;          // where the media was processed
  media_url: string;                           // "/api/tests/<id>/media" (supports Range)
  duration: number; width: number; height: number;
  grid: [number, number];                      // [48, 27]
  frames: { t: number; heat: number[] }[];     // heat: GW*GH values 0..255, row-major, image saliency
  transcript: { start: number; end: number; text: string }[];
  personas: Persona[];
  gaze: Gaze[];
  summary: {
    engaged: number; total: number;            // viewers with mean interest >= 3.5
    avg_interest: number;
    low_t: number | null;                      // second where panel interest was lowest
    top_focus: string | null;
    curve: { t: number; avg: number }[];       // panel mean interest per keyframe
  } | null;                                    // null until status == "done"
};

type Message = { role: "user" | "assistant"; content: string };
```

## Endpoints

| Method & path | Body / query | Response |
|---|---|---|
| `GET /api/health` | | `{ "ok": true }` |
| `POST /api/auth/login` | `{ email, password }` | `200 { email, name }` + sets httpOnly cookie; `401` on bad credentials; `429` after too many attempts |
| `POST /api/auth/logout` | | `204` |
| `GET /api/auth/me` | | `{ email, name }` or `401` |
| `GET /api/audience/preview` | `?age_min=20&age_max=45&genders=F,M&count=20` | `{ personas: Persona[] }` (same panel the test will use) |
| `POST /api/tests` | `multipart/form-data`: `media` (file: mp4/mov/webm/png/jpg, ≤500 MB), `age_min`, `age_max`, `genders` ("F,M"), `count` (5..60), `context` (optional), `people_csv` (optional file) | `201 { id }` — the job runs in the background |
| `GET /api/tests` | | `{ tests: TestSummary[] }` newest first, only the caller's tests |
| `GET /api/tests/{id}` | | `Test` (poll every 2 s while `status` is queued/running) |
| `DELETE /api/tests/{id}` | | `204` |
| `GET /api/tests/{id}/media` | | video/image bytes |
| `GET /api/tests/{id}/thumb.jpg` | | jpeg |
| `GET /api/tests/{id}/interviews/{persona_id}` | | `{ messages: Message[] }` |
| `POST /api/tests/{id}/interviews/{persona_id}` | `{ message }` | `{ reply, messages: Message[] }` (5–15 s; the persona answers in the language of the question) |
| `GET /api/avatars/{key}.jpg` | | jpeg portrait |

Errors are `{"detail": "human readable message"}` with a fitting status code (400 validation, 401, 403, 404, 413 too large, 429, 500).
