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

## v3 additions — richer personas, library, evidence, themes, decision report, cost

### Persona profile (two tiers)
`Persona` gains optional fields (present on library personas and on tests created after v3):
```ts
type Profile = {                       // tier 1, generated automatically for every persona (~1.5k chars)
  full_name: string;                   // "佐藤 蓮" (Japanese name, reading in parentheses ok)
  meta: string;                        // "10代/男性/高校生/未婚" (age band/gender/job/marital, in Japanese)
  headline: string;                    // one-line identity, e.g. "承認を求めるデジタルネイティブ"
  household: string; income: string; region: string;
  daily_life: string;                  // 2-3 sentences
  media: string[];                     // channels with how they use them
  ad_attitude: string;                 // how they treat ads, 1-2 sentences
  purchase_drivers: string[]; purchase_barriers: string[];
  values_top: string[]; values_low: string[];          // Schwartz-style, 3 each
  big_five: { openness: number; conscientiousness: number; extraversion: number; agreeableness: number; neuroticism: number }; // 0-100
  speech_style: string;                // how they talk, with 2-3 typical phrases
  insights: { title: string; body: string }[];          // 2 short insights
};
type Persona = { /* v1 fields */ profile?: Profile; has_deep_profile?: boolean };
```
Tier 2 ("deep profile") is long markdown (insights, contradictions, communication analysis — like the AI For Growth Talk persona report). It is generated only on request:
| Method & path | Response |
|---|---|
| `GET /api/personas/{pid}/deep` | `{ markdown: string \| null, status: "none" \| "generating" \| "ready" }` |
| `POST /api/personas/{pid}/deep` | `202 { status: "generating" }` (poll GET every 3 s; takes ~40-90 s) |
`pid` here is a **global persona id** (`"lib_..."` for library personas, `"{test_id}:{P001}"` for test personas).

### Persona library
```ts
type LibraryGroup = { id: string; name: string; name_en: string; description: string; personas: Persona[] };
```
| Method & path | Response |
|---|---|
| `GET /api/library` | `{ groups: LibraryGroup[] }` — e.g. 性年代 (14), ライフスタイル (12), メディア（ヘビー層） (12) |
| `GET /api/library/personas/{pid}` | `Persona` (with profile) |
`POST /api/tests` accepts `library_persona_ids` (comma-separated) instead of the age/gender/count sampling. When present, those personas are the panel (5–60).

### Evidence labels
`Gaze` and talk persona messages gain:
```ts
basis: "profile" | "inferred" | "invented";   // profile = follows a stated fact of the persona; inferred = reasonable guess from it; invented = no support
because: string;                               // ≤ 80 chars, which fact or reason
```
UI shows a small label (e.g. "根拠: プロフィール" / "推測" / "創作") and the `because` text on hover. Older data has no `basis` — show nothing.

### Themes (open-answer summary)
`Test.themes`:
```ts
type Theme = { id: string; title: string; description: string; share: number;     // share of all thoughts, 0..1
               by_segment: { segment: string; share: number }[];                 // "<25","25-34","35-44","45+","Female","Male"
               examples: { persona_id: string; t: number; text: string }[] };     // up to 3
```
`Test.themes: Theme[] | null` (null while not computed; computed at the end of the run; `POST /api/tests/{id}/themes` recomputes, 202).

### Decision report + exports
| Method & path | Response |
|---|---|
| `POST /api/tests/{id}/report` | `202 { status: "generating" }` — body `{ decision_question?: string, lang: "ja" \| "en" }` |
| `GET /api/tests/{id}/report` | `{ status: "none" \| "generating" \| "ready" \| "failed", report: DecisionReport \| null, error?: string }` |
| `GET /api/tests/{id}/report.pptx` | editable PowerPoint (charts are native PPT charts) |
| `GET /api/tests/{id}/report.pdf` | PDF of the same deck (may be 501 if no converter is available — then hide the button) |
```ts
type DecisionReport = {
  decision_question: string;
  thesis: string;                                         // one line
  headline_cards: { label: string; value: string; note: string }[];   // exactly 4: primary segment, key tension, primary driver, biggest friction
  insights: { title: string; evidence: string; so_what: string; now_what: string; score: number }[];  // 3-5, picked from 10 candidates
  segments: { segment: string; verdict: "win" | "grow" | "deprioritize"; why: string }[];
  tensions: { tension: string; strategy: string }[];      // up to 3
  actions: { horizon: "48h" | "2w" | "6w"; action: string; kpi: string }[];   // 3 per horizon
  numbers: { key: string; label: string; value: string }[];   // every number shown in the report comes from here (computed by code)
  generated_at: string; lang: "ja" | "en";
};
```

### Cost
| Method & path | Response |
|---|---|
| `POST /api/tests/{id}/talks/{talk_id}/estimate` | body `{ rounds: number }` → `{ usd: number, basis: "measured" \| "price_list", per_round_usd: number }` — shown next to Send / Auto |
| `GET /api/usage` | `{ month_usd: number, tests: number, talk_messages: number }` for the signed-in user |
