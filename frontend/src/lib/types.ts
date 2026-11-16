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
};

export type Message = { role: "user" | "assistant"; content: string };
