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

## v2 additions — talks (replace the old per-viewer interview UI)

A **talk** is a saved conversation between the user and one or more viewers of a finished test.

```ts
type TalkMode = "qa" | "conversation";     // qa = 一問一答: every viewer answers the question once, independently
                                           // conversation = 会話: viewers answer one after another and react to each other
type TalkMessage =
  | { role: "user"; content: string; at: string }
  | { role: "persona"; persona_id: string; content: string; at: string };
type Talk = {
  id: string; test_id: string; mode: TalkMode;
  persona_ids: string[];                   // 1 = one-to-one talk
  title: string;                           // first question, trimmed
  created_at: string; updated_at: string;
  messages: TalkMessage[];
  suggestion: string | null;               // AI-suggested next question, in the language of the last question
};
```

| Method & path | Body | Response |
|---|---|---|
| `GET /api/tests/{id}/talks` | | `{ talks: Omit<Talk,"messages">[] }` newest first |
| `POST /api/tests/{id}/talks` | `{ persona_ids: string[] (1..20), mode: TalkMode }` | `201 Talk` (empty messages) |
| `GET /api/tests/{id}/talks/{talk_id}` | | `Talk` |
| `DELETE /api/tests/{id}/talks/{talk_id}` | | `204` |
| `PATCH /api/tests/{id}/talks/{talk_id}` | `{ mode }` | `Talk` (switch mode mid-talk) |
| `POST /api/tests/{id}/talks/{talk_id}/ask` | `{ message: string }` — or `{ use_suggestion: true }` for auto mode | **`text/event-stream`** (see below) |

The `ask` stream (Server-Sent Events, read it with `fetch` + `ReadableStream`, it is a POST):
```
event: user        data: {"content": "...", "at": "..."}                 // the question as stored (useful for use_suggestion)
event: thinking    data: {"persona_id": "P003"}                          // this viewer is now writing
event: message     data: {"persona_id": "P003", "content": "...", "at": "..."}
...                                                                       // qa: viewers in parallel, events arrive as each finishes
                                                                          // conversation: one viewer at a time, in order
event: suggestion  data: {"content": "..."}                               // next question to offer (may be null)
event: done        data: {}
event: error       data: {"detail": "..."}                               // a single viewer failing does not stop the others
```
Auto mode ("オート進行（5問）") is the client calling `ask` with `{use_suggestion: true}` up to 5 times in a row, stoppable between rounds.

Default question chips (client side): JA `この案の第一印象は？` `具体的には？` `話を続けてください。` `どこに惹かれますか？` `懸念は？` `買うきっかけは？`; EN `First impression of this ad?` `What exactly?` `Tell me more.` `What draws you in?` `Any concerns?` `What would make you buy?`

### Other v2 changes
- `POST /api/tests` accepts an optional `name` form field (defaults to the file name).
- `PATCH /api/tests/{id}` `{ name }` → `TestSummary` (rename).
- `POST /api/audience/preview` (multipart: `age_min, age_max, genders, count, people_csv`) returns the exact panel a CSV produces; `GET` stays for the no-CSV case.
- `Gaze.thought_en` is always present (empty string on older tests).
- The old `/interviews/{persona_id}` endpoints keep working but the UI should use talks.

Errors are `{"detail": "human readable message"}` with a fitting status code (400 validation, 401, 403, 404, 413 too large, 429, 500).
