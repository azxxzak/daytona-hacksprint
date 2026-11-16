export type Profile = {
  full_name: string;
  meta: string;
  headline: string;
  household: string;
  income: string;
  region: string;
  daily_life: string;
  media: string[];
  ad_attitude: string;
  purchase_drivers: string[];
  purchase_barriers: string[];
  values_top: string[];
  values_low: string[];
  big_five: { openness: number; conscientiousness: number; extraversion: number; agreeableness: number; neuroticism: number };
  speech_style: string;
  insights: { title: string; body: string }[];
};

export type Basis = "profile" | "inferred" | "invented";

export type LibraryGroup = { id: string; name: string; name_en: string; description: string; personas: Persona[] };

export type Theme = {
  id: string;
  title: string;
  description: string;
  share: number;
  by_segment: { segment: string; share: number }[];
  examples: { persona_id: string; t: number; text: string }[];
};

export type DecisionReport = {
  decision_question: string;
  thesis: string;
  headline_cards: { label: string; value: string; note: string }[];
  insights: { title: string; evidence: string; so_what: string; now_what: string; score: number }[];
  segments: { segment: string; verdict: "win" | "grow" | "deprioritize"; why: string }[];
  tensions: { tension: string; strategy: string }[];
  actions: { horizon: "48h" | "2w" | "6w"; action: string; kpi: string }[];
  numbers: { key: string; label: string; value: string }[];
  generated_at: string;
  lang: "ja" | "en";
};

export type Persona = {
  id: string;
  name: string;
  age: number;
  gender: "Female" | "Male";
  region: string;
  occupation: string;
  income: string;
  interests: string;
  media: string;
  values: string;
  color: string;
  avatar_url: string;
  profile?: Profile;
  has_deep_profile?: boolean;
};

export type Gaze = {
  id: string;
  t: number;
  x: number;
  y: number;
  looking_at: string;
  interest: 1 | 2 | 3 | 4 | 5;
  thought: string;
  thought_en: string;
  basis?: Basis;
  because?: string;
};

export type Status = "queued" | "running" | "done" | "failed";
export type Step = "queued" | "sandbox" | "analysis" | "viewers" | "saving" | "done";

export type TestSummary = {
  id: string;
  name: string;
  created_at: string;
  status: Status;
  viewers: number;
  media_kind: "video" | "image";
  thumb_url: string | null;
  engaged: number | null;
  avg_interest: number | null;
};

export type Summary = {
  engaged: number;
  total: number;
  avg_interest: number;
  low_t: number | null;
  top_focus: string | null;
  curve: { t: number; avg: number }[];
};

export type Test = TestSummary & {
  context: string;
  progress: { step: Step; message: string; percent: number };
  error: string | null;
  where: "daytona" | "local" | null;
  media_url: string;
  duration: number;
  width: number;
  height: number;
  grid: [number, number];
  frames: { t: number; heat: number[] }[];
  transcript: { start: number; end: number; text: string }[];
  personas: Persona[];
  gaze: Gaze[];
  summary: Summary | null;
  themes?: Theme[] | null;
};

export type Message = { role: "user" | "assistant"; content: string };

export type TalkMode = "qa" | "conversation";
export type TalkMessage =
  | { role: "user"; content: string; at: string }
  | { role: "persona"; persona_id: string; content: string; at: string; basis?: Basis; because?: string };
export type TalkSummary = {
  id: string;
  test_id: string;
  mode: TalkMode;
  persona_ids: string[];
  title: string;
  created_at: string;
  updated_at: string;
  suggestion: string | null;
};
export type Talk = TalkSummary & { messages: TalkMessage[] };
